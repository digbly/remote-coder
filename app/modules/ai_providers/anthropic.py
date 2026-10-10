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
    ThinkingComplete,
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

API_BASE = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"
MODEL_PAGE_SIZE = 100
THINKING_BUDGET_TOKENS = 2048
_THINKING_MODEL_PATTERN = re.compile(r"claude-(opus|sonnet|haiku)-4|claude-3[-.]7")


def _supports_thinking(model: str) -> bool:
    return _THINKING_MODEL_PATTERN.search(model) is not None


class AnthropicAdapter(ProviderAdapterBase):
    kind = "anthropic"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        }

    async def list_models(self, client: httpx.AsyncClient, api_key: str) -> list[ProviderModel]:
        models: list[ProviderModel] = []
        after_id: str | None = None
        try:
            while len(models) < MAX_PROVIDER_MODELS:
                params: dict[str, str | int] = {"limit": MODEL_PAGE_SIZE}
                if after_id is not None:
                    params["after_id"] = after_id
                response = await client.get(
                    f"{API_BASE}/models",
                    headers=self._headers(api_key),
                    params=params,
                    timeout=20,
                )
                payload = response_json(response, self.kind, api_key)
                items = validate_model_items(payload, self.kind, "data")
                for item in items:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                        raise ProviderAPIError(self.kind, response.status_code)
                    model_id = item["id"]
                    display_name = item.get("display_name")
                    models.append(
                        ProviderModel(
                            model_id,
                            display_name if isinstance(display_name, str) else model_id,
                        )
                    )
                    if len(models) >= MAX_PROVIDER_MODELS:
                        break

                has_more = payload.get("has_more")
                if not isinstance(has_more, bool):
                    raise ProviderAPIError(self.kind, response.status_code)
                if not has_more:
                    break
                last_id = payload.get("last_id")
                if not isinstance(last_id, str) or last_id == after_id:
                    raise ProviderAPIError(self.kind, response.status_code)
                after_id = last_id
        except httpx.HTTPError as exc:
            raise _safe_request_error(self.kind, exc) from None
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
            "max_tokens": 4096,
            "system": system,
            "messages": _messages(messages),
            "stream": True,
        }
        if _supports_thinking(model):
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": THINKING_BUDGET_TOKENS,
            }
        if tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]

        tool_inputs: dict[int, dict[str, object]] = {}
        tool_json: dict[int, str] = {}
        thinking_signatures: dict[int, str] = {}
        redacted_thinking: dict[int, str] = {}
        input_tokens: int | None = None
        output_tokens: int | None = None
        stop_reason: str | None = None
        try:
            async with client.stream(
                "POST",
                f"{API_BASE}/messages",
                headers=self._headers(api_key),
                json=payload,
                timeout=120,
            ) as response:
                if not response.is_success:
                    raise await streaming_response_error(response, self.kind, api_key)
                async for event in iter_sse_payloads(response, self.kind):
                    event_type = event.get("type")
                    if event_type == "message_start":
                        message = event.get("message")
                        usage = message.get("usage") if isinstance(message, dict) else None
                        if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
                            input_tokens = usage["input_tokens"]
                    elif event_type == "content_block_start":
                        index = event.get("index")
                        block = event.get("content_block")
                        if isinstance(index, int) and isinstance(block, dict):
                            block_type = block.get("type")
                            if block_type == "tool_use":
                                initial = block.get("input")
                                tool_inputs[index] = {
                                    "id": block.get("id"),
                                    "name": block.get("name"),
                                    "input": initial if isinstance(initial, dict) else {},
                                }
                                tool_json[index] = ""
                            elif block_type == "thinking":
                                thinking_signatures[index] = ""
                            elif block_type == "redacted_thinking":
                                data = block.get("data")
                                if isinstance(data, str):
                                    redacted_thinking[index] = data
                    elif event_type == "content_block_delta":
                        index = event.get("index")
                        delta = event.get("delta")
                        if isinstance(delta, dict):
                            delta_type = delta.get("type")
                            if delta_type == "text_delta":
                                text = delta.get("text")
                                if isinstance(text, str):
                                    yield TextDelta(text)
                            elif delta_type == "thinking_delta":
                                thinking = delta.get("thinking")
                                if isinstance(thinking, str):
                                    yield ThinkingDelta(thinking)
                            elif delta_type == "signature_delta" and isinstance(index, int):
                                signature = delta.get("signature")
                                if isinstance(signature, str):
                                    thinking_signatures[index] = (
                                        thinking_signatures.get(index, "") + signature
                                    )
                            elif delta_type == "input_json_delta" and isinstance(index, int):
                                partial = delta.get("partial_json")
                                if isinstance(partial, str):
                                    tool_json[index] = tool_json.get(index, "") + partial
                    elif event_type == "content_block_stop":
                        index = event.get("index")
                        if isinstance(index, int):
                            if index in tool_inputs:
                                yield _tool_call(index, tool_inputs, tool_json)
                            elif index in redacted_thinking:
                                yield ThinkingComplete(redacted=redacted_thinking.pop(index))
                            elif index in thinking_signatures:
                                signature = thinking_signatures.pop(index)
                                yield ThinkingComplete(signature=signature or None)
                    elif event_type == "message_delta":
                        usage = event.get("usage")
                        delta = event.get("delta")
                        if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
                            output_tokens = usage["output_tokens"]
                        if isinstance(delta, dict) and isinstance(delta.get("stop_reason"), str):
                            stop_reason = delta["stop_reason"]
                    elif event_type == "message_stop":
                        yield TurnComplete(stop_reason, input_tokens, output_tokens)
                    elif event_type == "error":
                        raise ProviderAPIError(
                            self.kind,
                            diagnostic=provider_error_detail(event, api_key),
                        )
        except httpx.HTTPError as exc:
            raise _safe_request_error(self.kind, exc) from None


def _messages(messages: Sequence[ChatMessage]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == "tool":
            blocks: list[dict[str, object]] = []
            while index < len(messages) and messages[index].role == "tool":
                tool_message = messages[index]
                if not tool_message.tool_call_id:
                    raise ProviderAPIError(AnthropicAdapter.kind)
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_message.tool_call_id,
                        "content": tool_message.content,
                    }
                )
                index += 1
            result.append({"role": "user", "content": blocks})
            continue

        content: list[dict[str, object]] = []
        if message.redacted_thinking is not None:
            content.append({"type": "redacted_thinking", "data": message.redacted_thinking})
        elif message.thinking is not None:
            thinking_block: dict[str, object] = {
                "type": "thinking",
                "thinking": message.thinking,
            }
            if message.thinking_signature is not None:
                thinking_block["signature"] = message.thinking_signature
            content.append(thinking_block)
        if message.content:
            content.append({"type": "text", "text": message.content})
        for call in message.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
            )
        if content:
            result.append({"role": message.role, "content": content})
        index += 1
    return result


def _tool_call(
    index: int,
    tool_inputs: dict[int, dict[str, object]],
    tool_json: dict[int, str],
) -> ToolCall:
    raw = tool_json.get(index, "")
    if raw:
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderAPIError(AnthropicAdapter.kind) from exc
        if not isinstance(arguments, dict):
            raise ProviderAPIError(AnthropicAdapter.kind)
    else:
        initial = tool_inputs[index].get("input")
        arguments = initial if isinstance(initial, dict) else {}
    tool_input = tool_inputs[index]
    tool_id = tool_input.get("id")
    name = tool_input.get("name")
    if not isinstance(tool_id, str) or not isinstance(name, str):
        raise ProviderAPIError(AnthropicAdapter.kind)
    return ToolCall(tool_id, name, arguments)
