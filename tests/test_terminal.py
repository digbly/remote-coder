import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.modules.terminal.service import TerminalSession
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login


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
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_terminal_url(1, uuid4().hex)):
            pass

    assert exc.value.code == 4401


def test_terminal_rejects_unknown_project(client: TestClient, projects_root: Path) -> None:
    _login(client)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_terminal_url(999, uuid4().hex)):
            pass

    assert exc.value.code == 4404


def test_terminal_rejects_invalid_id(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_terminal_url(project_id, "bad id!")):
            pass

    assert exc.value.code == 4404


def test_terminal_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_terminal_url(project_id, uuid4().hex)):
            pass

    assert exc.value.code == 4404


def test_terminal_rejects_cross_site_origin(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            _terminal_url(project_id, uuid4().hex),
            headers={"origin": "http://evil.example"},
        ):
            pass

    assert exc.value.code == 4403


def test_terminal_runs_shell_in_project_directory(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with client.websocket_connect(_terminal_url(project_id, uuid4().hex)) as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "pwd\n"}))
        output = _read_until(websocket, "terminal-repo")

    assert "terminal-repo" in output


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


def test_subscriber_queue_drops_oldest_when_full() -> None:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=2)
    TerminalSession._deliver(queue, b"a")
    TerminalSession._deliver(queue, b"b")
    TerminalSession._deliver(queue, b"c")

    assert queue.get_nowait() == b"b"
    assert queue.get_nowait() == b"c"


def test_replay_starts_at_escape_boundary_after_trimming() -> None:
    session = TerminalSession(
        Path("/tmp"), "/bin/bash", 1024, replay_bytes=9, queue_chunks=4
    )
    session._append(b"\x1b[31")
    session._append(b"mX\x1b[0m")

    assert session._replay() == b"\x1b[0m"
