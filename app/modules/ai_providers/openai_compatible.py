from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.modules.ai_providers.base import (
    MAX_PROVIDER_MODELS,
    ChatMessage,
    ProviderAdapterBase,
    ProviderAPIError,
    ProviderEvent,
    ProviderModel,
    ProviderTool,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    TurnComplete,
    _safe_request_error,
    iter_sse_payloads,
    provider_error_detail,
    response_json,
    sanitize_provider_detail,
    streaming_response_error,
    validate_model_items,
)

_REASONING_KEYS = ("reasoning_content", "reasoning")


class OpenAICompatibleAdapter(ProviderAdapterBase):
    """Adapter for generic OpenAI-compatible ``chat/completions`` endpoints."""

    def __init__(self, kind: str, base_url: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")

    async def list_models(self, client: httpx.AsyncClient, api_key: str) -> list[ProviderModel]:
        try:
            response = await client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=20,
            )
        except httpx.HTTPError as exc:
            raise _safe_request_error(self.kind, exc) from None

        payload = response_json(response, self.kind, api_key)
        items = validate_model_items(payload, self.kind, "data")
        models: list[ProviderModel] = []
        for item in items[:MAX_PROVIDER_MODELS]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ProviderAPIError(self.kind, response.status_code)
            model_id = item["id"]
            models.append(ProviderModel(model_id, model_id))
        return models

    async def stream(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ProviderTool],
    ) -> AsyncIterator[ProviderEvent]:
        payload: dict[str, object] = {
            "model": model,
            "messages": _messages(self.kind, system, messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        tool_calls: dict[int, dict[str, object]] = {}
        finish_reason: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=120,
            ) as response:
                if not response.is_success:
                    raise await streaming_response_error(response, self.kind, api_key)
                async for event in iter_sse_payloads(response, self.kind):
                    error = event.get("error")
                    if error is not None:
                        diagnostic = (
                            sanitize_provider_detail(error, api_key)
                            if isinstance(error, str)
                            else provider_error_detail(event, api_key)
                        )
                        raise ProviderAPIError(self.kind, diagnostic=diagnostic)
                    usage = event.get("usage")
                    if isinstance(usage, dict):
                        if isinstance(usage.get("prompt_tokens"), int):
                            input_tokens = usage["prompt_tokens"]
                        if isinstance(usage.get("completion_tokens"), int):
                            output_tokens = usage["completion_tokens"]
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise ProviderAPIError(self.kind)
                    reason = choice.get("finish_reason")
                    if isinstance(reason, str):
                        finish_reason = reason
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        yield TextDelta(text)
                    for key in _REASONING_KEYS:
                        reasoning = delta.get(key)
                        if isinstance(reasoning, str) and reasoning:
                            yield ThinkingDelta(reasoning)
                            break
                    calls = delta.get("tool_calls")
                    if isinstance(calls, list):
                        _accumulate_tool_calls(tool_calls, calls, self.kind)
        except httpx.HTTPError as exc:
            raise _safe_request_error(self.kind, exc) from None

        for call in _finalize_tool_calls(tool_calls, self.kind):
            yield call
        yield TurnComplete(finish_reason, input_tokens, output_tokens)


def _messages(kind: str, system: str, messages: Sequence[ChatMessage]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if system:
        result.append({"role": "system", "content": system})
    for message in messages:
        if message.role == "tool":
            if not message.tool_call_id:
                raise ProviderAPIError(kind)
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
            continue
        entry: dict[str, object] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in message.tool_calls
            ]
        result.append(entry)
    return result


def _accumulate_tool_calls(
    tool_calls: dict[int, dict[str, object]], calls: list[object], kind: str
) -> None:
    for raw in calls:
        if not isinstance(raw, dict):
            raise ProviderAPIError(kind)
        index = raw.get("index")
        if not isinstance(index, int):
            index = 0
        entry = tool_calls.setdefault(index, {"id": None, "name": None, "arguments": ""})
        call_id = raw.get("id")
        if isinstance(call_id, str):
            entry["id"] = call_id
        function = raw.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str):
                entry["name"] = name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                entry["arguments"] = str(entry.get("arguments") or "") + arguments


def _finalize_tool_calls(tool_calls: dict[int, dict[str, object]], kind: str) -> list[ToolCall]:
    result: list[ToolCall] = []
    for index in sorted(tool_calls):
        entry = tool_calls[index]
        call_id = entry.get("id")
        name = entry.get("name")
        if not isinstance(call_id, str) or not isinstance(name, str):
            raise ProviderAPIError(kind)
        raw = entry.get("arguments")
        if isinstance(raw, str) and raw:
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderAPIError(kind) from exc
            if not isinstance(decoded, dict):
                raise ProviderAPIError(kind)
            arguments: dict[str, object] = decoded
        else:
            arguments = {}
        result.append(ToolCall(call_id, name, arguments))
    return result
