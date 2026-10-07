from typing import Annotated

import jwt
from fastapi import Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ErrorCode, api_error
from app.models import User
from app.security import csrf_tokens_match, decode_access_token

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_current_user(request: Request, db: DbDep, settings: SettingsDep) -> User:
    unauthorized = api_error(
        ErrorCode.NOT_AUTHENTICATED,
        status_code=status.HTTP_401_UNAUTHORIZED,
        message="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

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
            message="Inactive user",
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
            message="CSRF token missing or invalid",
        )


CsrfDep = Annotated[None, Depends(verify_csrf)]
