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
    ToolCall,
    TurnComplete,
)

MAX_ASSISTANT_OUTPUT_CHARS = 48_000
MAX_TOTAL_TOOL_OUTPUT_CHARS = 64_000
logger = logging.getLogger(__name__)
SYSTEM_INSTRUCTIONS = (
    "You are a code assistant for the selected project. You may only inspect project files "
    "using the provided project tools. You may run commands using run_project_command; "
    "the user may need to approve them. You may create a proposed replacement for an existing "
    "file using propose_file_change; this only creates a reviewable diff and does not change "
    "the file. Never claim to have applied a change. Only claim command execution when the "
    "tool returned a successful exit status. Do not request or use paths outside the project. "
    "Tell the user when a proposal is ready for review."
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
    output_chars = 0
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
        async with httpx.AsyncClient() as client:
            for round_index in range(MAX_TOOL_ROUNDS_PER_TURN):
                round_text: list[str] = []
                tool_calls: list[ToolCall] = []
                completed = False
                async for provider_event in adapter.stream(
                    client,
                    api_key,
                    model_id,
                    SYSTEM_INSTRUCTIONS,
                    messages,
                    PROJECT_TOOLS,
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
                    elif isinstance(provider_event, ToolCall):
                        tool_calls.append(provider_event)
                    elif isinstance(provider_event, TurnComplete):
                        completed = True

                if not completed:
                    raise ProviderAPIError(
                        adapter.kind,
                        diagnostic="Stream ended without a completion event",
                    )
                if not tool_calls:
                    break
                total_tool_calls += len(tool_calls)
                if total_tool_calls > MAX_TOOL_CALLS_PER_TURN:
                    raise ChatTurnLimitError
                if round_index + 1 >= MAX_TOOL_ROUNDS_PER_TURN:
                    raise ChatTurnLimitError

                messages.append(
                    ProviderMessage(
                        role="assistant",
                        content="".join(round_text),
                        tool_calls=tuple(tool_calls),
                    )
                )
                for call in tool_calls:
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
                    if call.name == "propose_file_change":
                        try:
                            proposal_result = json.loads(result)
                        except json.JSONDecodeError:
                            proposal_result = None
                        if isinstance(proposal_result, dict) and isinstance(
                            proposal_result.get("proposal"), dict
                        ):
                            yield _event(
                                {
                                    "type": "proposal",
                                    **proposal_result["proposal"],
                                }
                            )
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
        service.finish_assistant(db, assistant_message, content, MessageStatus.COMPLETED)
        yield _event(
            {
                "type": "complete",
                "conversation_id": conversation_id,
                "assistant_message_id": assistant_message.id,
                "status": MessageStatus.COMPLETED.value,
            }
        )
    except ChatTurnLimitError:
        content = "".join(text_parts)
        service.finish_assistant(db, assistant_message, content, MessageStatus.FAILED)
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
        service.finish_assistant(db, assistant_message, content, MessageStatus.FAILED)
        yield _error_event(ErrorCode.AI_PROVIDER_FAILED, assistant_message.id)
    except asyncio.CancelledError:
        service.finish_assistant(
            db,
            assistant_message,
            "".join(text_parts),
            MessageStatus.INTERRUPTED,
        )
        raise
    except Exception:
        logger.exception(
            "Unexpected AI chat stream failure conversation_id=%s provider=%s",
            conversation_id,
            adapter.kind,
        )
        service.finish_assistant(db, assistant_message, "".join(text_parts), MessageStatus.FAILED)
        raise


def _error_event(code: ErrorCode, message_id: int) -> bytes:
    return _event(
        {
            "type": "error",
            "code": code.value,
            "message": translate(code.value),
            "assistant_message_id": message_id,
        }
    )


def _event(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
