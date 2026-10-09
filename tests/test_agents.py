from fastapi.testclient import TestClient

from tests.conftest import OTHER_USERNAME, _csrf, _login

AGENTS_URL = "/api/v1/agents"
SETTINGS_URL = "/api/v1/agents/settings"


def test_agents_requires_authentication(client: TestClient) -> None:
    assert client.get(AGENTS_URL, params={"commands": "sh"}).status_code == 401


def test_agents_detects_installed_commands(client: TestClient) -> None:
    _login(client)

    response = client.get(AGENTS_URL, params={"commands": "sh,definitely-missing-cmd-xyz"})
    assert response.status_code == 200

    agents = {agent["command"]: agent for agent in response.json()["agents"]}
    assert agents["sh"]["installed"] is True
    assert agents["sh"]["path"]
    assert agents["definitely-missing-cmd-xyz"]["installed"] is False
    assert agents["definitely-missing-cmd-xyz"]["path"] is None


def test_agents_ignores_invalid_and_duplicate_commands(client: TestClient) -> None:
    _login(client)

    response = client.get(AGENTS_URL, params={"commands": "sh,sh,../etc/passwd,bad cmd"})
    assert response.status_code == 200

    commands = [agent["command"] for agent in response.json()["agents"]]
    assert commands == ["sh"]


def test_agents_without_commands_returns_empty(client: TestClient) -> None:
    _login(client)

    response = client.get(AGENTS_URL)
    assert response.status_code == 200
    assert response.json() == {"agents": []}


def test_agent_settings_requires_authentication(client: TestClient) -> None:
    assert client.get(SETTINGS_URL).status_code == 401


def test_agent_settings_starts_empty(client: TestClient) -> None:
    _login(client)

    assert client.get(SETTINGS_URL).json() == {"settings": []}


def test_agent_setting_roundtrip_and_overwrite(client: TestClient) -> None:
    _login(client)

    first = client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "claude", "args": "--verbose"},
        headers=_csrf(client),
    )
    assert first.status_code == 200
    assert first.json() == {"agent_id": "claude", "command": "claude", "args": "--verbose"}

    second = client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "claude", "args": "--model opus"},
        headers=_csrf(client),
    )
    assert second.status_code == 200
    assert client.get(SETTINGS_URL).json() == {
        "settings": [{"agent_id": "claude", "command": "claude", "args": "--model opus"}]
    }


def test_agent_setting_rejects_invalid_command(client: TestClient) -> None:
    _login(client)

    response = client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "../../bin/sh", "args": ""},
        headers=_csrf(client),
    )
    assert response.status_code == 422


def test_agent_setting_rejects_multiline_args(client: TestClient) -> None:
    _login(client)

    response = client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "claude", "args": "a\nb"},
        headers=_csrf(client),
    )
    assert response.status_code == 422


def test_agent_settings_are_scoped_per_user(client: TestClient) -> None:
    _login(client)
    client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "claude", "args": ""},
        headers=_csrf(client),
    )

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    assert client.get(SETTINGS_URL).json() == {"settings": []}
