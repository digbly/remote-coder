import logging
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core import user_settings
from app.core.errors import ErrorCode, api_error
from app.modules.ai_chat.models import ChatMessage, Conversation, MessageRole, MessageStatus
from app.modules.ai_chat.schemas import (
    ChatMessageRead,
    CommandPermission,
    ConversationDetail,
    ConversationRead,
)
from app.modules.ai_providers.base import ChatMessage as ProviderMessage
from app.modules.auth.models import User
from app.modules.projects import service as project_service
from app.modules.projects.models import Project

MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 80_000
MAX_CONVERSATIONS = 100
DEFAULT_TITLE = "New chat"
COMMAND_PERMISSION_KEY = "ai_chat_command_permission"
logger = logging.getLogger(__name__)


def get_command_permission(db: Session, user_id: int) -> CommandPermission:
    value = user_settings.get_value(db, user_id, COMMAND_PERMISSION_KEY)
    try:
        return CommandPermission(value) if value is not None else CommandPermission.MANUAL
    except ValueError as exc:
        logger.error("Invalid saved AI chat command permission for user_id=%s", user_id)
        raise RuntimeError("saved AI chat command permission is invalid") from exc


def set_command_permission(
    db: Session, user_id: int, mode: CommandPermission
) -> CommandPermission:
    user_settings.set_value(db, user_id, COMMAND_PERMISSION_KEY, mode.value)
    return mode


def list_conversations(db: Session, user: User, project_id: int) -> list[ConversationRead]:
    project_service.get_project(db, user, project_id)
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.owner_id == user.id, Conversation.project_id == project_id)
        .order_by(desc(Conversation.updated_at), desc(Conversation.id))
        .limit(MAX_CONVERSATIONS)
    )
    return [ConversationRead.model_validate(item) for item in conversations]


def require_conversation(db: Session, user_id: int, project_id: int, conversation_id: str) -> None:
    _get_conversation(db, user_id, project_id, conversation_id)


def get_conversation_detail(
    db: Session, user: User, project_id: int, conversation_id: str
) -> ConversationDetail:
    project_service.get_project(db, user, project_id)
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.id)
    )
    return ConversationDetail(
        conversation=ConversationRead.model_validate(conversation),
        messages=[ChatMessageRead.model_validate(message) for message in messages],
    )


def prepare_turn(
    db: Session,
    user: User,
    project_id: int,
    conversation_id: str | None,
    provider_id: int,
    model_id: str,
    user_content: str,
) -> tuple[Project, Conversation, ChatMessage, ChatMessage, list[ProviderMessage]]:
    project = project_service.get_project(db, user, project_id)
    if conversation_id is None:
        conversation = Conversation(
            owner_id=user.id,
            project_id=project_id,
            provider_id=provider_id,
            model_id=model_id,
            title=_conversation_title(user_content),
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = _get_conversation(db, user.id, project_id, conversation_id)

    previous = list(
        db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.conversation_id == conversation.id,
                ChatMessage.status == MessageStatus.COMPLETED,
            )
            .order_by(desc(ChatMessage.id))
            .limit(MAX_HISTORY_MESSAGES)
        )
    )
    history: list[ProviderMessage] = []
    history_chars = 0
    for message in reversed(previous):
        if history_chars + len(message.content) > MAX_HISTORY_CHARS:
            break
        role = "user" if message.role is MessageRole.USER else "assistant"
        history.append(ProviderMessage(role=role, content=message.content))
        history_chars += len(message.content)

    conversation.provider_id = provider_id
    conversation.model_id = model_id
    if conversation.title == DEFAULT_TITLE:
        conversation.title = _conversation_title(user_content)
    user_message = ChatMessage(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=user_content,
        status=MessageStatus.COMPLETED,
    )
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="",
        status=MessageStatus.STREAMING,
    )
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(conversation)
    db.refresh(user_message)
    db.refresh(assistant_message)
    return project, conversation, user_message, assistant_message, history


def finish_assistant(
    db: Session,
    assistant_message: ChatMessage,
    content: str,
    status: MessageStatus,
    thinking: str = "",
) -> None:
    assistant_message.content = content
    assistant_message.thinking = thinking
    assistant_message.status = status
    db.commit()


def _get_conversation(
    db: Session, user_id: int, project_id: int, conversation_id: str
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_id == user_id,
            Conversation.project_id == project_id,
        )
    )
    if conversation is None:
        raise api_error(ErrorCode.AI_CHAT_CONVERSATION_NOT_FOUND, status_code=404)
    return conversation


def _conversation_title(content: str) -> str:
    title = " ".join(content.split())
    return title[:197] + "..." if len(title) > 200 else title
