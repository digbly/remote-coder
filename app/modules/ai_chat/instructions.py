"""User and project agent instructions (``AGENTS.md``) for chat sessions.

The project tools refuse paths outside the project, so the agent cannot read the
user-level file itself. The server therefore loads both files and injects them
into the system prompt when a chat turn starts.
"""

from __future__ import annotations

import logging
from pathlib import Path

MAX_INSTRUCTIONS_CHARS = 24_000
MAX_INSTRUCTIONS_FILE_CHARS = 16_000
PROJECT_INSTRUCTIONS_NAME = "AGENTS.md"
USER_INSTRUCTIONS_PARTS = (".config", "agents", PROJECT_INSTRUCTIONS_NAME)
# Only these display labels reach the provider: absolute server paths would leak
# the operator's home directory and worktree layout to a third-party AI vendor.
USER_INSTRUCTIONS_LABEL = "~/.config/agents/" + PROJECT_INSTRUCTIONS_NAME

logger = logging.getLogger(__name__)


def user_instructions_path() -> Path:
    """Return the user-level instructions path (``~/.config/agents/AGENTS.md``)."""
    return Path.home().joinpath(*USER_INSTRUCTIONS_PARTS)


def load_agent_instructions(project_path: Path | None) -> str:
    """Return the user and project instructions formatted for the system prompt.

    Missing or unreadable files are skipped. Each file is read up to
    ``MAX_INSTRUCTIONS_FILE_CHARS`` and the combined result is capped at
    ``MAX_INSTRUCTIONS_CHARS`` so large files cannot crowd out the conversation.
    """
    sources = [("User", user_instructions_path(), USER_INSTRUCTIONS_LABEL)]
    if project_path is not None:
        sources.append(
            ("Project", project_path / PROJECT_INSTRUCTIONS_NAME, PROJECT_INSTRUCTIONS_NAME)
        )

    sections: list[str] = []
    for label, path, display in sources:
        content = _read_optional(path, MAX_INSTRUCTIONS_FILE_CHARS)
        if content:
            sections.append(f"# {label} instructions ({display})\n\n{content}")
    return "\n\n".join(sections)[:MAX_INSTRUCTIONS_CHARS]


def _read_optional(path: Path, limit: int) -> str:
    try:
        if not path.is_file():
            return ""
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit).strip()
    except OSError:
        logger.warning("Could not read agent instructions at %s", path)
        return ""
