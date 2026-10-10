import asyncio
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.modules.terminal.service import TerminalSession
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login, assert_ws_close


def _register_project(client: TestClient, projects_root: Path) -> int:
    folder = projects_root / "terminal-repo"
    folder.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _read_until(websocket, needle: str) -> str:
    buffer = ""
    for _ in range(100):
        buffer += websocket.receive_bytes().decode("utf-8", errors="replace")
        if needle in buffer:
            return buffer
    raise AssertionError(f"did not see {needle!r} in terminal output: {buffer!r}")


def _terminal_url(project_id: int, terminal_id: str) -> str:
    return f"/api/v1/projects/{project_id}/terminal/{terminal_id}"


def test_terminal_requires_authentication(client: TestClient, projects_root: Path) -> None:
    assert_ws_close(client, _terminal_url(1, uuid4().hex), 4401)


def test_terminal_rejects_unknown_project(client: TestClient, projects_root: Path) -> None:
    _login(client)

    assert_ws_close(client, _terminal_url(999, uuid4().hex), 4404)


def test_terminal_rejects_invalid_id(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    assert_ws_close(client, _terminal_url(project_id, "bad id!"), 4404)


def test_terminal_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    assert_ws_close(client, _terminal_url(project_id, uuid4().hex), 4404)


def test_terminal_rejects_cross_site_origin(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    assert_ws_close(
        client,
        _terminal_url(project_id, uuid4().hex),
        4403,
        headers={"origin": "http://evil.example"},
    )


def test_terminal_runs_shell_in_project_directory(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with client.websocket_connect(_terminal_url(project_id, uuid4().hex)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "pwd\n"}))
        output = _read_until(websocket, "terminal-repo")

    assert "terminal-repo" in output


def test_terminal_runs_agent_command_on_new_session(
    client: TestClient, projects_root: Path
) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    client.put(
        "/api/v1/agents/settings/claude",
        json={"command": "pwd", "args": ""},
        headers=_csrf(client),
    )

    url = f"{_terminal_url(project_id, uuid4().hex)}?agent_id=claude"
    with client.websocket_connect(url) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        output = _read_until(websocket, "terminal-repo")

    assert "terminal-repo" in output


def test_terminal_runs_agent_command_with_args(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    client.put(
        "/api/v1/agents/settings/claude",
        json={"command": "echo", "args": "AGENT_ARGS=1"},
        headers=_csrf(client),
    )

    url = f"{_terminal_url(project_id, uuid4().hex)}?agent_id=claude"
    with client.websocket_connect(url) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        output = _read_until(websocket, "AGENT_ARGS=1")

    assert "AGENT_ARGS=1" in output


def test_terminal_ignores_unknown_agent(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    url = f"{_terminal_url(project_id, uuid4().hex)}?agent_id=does-not-exist"
    with client.websocket_connect(url) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "echo MANUAL=1\n"}))
        output = _read_until(websocket, "MANUAL=1")

    assert "MANUAL=1" in output


def test_terminal_session_applies_env_overrides(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_popen(*_args, **kwargs):
        captured.update(kwargs["env"])
        raise OSError

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    session = TerminalSession(
        tmp_path,
        "/bin/sh",
        1024,
        replay_bytes=4096,
        queue_chunks=8,
        env={"RC_AGENT_ENV": "present"},
    )

    with pytest.raises(OSError):
        session.start()

    assert captured["RC_AGENT_ENV"] == "present"


def test_terminal_interrupts_foreground_process(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with client.websocket_connect(_terminal_url(project_id, uuid4().hex)) as websocket:
        websocket.send_text(json.dumps({"type": "input", "data": "sleep 30\n"}))
        time.sleep(0.4)
        websocket.send_text(json.dumps({"type": "input", "data": "\x03"}))
        time.sleep(0.4)
        websocket.send_text(json.dumps({"type": "input", "data": "echo AFTER=$?\n"}))
        output = _read_until(websocket, "AFTER=130")

    assert "AFTER=130" in output


def test_terminal_survives_disconnect_and_replays(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    terminal_id = uuid4().hex

    with client.websocket_connect(_terminal_url(project_id, terminal_id)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "echo PERSIST=ok\n"}))
        _read_until(websocket, "PERSIST=ok")

    with client.websocket_connect(_terminal_url(project_id, terminal_id)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        output = _read_until(websocket, "PERSIST=ok")

    assert "PERSIST=ok" in output


def test_terminal_kill_removes_session(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    terminal_id = uuid4().hex

    with client.websocket_connect(_terminal_url(project_id, terminal_id)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "echo GONE=1\n"}))
        _read_until(websocket, "GONE=1")

    response = client.delete(
        f"/api/v1/projects/{project_id}/terminal/{terminal_id}", headers=_csrf(client)
    )
    assert response.status_code == 204

    with client.websocket_connect(_terminal_url(project_id, terminal_id)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "echo FRESH=1\n"}))
        output = _read_until(websocket, "FRESH=1")

    assert "GONE=1" not in output


def test_terminal_kill_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    terminal_id = uuid4().hex

    with client.websocket_connect(_terminal_url(project_id, terminal_id)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "echo KEEP=1\n"}))
        _read_until(websocket, "KEEP=1")

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)
    response = client.delete(
        f"/api/v1/projects/{project_id}/terminal/{terminal_id}", headers=_csrf(client)
    )

    assert response.status_code == 404


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "tracked.txt").write_text("hello\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "init")


def test_terminal_runs_shell_in_worktree_directory(client: TestClient, projects_root: Path) -> None:
    _login(client)
    repo = projects_root / "wt-main"
    _init_repo(repo)
    _git(repo, "worktree", "add", "-b", "agent", str(projects_root / "wt-agent"))
    response = client.post(LOCAL_URL, json={"path": str(repo)}, headers=_csrf(client))
    project_id = response.json()["id"]

    url = f"{_terminal_url(project_id, uuid4().hex)}?worktree=wt-agent"
    with client.websocket_connect(url) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "pwd\n"}))
        output = _read_until(websocket, "wt-agent")

    assert "wt-agent" in output


def test_terminal_rejects_unknown_worktree(client: TestClient, projects_root: Path) -> None:
    _login(client)
    repo = projects_root / "wt-main"
    _init_repo(repo)
    response = client.post(LOCAL_URL, json={"path": str(repo)}, headers=_csrf(client))
    project_id = response.json()["id"]

    url = f"{_terminal_url(project_id, uuid4().hex)}?worktree=does-not-exist"
    assert_ws_close(client, url, 4404)


def test_running_terminals_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/terminals/running").status_code == 401


def test_running_terminals_reports_worktree(client: TestClient, projects_root: Path) -> None:
    _login(client)
    repo = projects_root / "wt-main"
    _init_repo(repo)
    _git(repo, "worktree", "add", "-b", "agent", str(projects_root / "wt-agent"))
    response = client.post(LOCAL_URL, json={"path": str(repo)}, headers=_csrf(client))
    project_id = response.json()["id"]

    url = f"{_terminal_url(project_id, uuid4().hex)}?worktree=wt-agent"
    with client.websocket_connect(url) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "pwd\n"}))
        _read_until(websocket, "wt-agent")

    # Detaching keeps the shell alive, so the worktree is still reported as running.
    running = client.get("/api/v1/terminals/running")
    assert running.status_code == 200, running.text
    assert "wt-agent" in running.json()["projects"].get(str(project_id), [])


def test_subscriber_queue_drops_oldest_when_full() -> None:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=2)
    TerminalSession._deliver(queue, b"a")
    TerminalSession._deliver(queue, b"b")
    TerminalSession._deliver(queue, b"c")

    assert queue.get_nowait() == b"b"
    assert queue.get_nowait() == b"c"


def test_terminal_skips_noop_resize(monkeypatch) -> None:
    applied: list[tuple[int, int]] = []

    def fake_set_winsize(_fd: int, cols: int, rows: int) -> None:
        applied.append((cols, rows))

    monkeypatch.setattr("app.modules.terminal.service._set_winsize", fake_set_winsize)
    session = TerminalSession(Path("/tmp"), "/bin/bash", 1024, replay_bytes=4096, queue_chunks=4)
    session._master_fd = 7

    session.resize(120, 30)
    session.resize(120, 30)
    session.resize(100, 40)
    session.resize(100, 40)

    assert applied == [(120, 30), (100, 40)]


def test_replay_starts_at_escape_boundary_after_trimming() -> None:
    session = TerminalSession(
        Path("/tmp"), "/bin/bash", 1024, replay_bytes=9, queue_chunks=4
    )
    session._append(b"\x1b[31")
    session._append(b"mX\x1b[0m")

    assert session._replay() == b"\x1b[0m"
