from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProviderKind(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class AIProvider(Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        UniqueConstraint("scope_key", "kind", "name", name="uq_ai_providers_scope_kind_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[ProviderKind] = mapped_column(
        Enum(
            ProviderKind,
            name="ai_provider_kind",
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
