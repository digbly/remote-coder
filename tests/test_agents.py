from fastapi.testclient import TestClient

from tests.conftest import _login

AGENTS_URL = "/api/v1/agents"


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
