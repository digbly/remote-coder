import json
from pathlib import Path

from fastapi import HTTPException

from app.core.errors import ErrorCode
from app.modules.ai_changes.schemas import ChangeProposalRead
from app.modules.ai_chat import skills
from app.modules.ai_chat.commands import RUN_PROJECT_COMMAND
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_providers.base import ProviderTool, ToolCall

MAX_TOOL_RESULT_CHARS = 32_000
MAX_TOOL_CALLS_PER_TURN = 64
MAX_TOOL_ROUNDS_PER_TURN = 32
MAX_PATH_CHARS = 4096
MAX_SEARCH_QUERY_CHARS = 500
MAX_READ_CHARS = 24_000
MAX_READ_BYTES = 512_000
READ_FILE_NAME = "read_file"

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
        name=READ_FILE_NAME,
        description=(
            "Read a UTF-8 text file. Use a project-relative path for project files "
            "(for example \"src/app.py\"), a path relative to a skills directory for a "
            "skill's supporting files (for example \"my-skill/reference.md\"), or an "
            "absolute path. Absolute paths outside the project and skills directories "
            "require the user's approval."
        ),
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
    if name == "list_project_files":
        try:
            result = context.list_files(path)
        except HTTPException as exc:
            return _error_result(exc)
        return _encode_result(result)
    if name != READ_FILE_NAME:
        return _encode({"error": "unsupported_tool_or_arguments"})
    if not _is_path(path) or Path(path).is_absolute():
        # Absolute paths are handled by the streaming layer so an out-of-roots
        # read can require the user's approval; this entry point never reads them.
        return _encode({"error": "invalid_arguments"})
    return execute_read_file(context, path)


def read_path_needs_approval(context: ProjectContext, path: str) -> bool:
    """Return True when reading ``path`` falls outside the allowed read roots.

    Relative paths always resolve inside the project or the skills directories,
    so only absolute paths can require the user's approval.
    """
    target = Path(path)
    if not target.is_absolute():
        return False
    return _allowed_source(context, target.resolve()) is None


def execute_read_file(context: ProjectContext, path: str) -> str:
    """Read ``path`` after the allowed-roots (and, if needed, approval) check.

    Absolute paths outside the allowed roots are read here only when the caller
    already obtained approval (or the permission mode is allow-all).
    """
    target = Path(path)
    if not target.is_absolute():
        return _read_file(context, path)
    resolved = target.resolve()
    source = _allowed_source(context, resolved) or "external"
    return _read_text_result(resolved, path, source)


def _allowed_source(context: ProjectContext, resolved: Path) -> str | None:
    """Label the allowed root that contains ``resolved`` (``project``/``skill``)."""
    project_path = context.project_path
    if project_path is not None:
        project_skills = skills.project_skills_root(project_path).resolve()
        if resolved.is_relative_to(project_skills):
            return "skill"
        if resolved.is_relative_to(project_path.resolve()):
            return "project"
    if resolved.is_relative_to(skills.skills_root().resolve()):
        return "skill"
    return None


def _read_file(context: ProjectContext, path: str) -> str:
    """Read a project-relative path, falling back to the skills directories."""
    try:
        return _encode_result({**context.read_file(path), "source": "project"})
    except HTTPException as exc:
        if _error_code(exc) != ErrorCode.FILE_NOT_FOUND.value:
            return _error_result(exc)
    try:
        skill_file = skills.read_skill_file(path, context.project_path)
    except HTTPException as exc:
        return _error_result(exc)
    return _encode_result(
        {
            "path": skill_file.path,
            "content": skill_file.content,
            "truncated": skill_file.truncated,
            "source": "skill",
        }
    )


def _read_text_result(target: Path, display: str, source: str) -> str:
    """Read ``target`` (any location) as UTF-8 text with size/binary guards."""
    if not target.is_file():
        return _encode({"error": ErrorCode.FILE_NOT_FOUND.value})
    try:
        if target.stat().st_size > MAX_READ_BYTES:
            return _encode({"error": ErrorCode.FILE_TOO_LARGE.value})
        data = target.read_bytes()
    except OSError:
        return _encode({"error": ErrorCode.FILE_NOT_FOUND.value})

    if len(data) > MAX_READ_BYTES:
        return _encode({"error": ErrorCode.FILE_TOO_LARGE.value})
    if b"\x00" in data:
        return _encode({"error": ErrorCode.FILE_BINARY.value})
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _encode({"error": ErrorCode.FILE_BINARY.value})

    truncated = len(text) > MAX_READ_CHARS
    return _encode_result(
        {
            "path": display,
            "content": text[:MAX_READ_CHARS],
            "truncated": truncated,
            "source": source,
        }
    )


def _is_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= MAX_PATH_CHARS


def _encode_result(result: dict[str, object]) -> str:
    encoded = _encode(result)
    if len(encoded) <= MAX_TOOL_RESULT_CHARS:
        return encoded
    return _encode({"error": "context_result_too_large", "truncated": True})


def _error_result(exc: HTTPException) -> str:
    code = _error_code(exc)
    return _encode({"error": code if code is not None else "proposal_failed"})


def _error_code(exc: HTTPException) -> str | None:
    detail = exc.detail
    code = detail.get("code") if isinstance(detail, dict) else None
    return code if isinstance(code, str) else None


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
