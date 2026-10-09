import sys

from fastapi.testclient import TestClient

from app.modules.agents import model_sources, service
from app.modules.agents.catalog import registry
from app.modules.agents.model_sources import MAX_MODELS, CliModelsAgent
from tests.conftest import _csrf, _login

AGENTS_URL = "/api/v1/agents"
SETTINGS_URL = "/api/v1/agents/settings"


async def test_run_captures_stdout() -> None:
    assert await model_sources._run(["/bin/sh", "-c", "printf 'a\\nb\\n'"], 5) == b"a\nb\n"


async def test_run_returns_none_on_failure() -> None:
    assert await model_sources._run(["/bin/sh", "-c", "exit 3"], 5) is None
    assert await model_sources._run(["definitely-missing-cmd-xyz"], 5) is None


async def test_run_bounds_stdout(monkeypatch) -> None:
    monkeypatch.setattr(model_sources, "MAX_OUTPUT_BYTES", 8)

    output = await model_sources._run([sys.executable, "-c", "print('x' * 1000)"], 5)

    assert output == b"xxxxxxxx"


def test_cli_models_agent_is_used_for_claude_and_opencode() -> None:
    assert isinstance(registry.get("claude"), CliModelsAgent)
    assert isinstance(registry.get("opencode"), CliModelsAgent)


async def test_unparsable_args_return_no_models() -> None:
    agent = CliModelsAgent(registry.get("claude").spec)

    assert await agent.list_models("claude", '--flag "unclosed') == []


def test_parse_models_trims_dedupes_and_caps() -> None:
    agent = CliModelsAgent(registry.get("claude").spec)

    assert agent.parse_models(b" sonnet \n\nopus\nsonnet\nhaiku\n") == [
        "sonnet",
        "opus",
        "haiku",
    ]

    many = b"\n".join(f"m{index}".encode() for index in range(MAX_MODELS + 10))
    assert len(agent.parse_models(many)) == MAX_MODELS


def test_models_requires_authentication(client: TestClient) -> None:
    assert client.get(f"{AGENTS_URL}/claude/models").status_code == 401


def test_models_unknown_agent_is_not_found(client: TestClient) -> None:
    _login(client)

    assert client.get(f"{AGENTS_URL}/nope/models").status_code == 404


def test_models_empty_for_agent_without_model_listing(client: TestClient) -> None:
    _login(client)
    service.clear_models_cache()

    response = client.get(f"{AGENTS_URL}/gemini/models")

    assert response.status_code == 200
    assert response.json() == {"models": []}


def test_models_endpoint_returns_and_caches(client: TestClient, monkeypatch) -> None:
    _login(client)
    calls = {"count": 0}

    async def fake_list_models(self, command: str, args: str) -> list[str]:
        calls["count"] += 1
        return ["gpt-x", "gpt-y"]

    monkeypatch.setattr(CliModelsAgent, "list_models", fake_list_models)
    service.clear_models_cache()

    first = client.get(f"{AGENTS_URL}/claude/models")
    second = client.get(f"{AGENTS_URL}/claude/models")

    assert first.status_code == 200
    assert first.json() == {"models": ["gpt-x", "gpt-y"]}
    assert second.json() == {"models": ["gpt-x", "gpt-y"]}
    assert calls["count"] == 1


def test_models_fail_soft_when_command_missing(client: TestClient) -> None:
    _login(client)
    service.clear_models_cache()
    client.put(
        f"{SETTINGS_URL}/claude",
        json={"command": "definitely-missing-cmd-xyz", "args": ""},
        headers=_csrf(client),
    )

    response = client.get(f"{AGENTS_URL}/claude/models")

    assert response.status_code == 200
    assert response.json() == {"models": []}
