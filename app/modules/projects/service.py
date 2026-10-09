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
    FileTreeRead,
    GithubProjectCreate,
    LocalProjectCreate,
)

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 1000
MAX_TREE_DEPTH = 12
MAX_TREE_ENTRIES = 5000
MAX_FILE_BYTES = 1_000_000
_EXCLUDED_DIRECTORIES = {".git"}

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


def list_files(db: Session, owner: User, project_id: int) -> FileTreeRead:
    """Return the project's files as a read-only tree.

    Symbolic links are reported as files (never traversed) and the ``.git``
    directory is hidden, so the walk cannot loop or escape the project root.
    """
    project = get_project(db, owner, project_id)
    root = Path(project.path)
    if not root.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    state = _TreeLimits()
    entries = _build_tree(root, root, depth=0, state=state)
    return FileTreeRead(entries=entries, truncated=state.truncated)


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


def _resolve_project_file(
    db: Session, owner: User, project_id: int, path: str
) -> tuple[Path, Path]:
    project = get_project(db, owner, project_id)
    root = Path(project.path).resolve()
    if not root.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    candidate = path.strip()
    parts = PurePosixPath(candidate).parts
    if not candidate or candidate.startswith(("/", "~", "-")) or ".." in parts:
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    if _EXCLUDED_DIRECTORIES.intersection(parts):
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    target = (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    return root, target


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
    _clone_repository(remote_url, staging, payload.branch, payload.token, settings)
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
    remote_url: str,
    destination: Path,
    branch: str | None,
    token: str | None,
    settings: Settings,
) -> None:
    command = ["git", "clone", "--depth", "1"]
    if branch:
        command += ["--branch", branch]
    command += ["--", remote_url, str(destination)]

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"Authorization: Bearer {token}"

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


class _TreeLimits:
    def __init__(self) -> None:
        self.count = 0
        self.truncated = False


def _build_tree(root: Path, directory: Path, *, depth: int, state: _TreeLimits) -> list[FileNode]:
    if depth >= MAX_TREE_DEPTH:
        state.truncated = True
        return []

    try:
        with os.scandir(directory) as iterator:
            children = sorted(
                iterator,
                key=lambda entry: (not entry.is_dir(follow_symlinks=False), entry.name.lower()),
            )
    except OSError:
        return []

    nodes: list[FileNode] = []
    for entry in children:
        if state.count >= MAX_TREE_ENTRIES:
            state.truncated = True
            break
        if entry.name in _EXCLUDED_DIRECTORIES:
            continue

        state.count += 1
        relative = Path(entry.path).relative_to(root).as_posix()
        if entry.is_dir(follow_symlinks=False):
            nodes.append(
                FileNode(
                    name=entry.name,
                    path=relative,
                    type="directory",
                    children=_build_tree(root, Path(entry.path), depth=depth + 1, state=state),
                )
            )
        else:
            nodes.append(FileNode(name=entry.name, path=relative, type="file"))

    return nodes
