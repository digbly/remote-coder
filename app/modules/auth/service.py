from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.auth.models import User
from app.modules.auth.security import DUMMY_PASSWORD_HASH, hash_password, verify_password


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    hashed_password = user.hashed_password if user else DUMMY_PASSWORD_HASH
    password_matches = verify_password(password, hashed_password)

    if user is None or not password_matches:
        raise api_error(
            ErrorCode.INVALID_CREDENTIALS,
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise api_error(
            ErrorCode.INACTIVE_USER,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    return user


def ensure_admin_user(db: Session, settings: Settings) -> None:
    exists = db.scalar(select(User).where(User.username == settings.admin_username))
    if exists is not None:
        return

    db.add(
        User(
            username=settings.admin_username,
            hashed_password=hash_password(settings.admin_password),
        )
    )
    db.commit()
