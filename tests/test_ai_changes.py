import json
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.modules.ai_providers.base import ProviderModel, TextDelta, ToolCall, TurnComplete
from app.modules.ai_providers.openai import OpenAIAdapter
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login

PROVIDERS_URL = "/api/v1/ai-providers"


def _create_project(client: TestClient, folder: Path) -> int:
    folder.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_provider(client: TestClient) -> int:
    response = client.post(
        PROVIDERS_URL,
        json={"name": "OpenAI", "kind": "openai", "api_key": "provider-secret"},
        headers=_csrf(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _events(response) -> list[dict[str, object]]:
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines()]


def _create_proposal(
    client: TestClient,
    project_id: int,
    provider_id: int,
    monkeypatch,
) -> tuple[str, str, dict[str, object]]:
    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    calls = 0

    async def stream(self, *_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield ToolCall(
                "proposal-1",
                "propose_file_change",
                {"path": "main.py", "content": "print('updated')\n"},
            )
            yield TurnComplete("tool_calls")
        else:
            yield TextDelta("I prepared a diff for review.")
            yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Update main.py",
            },
            headers=_csrf(client),
        )
    )
    start = events[0]
    proposal_event = next(event for event in events if event["type"] == "proposal")
    return start["conversation"]["id"], proposal_event["id"], proposal_event


def test_proposal_is_reviewable_and_does_not_write_before_approval(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")

    conversation_id, proposal_id, event = _create_proposal(
        client, project_id, provider_id, monkeypatch
    )

    assert target.read_text(encoding="utf-8") == "print('original')\n"
    assert event["path"] == "main.py"
    assert "print('original')" in event["diff"]
    assert "print('updated')" in event["diff"]
    listed = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}/proposals"
    ).json()["proposals"]
    assert listed[0]["id"] == proposal_id
    assert listed[0]["status"] == "pending"


def test_apply_requires_explicit_approval_and_writes_proposed_content(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")
    conversation_id, proposal_id, _ = _create_proposal(client, project_id, provider_id, monkeypatch)

    response = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply",
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert response.json()["proposal"]["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "print('updated')\n"


def test_reject_leaves_file_unchanged_and_proposal_cannot_be_reused(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")
    conversation_id, proposal_id, _ = _create_proposal(client, project_id, provider_id, monkeypatch)
    endpoint = (
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}"
    )

    rejected = client.post(f"{endpoint}/reject", headers=_csrf(client))
    second_action = client.post(f"{endpoint}/apply", headers=_csrf(client))

    assert rejected.status_code == 200
    assert rejected.json()["proposal"]["status"] == "rejected"
    assert target.read_text(encoding="utf-8") == "print('original')\n"
    assert second_action.status_code == 409
    assert second_action.json()["detail"]["code"] == "AI_CHANGE_PROPOSAL_NOT_PENDING"


def test_stale_or_foreign_proposals_cannot_be_applied(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")
    conversation_id, proposal_id, _ = _create_proposal(client, project_id, provider_id, monkeypatch)
    endpoint = (
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply"
    )
    target.write_text("print('edited elsewhere')\n", encoding="utf-8")

    stale = client.post(endpoint, headers=_csrf(client))
    _login(client, OTHER_USERNAME)
    foreign = client.post(endpoint, headers=_csrf(client))

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "AI_CHANGE_PROPOSAL_STALE"
    assert target.read_text(encoding="utf-8") == "print('edited elsewhere')\n"
    assert foreign.status_code == 404
