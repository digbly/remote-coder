from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    STALE = "stale"


class ProposalChangeType(StrEnum):
    MODIFY = "modify"
    CREATE = "create"
    DELETE = "delete"
    CREATE_DIRECTORY = "create_directory"
    DELETE_DIRECTORY = "delete_directory"
    MOVE = "move"


class ChangeProposal(Base):
    __tablename__ = "ai_change_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(4096))
    target_path: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    change_type: Mapped[ProposalChangeType] = mapped_column(
        Enum(
            ProposalChangeType,
            name="ai_change_proposal_change_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ProposalChangeType.MODIFY,
    )
    original_hash: Mapped[str] = mapped_column(String(64))
    original_content: Mapped[str] = mapped_column(Text)
    proposed_content: Mapped[str] = mapped_column(Text)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(
            ProposalStatus,
            name="ai_change_proposal_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ProposalStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
