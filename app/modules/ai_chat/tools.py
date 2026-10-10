import json

from fastapi import HTTPException

from app.modules.ai_changes.schemas import ChangeProposalRead
from app.modules.ai_chat.commands import RUN_PROJECT_COMMAND
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_providers.base import ProviderTool, ToolCall

MAX_TOOL_RESULT_CHARS = 32_000
MAX_TOOL_CALLS_PER_TURN = 16
MAX_TOOL_ROUNDS_PER_TURN = 8
MAX_PATH_CHARS = 4096
MAX_SEARCH_QUERY_CHARS = 500

_PATH_ARGUMENTS = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,
}
_PATH_AND_CONTENT_ARGUMENTS = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}

PROJECT_TOOLS = (
    ProviderTool(
        name="list_project_files",
        description=(
            "List files and directories under a project-relative directory (recursively, "
            "one call returns the whole subtree). Call this at most once before reading files."
        ),
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
    ),
    ProviderTool(
        name="read_project_file",
        description="Read a UTF-8 text file using a project-relative path.",
        parameters=_PATH_ARGUMENTS,
    ),
    ProviderTool(
        name="search_project_files",
        description="Search file contents for a text pattern across the project.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "include": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    ProviderTool(
        name="propose_file_change",
        description=(
            "Propose replacement content for an existing project file. This creates a reviewable "
            "diff; use create_project_file for new files."
        ),
        parameters=_PATH_AND_CONTENT_ARGUMENTS,
    ),
    ProviderTool(
        name="create_project_file",
        description=(
            "Propose a new file that does not exist yet. Fails if a file already exists "
            "at the path."
        ),
        parameters=_PATH_AND_CONTENT_ARGUMENTS,
    ),
    ProviderTool(
        name="delete_project_file",
        description="Propose deleting an existing project file.",
        parameters=_PATH_ARGUMENTS,
    ),
    ProviderTool(
        name="create_project_directory",
        description="Propose creating an empty project directory.",
        parameters=_PATH_ARGUMENTS,
    ),
    ProviderTool(
        name="delete_project_directory",
        description="Propose deleting a project directory and everything inside it.",
        parameters=_PATH_ARGUMENTS,
    ),
    ProviderTool(
        name="move_project_entry",
        description="Propose moving or renaming a project file or directory to a new path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "target_path": {"type": "string"},
            },
            "required": ["path", "target_path"],
            "additionalProperties": False,
        },
    ),
    RUN_PROJECT_COMMAND,
)

_PROPOSAL_ACTIONS = {
    "delete_project_file": "delete_file",
    "create_project_directory": "create_directory",
    "delete_project_directory": "delete_directory",
}


def execute_project_tool(context: ProjectContext, call: ToolCall) -> str:
    name = call.name
    arguments = call.arguments

    if name in {"propose_file_change", "create_project_file"}:
        return _propose_path_and_content(context, name, arguments)
    if name in _PROPOSAL_ACTIONS:
        return _propose_path(context, arguments, _PROPOSAL_ACTIONS[name])
    if name == "move_project_entry":
        return _propose_move(context, arguments)
    if name == "search_project_files":
        return _search(context, arguments)
    return _read(context, name, arguments)


def _propose_path_and_content(
    context: ProjectContext, name: str, arguments: dict[str, object]
) -> str:
    if set(arguments) != {"path", "content"}:
        return _encode({"error": "invalid_arguments"})
    path = arguments.get("path")
    content = arguments.get("content")
    if not _is_path(path) or not isinstance(content, str):
        return _encode({"error": "invalid_arguments"})
    try:
        proposal = (
            context.create_new_file(path, content)
            if name == "create_project_file"
            else context.propose_change(path, content)
        )
    except HTTPException as exc:
        return _error_result(exc)
    return _proposal_result(proposal)


def _propose_path(context: ProjectContext, arguments: dict[str, object], action: str) -> str:
    if set(arguments) != {"path"}:
        return _encode({"error": "invalid_arguments"})
    path = arguments.get("path")
    if not _is_path(path):
        return _encode({"error": "invalid_arguments"})
    try:
        proposal = getattr(context, action)(path)
    except HTTPException as exc:
        return _error_result(exc)
    return _proposal_result(proposal)


def _propose_move(context: ProjectContext, arguments: dict[str, object]) -> str:
    if set(arguments) != {"path", "target_path"}:
        return _encode({"error": "invalid_arguments"})
    path = arguments.get("path")
    target_path = arguments.get("target_path")
    if not _is_path(path) or not _is_path(target_path):
        return _encode({"error": "invalid_arguments"})
    try:
        proposal = context.move_entry(path, target_path)
    except HTTPException as exc:
        return _error_result(exc)
    return _proposal_result(proposal)


def _search(context: ProjectContext, arguments: dict[str, object]) -> str:
    if set(arguments) - {"query", "include"}:
        return _encode({"error": "invalid_arguments"})
    query = arguments.get("query")
    include = arguments.get("include")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_SEARCH_QUERY_CHARS:
        return _encode({"error": "invalid_arguments"})
    if include is not None and not isinstance(include, str):
        return _encode({"error": "invalid_arguments"})
    try:
        result = context.search_files(query, include)
    except HTTPException as exc:
        return _error_result(exc)
    return _encode_result(result)


def _read(context: ProjectContext, name: str, arguments: dict[str, object]) -> str:
    if set(arguments) - {"path"}:
        return _encode({"error": "invalid_arguments"})
    path = arguments.get("path")
    if path is not None and (not isinstance(path, str) or len(path) > MAX_PATH_CHARS):
        return _encode({"error": "invalid_arguments"})
    try:
        if name == "list_project_files":
            result = context.list_files(path)
        elif name == "read_project_file" and isinstance(path, str) and path:
            result = context.read_file(path)
        else:
            return _encode({"error": "unsupported_tool_or_arguments"})
    except HTTPException as exc:
        return _error_result(exc)
    return _encode_result(result)


def _is_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= MAX_PATH_CHARS


def _encode_result(result: dict[str, object]) -> str:
    encoded = _encode(result)
    if len(encoded) <= MAX_TOOL_RESULT_CHARS:
        return encoded
    return _encode({"error": "context_result_too_large", "truncated": True})


def _error_result(exc: HTTPException) -> str:
    detail = exc.detail
    code = detail.get("code") if isinstance(detail, dict) else None
    return _encode({"error": code if isinstance(code, str) else "proposal_failed"})


def _proposal_result(proposal: ChangeProposalRead) -> str:
    return _encode(
        {
            "proposal": {
                "id": proposal.id,
                "path": proposal.path,
                "target_path": proposal.target_path,
                "change_type": proposal.change_type.value,
                "diff": proposal.diff,
                "status": proposal.status.value,
            }
        }
    )


def _encode(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
