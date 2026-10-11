"""Agent Skills for chat sessions.

Skills live under ``~/.agents/skills/<slug>/SKILL.md``. Each file starts with a
YAML frontmatter block (``name`` and ``description``) followed by the skill body.
The chat UI lists these slugs as slash commands and the server injects the
selected skill body into the system prompt for that turn.

A skill may span several files: ``SKILL.md`` can reference supporting resources
in the same folder (for example ``reference.md`` or ``examples/``). The project
tools refuse paths outside the project, so the agent reads those extra parts
through the chat ``read_file`` tool, which falls back to this directory
(read-only) via :func:`read_skill_file`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import status

from app.core.errors import ErrorCode, api_error

SKILL_FILE_NAME = "SKILL.md"
SKILLS_PARTS = (".agents", "skills")
MAX_SKILL_FILE_CHARS = 24_000
MAX_SKILL_RESOURCE_CHARS = 24_000
MAX_SKILL_RESOURCE_BYTES = 512_000
MAX_DESCRIPTION_CHARS = 1_000
_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RESERVED_SLUGS = {".", ".."}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Skill:
    """A single discoverable skill (metadata only)."""

    slug: str
    name: str
    description: str


@dataclass(frozen=True)
class SkillFile:
    """A supporting file read from a skill folder (read-only)."""

    path: str
    content: str
    truncated: bool


def skills_root() -> Path:
    """Return the directory that contains skill folders (``~/.agents/skills``)."""
    return Path.home().joinpath(*SKILLS_PARTS)


def list_skills() -> list[Skill]:
    """Return the available skills sorted by slug.

    Missing or unreadable directories are skipped so a bad install never breaks
    the chat. Directories without a readable ``SKILL.md`` are ignored.
    """
    root = skills_root()
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name.lower())
    except OSError:
        return []

    skills: list[Skill] = []
    for entry in entries:
        if not entry.is_dir() or not _is_valid_slug(entry.name):
            continue
        skill = _read_skill(entry)
        if skill is not None:
            skills.append(skill)
    return skills


def load_skill_body(slug: str) -> str | None:
    """Return the skill body (frontmatter stripped) for ``slug``.

    Returns ``None`` when the slug is invalid or the skill is missing, so the
    caller can reject the request instead of silently ignoring the skill.
    """
    if not _is_valid_slug(slug):
        return None
    directory = skills_root() / slug
    text = _read_text(directory / SKILL_FILE_NAME, MAX_SKILL_FILE_CHARS)
    if text is None:
        return None
    _, body = parse_frontmatter(text)
    return body or text


def read_skill_file(path: str) -> SkillFile:
    """Read a supporting file of a skill so the agent can follow multi-part skills.

    ``path`` is raised by the agent and is relative to the skills root
    (``~/.agents/skills``), for example ``my-skill/reference.md``. Paths that
    escape the skills root, binary files, and oversized files are rejected so the
    tool can never read arbitrary files from the operator's home directory.
    """
    root = skills_root().resolve()
    target = _resolve_within_skills_root(root, path)
    if not target.is_file():
        raise api_error(ErrorCode.FILE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    try:
        if target.stat().st_size > MAX_SKILL_RESOURCE_BYTES:
            raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)
        data = target.read_bytes()
    except OSError as exc:
        raise api_error(ErrorCode.FILE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND) from exc

    if len(data) > MAX_SKILL_RESOURCE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)
    if b"\x00" in data:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST) from exc

    return SkillFile(
        path=target.relative_to(root).as_posix(),
        content=text[:MAX_SKILL_RESOURCE_CHARS],
        truncated=len(text) > MAX_SKILL_RESOURCE_CHARS,
    )


def _resolve_within_skills_root(root: Path, path: str) -> Path:
    """Resolve a skills-root-relative path, rejecting anything that escapes it.

    ``root`` must already be resolved so the returned target can be made relative
    to it again (a symlinked home would otherwise break ``relative_to``).
    """
    candidate = path.strip()
    parts = PurePosixPath(candidate).parts
    if not candidate or candidate.startswith(("/", "~", "-")) or ".." in parts:
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    target = (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    return target


def _read_skill(directory: Path) -> Skill | None:
    text = _read_text(directory / SKILL_FILE_NAME, MAX_SKILL_FILE_CHARS)
    if text is None:
        return None
    meta, _ = parse_frontmatter(text)
    name = meta.get("name") or directory.name
    description = meta.get("description", "")[:MAX_DESCRIPTION_CHARS]
    return Skill(slug=directory.name, name=name, description=description)


def _is_valid_slug(slug: str) -> bool:
    return slug not in _RESERVED_SLUGS and bool(_SLUG_PATTERN.match(slug))


def _read_text(path: Path, limit: int) -> str | None:
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit).strip()
    except OSError:
        logger.warning("Could not read skill file at %s", path)
        return None


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a ``SKILL.md`` document into its frontmatter map and body.

    Implements just enough YAML for skill frontmatter: top-level ``key: value``
    pairs where values may be wrapped onto following indented lines (folded into
    a single space). Documents without a leading ``---`` block have no metadata.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, text
    end = next(
        (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
        None,
    )
    if end is None:
        return {}, text

    meta: dict[str, str] = {}
    key: str | None = None
    buffer: list[str] = []
    for raw in lines[1:end]:
        if raw[:1] in (" ", "\t") or ":" not in raw:
            if key is not None:
                buffer.append(raw.strip())
            continue
        if key is not None:
            meta[key] = _fold(buffer)
        key, _, value = raw.partition(":")
        key = key.strip()
        buffer = [value.strip()]
    if key is not None:
        meta[key] = _fold(buffer)

    body = "\n".join(lines[end + 1 :]).strip()
    return meta, body


def _fold(parts: list[str]) -> str:
    text = " ".join(part for part in parts if part)
    return text.strip().strip("\"'")
