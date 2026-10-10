from __future__ import annotations

import json
import re
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
    streaming_response_error,
    validate_model_items,
)

API_BASE = "https://api.openai.com/v1"
_REASONING_MODEL_PATTERN = re.compile(r"^(gpt-5|o3|o4)(-|$)")


def _supports_thinking(model: str) -> bool:
    return _REASONING_MODEL_PATTERN.match(model) is not None


class OpenAIAdapter(ProviderAdapterBase):
    kind = "openai"

    async def list_models(self, client: httpx.AsyncClient, api_key: str) -> list[ProviderModel]:
        try:
            response = await client.get(
                f"{API_BASE}/models",
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
            "instructions": system,
            "input": _input_items(messages),
            "stream": True,
        }
        if _supports_thinking(model):
            payload["reasoning"] = {"summary": "auto"}
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in tools
            ]

        try:
            async with client.stream(
                "POST",
                f"{API_BASE}/responses",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=120,
            ) as response:
                if not response.is_success:
                    raise await streaming_response_error(response, self.kind, api_key)
                async for event in iter_sse_payloads(response, self.kind):
                    event_type = event.get("type")
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            yield TextDelta(delta)
                    elif event_type == "response.reasoning_summary_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            yield ThinkingDelta(delta)
                    elif event_type == "response.output_item.done":
                        item = event.get("item")
                        if isinstance(item, dict) and item.get("type") == "function_call":
                            yield _tool_call(item)
                    elif event_type == "response.completed":
                        yield _completion(event)
                    elif event_type in {"error", "response.failed"}:
                        raise ProviderAPIError(
                            self.kind,
                            diagnostic=provider_error_detail(event, api_key),
                        )
        except httpx.HTTPError as exc:
            raise _safe_request_error(self.kind, exc) from None


def _input_items(messages: Sequence[ChatMessage]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for message in messages:
        if message.role == "tool":
            if not message.tool_call_id:
                raise ProviderAPIError(OpenAIAdapter.kind)
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
            continue

        if message.content:
            items.append({"role": message.role, "content": message.content})
        for call in message.tool_calls:
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                }
            )
    return items


def _tool_call(item: dict[str, object]) -> ToolCall:
    call_id = item.get("call_id")
    name = item.get("name")
    arguments = item.get("arguments")
    if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(arguments, str):
        raise ProviderAPIError(OpenAIAdapter.kind)
    try:
        decoded = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ProviderAPIError(OpenAIAdapter.kind) from exc
    if not isinstance(decoded, dict):
        raise ProviderAPIError(OpenAIAdapter.kind)
    return ToolCall(call_id, name, decoded)


def _completion(event: dict[str, object]) -> TurnComplete:
    response = event.get("response")
    usage = response.get("usage") if isinstance(response, dict) else None
    if not isinstance(usage, dict):
        return TurnComplete("completed")
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    return TurnComplete(
        "completed",
        input_tokens if isinstance(input_tokens, int) else None,
        output_tokens if isinstance(output_tokens, int) else None,
    )
