from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentSetting(Base):
    """Per-user launch configuration for a known agent (command + optional args)."""

    __tablename__ = "agent_settings"
    __table_args__ = (UniqueConstraint("user_id", "agent_id", name="uq_agent_settings_user_agent"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(64))
    command: Mapped[str] = mapped_column(String(256))
    args: Mapped[str] = mapped_column(String(1024), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
