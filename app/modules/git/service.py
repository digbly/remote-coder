import os
import subprocess
from pathlib import Path

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.auth.models import User
from app.modules.git.schemas import GitChange, GitStatusRead
from app.modules.projects.service import get_project

_STATUS_COMMAND = [
    "git",
    "status",
    "--porcelain=v2",
    "--branch",
    "--untracked-files=all",
    "-z",
]

_HEADER_PREFIX = "# branch.head "
_UPSTREAM_PREFIX = "# branch.upstream "
_AHEAD_BEHIND_PREFIX = "# branch.ab "


def get_git_status(db: Session, owner: User, project_id: int, settings: Settings) -> GitStatusRead:
    project = get_project(db, owner, project_id)
    path = Path(project.path)
    if not path.is_dir():
        raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)

    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        result = subprocess.run(
            _STATUS_COMMAND,
            cwd=path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.git_status_timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise api_error(
            ErrorCode.GIT_COMMAND_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from exc

    if result.returncode != 0:
        if "not a git repository" in result.stderr.lower():
            raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)
        raise api_error(
            ErrorCode.GIT_COMMAND_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return parse_status(result.stdout)


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
