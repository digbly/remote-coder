import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.auth.models import User
from app.modules.git.schemas import (
    GitChange,
    GitCommitRead,
    GitPullRequestCreate,
    GitPullRequestRead,
    GitStatusRead,
)
from app.modules.projects.service import get_project, parse_github_repository

_STATUS_ARGS = [
    "status",
    "--porcelain=v2",
    "--branch",
    "--untracked-files=all",
    "-z",
]

_HEADER_PREFIX = "# branch.head "
_UPSTREAM_PREFIX = "# branch.upstream "
_AHEAD_BEHIND_PREFIX = "# branch.ab "

_BRANCH_RE = re.compile(r"^(?!-)[A-Za-z0-9._/-]{1,255}$")
_DEFAULT_BRANCHES = ("main", "master")


def get_git_status(db: Session, owner: User, project_id: int, settings: Settings) -> GitStatusRead:
    path = _project_repository(db, owner, project_id, settings)
    return _read_status(path, settings)


def _read_status(path: Path, settings: Settings) -> GitStatusRead:
    result = _run_git(path, _STATUS_ARGS, timeout=settings.git_status_timeout_seconds)
    if result.returncode != 0:
        _raise_status_error(result)
    return parse_status(result.stdout)


def stage_paths(
    db: Session, owner: User, project_id: int, paths: list[str], settings: Settings
) -> GitStatusRead:
    """Stage the given paths, then return the refreshed status."""
    path = _project_repository(db, owner, project_id, settings)
    _validate_paths(paths)

    result = _run_git(path, ["add", "--", *paths], timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)
    return _read_status(path, settings)


def unstage_paths(
    db: Session, owner: User, project_id: int, paths: list[str], settings: Settings
) -> GitStatusRead:
    """Move the given paths back to the working tree, then return the status."""
    path = _project_repository(db, owner, project_id, settings)
    _validate_paths(paths)

    if _has_head(path, settings):
        args = ["restore", "--staged", "--", *paths]
    else:
        args = ["rm", "--cached", "-r", "--", *paths]

    result = _run_git(path, args, timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)
    return _read_status(path, settings)


def commit_staged(
    db: Session, owner: User, project_id: int, message: str, settings: Settings
) -> GitCommitRead:
    """Commit whatever is already staged in the index."""
    path = _project_repository(db, owner, project_id, settings)

    cleaned = message.strip()
    if not cleaned:
        raise api_error(
            ErrorCode.VALIDATION_ERROR, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        )

    current = _read_status(path, settings)
    if not current.staged:
        raise api_error(ErrorCode.GIT_NOTHING_TO_COMMIT, status_code=status.HTTP_400_BAD_REQUEST)

    result = _run_git(path, ["commit", "-m", cleaned], timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)

    revision = _run_git(
        path, ["rev-parse", "--short", "HEAD"], timeout=settings.git_commit_timeout_seconds
    )
    commit_hash = revision.stdout.strip() if revision.returncode == 0 else ""
    return GitCommitRead(commit=commit_hash, branch=current.branch)


def create_pull_request(
    db: Session, owner: User, project_id: int, payload: GitPullRequestCreate, settings: Settings
) -> GitPullRequestRead:
    """Push a branch and open a GitHub pull request for it via the ``gh`` CLI."""
    path = _project_repository(db, owner, project_id, settings)

    if _github_remote(path, settings) is None:
        raise api_error(ErrorCode.GIT_REMOTE_MISSING, status_code=status.HTTP_400_BAD_REQUEST)

    base = _default_branch(path, settings)
    current = _current_branch(path, settings)
    branch = payload.branch.strip()

    if current == base:
        if not _valid_branch_name(branch) or branch == base:
            raise api_error(ErrorCode.GIT_BRANCH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
        checkout = _run_git(
            path, ["checkout", "-b", branch], timeout=settings.git_commit_timeout_seconds
        )
        if checkout.returncode != 0:
            raise api_error(ErrorCode.GIT_BRANCH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    else:
        branch = current

    push = _run_git(
        path,
        ["push", "-u", "origin", branch],
        timeout=settings.git_push_timeout_seconds,
        error_code=ErrorCode.GIT_PUSH_FAILED,
    )
    if push.returncode != 0:
        raise api_error(ErrorCode.GIT_PUSH_FAILED, status_code=status.HTTP_400_BAD_REQUEST)

    created = _run_gh(
        path,
        ["pr", "create", "--fill", "--base", base, "--head", branch],
        timeout=settings.github_pr_timeout_seconds,
    )
    if created.returncode != 0:
        raise api_error(ErrorCode.GIT_PULL_REQUEST_FAILED, status_code=status.HTTP_400_BAD_REQUEST)

    url = _last_url(created.stdout)
    if url is None:
        raise api_error(
            ErrorCode.GIT_PULL_REQUEST_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return GitPullRequestRead(url=url, branch=branch, base=base)


def parse_status(output: str) -> GitStatusRead:
    """Parse ``git status --porcelain=v2 --branch -z`` output.

    Records are NUL-separated. Type-2 (rename/copy) records are followed by a
    separate NUL-terminated original path, which is consumed here.
    """
    result = GitStatusRead()
    records = output.split("\0")
    index = 0

    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue

        if record.startswith("# "):
            _apply_branch_header(result, record)
        elif record.startswith("? "):
            result.untracked.append(record[2:])
        elif record.startswith("! "):
            continue
        elif record.startswith("u "):
            result.conflicted.append(_path_field(record, 10))
        elif record.startswith("1 "):
            fields = record.split(" ", 8)
            _classify(result, fields[1], fields[8])
        elif record.startswith("2 "):
            fields = record.split(" ", 9)
            origin = records[index] if index < len(records) else None
            index += 1
            _classify(result, fields[1], fields[9], origin)

    return result


def _apply_branch_header(result: GitStatusRead, record: str) -> None:
    if record.startswith(_HEADER_PREFIX):
        head = record[len(_HEADER_PREFIX) :]
        result.branch = None if head == "(detached)" else head
    elif record.startswith(_UPSTREAM_PREFIX):
        result.upstream = record[len(_UPSTREAM_PREFIX) :]
    elif record.startswith(_AHEAD_BEHIND_PREFIX):
        for token in record[len(_AHEAD_BEHIND_PREFIX) :].split():
            if token.startswith("+"):
                result.ahead = int(token[1:])
            elif token.startswith("-"):
                result.behind = int(token[1:])


def _classify(result: GitStatusRead, xy: str, path: str, origin: str | None = None) -> None:
    index_status, worktree_status = xy[0], xy[1]
    if index_status != ".":
        result.staged.append(GitChange(path=path, status=index_status, orig_path=origin))
    if worktree_status != ".":
        result.unstaged.append(GitChange(path=path, status=worktree_status, orig_path=origin))


def _path_field(record: str, count: int) -> str:
    return record.split(" ", count)[count]


def _project_repository(db: Session, owner: User, project_id: int, settings: Settings) -> Path:
    project = get_project(db, owner, project_id)
    path = Path(project.path)
    if not path.is_dir():
        raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)

    inside = _run_git(
        path, ["rev-parse", "--is-inside-work-tree"], timeout=settings.git_status_timeout_seconds
    )
    if inside.returncode != 0:
        raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)
    return path


def _validate_paths(paths: list[str]) -> None:
    for raw in paths:
        candidate = raw.strip()
        parts = PurePosixPath(candidate).parts
        if not candidate or candidate.startswith(("-", "/", "~")) or ".." in parts:
            raise api_error(ErrorCode.GIT_INVALID_PATH, status_code=status.HTTP_400_BAD_REQUEST)


def _valid_branch_name(branch: str) -> bool:
    if not _BRANCH_RE.fullmatch(branch) or branch in {".", ".."}:
        return False
    return not (branch.startswith("/") or branch.endswith("/") or "//" in branch)


def _github_remote(path: Path, settings: Settings) -> str | None:
    result = _run_git(
        path, ["remote", "get-url", "origin"], timeout=settings.git_status_timeout_seconds
    )
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    try:
        parse_github_repository(url)
    except HTTPException:
        return None
    return url


def _has_head(path: Path, settings: Settings) -> bool:
    result = _run_git(
        path, ["rev-parse", "--verify", "-q", "HEAD"], timeout=settings.git_status_timeout_seconds
    )
    return result.returncode == 0


def _default_branch(path: Path, settings: Settings) -> str:
    result = _run_git(
        path,
        ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        timeout=settings.git_status_timeout_seconds,
    )
    if result.returncode == 0 and "/" in result.stdout.strip():
        return result.stdout.strip().split("/", 1)[1]

    for candidate in _DEFAULT_BRANCHES:
        exists = _run_git(
            path, ["rev-parse", "--verify", candidate], timeout=settings.git_status_timeout_seconds
        )
        if exists.returncode == 0:
            return candidate
    return _DEFAULT_BRANCHES[0]


def _current_branch(path: Path, settings: Settings) -> str:
    result = _run_git(
        path, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=settings.git_status_timeout_seconds
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _last_url(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped.startswith("http"):
            return stripped
    return None


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _run_git(
    path: Path,
    args: list[str],
    *,
    timeout: int,
    error_code: ErrorCode = ErrorCode.GIT_COMMAND_FAILED,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise api_error(error_code, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from exc


def _ensure_success(result: subprocess.CompletedProcess[str], error_code: ErrorCode) -> None:
    if result.returncode != 0:
        raise api_error(error_code, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _run_gh(path: Path, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args],
            cwd=path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise api_error(
            ErrorCode.GIT_PULL_REQUEST_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from exc


def _raise_status_error(result: subprocess.CompletedProcess[str]) -> None:
    if "not a git repository" in result.stderr.lower():
        raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)
    raise api_error(ErrorCode.GIT_COMMAND_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
