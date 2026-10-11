from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

DEFAULT_SESSION_LIMIT = 100
MAX_SESSION_LIMIT = 500
MAX_TITLE_LENGTH = 200
UNTITLED_SESSION = "Untitled session"


@dataclass(frozen=True, slots=True)
class AgentSession:
    """A single resumable session recorded by a CLI agent on the host."""

    agent_id: str
    id: str
    title: str
    directory: str
    updated_at: datetime


class AgentSessionSource(Protocol):
    """Reads the sessions one agent has recorded for a project directory."""

    agent_id: str

    def list_sessions(self, directory: Path, limit: int) -> list[AgentSession]: ...


class OpencodeSessionSource:
    """Reads OpenCode sessions from its local SQLite database, read-only.

    OpenCode records each session's launch directory, so sessions are matched
    to a project/worktree by directory rather than by transcript files.
    """

    agent_id = "opencode"

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    @property
    def database_path(self) -> Path:
        return self._data_dir / "opencode.db"

    def list_sessions(self, directory: Path, limit: int) -> list[AgentSession]:
        db_path = self.database_path
        if limit <= 0 or not db_path.is_file():
            return []
        try:
            connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
        except (sqlite3.Error, ValueError):
            return []
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, title, directory, time_updated FROM session "
                "WHERE rtrim(directory, '/') = ? AND time_archived IS NULL "
                "ORDER BY time_updated DESC LIMIT ?",
                (_normalize_directory(directory), limit),
            ).fetchall()
        except sqlite3.Error:
            return []
        finally:
            connection.close()
        return [_row_to_session(self.agent_id, row) for row in rows]


def opencode_data_dir(settings: Settings) -> Path:
    """Resolve OpenCode's data directory as an absolute path."""
    configured = settings.opencode_data_dir.strip()
    if configured:
        return Path(configured).expanduser().resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return (base / "opencode").resolve()


def build_session_sources(settings: Settings) -> list[AgentSessionSource]:
    """The session sources the server can read, keyed by agent id.

    Only agents with a known, stable on-disk format are listed; adding another
    agent means appending its source here.
    """
    return [OpencodeSessionSource(opencode_data_dir(settings))]


def list_sessions(
    settings: Settings, directory: Path, limit: int = DEFAULT_SESSION_LIMIT
) -> list[AgentSession]:
    """Every recorded session whose directory matches ``directory``, newest first."""
    bounded = max(1, min(limit, MAX_SESSION_LIMIT))
    sessions: list[AgentSession] = []
    for source in build_session_sources(settings):
        sessions.extend(source.list_sessions(directory, bounded))
    sessions.sort(key=lambda session: session.updated_at, reverse=True)
    return sessions[:bounded]


def _normalize_directory(directory: Path) -> str:
    text = str(directory)
    if len(text) > 1 and text.endswith("/"):
        return text[:-1]
    return text


def _row_to_session(agent_id: str, row: sqlite3.Row) -> AgentSession:
    title = str(row["title"] or "").strip() or UNTITLED_SESSION
    return AgentSession(
        agent_id=agent_id,
        id=str(row["id"]),
        title=title[:MAX_TITLE_LENGTH],
        directory=str(row["directory"] or ""),
        updated_at=_from_millis(row["time_updated"]),
    )


def _from_millis(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(UTC)
