from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from urllib.parse import quote
from uuid import uuid4

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

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL_PAGE_SIZE = 100


class GeminiAdapter(ProviderAdapterBase):
    kind = "gemini"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"x-goog-api-key": api_key}

    async def list_models(self, client: httpx.AsyncClient, api_key: str) -> list[ProviderModel]:
        models: list[ProviderModel] = []
        page_token: str | None = None
        try:
            while len(models) < MAX_PROVIDER_MODELS:
                params: dict[str, str | int] = {"pageSize": MODEL_PAGE_SIZE}
                if page_token is not None:
                    params["pageToken"] = page_token
                response = await client.get(
                    f"{API_BASE}/models",
                    headers=self._headers(api_key),
                    params=params,
                    timeout=20,
                )
                payload = response_json(response, self.kind, api_key)
                items = validate_model_items(payload, self.kind, "models")
                for item in items:
                    if not isinstance(item, dict):
                        raise ProviderAPIError(self.kind, response.status_code)
                    methods = item.get("supportedGenerationMethods")
                    name = item.get("name")
                    if not isinstance(methods, list) or not isinstance(name, str):
                        raise ProviderAPIError(self.kind, response.status_code)
                    if "generateContent" not in methods:
                        continue
                    model_id = name.removeprefix("models/")
                    if not model_id:
                        raise ProviderAPIError(self.kind, response.status_code)
                    display_name = item.get("displayName")
                    models.append(
                        ProviderModel(
                            model_id,
                            display_name if isinstance(display_name, str) else model_id,
                        )
                    )
                    if len(models) >= MAX_PROVIDER_MODELS:
                        break

                next_token = payload.get("nextPageToken")
                if not next_token:
                    break
                if not isinstance(next_token, str) or next_token == page_token:
                    raise ProviderAPIError(self.kind, response.status_code)
                page_token = next_token
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
        model_path = quote(model.removeprefix("models/"), safe="")
        payload: dict[str, object] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": _contents(messages),
        }
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": _gemini_schema(tool.parameters),
                        }
                        for tool in tools
                    ]
                }
            ]

        try:
            async with client.stream(
                "POST",
                f"{API_BASE}/models/{model_path}:streamGenerateContent",
                headers=self._headers(api_key),
                params={"alt": "sse"},
                json=payload,
                timeout=120,
            ) as response:
                if not response.is_success:
                    raise await streaming_response_error(response, self.kind, api_key)
                async for chunk in iter_sse_payloads(response, self.kind):
                    for event in _chunk_events(chunk, api_key):
                        yield event
        except httpx.HTTPError as exc:
            raise _safe_request_error(self.kind, exc) from None


def _contents(messages: Sequence[ChatMessage]) -> list[dict[str, object]]:
    contents: list[dict[str, object]] = []
    for message in messages:
        parts: list[dict[str, object]] = []
        if message.role == "tool":
            if not message.tool_name:
                raise ProviderAPIError(GeminiAdapter.kind)
            function_response: dict[str, object] = {
                "name": message.tool_name,
                "response": {"content": message.content},
            }
            if message.tool_call_id:
                function_response["id"] = message.tool_call_id
            parts.append({"functionResponse": function_response})
            contents.append({"role": "user", "parts": parts})
            continue

        if message.content:
            parts.append({"text": message.content})
        for call in message.tool_calls:
            part: dict[str, object] = {
                "functionCall": {
                    "name": call.name,
                    "args": call.arguments,
                    "id": call.id,
                }
            }
            if call.thought_signature:
                part["thoughtSignature"] = call.thought_signature
            parts.append(part)
        if parts:
            contents.append(
                {"role": "model" if message.role == "assistant" else "user", "parts": parts}
            )
    return contents


def _gemini_schema(schema: dict[str, object]) -> dict[str, object]:
    return {
        key: _convert_schema_value(value)
        for key, value in schema.items()
        if key != "additionalProperties"
    }


def _convert_schema_value(value: object) -> object:
    if isinstance(value, dict):
        return _gemini_schema(value)
    if isinstance(value, list):
        return [_convert_schema_value(item) for item in value]
    return value


def _chunk_events(chunk: dict[str, object], api_key: str | None = None) -> list[ProviderEvent]:
    events: list[ProviderEvent] = []
    if "error" in chunk:
        raise ProviderAPIError(
            GeminiAdapter.kind,
            diagnostic=provider_error_detail(chunk, api_key),
        )
    prompt_feedback = chunk.get("promptFeedback")
    if isinstance(prompt_feedback, dict) and isinstance(prompt_feedback.get("blockReason"), str):
        raise ProviderAPIError(
            GeminiAdapter.kind,
            diagnostic=sanitize_provider_detail(
                f"Prompt blocked: {prompt_feedback['blockReason']}", api_key
            ),
        )
    candidates = chunk.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(parts, list):
                for part in parts:
                    if not isinstance(part, dict) or part.get("thought") is True:
                        continue
                    text = part.get("text")
                    if isinstance(text, str):
                        events.append(TextDelta(text))
                    function_call = part.get("functionCall")
                    if isinstance(function_call, dict):
                        name = function_call.get("name")
                        arguments = function_call.get("args", {})
                        call_id = function_call.get("id")
                        thought_signature = part.get("thoughtSignature")
                        if not isinstance(name, str) or not isinstance(arguments, dict):
                            raise ProviderAPIError(GeminiAdapter.kind)
                        call_id = call_id if isinstance(call_id, str) else uuid4().hex
                        thought_signature = (
                            thought_signature if isinstance(thought_signature, str) else None
                        )
                        events.append(ToolCall(call_id, name, arguments, thought_signature))

            finish_reason = candidate.get("finishReason")
            if isinstance(finish_reason, str):
                usage = chunk.get("usageMetadata")
                prompt_tokens = usage.get("promptTokenCount") if isinstance(usage, dict) else None
                output_tokens = (
                    usage.get("candidatesTokenCount") if isinstance(usage, dict) else None
                )
                events.append(
                    TurnComplete(
                        finish_reason,
                        prompt_tokens if isinstance(prompt_tokens, int) else None,
                        output_tokens if isinstance(output_tokens, int) else None,
                    )
                )
    return events
