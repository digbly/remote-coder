import json

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from app.modules.ai_providers.anthropic import AnthropicAdapter
from app.modules.ai_providers.base import (
    ChatMessage,
    ProviderAPIError,
    ProviderTool,
    TextDelta,
    ToolCall,
    TurnComplete,
)
from app.modules.ai_providers.gemini import GeminiAdapter
from app.modules.ai_providers.openai import OpenAIAdapter

API_KEY = "private-provider-key"
TOOLS = [ProviderTool(name="read_file", description="Read a file", parameters={"type": "object"})]
MESSAGES = [ChatMessage(role="user", content="Read main.py")]


async def _client(handler) -> AsyncClient:
    return AsyncClient(transport=MockTransport(handler))


@pytest.mark.asyncio
async def test_openai_lists_models_with_bearer_auth() -> None:
    def handler(request: Request) -> Response:
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in str(request.url)
        return Response(200, json={"data": [{"id": "gpt-example", "owned_by": "test"}]})

    async with await _client(handler) as client:
        models = await OpenAIAdapter().list_models(client, API_KEY)

    assert [model.id for model in models] == ["gpt-example"]


@pytest.mark.asyncio
async def test_openai_streams_text_tool_call_and_completion() -> None:
    events = [
        {
            "type": "response.output_text.delta",
            "delta": "Checking the file.",
        },
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call-1",
                "name": "read_file",
                "arguments": '{"path":"main.py"}',
            },
        },
        {
            "type": "response.completed",
            "response": {"usage": {"input_tokens": 5, "output_tokens": 7}},
        },
    ]

    def handler(request: Request) -> Response:
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["tools"][0]["type"] == "function"
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in OpenAIAdapter().stream(
                client, API_KEY, "gpt-example", "system", MESSAGES, TOOLS
            )
        ]

    assert actual == [
        TextDelta("Checking the file."),
        ToolCall("call-1", "read_file", {"path": "main.py"}),
        TurnComplete("completed", 5, 7),
    ]


@pytest.mark.asyncio
async def test_anthropic_paginates_model_list_and_uses_version_headers() -> None:
    requests: list[Request] = []

    def handler(request: Request) -> Response:
        requests.append(request)
        assert request.url.path == "/v1/models"
        assert request.headers["x-api-key"] == API_KEY
        assert request.headers["anthropic-version"] == "2023-06-01"
        if request.url.params.get("after_id") is None:
            return Response(
                200,
                json={
                    "data": [{"id": "claude-a", "display_name": "Claude A"}],
                    "has_more": True,
                    "last_id": "claude-a",
                },
            )
        return Response(200, json={"data": [{"id": "claude-b"}], "has_more": False})

    async with await _client(handler) as client:
        models = await AnthropicAdapter().list_models(client, API_KEY)

    assert [model.id for model in models] == ["claude-a", "claude-b"]
    assert requests[1].url.params["after_id"] == "claude-a"


@pytest.mark.asyncio
async def test_anthropic_streams_text_tool_call_and_completion() -> None:
    events = [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tool-1", "name": "read_file", "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"path":"main.py"}'},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": "Done"},
        },
        {
            "type": "message_delta",
            "usage": {"output_tokens": 4},
            "delta": {"stop_reason": "end_turn"},
        },
        {"type": "message_stop"},
    ]

    def handler(request: Request) -> Response:
        payload = json.loads(request.content)
        assert request.headers["x-api-key"] == API_KEY
        assert payload["stream"] is True
        assert payload["tools"][0]["input_schema"]["type"] == "object"
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in AnthropicAdapter().stream(
                client, API_KEY, "claude-example", "system", MESSAGES, TOOLS
            )
        ]

    assert actual == [
        ToolCall("tool-1", "read_file", {"path": "main.py"}),
        TextDelta("Done"),
        TurnComplete("end_turn", None, 4),
    ]


@pytest.mark.asyncio
async def test_gemini_lists_only_text_generation_models_and_paginates() -> None:
    requests: list[Request] = []

    def handler(request: Request) -> Response:
        requests.append(request)
        assert request.headers["x-goog-api-key"] == API_KEY
        if request.url.params.get("pageToken") is None:
            return Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-text",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {"name": "models/gemini-audio", "supportedGenerationMethods": ["predict"]},
                    ],
                    "nextPageToken": "next",
                },
            )
        return Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-next",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        )

    async with await _client(handler) as client:
        models = await GeminiAdapter().list_models(client, API_KEY)

    assert [model.id for model in models] == ["gemini-text", "gemini-next"]
    assert requests[1].url.params["pageToken"] == "next"
    assert API_KEY not in str(requests[0].url)


@pytest.mark.asyncio
async def test_gemini_streams_text_tool_call_and_completion() -> None:
    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Reading now"},
                        {"functionCall": {"name": "read_file", "args": {"path": "main.py"}}},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
    }

    def handler(request: Request) -> Response:
        assert request.url.path.endswith(":streamGenerateContent")
        assert request.url.params["alt"] == "sse"
        assert request.headers["x-goog-api-key"] == API_KEY
        payload = json.loads(request.content)
        assert payload["tools"][0]["functionDeclarations"][0]["name"] == "read_file"
        body = f"data: {json.dumps(chunk)}\n\n"
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in GeminiAdapter().stream(
                client, API_KEY, "gemini-text", "system", MESSAGES, TOOLS
            )
        ]

    assert len(actual) == 3
    assert actual[0] == TextDelta("Reading now")
    assert isinstance(actual[1], ToolCall)
    assert actual[1].name == "read_file"
    assert actual[1].arguments == {"path": "main.py"}
    assert actual[2] == TurnComplete("STOP", 2, 3)


@pytest.mark.asyncio
async def test_provider_errors_do_not_expose_api_key() -> None:
    def handler(_request: Request) -> Response:
        return Response(401, json={"error": {"message": f"invalid key: {API_KEY}"}})

    async with await _client(handler) as client:
        with pytest.raises(ProviderAPIError) as exc_info:
            await OpenAIAdapter().list_models(client, API_KEY)

    assert API_KEY not in str(exc_info.value)
