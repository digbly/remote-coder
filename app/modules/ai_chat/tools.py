import json

from fastapi import HTTPException

from app.modules.ai_chat.commands import RUN_PROJECT_COMMAND
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_providers.base import ProviderTool, ToolCall

MAX_TOOL_RESULT_CHARS = 32_000
MAX_TOOL_CALLS_PER_TURN = 8
MAX_TOOL_ROUNDS_PER_TURN = 4

PROJECT_TOOLS = (
    ProviderTool(
        name="list_project_files",
        description="List files and directories in a project-relative directory.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    ProviderTool(
        name="read_project_file",
        description="Read a UTF-8 text file using a project-relative path.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    ),
    ProviderTool(
        name="propose_file_change",
        description=(
            "Propose replacement content for an existing project file. This only creates a "
            "reviewable diff; it does not modify the file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    ),
    RUN_PROJECT_COMMAND,
)


def execute_project_tool(context: ProjectContext, call: ToolCall) -> str:
    arguments = call.arguments
    if call.name == "propose_file_change":
        if set(arguments) != {"path", "content"}:
            return _encode({"error": "invalid_arguments"})
        path = arguments.get("path")
        content = arguments.get("content")
        if (
            not isinstance(path, str)
            or not path
            or len(path) > 4096
            or not isinstance(content, str)
        ):
            return _encode({"error": "invalid_arguments"})
        try:
            proposal = context.propose_change(path, content)
        except HTTPException as exc:
            detail = exc.detail
            code = detail.get("code") if isinstance(detail, dict) else None
            return _encode({"error": code if isinstance(code, str) else "proposal_failed"})
        return _encode(
            {
                "proposal": {
                    "id": proposal.id,
                    "path": proposal.path,
                    "diff": proposal.diff,
                    "status": proposal.status.value,
                }
            }
        )

    if set(arguments) - {"path"}:
        return _encode({"error": "invalid_arguments"})

    path = arguments.get("path")
    if path is not None and (not isinstance(path, str) or len(path) > 4096):
        return _encode({"error": "invalid_arguments"})

    try:
        if call.name == "list_project_files":
            result = context.list_files(path)
        elif call.name == "read_project_file" and isinstance(path, str) and path:
            result = context.read_file(path)
        else:
            return _encode({"error": "unsupported_tool_or_arguments"})
    except HTTPException as exc:
        detail = exc.detail
        code = detail.get("code") if isinstance(detail, dict) else None
        result = {"error": code if isinstance(code, str) else "context_unavailable"}

    encoded = _encode(result)
    if len(encoded) <= MAX_TOOL_RESULT_CHARS:
        return encoded
    return _encode({"error": "context_result_too_large", "truncated": True})


def _encode(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
