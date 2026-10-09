import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import OTHER_USERNAME, _login

GET_URL = "/api/v1/workspace"
WS_URL = "/api/v1/workspace/ws"


def _sample_state(name: str) -> dict:
    return {
        "activeProject": {"id": 1, "name": name},
        "workspaces": {
            "1": {
                "tabs": [{"id": "tab-1", "title": name, "kind": "terminal", "projectId": 1}],
                "activeId": "tab-1",
            }
        },
        "layout": {"leftOpen": True, "leftWidth": 240, "rightOpen": True, "rightWidth": 320},
    }


def test_workspace_get_requires_authentication(client: TestClient) -> None:
    assert client.get(GET_URL).status_code == 401


def test_workspace_websocket_requires_authentication(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_URL):
            pass

    assert exc.value.code == 4401


def test_workspace_websocket_rejects_cross_site_origin(client: TestClient) -> None:
    _login(client)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_URL, headers={"origin": "http://evil.example"}):
            pass

    assert exc.value.code == 4403


def test_workspace_starts_empty(client: TestClient) -> None:
    _login(client)

    with client.websocket_connect(WS_URL) as websocket:
        assert websocket.receive_json() == {"type": "state", "state": None}

    assert client.get(GET_URL).json() == {"state": None}


def test_workspace_broadcasts_and_persists(client: TestClient) -> None:
    _login(client)
    state = _sample_state("alpha")

    with client.websocket_connect(WS_URL) as first, client.websocket_connect(WS_URL) as second:
        assert first.receive_json()["state"] is None
        assert second.receive_json()["state"] is None

        first.send_text(json.dumps({"type": "update", "state": state, "origin": "client-a"}))

        message = second.receive_json()
        assert message["state"] == state
        assert message["origin"] == "client-a"

    assert client.get(GET_URL).json() == {"state": state}


def test_workspace_replays_state_on_reconnect(client: TestClient) -> None:
    _login(client)
    state = _sample_state("beta")

    with client.websocket_connect(WS_URL) as first, client.websocket_connect(WS_URL) as second:
        assert first.receive_json()["state"] is None
        assert second.receive_json()["state"] is None
        first.send_text(json.dumps({"type": "update", "state": state, "origin": "client-a"}))
        second.receive_json()

    with client.websocket_connect(WS_URL) as websocket:
        assert websocket.receive_json() == {"type": "state", "state": state}


def test_workspace_is_scoped_per_user(client: TestClient) -> None:
    _login(client)
    state = _sample_state("gamma")

    with client.websocket_connect(WS_URL) as first, client.websocket_connect(WS_URL) as second:
        first.receive_json()
        second.receive_json()
        first.send_text(json.dumps({"type": "update", "state": state}))
        second.receive_json()

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    assert client.get(GET_URL).json() == {"state": None}
