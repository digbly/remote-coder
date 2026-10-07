from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProjectSource(StrEnum):
    LOCAL = "local"
    GITHUB = "github"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_projects_owner_name"),
        UniqueConstraint("owner_id", "path", name="uq_projects_owner_path"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    source: Mapped[ProjectSource] = mapped_column(
        Enum(
            ProjectSource,
            name="project_source",
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    remote_url: Mapped[str | None] = mapped_column(String(500), default=None)
    path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
