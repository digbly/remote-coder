import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.modules.browser import service
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login, assert_ws_close


def _register_repo_with_worktree(client: TestClient, projects_root: Path) -> tuple[int, Path]:
    repo = projects_root / "wt-main"
    _init_repo(repo)
    _git(repo, "worktree", "add", "-b", "agent", str(projects_root / "wt-agent"))
    response = client.post(LOCAL_URL, json={"path": str(repo)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"], repo


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


def _browser_url(project_id: int, subpath: str = "stream") -> str:
    return f"/api/v1/projects/{project_id}/browser/{subpath}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Upstream:
    """A minimal WebSocket server standing in for the agent-browser stream."""

    def __init__(self) -> None:
        self.port = _free_port()
        routes = [WebSocketRoute("/", self._ws)]
        config = uvicorn.Config(
            Starlette(routes=routes), host="127.0.0.1", port=self.port, log_level="error"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    async def _ws(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async for message in websocket.iter_text():
            await websocket.send_text(f"echo:{message}")

    def __enter__(self) -> "_Upstream":
        self._thread.start()
        for _ in range(200):
            if self._server.started:
                break
            time.sleep(0.05)
        else:  # pragma: no cover - startup failure
            raise RuntimeError("upstream server did not start")
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], env: dict[str, str]) -> str:
        self.calls.append(command)
        return ""


def _session_for(port: int, runner: service.CommandRunner) -> service.BrowserSession:
    settings = Settings()
    return service.BrowserSession(
        host="127.0.0.1", port=port, name="test", runner=runner, settings=settings
    )


class _StubManager:
    def __init__(self, session: service.BrowserSession) -> None:
        self.session = session

    def ensure(self, key, *, name, settings, runner=None, port=None):  # noqa: ANN001
        self.session.touch()
        return self.session

    def kill(self, key) -> None:  # noqa: ANN001
        return None

    def kill_all(self) -> None:
        return None


def test_browser_requires_authentication(client: TestClient, projects_root: Path) -> None:
    response = client.post(_browser_url(1, "navigate"), json={"url": "https://x.com"})
    assert response.status_code == 401


def test_browser_rejects_unknown_project(client: TestClient, projects_root: Path) -> None:
    _login(client)
    response = client.post(
        _browser_url(999, "navigate"), json={"url": "https://x.com"}
    )
    assert response.status_code == 404




def test_browser_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    response = client.post(
        _browser_url(project_id, "navigate"), json={"url": "https://x.com"}
    )
    assert response.status_code == 404


def test_browser_ws_requires_authentication(client: TestClient, projects_root: Path) -> None:
    assert_ws_close(client, _browser_url(1), 4401)


def test_browser_ws_rejects_cross_site_origin(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    assert_ws_close(
        client,
        _browser_url(project_id),
        4403,
        headers={"origin": "http://evil.example"},
    )


def test_browser_navigate_rejects_cross_site_origin(
    client: TestClient, projects_root: Path
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    response = client.post(
        _browser_url(project_id, "navigate"),
        json={"url": "https://example.com/"},
        headers={**_csrf(client), "origin": "http://evil.example"},
    )
    assert response.status_code == 403


def test_browser_rejects_non_http_url(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    response = client.post(
        _browser_url(project_id, "navigate"),
        json={"url": "file:///etc/passwd"},
        headers=_csrf(client),
    )
    assert response.status_code == 400


def test_browser_navigate_runs_command(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    runner = _RecordingRunner()
    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.post(
        _browser_url(project_id, "navigate"),
        json={"url": "https://example.com/"},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert runner.calls == [["agent-browser", "open", "https://example.com/"]]


def test_browser_control_runs_action(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    runner = _RecordingRunner()
    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.post(_browser_url(project_id, "reload"), headers=_csrf(client))

    assert response.status_code == 200
    assert runner.calls == [["agent-browser", "reload"]]


def test_browser_control_rejects_unknown_action(
    client: TestClient, projects_root: Path
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    response = client.post(_browser_url(project_id, "explode"), headers=_csrf(client))
    assert response.status_code == 400


def test_browser_set_viewport_runs_command(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    runner = _RecordingRunner()
    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.post(
        _browser_url(project_id, "viewport"),
        json={"width": 900, "height": 500},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert runner.calls == [["agent-browser", "set", "viewport", "900", "500"]]


def test_browser_set_viewport_rejects_out_of_range(
    client: TestClient, projects_root: Path
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    response = client.post(
        _browser_url(project_id, "viewport"),
        json={"width": 10, "height": 500},
        headers=_csrf(client),
    )
    assert response.status_code == 422


def test_browser_insert_runs_command(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    runner = _RecordingRunner()
    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.post(
        _browser_url(project_id, "insert"),
        json={"text": "pasted text"},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert runner.calls == [["agent-browser", "keyboard", "inserttext", "pasted text"]]


def test_browser_selection_returns_text(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    def runner(command: list[str], env: dict[str, str]) -> str:
        return json.dumps({"success": True, "data": {"result": "SELECTED"}, "error": None})

    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.get(_browser_url(project_id, "selection"))

    assert response.status_code == 200
    assert response.json() == {"text": "SELECTED"}


def test_browser_close_session_kills(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    killed: list[tuple[int, int, str]] = []
    monkeypatch.setattr(service, "manager", _KillRecordingManager(killed))

    response = client.delete(
        f"{_browser_url(project_id, 'session')}?session=tab-1", headers=_csrf(client)
    )

    assert response.status_code == 200
    assert killed == [(1, project_id, "tab-1")]


class _KillRecordingManager:
    def __init__(self, killed: list[tuple[int, int, str]]) -> None:
        self.killed = killed

    def kill(self, key) -> None:  # noqa: ANN001
        self.killed.append(key)

    def kill_all(self) -> None:
        return None


class _FailingManager:
    def ensure(self, key, *, name, settings, runner=None, port=None):  # noqa: ANN001
        raise service.BrowserError("boom")

    def kill(self, key) -> None:  # noqa: ANN001
        return None

    def kill_all(self) -> None:
        return None


def test_browser_stream_reports_start_failure(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    monkeypatch.setattr(service, "manager", _FailingManager())

    with client.websocket_connect(_browser_url(project_id)) as websocket:
        message = json.loads(websocket.receive_text())
        assert message["type"] == "error"
        assert message["code"] == "BROWSER_START_FAILED"
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_text()
        assert exc.value.code == 4500


def test_browser_proxies_stream(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    with _Upstream() as upstream:
        session = _session_for(upstream.port, _RecordingRunner())
        monkeypatch.setattr(service, "manager", _StubManager(session))
        with client.websocket_connect(_browser_url(project_id)) as websocket:
            websocket.send_text("ping")
            assert websocket.receive_text() == "echo:ping"


def test_open_command_flags() -> None:
    headless = service.open_command(Settings(browser_binary="agent-browser"))
    assert headless[:2] == ["agent-browser", "open"]
    assert "--init-script" in headless

    headed = service.open_command(
        Settings(
            browser_binary="agent-browser",
            browser_headless=False,
            browser_allowed_domains="example.com",
        )
    )
    assert "--headed" in headed
    assert "--allowed-domains" in headed
    assert "example.com" in headed


def test_session_name() -> None:
    assert service.safe_session("tab one/../x") == "tab-one-..-x"
    assert service.safe_session("") == "default"
    assert service.session_name(1, 2, "abc") == "u1-p2-abc"


def test_parse_status_extracts_json() -> None:
    assert service.parse_status(None) is None
    assert service.parse_status("no json here") is None
    payload = service.parse_status('noise\n{"enabled": true, "port": 9223}\ntail')
    assert payload == {"enabled": True, "port": 9223}


def test_inspect_command() -> None:
    assert service.inspect_command(Settings(browser_binary="agent-browser")) == [
        "agent-browser",
        "inspect",
    ]


def test_parse_inspect_url() -> None:
    assert service.parse_inspect_url(None) is None
    assert service.parse_inspect_url("nothing here") is None
    assert (
        service.parse_inspect_url("✓ Opened DevTools: http://127.0.0.1:32825")
        == "http://127.0.0.1:32825"
    )


def test_is_loopback_url() -> None:
    assert service.is_loopback_url("http://127.0.0.1:32825")
    assert service.is_loopback_url("http://localhost:1/")
    assert not service.is_loopback_url("http://evil.example/")
    assert not service.is_loopback_url("file:///etc/passwd")


def test_browser_inspect_returns_url(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    def runner(command: list[str], env: dict[str, str]) -> str:
        return "✓ Opened DevTools: http://127.0.0.1:32825"

    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.post(_browser_url(project_id, "inspect"), headers=_csrf(client))

    assert response.status_code == 200
    assert response.json() == {"url": "http://127.0.0.1:32825"}


def test_browser_inspect_rejects_non_loopback_url(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    def runner(command: list[str], env: dict[str, str]) -> str:
        return "✓ Opened DevTools: http://evil.example/"

    monkeypatch.setattr(service, "manager", _StubManager(_session_for(1234, runner)))

    response = client.post(_browser_url(project_id, "inspect"), headers=_csrf(client))

    assert response.status_code == 502


def _manager_runner(command: list[str], env: dict[str, str]) -> str:
    return json.dumps(
        {
            "success": True,
            "data": {"enabled": True, "port": 9223, "connected": True, "screencasting": False},
            "error": None,
        }
    )


def test_manager_reuses_and_kills_session() -> None:
    settings = Settings(browser_bind_host="127.0.0.1")
    manager = service.BrowserManager()
    key = (1, 1, uuid4().hex)
    try:
        first = manager.ensure(key, name="s1", settings=settings, runner=_manager_runner)
        again = manager.ensure(key, name="s1", settings=settings, runner=_manager_runner)
        assert first is again
        assert first.alive()
    finally:
        manager.kill_all()

    assert manager.get(key) is None


def test_manager_evicts_least_recently_used() -> None:
    settings = Settings(browser_bind_host="127.0.0.1", browser_max_sessions=1)
    manager = service.BrowserManager()
    first_key = (1, 1, "one")
    second_key = (1, 1, "two")
    try:
        manager.ensure(first_key, name="one", settings=settings, runner=_manager_runner)
        manager.ensure(second_key, name="two", settings=settings, runner=_manager_runner)
        assert manager.get(first_key) is None
        assert manager.get(second_key) is not None
    finally:
        manager.kill_all()


def test_manager_reaps_idle_session() -> None:
    settings = Settings(browser_bind_host="127.0.0.1")
    manager = service.BrowserManager()
    key = (1, 1, uuid4().hex)
    try:
        session = manager.ensure(key, name="s1", settings=settings, runner=_manager_runner)
        session.last_seen = time.monotonic() - 3600
        manager.reap_idle(ttl_seconds=60)
        assert manager.get(key) is None
    finally:
        manager.kill_all()


def test_manager_isolates_sessions() -> None:
    settings = Settings(browser_bind_host="127.0.0.1")
    manager = service.BrowserManager()
    try:
        first = manager.ensure(
            (1, 1, "a"), name="u1-p1-a", settings=settings, runner=_manager_runner
        )
        second = manager.ensure(
            (1, 1, "b"), name="u1-p1-b", settings=settings, runner=_manager_runner
        )
        assert first is not second
        assert manager.get((1, 1, "a")) is first
        assert manager.get((1, 1, "b")) is second
    finally:
        manager.kill_all()


def test_manager_start_failure_raises() -> None:
    def failing_runner(command: list[str], env: dict[str, str]) -> str:
        raise service.BrowserError("boom")

    manager = service.BrowserManager()
    with pytest.raises(service.BrowserError):
        manager.ensure(
            (1, 1, "x"),
            name="x",
            settings=Settings(browser_bind_host="127.0.0.1"),
            runner=failing_runner,
        )
