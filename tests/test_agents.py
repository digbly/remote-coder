from fastapi.testclient import TestClient

from app.modules.agents.catalog import DEFAULT_AGENT_SPECS
from tests.conftest import OTHER_USERNAME, _csrf, _login

AGENTS_URL = "/api/v1/agents"
SETTINGS_URL = "/api/v1/agents/settings"

EXPECTED_IDS = [spec.id for spec in DEFAULT_AGENT_SPECS]


def test_agents_requires_authentication(client: TestClient) -> None:
    assert client.get(AGENTS_URL).status_code == 401


def test_agents_lists_catalog_with_defaults(client: TestClient) -> None:
    _login(client)

    response = client.get(AGENTS_URL)
    assert response.status_code == 200

    agents = {agent["id"]: agent for agent in response.json()["agents"]}
    assert list(agents) == EXPECTED_IDS
    for spec in DEFAULT_AGENT_SPECS:
        entry = agents[spec.id]
        assert entry["label"] == spec.label
        assert entry["command"] == spec.command
        assert entry["args"] == spec.args
        assert isinstance(entry["installed"], bool)


def test_agent_setting_reflected_in_catalog(client: TestClient) -> None:
    _login(client)

    first = client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "echo", "args": "--verbose"},
        headers=_csrf(client),
    )
    assert first.status_code == 200
    assert first.json() == {"agent_id": "claude", "command": "echo", "args": "--verbose"}

    agents = {agent["id"]: agent for agent in client.get(AGENTS_URL).json()["agents"]}
    assert agents["claude"]["command"] == "echo"
    assert agents["claude"]["args"] == "--verbose"

    second = client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "echo", "args": "--model opus"},
        headers=_csrf(client),
    )
    assert second.status_code == 200
    assert client.get(SETTINGS_URL).json() == {
        "settings": [{"agent_id": "claude", "command": "echo", "args": "--model opus"}]
    }


def test_agent_settings_requires_authentication(client: TestClient) -> None:
    assert client.get(SETTINGS_URL).status_code == 401


def test_agent_settings_starts_empty(client: TestClient) -> None:
    _login(client)

    assert client.get(SETTINGS_URL).json() == {"settings": []}


def test_agent_setting_rejects_unknown_agent(client: TestClient) -> None:
    _login(client)

    response = client.put(
        f"{SETTINGS_URL}/not-a-real-agent",
        json={"command": "echo", "args": ""},
        headers=_csrf(client),
    )
    assert response.status_code == 404


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
