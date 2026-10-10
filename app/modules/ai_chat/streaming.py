import asyncio
import json
import logging
from collections.abc import AsyncIterator

import httpx
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.i18n import translate
from app.modules.ai_chat import approvals, service
from app.modules.ai_chat.commands import (
    RUN_PROJECT_COMMAND_NAME,
    command_from_call,
    command_needs_approval,
    execute_project_command,
)
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_chat.models import ChatMessage, MessageStatus
from app.modules.ai_chat.schemas import CommandPermission
from app.modules.ai_chat.tools import (
    MAX_TOOL_CALLS_PER_TURN,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOOL_ROUNDS_PER_TURN,
    PROJECT_TOOLS,
    execute_project_tool,
)
from app.modules.ai_providers.base import (
    ChatMessage as ProviderMessage,
)
from app.modules.ai_providers.base import (
    ProviderAdapter,
    ProviderAPIError,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    ToolCall,
    TurnComplete,
)

MAX_ASSISTANT_OUTPUT_CHARS = 48_000
MAX_THINKING_OUTPUT_CHARS = 48_000
MAX_TOTAL_TOOL_OUTPUT_CHARS = 64_000
logger = logging.getLogger(__name__)
SYSTEM_INSTRUCTIONS = (
    "You are a code assistant for the selected project. Inspect files with the provided "
    "project tools. File and directory changes use propose_file_change (edit an existing file), "
    "create_project_file (new file), delete_project_file, create_project_directory, "
    "delete_project_directory, and move_project_entry; each returns a reviewable change that "
    "may be applied immediately or await the user's approval. Never claim a change, command, "
    "or proposal outcome that the tool result did not report. You may run commands using "
    "run_project_command; the user may need to approve them. Do not use paths outside the "
    "project."
)
FINAL_ANSWER_INSTRUCTION = (
    "Tool use is now disabled for this turn. Provide your best final answer to the user's "
    "request using only the information already gathered. Do not request any further tools."
)


class ChatTurnLimitError(Exception):
    pass


async def stream_chat_turn(
    db: Session,
    adapter: ProviderAdapter,
    api_key: str,
    model_id: str,
    context: ProjectContext,
    conversation_id: str,
    conversation_title: str,
    user_message_id: int,
    user_content: str,
    assistant_message: ChatMessage,
    history: list[ProviderMessage],
    permission: CommandPermission = CommandPermission.MANUAL,
) -> AsyncIterator[bytes]:
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    output_chars = 0
    thinking_chars = 0
    messages = [*history, ProviderMessage(role="user", content=user_content)]
    try:
        yield _event(
            {
                "type": "message_start",
                "conversation": {
                    "id": conversation_id,
                    "title": conversation_title,
                },
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message.id,
            }
        )
        total_tool_calls = 0
        total_tool_output = 0
        proposal_emitted = False
        async with httpx.AsyncClient() as client:
            for round_index in range(MAX_TOOL_ROUNDS_PER_TURN):
                final_round = round_index + 1 >= MAX_TOOL_ROUNDS_PER_TURN
                round_tools = () if final_round else PROJECT_TOOLS
                round_system = (
                    f"{SYSTEM_INSTRUCTIONS}\n\n{FINAL_ANSWER_INSTRUCTION}"
                    if final_round
                    else SYSTEM_INSTRUCTIONS
                )
                if final_round:
                    yield _notice_event(ErrorCode.AI_CHAT_TOOL_LIMIT_REACHED)
                round_text: list[str] = []
                round_thinking: list[str] = []
                round_thinking_signature: str | None = None
                round_redacted_thinking: str | None = None
                tool_calls: list[ToolCall] = []
                completed = False
                async for provider_event in adapter.stream(
                    client,
                    api_key,
                    model_id,
                    round_system,
                    messages,
                    round_tools,
                ):
                    if isinstance(provider_event, TextDelta):
                        if not provider_event.text:
                            continue
                        if output_chars + len(provider_event.text) > MAX_ASSISTANT_OUTPUT_CHARS:
                            raise ChatTurnLimitError
                        text_parts.append(provider_event.text)
                        round_text.append(provider_event.text)
                        output_chars += len(provider_event.text)
                        yield _event({"type": "text_delta", "text": provider_event.text})
                    elif isinstance(provider_event, ThinkingDelta):
                        if not provider_event.text:
                            continue
                        if thinking_chars + len(provider_event.text) > MAX_THINKING_OUTPUT_CHARS:
                            raise ChatTurnLimitError
                        thinking_parts.append(provider_event.text)
                        round_thinking.append(provider_event.text)
                        thinking_chars += len(provider_event.text)
                        yield _event({"type": "thinking_delta", "text": provider_event.text})
                    elif isinstance(provider_event, ThinkingComplete):
                        round_thinking_signature = provider_event.signature
                        round_redacted_thinking = provider_event.redacted
                    elif isinstance(provider_event, ToolCall):
                        tool_calls.append(provider_event)
                    elif isinstance(provider_event, TurnComplete):
                        completed = True

                if not completed:
                    raise ProviderAPIError(
                        adapter.kind,
                        diagnostic="Stream ended without a completion event",
                    )
                if not tool_calls or final_round:
                    break
                total_tool_calls += len(tool_calls)
                if total_tool_calls > MAX_TOOL_CALLS_PER_TURN:
                    raise ChatTurnLimitError

                messages.append(
                    ProviderMessage(
                        role="assistant",
                        content="".join(round_text),
                        tool_calls=tuple(tool_calls),
                        thinking=(
                            "".join(round_thinking)
                            if round_thinking or round_thinking_signature is not None
                            else None
                        ),
                        thinking_signature=round_thinking_signature,
                        redacted_thinking=round_redacted_thinking,
                    )
                )
                for call in tool_calls:
                    yield _tool_call_event(call)
                    command = command_from_call(call)
                    if call.name == RUN_PROJECT_COMMAND_NAME:
                        if command is None or context.project_path is None:
                            result = json.dumps({"error": "invalid_command_arguments"})
                        else:
                            result = ""
                            if command_needs_approval(command, permission):
                                try:
                                    pending = approvals.create_approval(
                                        context.user.id, context.project_id, command
                                    )
                                except approvals.ApprovalCapacityError:
                                    result = json.dumps({"error": "approval_capacity_reached"})
                                    pending = None
                                if pending is not None:
                                    try:
                                        yield _event(
                                            {
                                                "type": "command_approval",
                                                "approval_id": pending.approval_id,
                                                "command": command,
                                                "reason": (
                                                    "manual_permission"
                                                    if permission is CommandPermission.MANUAL
                                                    else "command_may_change_state"
                                                ),
                                            }
                                        )
                                        try:
                                            approved = await approvals.wait_for_decision(pending)
                                        except TimeoutError:
                                            result = json.dumps({"error": "approval_timed_out"})
                                            approved = False
                                            yield _event(
                                                {
                                                    "type": "command_approval_expired",
                                                    "approval_id": pending.approval_id,
                                                }
                                            )
                                        if not approved and not result:
                                            result = json.dumps({"error": "command_cancelled"})
                                    finally:
                                        approvals.discard_approval(pending)
                            if not result:
                                result = await execute_project_command(
                                    context.project_path, command
                                )
                    else:
                        result = execute_project_tool(context, call)
                    proposal_payload = _proposal_payload(result)
                    if proposal_payload is not None:
                        proposal_emitted = True
                        yield _event({"type": "proposal", **proposal_payload})
                    total_tool_output += len(result)
                    if (
                        len(result) > MAX_TOOL_RESULT_CHARS
                        or total_tool_output > MAX_TOTAL_TOOL_OUTPUT_CHARS
                    ):
                        raise ChatTurnLimitError
                    messages.append(
                        ProviderMessage(
                            role="tool",
                            content=result,
                            tool_call_id=call.id,
                            tool_name=call.name,
                        )
                    )

        content = "".join(text_parts)
        if not content.strip() and not proposal_emitted:
            logger.warning(
                "AI chat produced an empty response conversation_id=%s provider=%s",
                conversation_id,
                adapter.kind,
            )
            service.finish_assistant(
                db,
                assistant_message,
                "",
                MessageStatus.FAILED,
                thinking="".join(thinking_parts),
            )
            yield _error_event(ErrorCode.AI_CHAT_EMPTY_RESPONSE, assistant_message.id)
            return
        service.finish_assistant(
            db,
            assistant_message,
            content,
            MessageStatus.COMPLETED,
            thinking="".join(thinking_parts),
        )
        yield _event(
            {
                "type": "complete",
                "conversation_id": conversation_id,
                "assistant_message_id": assistant_message.id,
                "status": MessageStatus.COMPLETED.value,
            }
        )
    except ChatTurnLimitError:
        logger.warning(
            "AI chat turn limit exceeded conversation_id=%s provider=%s output_chars=%s "
            "thinking_chars=%s",
            conversation_id,
            adapter.kind,
            output_chars,
            thinking_chars,
        )
        content = "".join(text_parts)
        service.finish_assistant(
            db,
            assistant_message,
            content,
            MessageStatus.FAILED,
            thinking="".join(thinking_parts),
        )
        yield _error_event(ErrorCode.AI_CHAT_LIMIT_EXCEEDED, assistant_message.id)
    except ProviderAPIError as exc:
        logger.warning(
            "AI chat provider request failed conversation_id=%s provider=%s status=%s detail=%s",
            conversation_id,
            adapter.kind,
            exc.status_code,
            exc.diagnostic or str(exc),
        )
        content = "".join(text_parts)
        service.finish_assistant(
            db,
            assistant_message,
            content,
            MessageStatus.FAILED,
            thinking="".join(thinking_parts),
        )
        yield _error_event(
            ErrorCode.AI_PROVIDER_FAILED,
            assistant_message.id,
            detail=exc.diagnostic or str(exc),
        )
    except asyncio.CancelledError:
        service.finish_assistant(
            db,
            assistant_message,
            "".join(text_parts),
            MessageStatus.INTERRUPTED,
            thinking="".join(thinking_parts),
        )
        raise
    except Exception:
        logger.exception(
            "Unexpected AI chat stream failure conversation_id=%s provider=%s",
            conversation_id,
            adapter.kind,
        )
        service.finish_assistant(
            db,
            assistant_message,
            "".join(text_parts),
            MessageStatus.FAILED,
            thinking="".join(thinking_parts),
        )
        raise


def _error_event(code: ErrorCode, message_id: int, detail: str | None = None) -> bytes:
    return _event(
        {
            "type": "error",
            "code": code.value,
            "message": detail or translate(code.value),
            "assistant_message_id": message_id,
        }
    )


def _notice_event(code: ErrorCode) -> bytes:
    return _event(
        {
            "type": "notice",
            "code": code.value,
            "message": translate(code.value),
        }
    )


def _tool_call_event(call: ToolCall) -> bytes:
    payload: dict[str, object] = {"type": "tool_call", "name": call.name}
    path = call.arguments.get("path")
    if isinstance(path, str):
        payload["path"] = path
    return _event(payload)


def _proposal_payload(result: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("proposal"), dict):
        return parsed["proposal"]
    return None


def _event(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
