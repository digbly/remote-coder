import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.auth.models import User
from app.modules.projects.models import Project, ProjectSource
from app.modules.projects.schemas import (
    DirectoryEntry,
    DirectoryListing,
    FileContentRead,
    FileNode,
    FileSearchRead,
    FileTreeRead,
    GithubProjectCreate,
    LocalProjectCreate,
    SearchFileResult,
    SearchMatch,
    SearchSpan,
)

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 1000
MAX_TREE_ENTRIES = 5000
MAX_FILE_BYTES = 1_000_000
MAX_SEARCH_RESULTS = 200
MAX_SEARCH_FILES = 20_000
MAX_SEARCH_BYTES = 100_000_000
MAX_MATCHES_PER_FILE = 100
_MAX_MATCH_TEXT = 500
_MAX_MATCH_LINE = 2_000
_MAX_HIGHLIGHTS = 100
_EXCLUDED_DIRECTORIES = {".git"}
# Heavy dependency/cache folders that are skipped by default (like a code
# search tool's ignore list). Naming one of these in the ``include`` filter
# opts back into searching it.
_DEFAULT_IGNORED_DIRECTORIES = {
    ".venv",
    "venv",
    "env",
    "virtualenv",
    "node_modules",
    "bower_components",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".cache",
    ".next",
    ".nuxt",
    ".turbo",
    ".parcel-cache",
    ".gradle",
    "dist",
    "build",
    "target",
}

_GITHUB_URL_RE = re.compile(
    r"^(?:https?://|git@)?(?:www\.)?github\.com[/:]"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def parse_github_repository(repo_url: str) -> tuple[str, str]:
    match = _GITHUB_URL_RE.match(repo_url.strip())
    if not match:
        raise api_error(ErrorCode.INVALID_GITHUB_URL, status_code=status.HTTP_400_BAD_REQUEST)
    return match.group("owner"), match.group("repo")


def list_projects(db: Session, owner: User, *, limit: int, offset: int) -> list[Project]:
    statement = (
        select(Project)
        .where(Project.owner_id == owner.id)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement))


def browse_directories(path: str | None) -> DirectoryListing:
    root = Path.home().resolve()
    target = Path(path).expanduser().resolve() if path else root
    if not target.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        directories = [
            DirectoryEntry(name=child.name, path=str(child))
            for child in sorted(target.iterdir(), key=lambda item: item.name.lower())
            if child.is_dir()
        ]
    except OSError as exc:
        raise api_error(
            ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST
        ) from exc

    parent = None if target.parent == target else str(target.parent)
    return DirectoryListing(
        root=str(root),
        path=str(target),
        parent=parent,
        directories=directories,
    )


def list_files(
    db: Session, owner: User, project_id: int, path: str | None = None
) -> FileTreeRead:
    """Return a single directory's immediate children as a read-only listing.

    The client loads the tree lazily, one folder at a time, so a large project
    is never walked in full. Symbolic links are reported as files (never
    traversed) and the ``.git`` directory is hidden, so a listing cannot loop or
    escape the project root. ``path`` is a project-relative directory; ``None``
    or an empty string lists the project root.
    """
    project = get_project(db, owner, project_id)
    root = Path(project.path).resolve()
    if not root.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    directory = _resolve_project_dir(root, path)
    if not directory.is_dir():
        raise api_error(ErrorCode.FILE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    try:
        with os.scandir(directory) as iterator:
            children = sorted(
                iterator,
                key=lambda entry: (not entry.is_dir(follow_symlinks=False), entry.name.lower()),
            )
    except OSError as exc:
        raise api_error(
            ErrorCode.FILE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND
        ) from exc

    entries: list[FileNode] = []
    truncated = False
    for entry in children:
        if entry.name in _EXCLUDED_DIRECTORIES:
            continue
        if len(entries) >= MAX_TREE_ENTRIES:
            truncated = True
            break

        relative = Path(entry.path).relative_to(root).as_posix()
        node_type = "directory" if entry.is_dir(follow_symlinks=False) else "file"
        entries.append(FileNode(name=entry.name, path=relative, type=node_type))

    return FileTreeRead(entries=entries, truncated=truncated)


def read_file(db: Session, owner: User, project_id: int, path: str) -> FileContentRead:
    """Return a single text file's content for the editor.

    The path is resolved inside the project root (symlinks that escape the
    project are rejected), and binary or oversized files are refused so the
    browser never has to render something it cannot handle.
    """
    root, target = _resolve_project_file(db, owner, project_id, path)
    if not target.is_file():
        raise api_error(ErrorCode.FILE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    try:
        if target.stat().st_size > MAX_FILE_BYTES:
            raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)
        data = target.read_bytes()
    except OSError as exc:
        raise api_error(ErrorCode.FILE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND) from exc

    if len(data) > MAX_FILE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)
    if b"\x00" in data:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST) from exc

    return FileContentRead(
        path=target.relative_to(root).as_posix(), content=content, size=len(data)
    )


def write_file(
    db: Session, owner: User, project_id: int, path: str, content: str
) -> FileContentRead:
    """Persist the editor's content to ``path`` using an atomic replace."""
    root, target = _resolve_project_file(db, owner, project_id, path)
    if not target.parent.is_dir():
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)

    staging = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        staging.write_bytes(data)
        os.replace(staging, target)
    except OSError as exc:
        try:
            staging.unlink()
        except OSError:
            pass
        raise api_error(
            ErrorCode.FILE_WRITE_FAILED, status_code=status.HTTP_400_BAD_REQUEST
        ) from exc

    return FileContentRead(
        path=target.relative_to(root).as_posix(), content=content, size=len(data)
    )


def search_files(
    db: Session,
    owner: User,
    project_id: int,
    *,
    query: str,
    mode: str = "names",
    include: str | None = None,
    exclude: str | None = None,
    case_sensitive: bool = False,
    whole_word: bool = False,
    regex: bool = False,
) -> FileSearchRead:
    """Search the project tree by file name or file contents.

    The walk never follows symlinks (so it cannot loop or leave the project),
    always skips ``.git``, and by default skips heavy dependency/cache folders
    (see ``_DEFAULT_IGNORED_DIRECTORIES``); naming one of those folders in
    ``include`` opts back into it. ``include``/``exclude`` are comma separated
    globs matched against the project-relative path (or file name). Results are
    capped so a huge tree cannot exhaust the request.
    """
    project = get_project(db, owner, project_id)
    root = Path(project.path).resolve()
    if not root.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    matcher = _build_search_matcher(
        query, case_sensitive=case_sensitive, whole_word=whole_word, regex=regex
    )
    include_globs = _parse_globs(include)
    exclude_globs = _parse_globs(exclude)
    ignored_dirs = _ignored_directories(root, include_globs)

    entries: list[SearchFileResult] = []
    scanned = 0
    scanned_bytes = 0
    truncated = False

    stack: list[tuple[str, str]] = [(str(root), "")]
    while stack and not truncated:
        directory, relative_dir = stack.pop()
        try:
            with os.scandir(directory) as iterator:
                children = sorted(
                    iterator,
                    key=lambda entry: (
                        not entry.is_dir(follow_symlinks=False),
                        entry.name.lower(),
                    ),
                )
        except OSError:
            continue

        subdirectories: list[tuple[str, str]] = []
        for entry in children:
            if entry.is_symlink():
                continue
            name = entry.name
            relative = f"{relative_dir}/{name}" if relative_dir else name

            if entry.is_dir(follow_symlinks=False):
                if name in _EXCLUDED_DIRECTORIES or name in ignored_dirs:
                    continue
                subdirectories.append((entry.path, relative))
                continue

            if not _matches_search_globs(relative, include_globs, exclude_globs):
                continue

            scanned += 1
            if scanned > MAX_SEARCH_FILES:
                truncated = True
                break

            if mode == "contents":
                matches, consumed = _match_file_contents(Path(entry.path), matcher)
                scanned_bytes += consumed
                if matches:
                    entries.append(SearchFileResult(path=relative, matches=matches))
                if scanned_bytes > MAX_SEARCH_BYTES:
                    truncated = True
                    break
            elif matcher.search(name):
                entries.append(
                    SearchFileResult(path=relative, spans=_match_spans(name, len(name), matcher))
                )

            if len(entries) >= MAX_SEARCH_RESULTS:
                truncated = True
                break

        stack.extend(reversed(subdirectories))

    return FileSearchRead(entries=entries, truncated=truncated)


def _ignored_directories(root: Path, include_globs: list[str]) -> set[str]:
    """Default-ignored dirs (built-in plus the project's ``.gitignore``).

    Naming one of them in ``include`` opts back into the whole tree.
    """
    ignored = _DEFAULT_IGNORED_DIRECTORIES | _gitignore_directories(root)
    if any(_pattern_root(pattern) in ignored for pattern in include_globs):
        return set()
    return ignored


def _gitignore_directories(root: Path) -> set[str]:
    """Best-effort directory names from the project's ``.gitignore``.

    Only plain names map cleanly onto our name-based ignore (globs and
    negations are skipped); the last path segment of a nested entry is used.
    """
    try:
        content = (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    names: set[str] = set()
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        entry = line.rstrip("/")
        if not entry or any(char in entry for char in "*?[]"):
            continue
        names.add(PurePosixPath(entry).name)
    return names


def _pattern_root(pattern: str) -> str:
    parts = PurePosixPath(pattern).parts
    return parts[0] if parts else ""


def _build_search_matcher(
    query: str, *, case_sensitive: bool, whole_word: bool, regex: bool
) -> re.Pattern[str]:
    pattern = query if regex else re.escape(query)
    if whole_word:
        pattern = rf"(?<![0-9A-Za-z_]){pattern}(?![0-9A-Za-z_])"
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise api_error(
            ErrorCode.SEARCH_QUERY_INVALID, status_code=status.HTTP_400_BAD_REQUEST
        ) from exc


def _parse_globs(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _matches_search_globs(relative: str, include: list[str], exclude: list[str]) -> bool:
    if any(_glob_match(relative, pattern) for pattern in exclude):
        return False
    if not include:
        return True
    return any(_glob_match(relative, pattern) for pattern in include)


def _glob_match(relative: str, pattern: str) -> bool:
    name = PurePosixPath(relative).name
    if pattern.startswith("**/"):
        return fnmatch.fnmatchcase(name, pattern[3:]) or fnmatch.fnmatchcase(relative, pattern)
    if "/" in pattern:
        return fnmatch.fnmatchcase(relative, pattern)
    return fnmatch.fnmatchcase(name, pattern)


def _match_spans(text: str, limit: int, matcher: re.Pattern[str]) -> list[SearchSpan]:
    """Highlight spans for ``matcher`` within the first ``limit`` characters."""
    spans: list[SearchSpan] = []
    for found in matcher.finditer(text):
        start, end = found.span()
        if start >= limit:
            break
        spans.append(SearchSpan(start=start, end=min(end, limit)))
        if len(spans) >= _MAX_HIGHLIGHTS:
            break
    return spans


def _match_file_contents(
    path: Path, matcher: re.Pattern[str]
) -> tuple[list[SearchMatch], int]:
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            return [], 0
        data = path.read_bytes()
    except OSError:
        return [], 0
    if len(data) > MAX_FILE_BYTES:
        return [], 0
    if b"\x00" in data:
        return [], len(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [], len(data)

    matches: list[SearchMatch] = []
    for number, line in enumerate(text.splitlines(), start=1):
        haystack = line[:_MAX_MATCH_LINE]
        if not matcher.search(haystack):
            continue
        display = haystack[:_MAX_MATCH_TEXT]
        spans = _match_spans(haystack, len(display), matcher)
        matches.append(SearchMatch(line=number, text=display, spans=spans))
        if len(matches) >= MAX_MATCHES_PER_FILE:
            break
    return matches, len(data)


def _resolve_project_file(
    db: Session, owner: User, project_id: int, path: str
) -> tuple[Path, Path]:
    project = get_project(db, owner, project_id)
    root = Path(project.path).resolve()
    if not root.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    return root, _resolve_within_root(root, path)


def _resolve_project_dir(root: Path, path: str | None) -> Path:
    """Resolve a project-relative directory, rejecting escapes.

    An empty or missing path resolves to the project root itself.
    """
    if path is None or not path.strip():
        return root
    return _resolve_within_root(root, path)


def _resolve_within_root(root: Path, path: str) -> Path:
    """Resolve a project-relative path, rejecting anything that escapes ``root``."""
    candidate = path.strip()
    parts = PurePosixPath(candidate).parts
    if not candidate or candidate.startswith(("/", "~", "-")) or ".." in parts:
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    if _EXCLUDED_DIRECTORIES.intersection(parts):
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    target = (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    return target


def get_project(db: Session, owner: User, project_id: int) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == owner.id)
    )
    if project is None:
        raise api_error(ErrorCode.PROJECT_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)
    return project


def delete_project(db: Session, owner: User, project_id: int, settings: Settings) -> None:
    project = get_project(db, owner, project_id)
    if project.source is ProjectSource.GITHUB:
        _remove_clone(project.path, settings)
    db.delete(project)
    db.commit()


def create_local_project(
    db: Session, owner: User, payload: LocalProjectCreate
) -> Project:
    path = Path(payload.path).expanduser().resolve()
    if not path.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    _ensure_path_available(db, owner.id, str(path))
    name = _resolve_name(db, owner.id, payload.name or path.name, provided=payload.name is not None)
    project = Project(
        owner_id=owner.id,
        name=name,
        source=ProjectSource.LOCAL,
        path=str(path),
    )
    return _save(db, project)


def create_github_project(
    db: Session, owner: User, payload: GithubProjectCreate, settings: Settings
) -> Project:
    repo_owner, repo_name = parse_github_repository(payload.repo_url)
    remote_url = f"https://github.com/{repo_owner}/{repo_name}.git"

    root = _projects_root(settings)
    name = _resolve_name(db, owner.id, payload.name or repo_name, provided=payload.name is not None)
    destination = (root / str(owner.id) / name).resolve()
    _ensure_destination_available(db, owner.id, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    staging = destination.with_name(f".{destination.name}.cloning-{uuid4().hex}")
    _clone_repository(f"{repo_owner}/{repo_name}", staging, payload.branch, settings)
    _promote_clone(staging, destination)

    project = Project(
        owner_id=owner.id,
        name=name,
        source=ProjectSource.GITHUB,
        remote_url=remote_url,
        path=str(destination),
    )
    try:
        return _save(db, project)
    except HTTPException:
        _remove_directory(destination)
        raise


def _projects_root(settings: Settings) -> Path:
    return Path(settings.projects_root).expanduser().resolve()


def _clone_repository(
    repository: str,
    destination: Path,
    branch: str | None,
    settings: Settings,
) -> None:
    command = ["gh", "repo", "clone", repository, str(destination), "--", "--depth", "1"]
    if branch:
        command += ["--branch", branch]

    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.github_clone_timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _remove_directory(destination)
        raise api_error(
            ErrorCode.PROJECT_CLONE_FAILED, status_code=status.HTTP_400_BAD_REQUEST
        ) from exc

    if result.returncode != 0:
        _remove_directory(destination)
        raise api_error(ErrorCode.PROJECT_CLONE_FAILED, status_code=status.HTTP_400_BAD_REQUEST)


def _promote_clone(staging: Path, destination: Path) -> None:
    try:
        os.rename(staging, destination)
    except OSError as exc:
        _remove_directory(staging)
        raise api_error(
            ErrorCode.PROJECT_PATH_EXISTS, status_code=status.HTTP_409_CONFLICT
        ) from exc


def _remove_clone(path: str, settings: Settings) -> None:
    target = Path(path).resolve()
    if target.is_relative_to(_projects_root(settings)):
        _remove_directory(target)


def _remove_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _ensure_destination_available(db: Session, owner_id: int, destination: Path) -> None:
    if destination.exists():
        raise api_error(ErrorCode.PROJECT_PATH_EXISTS, status_code=status.HTTP_409_CONFLICT)
    _ensure_path_available(db, owner_id, str(destination))


def _ensure_path_available(db: Session, owner_id: int, path: str) -> None:
    exists = db.scalar(select(Project.id).where(Project.owner_id == owner_id, Project.path == path))
    if exists is not None:
        raise api_error(ErrorCode.PROJECT_PATH_EXISTS, status_code=status.HTTP_409_CONFLICT)


def _resolve_name(db: Session, owner_id: int, base: str, *, provided: bool) -> str:
    if provided:
        if _name_exists(db, owner_id, base):
            raise api_error(ErrorCode.PROJECT_NAME_EXISTS, status_code=status.HTTP_409_CONFLICT)
        return base

    candidate = base
    index = 2
    while _name_exists(db, owner_id, candidate):
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _name_exists(db: Session, owner_id: int, name: str) -> bool:
    return (
        db.scalar(select(Project.id).where(Project.owner_id == owner_id, Project.name == name))
        is not None
    )


def _save(db: Session, project: Project) -> Project:
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise api_error(_conflict_code(exc), status_code=status.HTTP_409_CONFLICT) from exc
    db.refresh(project)
    return project


def _conflict_code(exc: IntegrityError) -> ErrorCode:
    message = str(getattr(exc, "orig", exc))
    if "path" in message:
        return ErrorCode.PROJECT_PATH_EXISTS
    return ErrorCode.PROJECT_NAME_EXISTS
