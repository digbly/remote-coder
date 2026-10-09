from typing import Annotated

import jwt
from fastapi import Depends, Request, status
from sqlalchemy import select

from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, not_authenticated_error
from app.modules.auth.models import User
from app.modules.auth.security import csrf_tokens_match, decode_access_token

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_current_user(request: Request, db: DbDep, settings: SettingsDep) -> User:
    unauthorized = not_authenticated_error()

    token = request.cookies.get(settings.access_token_cookie_name)
    if not token:
        raise unauthorized

    try:
        payload = decode_access_token(token, settings)
    except jwt.PyJWTError as exc:
        raise unauthorized from exc

    username = payload.get("sub")
    if not username:
        raise unauthorized

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise unauthorized

    if not user.is_active:
        raise api_error(
            ErrorCode.INACTIVE_USER,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def verify_csrf(request: Request, settings: SettingsDep) -> None:
    if request.method in _SAFE_METHODS:
        return

    submitted = request.headers.get(settings.csrf_header_name)
    expected = request.cookies.get(settings.csrf_cookie_name)
    if not csrf_tokens_match(submitted, expected):
        raise api_error(
            ErrorCode.CSRF_INVALID,
            status_code=status.HTTP_403_FORBIDDEN,
        )


CsrfDep = Annotated[None, Depends(verify_csrf)]
