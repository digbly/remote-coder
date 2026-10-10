from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx

MAX_PROVIDER_MODELS = 500


class ProviderAPIError(Exception):
    """A sanitized provider request or response error."""

    def __init__(self, provider: str, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        message = (
            f"{provider} API returned status {status_code}"
            if status_code is not None
            else f"{provider} API request or response failed"
        )
        super().__init__(message)


@dataclass(frozen=True)
class ProviderModel:
    id: str
    display_name: str


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class ProviderTool:
    name: str
    description: str
    parameters: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class TurnComplete:
    reason: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None


ProviderEvent = TextDelta | ToolCall | TurnComplete


class ProviderAdapter(Protocol):
    kind: str

    async def list_models(self, client: httpx.AsyncClient, api_key: str) -> list[ProviderModel]: ...

    async def validate_connection(self, client: httpx.AsyncClient, api_key: str) -> None: ...

    def stream(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ProviderTool],
    ) -> AsyncIterator[ProviderEvent]: ...


class ProviderAdapterBase:
    kind: str

    async def validate_connection(self, client: httpx.AsyncClient, api_key: str) -> None:
        await self.list_models(client, api_key)


async def iter_sse_payloads(
    response: httpx.Response, provider: str
) -> AsyncIterator[dict[str, object]]:
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line and data_lines:
            payload = _decode_sse_data("\n".join(data_lines), provider)
            data_lines.clear()
            if payload is not None:
                yield payload
    if data_lines:
        payload = _decode_sse_data("\n".join(data_lines), provider)
        if payload is not None:
            yield payload


def _decode_sse_data(data: str, provider: str) -> dict[str, object] | None:
    if data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ProviderAPIError(provider) from exc
    if not isinstance(payload, dict):
        raise ProviderAPIError(provider)
    return payload


def response_json(response: httpx.Response, provider: str) -> dict[str, object]:
    if not response.is_success:
        raise ProviderAPIError(provider, response.status_code)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderAPIError(provider, response.status_code) from exc
    if not isinstance(payload, dict):
        raise ProviderAPIError(provider, response.status_code)
    return payload


def validate_model_items(
    payload: dict[str, object], provider: str, field_name: str
) -> list[object]:
    items = payload.get(field_name)
    if not isinstance(items, list):
        raise ProviderAPIError(provider)
    return items


def _safe_request_error(provider: str) -> ProviderAPIError:
    return ProviderAPIError(provider)
