from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserSetting(Base):
    """A single per-user setting stored as a key/value pair.

    Keeping settings generic means new preferences can be added without a
    schema change. It lives in ``core`` because it is shared across feature
    modules rather than owning one.
    """

    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(2048))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


MAX_KEY_LENGTH = 64
MAX_VALUE_LENGTH = 2048


def get_value(db: Session, user_id: int, key: str) -> str | None:
    """Return the stored value for ``key``, or ``None`` when it is unset."""
    setting = db.scalar(
        select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
    )
    return setting.value if setting is not None else None


def set_value(db: Session, user_id: int, key: str, value: str) -> str:
    """Create or update the setting, returning the stored value."""
    if not key or len(key) > MAX_KEY_LENGTH:
        raise ValueError("setting key is invalid")
    if len(value) > MAX_VALUE_LENGTH:
        raise ValueError("setting value is too long")

    setting = db.scalar(
        select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
    )
    if setting is None:
        setting = UserSetting(user_id=user_id, key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    return value


def delete_value(db: Session, user_id: int, key: str) -> None:
    """Remove the setting when present; a no-op otherwise."""
    setting = db.scalar(
        select(UserSetting).where(UserSetting.user_id == user_id, UserSetting.key == key)
    )
    if setting is not None:
        db.delete(setting)
        db.commit()
