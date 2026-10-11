from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.agent_sessions.schemas import AgentSessionRead
from app.modules.agents import service as agents_service
from app.modules.agents.sessions import list_sessions as list_cli_sessions
from app.modules.ai_chat import service as chat_service
from app.modules.auth.models import User
from app.modules.git import service as git_service
from app.modules.projects import service as project_service

MAX_SESSIONS = 200


def resolve_directory(
    db: Session, user: User, project_id: int, worktree: str | None, settings: Settings
) -> Path:
    """The project or worktree directory whose sessions should be listed."""
    project = project_service.get_project(db, user, project_id)
    directory = Path(project.path).resolve()
    if worktree:
        resolved = git_service.find_worktree(directory, worktree, settings)
        if resolved is None or not resolved.is_dir():
            raise api_error(ErrorCode.GIT_WORKTREE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)
        directory = resolved.resolve()
    return directory


def list_project_sessions(
    db: Session,
    user: User,
    project_id: int,
    worktree: str | None,
    settings: Settings,
) -> list[AgentSessionRead]:
    """Merge in-app chat conversations and host CLI agent sessions, newest first."""
    directory = resolve_directory(db, user, project_id, worktree, settings)

    sessions: list[AgentSessionRead] = [
        AgentSessionRead(
            source="chat",
            id=conversation.id,
            title=conversation.title,
            updated_at=_as_utc(conversation.updated_at),
        )
        for conversation in chat_service.list_conversations(db, user, project_id)
    ]

    for session in list_cli_sessions(settings, directory):
        sessions.append(
            AgentSessionRead(
                source="cli",
                id=session.id,
                title=session.title,
                agent_id=session.agent_id,
                agent_label=agents_service.agent_label(session.agent_id),
                updated_at=_as_utc(session.updated_at),
            )
        )

    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions[:MAX_SESSIONS]


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC-aware so mixed sources sort and serialize consistently."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
