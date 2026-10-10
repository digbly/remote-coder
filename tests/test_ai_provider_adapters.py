import json

import pytest
from httpx import AsyncClient, MockTransport, Request, Response

from app.modules.ai_providers.anthropic import AnthropicAdapter
from app.modules.ai_providers.base import (
    ChatMessage,
    ProviderAPIError,
    ProviderTool,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
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
    gemini_tools = [
        ProviderTool(
            name="read_file",
            description="Read a file",
            parameters={
                "type": "object",
                "properties": {
                    "options": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "additionalProperties": False,
                    }
                },
                "additionalProperties": False,
            },
        )
    ]
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
        declaration = payload["tools"][0]["functionDeclarations"][0]
        assert declaration["name"] == "read_file"
        assert "additionalProperties" not in declaration["parameters"]
        assert "additionalProperties" not in declaration["parameters"]["properties"]["options"]
        assert "generationConfig" not in payload
        body = f"data: {json.dumps(chunk)}\n\n"
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in GeminiAdapter().stream(
                client, API_KEY, "gemini-text", "system", MESSAGES, gemini_tools
            )
        ]

    assert len(actual) == 3
    assert actual[0] == TextDelta("Reading now")
    assert isinstance(actual[1], ToolCall)
    assert actual[1].name == "read_file"
    assert actual[1].arguments == {"path": "main.py"}
    assert actual[2] == TurnComplete("STOP", 2, 3)


@pytest.mark.asyncio
async def test_gemini_round_trips_thought_signature_for_tool_calls() -> None:
    thought_signature = "sig-123"
    messages = [
        ChatMessage(
            role="assistant",
            tool_calls=(ToolCall("call-1", "read_file", {"path": "main.py"}, thought_signature),),
        )
    ]
    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "read_file",
                                "args": {"path": "main.py"},
                                "id": "call-1",
                            },
                            "thoughtSignature": thought_signature,
                        }
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3},
    }

    def handler(request: Request) -> Response:
        payload = json.loads(request.content)
        sent_part = payload["contents"][0]["parts"][0]
        assert sent_part["thoughtSignature"] == thought_signature
        assert "thoughtSignature" not in sent_part["functionCall"]
        body = f"data: {json.dumps(chunk)}\n\n"
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in GeminiAdapter().stream(
                client,
                API_KEY,
                "gemini-text",
                "system",
                messages,
                TOOLS,
            )
        ]

    assert actual[0].thought_signature == thought_signature
    assert actual[0].name == "read_file"
    assert actual[1] == TurnComplete("STOP", 2, 3)


@pytest.mark.asyncio
async def test_gemini_requests_and_streams_thought_summaries() -> None:
    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Let me think", "thought": True},
                        {"text": "The answer"},
                    ]
                },
                "finishReason": "STOP",
            }
        ]
    }

    def handler(request: Request) -> Response:
        payload = json.loads(request.content)
        assert payload["generationConfig"]["thinkingConfig"]["includeThoughts"] is True
        body = f"data: {json.dumps(chunk)}\n\n"
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in GeminiAdapter().stream(
                client, API_KEY, "gemini-2.5-flash", "system", MESSAGES, TOOLS
            )
        ]

    assert actual == [
        ThinkingDelta("Let me think"),
        TextDelta("The answer"),
        TurnComplete("STOP", None, None),
    ]


@pytest.mark.asyncio
async def test_anthropic_requests_and_streams_thinking() -> None:
    events = [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "Weighing options"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "signature_delta", "signature": "sig-abc"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "tool-1",
                "name": "read_file",
                "input": {},
            },
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"path":"main.py"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
        {"type": "message_stop"},
    ]
    requests: list[dict[str, object]] = []

    def handler(request: Request) -> Response:
        requests.append(json.loads(request.content))
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in AnthropicAdapter().stream(
                client, API_KEY, "claude-sonnet-4-20250514", "system", MESSAGES, TOOLS
            )
        ]

    assert requests[0]["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert actual == [
        ThinkingDelta("Weighing options"),
        ThinkingComplete(signature="sig-abc"),
        ToolCall("tool-1", "read_file", {"path": "main.py"}),
        TurnComplete("tool_use", None, None),
    ]


@pytest.mark.asyncio
async def test_anthropic_round_trips_thinking_before_tool_use() -> None:
    assistant = ChatMessage(
        role="assistant",
        tool_calls=(ToolCall("tool-1", "read_file", {"path": "main.py"}),),
        thinking="Weighing options",
        thinking_signature="sig-abc",
    )
    captured: dict[str, object] = {}

    def handler(request: Request) -> Response:
        captured.update(json.loads(request.content))
        return Response(200, headers={"content-type": "text/event-stream"}, text="")

    async with await _client(handler) as client:
        async for _event in AnthropicAdapter().stream(
            client, API_KEY, "claude-sonnet-4-20250514", "system", [assistant], TOOLS
        ):
            pass

    messages = captured["messages"]
    assert messages[0]["content"][0] == {
        "type": "thinking",
        "thinking": "Weighing options",
        "signature": "sig-abc",
    }
    assert messages[0]["content"][1]["type"] == "tool_use"


@pytest.mark.asyncio
async def test_anthropic_merges_parallel_tool_results_into_one_user_turn() -> None:
    assistant = ChatMessage(
        role="assistant",
        tool_calls=(
            ToolCall("tool-1", "read_file", {"path": "a.py"}),
            ToolCall("tool-2", "read_file", {"path": "b.py"}),
        ),
        thinking="Reasoning",
        thinking_signature="sig-abc",
    )
    tool_one = ChatMessage(role="tool", content="A", tool_call_id="tool-1", tool_name="read_file")
    tool_two = ChatMessage(role="tool", content="B", tool_call_id="tool-2", tool_name="read_file")
    captured: dict[str, object] = {}

    def handler(request: Request) -> Response:
        captured.update(json.loads(request.content))
        return Response(200, headers={"content-type": "text/event-stream"}, text="")

    async with await _client(handler) as client:
        async for _event in AnthropicAdapter().stream(
            client,
            API_KEY,
            "claude-sonnet-4-20250514",
            "system",
            [assistant, tool_one, tool_two],
            TOOLS,
        ):
            pass

    messages = captured["messages"]
    assert [message["role"] for message in messages] == ["assistant", "user"]
    assert [block["type"] for block in messages[1]["content"]] == ["tool_result", "tool_result"]


@pytest.mark.asyncio
async def test_openai_requests_and_streams_reasoning_summary() -> None:
    events = [
        {"type": "response.reasoning_summary_text.delta", "delta": "Considering options"},
        {"type": "response.output_text.delta", "delta": "Answer"},
        {
            "type": "response.completed",
            "response": {"usage": {"input_tokens": 1, "output_tokens": 2}},
        },
    ]

    def handler(request: Request) -> Response:
        payload = json.loads(request.content)
        assert payload["reasoning"] == {"summary": "auto"}
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        actual = [
            event
            async for event in OpenAIAdapter().stream(
                client, API_KEY, "gpt-5", "system", MESSAGES, TOOLS
            )
        ]

    assert actual == [
        ThinkingDelta("Considering options"),
        TextDelta("Answer"),
        TurnComplete("completed", 1, 2),
    ]


@pytest.mark.asyncio
async def test_provider_errors_do_not_expose_api_key() -> None:
    def handler(_request: Request) -> Response:
        return Response(401, json={"error": {"message": f"invalid key: {API_KEY}"}})

    async with await _client(handler) as client:
        with pytest.raises(ProviderAPIError) as exc_info:
            await OpenAIAdapter().list_models(client, API_KEY)

    assert API_KEY not in str(exc_info.value)
    assert exc_info.value.status_code == 401
    assert exc_info.value.diagnostic == "invalid key: [REDACTED]"


@pytest.mark.asyncio
async def test_gemini_stream_error_includes_sanitized_provider_detail() -> None:
    chunk = {
        "error": {
            "code": 400,
            "message": f"Invalid API key: {API_KEY}",
            "status": "INVALID_ARGUMENT",
        }
    }

    def handler(_request: Request) -> Response:
        body = f"data: {json.dumps(chunk)}\n\n"
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        with pytest.raises(ProviderAPIError) as exc_info:
            async for _event in GeminiAdapter().stream(
                client, API_KEY, "gemini-test", "system", MESSAGES, TOOLS
            ):
                pass

    assert exc_info.value.diagnostic == "Invalid API key: [REDACTED]"
    assert API_KEY not in (exc_info.value.diagnostic or "")


@pytest.mark.asyncio
async def test_gemini_http_error_includes_sanitized_provider_detail() -> None:
    def handler(_request: Request) -> Response:
        return Response(
            400,
            json={"error": {"message": f"Invalid key {API_KEY}\nrequest rejected"}},
        )

    async with await _client(handler) as client:
        with pytest.raises(ProviderAPIError) as exc_info:
            async for _event in GeminiAdapter().stream(
                client, API_KEY, "gemini-test", "system", MESSAGES, TOOLS
            ):
                pass

    assert exc_info.value.status_code == 400
    assert exc_info.value.diagnostic == "Invalid key [REDACTED] request rejected"
    assert API_KEY not in (exc_info.value.diagnostic or "")


@pytest.mark.asyncio
async def test_gemini_blocked_prompt_includes_reason() -> None:
    chunk = {"promptFeedback": {"blockReason": "SAFETY"}}

    def handler(_request: Request) -> Response:
        body = f"data: {json.dumps(chunk)}\n\n"
        return Response(200, headers={"content-type": "text/event-stream"}, text=body)

    async with await _client(handler) as client:
        with pytest.raises(ProviderAPIError) as exc_info:
            async for _event in GeminiAdapter().stream(
                client, API_KEY, "gemini-test", "system", MESSAGES, TOOLS
            ):
                pass

    assert exc_info.value.diagnostic == "Prompt blocked: SAFETY"
