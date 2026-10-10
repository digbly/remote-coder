from enum import StrEnum

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.i18n import translate


class ErrorCode(StrEnum):
    """Stable, machine-readable error identifiers.

    Clients translate these codes into the active UI language; the
    accompanying ``message`` is localized from ``Accept-Language`` (falling
    back to English) for humans and for clients that do not recognize the code.
    """

    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INACTIVE_USER = "INACTIVE_USER"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    CSRF_INVALID = "CSRF_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    INVALID_GITHUB_URL = "INVALID_GITHUB_URL"
    PROJECT_PATH_INVALID = "PROJECT_PATH_INVALID"
    PROJECT_PATH_EXISTS = "PROJECT_PATH_EXISTS"
    PROJECT_NAME_EXISTS = "PROJECT_NAME_EXISTS"
    PROJECT_CLONE_FAILED = "PROJECT_CLONE_FAILED"
    FILE_PATH_INVALID = "FILE_PATH_INVALID"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_BINARY = "FILE_BINARY"
    FILE_WRITE_FAILED = "FILE_WRITE_FAILED"
    SEARCH_QUERY_INVALID = "SEARCH_QUERY_INVALID"
    GIT_NOT_A_REPOSITORY = "GIT_NOT_A_REPOSITORY"
    GIT_COMMAND_FAILED = "GIT_COMMAND_FAILED"
    GIT_INVALID_PATH = "GIT_INVALID_PATH"
    GIT_NOTHING_TO_COMMIT = "GIT_NOTHING_TO_COMMIT"
    GIT_REMOTE_MISSING = "GIT_REMOTE_MISSING"
    GIT_BRANCH_INVALID = "GIT_BRANCH_INVALID"
    GIT_PUSH_FAILED = "GIT_PUSH_FAILED"
    GIT_PULL_REQUEST_FAILED = "GIT_PULL_REQUEST_FAILED"
    GIT_DISCARD_FAILED = "GIT_DISCARD_FAILED"
    GIT_PULL_FAILED = "GIT_PULL_FAILED"
    GIT_NO_UPSTREAM = "GIT_NO_UPSTREAM"
    GIT_WORKTREE_INVALID = "GIT_WORKTREE_INVALID"
    GIT_WORKTREE_EXISTS = "GIT_WORKTREE_EXISTS"
    GIT_WORKTREE_FAILED = "GIT_WORKTREE_FAILED"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_NOT_CONFIGURED = "AGENT_NOT_CONFIGURED"
    AGENT_UNSUPPORTED = "AGENT_UNSUPPORTED"
    AGENT_GENERATE_FAILED = "AGENT_GENERATE_FAILED"
    AI_PROVIDER_NOT_FOUND = "AI_PROVIDER_NOT_FOUND"
    AI_PROVIDER_ADMIN_REQUIRED = "AI_PROVIDER_ADMIN_REQUIRED"
    AI_PROVIDER_NAME_EXISTS = "AI_PROVIDER_NAME_EXISTS"
    AI_PROVIDER_FAILED = "AI_PROVIDER_FAILED"
    AI_CREDENTIAL_ENCRYPTION_UNAVAILABLE = "AI_CREDENTIAL_ENCRYPTION_UNAVAILABLE"
    AI_CHAT_CONVERSATION_NOT_FOUND = "AI_CHAT_CONVERSATION_NOT_FOUND"
    AI_CHAT_MODEL_UNAVAILABLE = "AI_CHAT_MODEL_UNAVAILABLE"
    AI_CHAT_LIMIT_EXCEEDED = "AI_CHAT_LIMIT_EXCEEDED"
    AI_CHAT_TOOL_LIMIT_REACHED = "AI_CHAT_TOOL_LIMIT_REACHED"
    AI_COMMAND_APPROVAL_NOT_FOUND = "AI_COMMAND_APPROVAL_NOT_FOUND"
    AI_CHANGE_PROPOSAL_NOT_FOUND = "AI_CHANGE_PROPOSAL_NOT_FOUND"
    AI_CHANGE_PROPOSAL_NOT_PENDING = "AI_CHANGE_PROPOSAL_NOT_PENDING"
    AI_CHANGE_PROPOSAL_STALE = "AI_CHANGE_PROPOSAL_STALE"
    VSCODE_DISABLED = "VSCODE_DISABLED"
    VSCODE_WORKTREE_NOT_FOUND = "VSCODE_WORKTREE_NOT_FOUND"
    VSCODE_START_FAILED = "VSCODE_START_FAILED"
    VSCODE_PROXY_FAILED = "VSCODE_PROXY_FAILED"
    VSCODE_FORBIDDEN = "VSCODE_FORBIDDEN"


class FieldError(BaseModel):
    field: str
    type: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    errors: list[FieldError] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: ErrorDetail


_RESPONSE_DESCRIPTIONS = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    502: "Bad gateway",
    503: "Service unavailable",
    422: "Validation error",
    429: "Too many requests",
    500: "Internal server error",
}


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {
        code: {"model": ErrorResponse, "description": _RESPONSE_DESCRIPTIONS[code]}
        for code in status_codes
    }


def api_error(
    code: ErrorCode,
    *,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": translate(code.value)},
        headers=headers,
    )


def not_authenticated_error() -> HTTPException:
    return api_error(
        ErrorCode.NOT_AUTHENTICATED,
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    return [
        {
            "field": ".".join(str(loc) for loc in error.get("loc", ()) if loc != "body"),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": translate(ErrorCode.VALIDATION_ERROR.value),
                "errors": _field_errors(exc),
            }
        },
    )
