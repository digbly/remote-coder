import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.core.errors import ErrorCode
from app.modules.ai_chat import skills
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_chat.models import ChatMessage as StoredMessage
from app.modules.ai_chat.models import MessageStatus
from app.modules.ai_chat.streaming import ChatTurnLimitError, stream_chat_turn
from app.modules.ai_chat.tools import MAX_TOOL_ROUNDS_PER_TURN
from app.modules.ai_providers.base import (
    ProviderAPIError,
    ProviderModel,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    TurnComplete,
)
from app.modules.ai_providers.openai import OpenAIAdapter
from app.modules.auth.models import User
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


def _write_skill(
    home: Path, slug: str, *, name: str, description: str, body: str
) -> None:
    directory = home / ".agents" / "skills" / slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def _events(response) -> list[dict[str, object]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


def test_chat_streams_and_persists_a_resumable_conversation(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, api_key: str) -> list[ProviderModel]:
        assert api_key == "provider-secret"
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, _client, api_key, model, _system, messages, tools, *, session_id=None):
        assert api_key == "provider-secret"
        assert model == "gpt-test"
        assert {tool.name for tool in tools} == {
            "list_project_files",
            "read_file",
            "search_project_files",
            "propose_file_change",
            "create_project_file",
            "delete_project_file",
            "create_project_directory",
            "delete_project_directory",
            "move_project_entry",
            "run_project_command",
        }
        calls["stream"] += 1
        if calls["stream"] == 2:
            assert [message.content for message in messages[-3:]] == [
                "First question",
                "First answer",
                "Second question",
            ]
        yield TextDelta("First answer" if calls["stream"] == 1 else "Second answer")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)

    first_events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "First question",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = first_events[0]["conversation"]["id"]

    assert [event["type"] for event in first_events] == [
        "message_start",
        "text_delta",
        "complete",
    ]
    assert first_events[1]["text"] == "First answer"

    second_events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "conversation_id": conversation_id,
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Second question",
            },
            headers=_csrf(client),
        )
    )
    detail = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()

    assert second_events[-1]["type"] == "complete"
    assert [message["content"] for message in detail["messages"]] == [
        "First question",
        "First answer",
        "Second question",
        "Second answer",
    ]
    assert all(message["status"] == "completed" for message in detail["messages"])
    assert (
        client.get(f"/api/v1/projects/{project_id}/ai-chat/conversations").json()["conversations"][
            0
        ]["id"]
        == conversation_id
    )


def test_chat_streams_and_persists_thinking(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, *_args, **_kwargs):
        yield ThinkingDelta("Deliberating")
        yield TextDelta("Answer")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Question",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]
    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]

    assert [event["type"] for event in events] == [
        "message_start",
        "thinking_delta",
        "text_delta",
        "complete",
    ]
    assert events[1]["text"] == "Deliberating"
    assert messages[-1]["thinking"] == "Deliberating"
    assert messages[-1]["content"] == "Answer"


def test_chat_runs_provider_command_and_returns_output_to_provider(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_path = projects_root / "project"
    project_id = _create_project(client, project_path)
    provider_id = _create_provider(client)
    settings_url = f"/api/v1/projects/{project_id}/ai-chat/command-permission"
    response = client.put(
        settings_url,
        json={"mode": "allow_all"},
        headers=_csrf(client),
    )
    assert response.status_code == 200

    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, _client, _api_key, _model, _system, messages, tools, *, session_id=None):
        assert "run_project_command" in {tool.name for tool in tools}
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("command-1", "run_project_command", {"command": "pwd"})
        else:
            result = json.loads(messages[-1].content)
            assert result["output"].strip() == str(project_path)
            assert result["exit_code"] == 0
            yield TextDelta("Command completed")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Show my working directory",
            },
            headers=_csrf(client),
        )
    )

    assert [event["type"] for event in events] == [
        "message_start",
        "tool_call",
        "text_delta",
        "complete",
    ]
    assert events[1]["name"] == "run_project_command"
    assert events[2]["text"] == "Command completed"


def test_chat_rejects_unavailable_model_before_persisting_messages(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-valid", "GPT Valid")]

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)

    response = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
        json={
            "provider_id": provider_id,
            "model_id": "not-listed",
            "message": "Hello",
        },
        headers=_csrf(client),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == ErrorCode.AI_CHAT_MODEL_UNAVAILABLE.value
    assert (
        client.get(f"/api/v1/projects/{project_id}/ai-chat/conversations").json()["conversations"]
        == []
    )


def test_chat_conversation_is_scoped_to_owner_and_project(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    other_project_id = _create_project(client, projects_root / "other-project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, *_args, **_kwargs):
        yield TextDelta("Answer")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Question",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]

    cross_project = client.get(
        f"/api/v1/projects/{other_project_id}/ai-chat/conversations/{conversation_id}"
    )
    _login(client, OTHER_USERNAME)
    cross_user = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    )

    assert cross_project.status_code == 404
    assert cross_project.json()["detail"]["code"] == "AI_CHAT_CONVERSATION_NOT_FOUND"
    assert cross_user.status_code == 404
    assert cross_user.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_chat_recovers_with_final_answer_when_tool_rounds_exhausted(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    calls = {"n": 0}
    tools_seen: list[tuple] = []
    systems_seen: list[str] = []

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, _client, _api_key, _model, _system, messages, tools, *, session_id=None):
        calls["n"] += 1
        tools_seen.append(tuple(tools))
        systems_seen.append(_system)
        if tools:
            yield ToolCall(f"call-{calls['n']}", "list_project_files", {})
        else:
            yield TextDelta("Final answer")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Keep exploring forever",
            },
            headers=_csrf(client),
        )
    )

    assert events[-1]["type"] == "complete"
    assert events[-1]["status"] == "completed"
    assert any(event["type"] == "notice" for event in events)
    assert any(event["type"] == "tool_call" for event in events)
    assert any(
        event["type"] == "text_delta" and event["text"] == "Final answer" for event in events
    )
    assert calls["n"] == MAX_TOOL_ROUNDS_PER_TURN
    assert tools_seen[-1] == ()
    assert all(len(tools) > 0 for tools in tools_seen[:-1])
    assert "Tool use is now disabled for this turn." in systems_seen[-1]
    assert all("Tool use is now disabled" not in system for system in systems_seen[:-1])


def test_chat_empty_model_response_is_reported_as_failure(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, *_args, **_kwargs):
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Question",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]
    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "AI_CHAT_EMPTY_RESPONSE"
    assert messages[-1]["status"] == "failed"
    assert messages[-1]["error"] == events[-1]["message"]


def test_chat_provider_failure_is_streamed_and_persisted(
    client: TestClient, projects_root, monkeypatch, caplog
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def fail_stream(self, *_args, **_kwargs):
        raise ProviderAPIError("openai", 400, "model is not available")
        yield

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", fail_stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Question",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]
    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "AI_PROVIDER_FAILED"
    assert events[-1]["message"] == "model is not available"
    assert messages[-1]["status"] == "failed"
    assert messages[-1]["error"] == "model is not available"
    assert "provider-secret" not in str(events)
    assert "provider=openai status=400 detail=model is not available" in caplog.text


def test_chat_turn_limit_is_streamed_and_persisted(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def limit_stream(self, *_args, **_kwargs):
        raise ChatTurnLimitError
        yield

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", limit_stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Question",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]
    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]

    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "AI_CHAT_LIMIT_EXCEEDED"
    assert messages[-1]["status"] == "failed"
    assert messages[-1]["error"] == events[-1]["message"]


def test_chat_edit_and_resend_replaces_the_turn_and_later_messages(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    seen_history: list[list[str]] = []

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, _system, messages, _tools, *, session_id=None
    ):
        seen_history.append([message.content for message in messages])
        yield TextDelta(f"Answer to: {messages[-1].content}")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)

    def send(message: str, conversation_id: str | None = None, edit_id: int | None = None):
        payload: dict[str, object] = {
            "provider_id": provider_id,
            "model_id": "gpt-test",
            "message": message,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        if edit_id is not None:
            payload["edit_user_message_id"] = edit_id
        return _events(
            client.post(
                f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
                json=payload,
                headers=_csrf(client),
            )
        )

    first = send("First question")
    conversation_id = first[0]["conversation"]["id"]
    send("Second question", conversation_id)

    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]
    assert [message["content"] for message in messages] == [
        "First question",
        "Answer to: First question",
        "Second question",
        "Answer to: Second question",
    ]
    first_user_id = messages[0]["id"]

    seen_history.clear()
    edited = send("Edited question", conversation_id, first_user_id)

    detail = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()
    assert edited[-1]["type"] == "complete"
    # The edited turn and everything after it are replaced by the new turn.
    assert [message["content"] for message in detail["messages"]] == [
        "Edited question",
        "Answer to: Edited question",
    ]
    assert all(message["status"] == "completed" for message in detail["messages"])
    assert seen_history == [["Edited question"]]


def test_chat_edit_rejects_missing_or_assistant_message(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, *_args, **_kwargs):
        yield TextDelta("Answer")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Question"},
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]
    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]
    assistant_id = messages[1]["id"]

    for edit_id in (assistant_id, 999_999):
        response = client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "conversation_id": conversation_id,
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Edited",
                "edit_user_message_id": edit_id,
            },
            headers=_csrf(client),
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "AI_CHAT_MESSAGE_NOT_FOUND"

    missing_conversation = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
        json={
            "provider_id": provider_id,
            "model_id": "gpt-test",
            "message": "Edited",
            "edit_user_message_id": messages[0]["id"],
        },
        headers=_csrf(client),
    )
    assert missing_conversation.status_code == 422

    unchanged = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]
    assert [message["content"] for message in unchanged] == ["Question", "Answer"]


def test_chat_injects_user_and_project_instructions_into_the_system_prompt(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    home = projects_root / "home"
    (home / ".config" / "agents").mkdir(parents=True)
    (home / ".config" / "agents" / "AGENTS.md").write_text(
        "Always answer in Vietnamese.\n", encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    project_path = projects_root / "project"
    project_id = _create_project(client, project_path)
    provider_id = _create_provider(client)
    (project_path / "AGENTS.md").write_text("Use tabs, not spaces.\n", encoding="utf-8")
    captured: list[str] = []

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, system, _messages, _tools, *, session_id=None
    ):
        captured.append(system)
        yield TextDelta("ok")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Question"},
            headers=_csrf(client),
        )
    )

    assert len(captured) == 1
    assert "You are a code assistant" in captured[0]
    assert "Always answer in Vietnamese." in captured[0]
    assert "Use tabs, not spaces." in captured[0]


def test_chat_final_round_keeps_agent_instructions(
    client: TestClient, projects_root, monkeypatch
) -> None:
    """Tools are disabled for the last round, but the conventions must still apply."""
    _login(client)
    monkeypatch.setenv("HOME", str(projects_root / "home"))
    project_path = projects_root / "project"
    project_id = _create_project(client, project_path)
    provider_id = _create_provider(client)
    (project_path / "AGENTS.md").write_text("Use tabs, not spaces.\n", encoding="utf-8")
    systems: list[str] = []

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, system, _messages, tools, *, session_id=None
    ):
        systems.append(system)
        if tools:
            yield ToolCall(f"call-{len(systems)}", "list_project_files", {})
        else:
            yield TextDelta("Final answer")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Question"},
            headers=_csrf(client),
        )
    )

    assert len(systems) == MAX_TOOL_ROUNDS_PER_TURN
    assert "Tool use is now disabled for this turn." in systems[-1]
    assert all("Use tabs, not spaces." in system for system in systems)


def test_skills_endpoint_lists_available_skills(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    home = projects_root / "home"
    _write_skill(
        home, "doc-writer", name="Doc Writer", description="Writes docs.", body="# Doc"
    )
    _write_skill(
        home, "interview-me", name="interview-me", description="Ask questions.", body="# Ask"
    )
    # Directories without a SKILL.md are ignored.
    (home / ".agents" / "skills" / "not-a-skill").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    project_id = _create_project(client, projects_root / "project")

    response = client.get(f"/api/v1/projects/{project_id}/ai-chat/skills")

    assert response.status_code == 200
    payload = response.json()["skills"]
    assert [item["slug"] for item in payload] == ["doc-writer", "interview-me"]
    assert payload[0] == {
        "slug": "doc-writer",
        "name": "Doc Writer",
        "description": "Writes docs.",
    }


def test_skills_endpoint_requires_authentication(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    client.cookies.clear()

    response = client.get(f"/api/v1/projects/{project_id}/ai-chat/skills")

    assert response.status_code == 401


def test_parse_frontmatter_folds_wrapped_description() -> None:
    text = (
        "---\nname: doc-writer\ndescription: First line\n"
        "  wrapped line.\n---\n\n# Body\n\nContent.\n"
    )
    meta, body = skills.parse_frontmatter(text)

    assert meta["name"] == "doc-writer"
    assert meta["description"] == "First line wrapped line."
    assert body.startswith("# Body")


def test_load_skill_body_strips_frontmatter(projects_root, monkeypatch) -> None:
    home = projects_root / "home"
    _write_skill(
        home, "doc-writer", name="Doc Writer", description="Writes docs.", body="# Steps"
    )
    monkeypatch.setenv("HOME", str(home))

    assert skills.load_skill_body("doc-writer") == "# Steps"
    assert skills.load_skill_body("../escape") is None
    assert skills.load_skill_body("missing") is None


def test_chat_applies_selected_skill_to_the_system_prompt(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    home = projects_root / "home"
    _write_skill(
        home,
        "doc-writer",
        name="Doc Writer",
        description="Writes docs.",
        body="Always write documentation with examples.",
    )
    monkeypatch.setenv("HOME", str(home))
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    captured: list[str] = []

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, system, _messages, _tools, *, session_id=None
    ):
        captured.append(system)
        yield TextDelta("ok")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)

    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "",
                "skill": "doc-writer",
            },
            headers=_csrf(client),
        )
    )
    conversation_id = events[0]["conversation"]["id"]
    messages = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
    ).json()["messages"]

    assert "Always write documentation with examples." in captured[0]
    assert "Active skill" in captured[0]
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "/doc-writer"


def test_chat_rejects_unknown_or_unsafe_skill(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    monkeypatch.setenv("HOME", str(projects_root / "home"))
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)

    for slug in ("missing-skill", "../escape"):
        response = client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Hi",
                "skill": slug,
            },
            headers=_csrf(client),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == ErrorCode.AI_CHAT_SKILL_UNAVAILABLE.value
    assert (
        client.get(f"/api/v1/projects/{project_id}/ai-chat/conversations").json()[
            "conversations"
        ]
        == []
    )


def test_chat_retries_transient_provider_error(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    calls = {"n": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(self, *_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ProviderAPIError("openai", 503, "temporarily overloaded")
        yield TextDelta("Recovered")
        yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    monkeypatch.setattr("app.modules.ai_chat.streaming.PROVIDER_RETRY_BACKOFF_SECONDS", 0.0)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Question"},
            headers=_csrf(client),
        )
    )

    assert calls["n"] == 2
    assert events[-1]["type"] == "complete"
    assert any(event["type"] == "text_delta" and event["text"] == "Recovered" for event in events)


def test_readonly_context_tool_refuses_traversal_and_never_writes(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    project_path = projects_root / "project"
    project_id = _create_project(client, project_path)
    provider_id = _create_provider(client)
    (project_path / "source.py").write_text("original", encoding="utf-8")
    outside = projects_root / "outside.txt"
    outside.write_text("outside-secret", encoding="utf-8")
    tool_results: list[str] = []
    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, _system, messages, _tools, *, session_id=None
    ):
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("read-1", "read_file", {"path": "../outside.txt"})
        else:
            tool_results.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("I could not read outside the project.")
        yield TurnComplete("tool_calls" if calls["stream"] == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Read outside the project",
            },
            headers=_csrf(client),
        )
    )

    assert events[-1]["type"] == "complete"
    assert tool_results == ['{"error":"FILE_PATH_INVALID"}']
    assert (project_path / "source.py").read_text(encoding="utf-8") == "original"


def test_read_file_tool_reads_a_supporting_skill_file(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    home = projects_root / "home"
    _write_skill(
        home,
        "code-review",
        name="Code Review",
        description="Review code.",
        body="Read reference.md before reviewing.",
    )
    reference = home / ".agents" / "skills" / "code-review" / "reference.md"
    reference.write_text("# Checklist\n\n- Check error handling\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    tool_results: list[str] = []
    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, _system, messages, _tools, *, session_id=None
    ):
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("read-1", "read_file", {"path": "code-review/reference.md"})
        else:
            tool_results.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("Reviewed using the checklist.")
        yield TurnComplete("tool_calls" if calls["stream"] == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Review"},
            headers=_csrf(client),
        )
    )

    assert events[-1]["type"] == "complete"
    result = json.loads(tool_results[0])
    assert result["path"] == "code-review/reference.md"
    assert "Check error handling" in result["content"]
    assert result["truncated"] is False


def test_read_file_tool_prefers_a_project_file_over_a_skill_file(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    home = projects_root / "home"
    _write_skill(
        home, "shared", name="Shared", description="Shared.", body="# Shared"
    )
    (home / ".agents" / "skills" / "shared" / "reference.md").write_text(
        "skill-version", encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(home))
    project_path = projects_root / "project"
    project_id = _create_project(client, project_path)
    provider_id = _create_provider(client)
    (project_path / "shared").mkdir()
    (project_path / "shared" / "reference.md").write_text("project-version", encoding="utf-8")
    tool_results: list[str] = []
    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, _system, messages, _tools, *, session_id=None
    ):
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("read-1", "read_file", {"path": "shared/reference.md"})
        else:
            tool_results.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("done")
        yield TurnComplete("tool_calls" if calls["stream"] == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Read"},
            headers=_csrf(client),
        )
    )

    assert json.loads(tool_results[0])["content"] == "project-version"


def test_read_file_tool_handles_a_symlinked_skills_root(
    client: TestClient, projects_root, monkeypatch
) -> None:
    """A symlinked home must not break skill reads (root vs. resolved paths)."""
    _login(client)
    real_home = projects_root / "real-home"
    _write_skill(
        real_home, "code-review", name="Code Review", description="Review.", body="# Review"
    )
    (real_home / ".agents" / "skills" / "code-review" / "reference.md").write_text(
        "symlink-ok", encoding="utf-8"
    )
    home_link = projects_root / "home"
    home_link.symlink_to(real_home)
    monkeypatch.setenv("HOME", str(home_link))
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    tool_results: list[str] = []
    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, _system, messages, _tools, *, session_id=None
    ):
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("read-1", "read_file", {"path": "code-review/reference.md"})
        else:
            tool_results.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("done")
        yield TurnComplete("tool_calls" if calls["stream"] == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Read"},
            headers=_csrf(client),
        )
    )

    result = json.loads(tool_results[0])
    assert result["path"] == "code-review/reference.md"
    assert result["content"] == "symlink-ok"


def test_read_file_tool_rejects_escapes_and_missing_files(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    home = projects_root / "home"
    _write_skill(
        home, "code-review", name="Code Review", description="Review code.", body="# Review"
    )
    (home / "secret.txt").write_text("home-secret", encoding="utf-8")
    (home / ".agents" / "skills" / "escape-link").symlink_to(home)
    monkeypatch.setenv("HOME", str(home))
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)
    tool_results: list[str] = []
    calls = {"stream": 0}

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    async def stream(
        self, _client, _api_key, _model, _system, messages, _tools, *, session_id=None
    ):
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("t-1", "read_file", {"path": "../secret.txt"})
            yield ToolCall("t-2", "read_file", {"path": "/etc/passwd"})
            yield ToolCall("t-3", "read_file", {"path": "escape-link/secret.txt"})
            yield ToolCall("t-4", "read_file", {"path": "code-review/missing.md"})
        else:
            tool_results.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("done")
        yield TurnComplete("tool_calls" if calls["stream"] == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "Read"},
            headers=_csrf(client),
        )
    )

    assert events[-1]["type"] == "complete"
    assert tool_results == [
        '{"error":"FILE_PATH_INVALID"}',
        '{"error":"FILE_PATH_INVALID"}',
        '{"error":"FILE_PATH_INVALID"}',
        '{"error":"FILE_NOT_FOUND"}',
    ]


@pytest.mark.asyncio
async def test_cancelled_stream_persists_interrupted_status(monkeypatch) -> None:
    from app.modules.ai_chat import service as chat_service

    statuses: list[MessageStatus] = []

    def finish(_db, _message, _content, status, thinking=""):
        statuses.append(status)

    class InterruptedAdapter:
        kind = "openai"

        async def stream(self, *_args, **_kwargs):
            yield TextDelta("Partial response")
            raise asyncio.CancelledError

    monkeypatch.setattr(chat_service, "finish_assistant", finish)
    assistant = StoredMessage(id=42)
    user = User(id=1, username="alice")
    stream = stream_chat_turn(
        db=Mock(),
        adapter=InterruptedAdapter(),
        api_key="private",
        model_id="test",
        context=ProjectContext(Mock(), user, 1, "conversation"),
        conversation_id="conversation",
        conversation_title="test",
        user_message_id=1,
        user_content="Question",
        assistant_message=assistant,
        history=[],
    )

    assert json.loads((await anext(stream)).decode())["type"] == "message_start"
    assert json.loads((await anext(stream)).decode()) == {
        "type": "text_delta",
        "text": "Partial response",
    }
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)

    assert statuses == [MessageStatus.INTERRUPTED]


@pytest.mark.asyncio
async def test_cancelled_immediately_after_start_persists_interrupted_status(monkeypatch) -> None:
    from app.modules.ai_chat import service as chat_service

    statuses: list[MessageStatus] = []

    def finish(_db, _message, _content, status, thinking=""):
        statuses.append(status)

    class UnusedAdapter:
        kind = "openai"

        async def stream(self, *_args, **_kwargs):
            yield TurnComplete("completed")

    monkeypatch.setattr(chat_service, "finish_assistant", finish)
    stream = stream_chat_turn(
        db=Mock(),
        adapter=UnusedAdapter(),
        api_key="private",
        model_id="test",
        context=ProjectContext(Mock(), User(id=1, username="alice"), 1, "conversation"),
        conversation_id="conversation",
        conversation_title="test",
        user_message_id=1,
        user_content="Question",
        assistant_message=StoredMessage(id=42),
        history=[],
    )

    assert json.loads((await anext(stream)).decode())["type"] == "message_start"
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError)

    assert statuses == [MessageStatus.INTERRUPTED]


@pytest.mark.asyncio
async def test_unexpected_stream_failure_persists_failed_status(monkeypatch) -> None:
    from app.modules.ai_chat import service as chat_service

    statuses: list[MessageStatus] = []

    def finish(_db, _message, _content, status, thinking=""):
        statuses.append(status)

    class FailingAdapter:
        kind = "openai"

        async def stream(self, *_args, **_kwargs):
            raise RuntimeError("unexpected provider failure")
            yield

    monkeypatch.setattr(chat_service, "finish_assistant", finish)
    stream = stream_chat_turn(
        db=Mock(),
        adapter=FailingAdapter(),
        api_key="private",
        model_id="test",
        context=ProjectContext(Mock(), User(id=1, username="alice"), 1, "conversation"),
        conversation_id="conversation",
        conversation_title="test",
        user_message_id=1,
        user_content="Question",
        assistant_message=StoredMessage(id=42),
        history=[],
    )

    assert json.loads((await anext(stream)).decode())["type"] == "message_start"
    with pytest.raises(RuntimeError, match="unexpected provider failure"):
        await anext(stream)

    assert statuses == [MessageStatus.FAILED]


def test_chat_requires_message_or_skill(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    monkeypatch.setenv("HOME", str(projects_root / "home"))
    project_id = _create_project(client, projects_root / "project")
    provider_id = _create_provider(client)

    response = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
        json={"provider_id": provider_id, "model_id": "gpt-test", "message": ""},
        headers=_csrf(client),
    )

    assert response.status_code == 422
