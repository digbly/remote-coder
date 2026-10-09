from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error, not_authenticated_error
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.security import (
    DUMMY_PASSWORD_HASH,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


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


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _create_refresh_token(db: Session, user_id: int, settings: Settings) -> str:
    raw_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    return raw_token


def _prune_expired_tokens(db: Session, user_id: int) -> None:
    """Drop tokens past their natural expiry; revoked-but-unexpired tokens are
    kept so that reuse of a rotated token can still be detected."""
    db.execute(
        delete(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.expires_at < datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )


def issue_refresh_token(db: Session, user: User, settings: Settings) -> str:
    _prune_expired_tokens(db, user.id)
    raw_token = _create_refresh_token(db, user.id, settings)
    db.commit()
    return raw_token


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    db.commit()


def rotate_refresh_token(
    db: Session, raw_token: str | None, settings: Settings
) -> tuple[User, str]:
    """Validate and rotate a refresh token, returning the user and a new token.

    Reusing an already-rotated token is treated as theft: every active token for
    that user is revoked.
    """
    if not raw_token:
        raise not_authenticated_error()

    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if token is None:
        raise not_authenticated_error()

    now = datetime.now(UTC)
    if token.revoked_at is not None:
        revoke_all_user_tokens(db, token.user_id)
        raise not_authenticated_error()

    if _as_utc(token.expires_at) <= now:
        token.revoked_at = now
        db.commit()
        raise not_authenticated_error()

    user = db.get(User, token.user_id)
    if user is None:
        raise not_authenticated_error()

    if not user.is_active:
        raise api_error(
            ErrorCode.INACTIVE_USER,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    revoked = db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == token.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    if revoked.rowcount == 0:
        revoke_all_user_tokens(db, token.user_id)
        raise not_authenticated_error()

    _prune_expired_tokens(db, user.id)
    new_raw_token = _create_refresh_token(db, user.id, settings)
    db.commit()
    return user, new_raw_token


def revoke_refresh_token(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return

    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        db.commit()


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
