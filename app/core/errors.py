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
    401: "Unauthorized",
    403: "Forbidden",
    422: "Validation error",
    429: "Too many requests",
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
