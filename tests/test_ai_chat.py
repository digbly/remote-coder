import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.core.errors import ErrorCode
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_chat.models import ChatMessage as StoredMessage
from app.modules.ai_chat.models import MessageStatus
from app.modules.ai_chat.streaming import stream_chat_turn
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

    async def stream(self, _client, api_key, model, _system, messages, tools):
        assert api_key == "provider-secret"
        assert model == "gpt-test"
        assert {tool.name for tool in tools} == {
            "list_project_files",
            "read_project_file",
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

    async def stream(self, _client, _api_key, _model, _system, messages, tools):
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

    async def stream(self, _client, _api_key, _model, _system, messages, tools):
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
    assert "provider-secret" not in str(events)
    assert "provider=openai status=400 detail=model is not available" in caplog.text


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

    async def stream(self, _client, _api_key, _model, _system, messages, _tools):
        calls["stream"] += 1
        if calls["stream"] == 1:
            yield ToolCall("read-1", "read_project_file", {"path": "../outside.txt"})
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
