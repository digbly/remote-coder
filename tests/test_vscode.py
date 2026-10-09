import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.modules.vscode import service
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login


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


def _vscode_url(project_id: int, worktree: str, subpath: str = "") -> str:
    suffix = f"/{subpath}" if subpath else ""
    return f"/api/v1/projects/{project_id}/vscode/{worktree}{suffix}"


class _Upstream:
    """A minimal HTTP + WebSocket server standing in for code-server."""

    def __init__(self) -> None:
        self.port = _free_port()
        routes = [
            Route("/", lambda request: PlainTextResponse("root-ok")),
            Route("/hello", lambda request: PlainTextResponse("upstream-ok")),
            Route("/go", lambda request: RedirectResponse(url="/hello")),
            Route(
                "/framed",
                lambda request: PlainTextResponse(
                    "framed",
                    headers={
                        "X-Frame-Options": "DENY",
                        "Content-Security-Policy": "default-src 'self'",
                    },
                ),
            ),
            WebSocketRoute("/ws", self._ws),
        ]
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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _session_for(port: int, cwd: Path) -> service.VSCodeSession:
    process = SimpleNamespace(pid=0, poll=lambda: None)
    return service.VSCodeSession(
        cwd=cwd, host="127.0.0.1", port=port, data_dir=cwd, process=process
    )


class _StubManager:
    def __init__(self, session: service.VSCodeSession) -> None:
        self.session = session

    def ensure(self, key, *, cwd, settings, launch_builder=None):  # noqa: ANN001
        self.session.touch()
        return self.session

    def kill(self, key) -> None:  # noqa: ANN001
        return None

    def kill_all(self) -> None:
        return None


def test_vscode_requires_authentication(client: TestClient, projects_root: Path) -> None:
    response = client.get(_vscode_url(1, "wt-agent", "hello"))
    assert response.status_code == 401


def test_vscode_rejects_unknown_project(client: TestClient, projects_root: Path) -> None:
    _login(client)
    response = client.get(_vscode_url(999, "wt-agent", "hello"))
    assert response.status_code == 404


def test_vscode_rejects_unknown_worktree(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    response = client.get(_vscode_url(project_id, "does-not-exist", "hello"))
    assert response.status_code == 404


def test_vscode_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    response = client.get(_vscode_url(project_id, "wt-agent", "hello"))
    assert response.status_code == 404


def test_vscode_ws_requires_authentication(client: TestClient, projects_root: Path) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(_vscode_url(1, "wt-agent", "ws")):
            pass

    assert exc.value.code == 4401


def test_vscode_ws_rejects_cross_site_origin(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_repo_with_worktree(client, projects_root)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            _vscode_url(project_id, "wt-agent", "ws"),
            headers={"origin": "http://evil.example"},
        ):
            pass

    assert exc.value.code == 4403


def test_vscode_proxies_http(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, repo = _register_repo_with_worktree(client, projects_root)

    with _Upstream() as upstream:
        monkeypatch.setattr(service, "manager", _StubManager(_session_for(upstream.port, repo)))
        response = client.get(_vscode_url(project_id, "wt-agent", "hello"))

    assert response.status_code == 200
    assert response.text == "upstream-ok"


def test_vscode_proxies_root_with_trailing_slash(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, repo = _register_repo_with_worktree(client, projects_root)

    with _Upstream() as upstream:
        monkeypatch.setattr(service, "manager", _StubManager(_session_for(upstream.port, repo)))
        without_slash = client.get(_vscode_url(project_id, "wt-agent"))
        with_slash = client.get(f"{_vscode_url(project_id, 'wt-agent')}/")

    assert without_slash.status_code == 200
    assert without_slash.text == "root-ok"
    assert with_slash.status_code == 200
    assert with_slash.text == "root-ok"


def test_vscode_strips_framing_headers_only_when_embedded(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, repo = _register_repo_with_worktree(client, projects_root)

    with _Upstream() as upstream:
        monkeypatch.setattr(service, "manager", _StubManager(_session_for(upstream.port, repo)))
        embedded = client.get(
            _vscode_url(project_id, "wt-agent", "framed"),
            headers={"Sec-Fetch-Dest": "iframe"},
        )
        top_level = client.get(
            _vscode_url(project_id, "wt-agent", "framed"),
            headers={"Sec-Fetch-Dest": "document"},
        )

    assert "x-frame-options" not in embedded.headers
    assert "content-security-policy" not in embedded.headers
    assert top_level.headers["x-frame-options"] == "DENY"
    assert top_level.headers["content-security-policy"] == "default-src 'self'"


def test_vscode_rewrites_redirect_to_proxy_prefix(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, repo = _register_repo_with_worktree(client, projects_root)

    with _Upstream() as upstream:
        monkeypatch.setattr(service, "manager", _StubManager(_session_for(upstream.port, repo)))
        response = client.get(_vscode_url(project_id, "wt-agent", "go"), follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == _vscode_url(project_id, "wt-agent", "hello")


def test_vscode_proxies_websocket(
    client: TestClient, projects_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    project_id, repo = _register_repo_with_worktree(client, projects_root)

    with _Upstream() as upstream:
        monkeypatch.setattr(service, "manager", _StubManager(_session_for(upstream.port, repo)))
        with client.websocket_connect(_vscode_url(project_id, "wt-agent", "ws")) as websocket:
            websocket.send_text("ping")
            assert websocket.receive_text() == "echo:ping"


def test_launch_command_includes_bind_and_data_dir() -> None:
    settings = Settings(vscode_binary="code-server", vscode_bind_host="127.0.0.1")
    command = service.launch_command(
        port=8800, cwd=Path("/work"), data_dir=Path("/data"), settings=settings
    )

    assert command[0] == "code-server"
    assert "--bind-addr" in command
    assert "127.0.0.1:8800" in command
    assert command[-1] == "/work"
    assert "--auth" in command and "none" in command


def test_safe_name_sanitizes_worktree() -> None:
    assert service.safe_name("feature/one") == "feature-one"
    assert service.safe_name("..") == "worktree"


_LISTENER = (
    "import socket,sys,time;"
    "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
    "s.bind(('127.0.0.1',int(sys.argv[1])));s.listen();time.sleep(60)"
)


def _listener_builder(port: int, cwd: Path, data_dir: Path) -> list[str]:
    return [sys.executable, "-c", _LISTENER, str(port)]


def _manager_settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(vscode_user_data_root=str(tmp_path / "vscode"), **overrides)


def test_manager_reuses_and_kills_session(tmp_path: Path) -> None:
    settings = _manager_settings(tmp_path)
    manager = service.VSCodeManager()
    key = (1, 1, uuid4().hex)
    try:
        first = manager.ensure(
            key, cwd=tmp_path, settings=settings, launch_builder=_listener_builder
        )
        again = manager.ensure(
            key, cwd=tmp_path, settings=settings, launch_builder=_listener_builder
        )
        assert first is again
        assert first.alive()
    finally:
        manager.kill_all()

    assert manager.get(key) is None


def test_manager_evicts_least_recently_used(tmp_path: Path) -> None:
    settings = _manager_settings(tmp_path, vscode_max_sessions=1)
    manager = service.VSCodeManager()
    first_key = (1, 1, "one")
    second_key = (1, 1, "two")
    try:
        manager.ensure(first_key, cwd=tmp_path, settings=settings, launch_builder=_listener_builder)
        manager.ensure(
            second_key, cwd=tmp_path, settings=settings, launch_builder=_listener_builder
        )
        assert manager.get(first_key) is None
        assert manager.get(second_key) is not None
    finally:
        manager.kill_all()


def test_manager_reaps_idle_session(tmp_path: Path) -> None:
    settings = _manager_settings(tmp_path)
    manager = service.VSCodeManager()
    key = (1, 1, uuid4().hex)
    try:
        session = manager.ensure(
            key, cwd=tmp_path, settings=settings, launch_builder=_listener_builder
        )
        session.last_seen = time.monotonic() - 3600
        manager.reap_idle(ttl_seconds=60)
        assert manager.get(key) is None
    finally:
        manager.kill_all()
