from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class Conversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    model_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, index=True
    )


class ChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="ai_chat_message_role",
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    content: Mapped[str] = mapped_column(Text)
    thinking: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[MessageStatus] = mapped_column(
        Enum(
            MessageStatus,
            name="ai_chat_message_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=MessageStatus.COMPLETED,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
