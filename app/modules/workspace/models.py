from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    """Per-user workspace document (tabs, active project, layout) for sync.

    The whole editor state is stored as a single JSON document so any client of
    the same user can attach to the exact same view. It is intentionally opaque
    to the backend; the frontend owns the shape.
    """

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
