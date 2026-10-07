from enum import StrEnum

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    """Stable, machine-readable error identifiers.

    Clients translate these codes into the active UI language; the
    accompanying ``message`` is an English fallback for humans and for
    clients that do not recognize the code.
    """

    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INACTIVE_USER = "INACTIVE_USER"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    CSRF_INVALID = "CSRF_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


def api_error(
    code: ErrorCode,
    *,
    message: str,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code.value, "message": message},
        headers=headers,
    )


async def validation_exception_handler(
    _request: Request, _exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Invalid request",
            }
        },
    )
