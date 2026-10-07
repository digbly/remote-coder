import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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


def test_terminal_requires_authentication(client: TestClient, projects_root: Path) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/projects/1/terminal"):
            pass

    assert exc.value.code == 4401


def test_terminal_rejects_unknown_project(client: TestClient, projects_root: Path) -> None:
    _login(client)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/projects/999/terminal"):
            pass

    assert exc.value.code == 4404


def test_terminal_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/projects/{project_id}/terminal"):
            pass

    assert exc.value.code == 4404


def test_terminal_rejects_cross_site_origin(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/api/v1/projects/{project_id}/terminal",
            headers={"origin": "http://evil.example"},
        ):
            pass

    assert exc.value.code == 4403


def test_terminal_runs_shell_in_project_directory(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with client.websocket_connect(f"/api/v1/projects/{project_id}/terminal") as websocket:
        websocket.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
        websocket.send_text(json.dumps({"type": "input", "data": "pwd\n"}))
        output = _read_until(websocket, "terminal-repo")

    assert "terminal-repo" in output


def test_terminal_interrupts_foreground_process(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _register_project(client, projects_root)

    with client.websocket_connect(f"/api/v1/projects/{project_id}/terminal") as websocket:
        websocket.send_text(json.dumps({"type": "input", "data": "sleep 30\n"}))
        time.sleep(0.4)
        websocket.send_text(json.dumps({"type": "input", "data": "\x03"}))
        time.sleep(0.4)
        websocket.send_text(json.dumps({"type": "input", "data": "echo AFTER=$?\n"}))
        output = _read_until(websocket, "AFTER=130")

    assert "AFTER=130" in output
