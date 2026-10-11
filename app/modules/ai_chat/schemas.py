from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.ai_chat.models import MessageRole, MessageStatus


class CommandPermission(StrEnum):
    MANUAL = "manual"
    RISKY = "risky"
    ALLOW_ALL = "allow_all"


class CommandPermissionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: CommandPermission


class CommandApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class ChatTurnRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)
    provider_id: int = Field(gt=0)
    model_id: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1, max_length=16000)
    edit_user_message_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _require_conversation_for_edit(self) -> "ChatTurnRequest":
        if self.edit_user_message_id is not None and self.conversation_id is None:
            raise ValueError("edit_user_message_id requires conversation_id")
        return self


class ConversationRead(BaseModel):
    id: str
    project_id: int
    provider_id: int | None
    model_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationRead]


class ChatMessageRead(BaseModel):
    id: int
    role: MessageRole
    content: str
    thinking: str
    error: str
    status: MessageStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetail(BaseModel):
    conversation: ConversationRead
    messages: list[ChatMessageRead]
