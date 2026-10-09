import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.agents import service as agent_service
from app.modules.auth.models import User
from app.modules.git.schemas import (
    GitBranchesRead,
    GitChange,
    GitCommitRead,
    GitPullRequestCreate,
    GitPullRequestRead,
    GitPullRequestStatusRead,
    GitPullRequestSummary,
    GitStatusRead,
    GitWorktreeRead,
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
_WORKTREE_BRANCH_PREFIX = "refs/heads/"

_COMMIT_MESSAGE_PROMPT = (
    "You are an expert software engineer writing a git commit message.\n"
    "Write ONE commit message for the changes below.\n"
    "Rules:\n"
    "- Use the imperative mood in the subject line.\n"
    "- Keep the subject line under 72 characters.\n"
    "- Follow Conventional Commits (feat, fix, docs, refactor, test, chore) when it fits.\n"
    "- Optionally add a short body after a blank line.\n"
    "- Output only the commit message, without quotes, markdown or explanation."
)

# Cap the generated message so a chatty agent cannot return an unbounded blob.
_COMMIT_MESSAGE_MAX_CHARS = 5000
_FENCE_LINE = re.compile(r"^```[A-Za-z0-9_+-]*$")


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


def stage_all(db: Session, owner: User, project_id: int, settings: Settings) -> GitStatusRead:
    """Stage every change in the working tree, then return the refreshed status."""
    path = _project_repository(db, owner, project_id, settings)

    result = _run_git(path, ["add", "-A"], timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)
    return _read_status(path, settings)


def unstage_paths(
    db: Session, owner: User, project_id: int, paths: list[str], settings: Settings
) -> GitStatusRead:
    """Move the given paths back to the working tree, then return the status."""
    path = _project_repository(db, owner, project_id, settings)
    _validate_paths(paths)

    _unstage(path, paths, settings)
    return _read_status(path, settings)


def unstage_all(db: Session, owner: User, project_id: int, settings: Settings) -> GitStatusRead:
    """Move every staged path back to the working tree."""
    path = _project_repository(db, owner, project_id, settings)
    current = _read_status(path, settings)

    _unstage(path, [change.path for change in current.staged], settings)
    return _read_status(path, settings)


def discard_paths(
    db: Session, owner: User, project_id: int, paths: list[str], settings: Settings
) -> GitStatusRead:
    """Discard working tree and index changes for the given paths.

    Paths present in ``HEAD`` are restored from it; every other path is
    removed from the index (when staged) and from disk. Rename targets may be
    passed alongside their original path so both sides are reverted.
    """
    path = _project_repository(db, owner, project_id, settings)
    _validate_paths(paths)
    if not paths:
        return _read_status(path, settings)

    restore, remove = _partition_by_head(path, paths, settings)

    if restore:
        _run_discard(
            path, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *restore], settings
        )

    if remove:
        staged, _ = _partition_tracked(path, remove, settings)
        if staged:
            _run_discard(path, ["rm", "--cached", "-r", "--", *staged], settings)
        _run_discard(path, ["clean", "-f", "-d", "--", *remove], settings)

    return _read_status(path, settings)


def pull_branch(db: Session, owner: User, project_id: int, settings: Settings) -> GitStatusRead:
    """Fast-forward the current branch from its upstream."""
    path = _project_repository(db, owner, project_id, settings)
    branch = _current_branch(path, settings)
    if not branch or _upstream_branch(path, branch, settings) is None:
        raise api_error(ErrorCode.GIT_NO_UPSTREAM, status_code=status.HTTP_400_BAD_REQUEST)

    result = _run_git(
        path,
        ["pull", "--ff-only"],
        timeout=settings.git_push_timeout_seconds,
        error_code=ErrorCode.GIT_PULL_FAILED,
    )
    if result.returncode != 0:
        raise api_error(ErrorCode.GIT_PULL_FAILED, status_code=status.HTTP_400_BAD_REQUEST)
    return _read_status(path, settings)


def push_branch(db: Session, owner: User, project_id: int, settings: Settings) -> GitStatusRead:
    """Push the current branch, setting its upstream on the first push."""
    path = _project_repository(db, owner, project_id, settings)
    branch = _current_branch(path, settings)
    if not branch:
        raise api_error(ErrorCode.GIT_BRANCH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    if _upstream_branch(path, branch, settings) is None:
        args = ["push", "-u", "origin", branch]
    else:
        args = ["push"]

    result = _run_git(
        path,
        args,
        timeout=settings.git_push_timeout_seconds,
        error_code=ErrorCode.GIT_PUSH_FAILED,
    )
    if result.returncode != 0:
        raise api_error(ErrorCode.GIT_PUSH_FAILED, status_code=status.HTTP_400_BAD_REQUEST)
    return _read_status(path, settings)


def list_branches(
    db: Session, owner: User, project_id: int, settings: Settings
) -> GitBranchesRead:
    """Return the current branch together with every local branch."""
    path = _project_repository(db, owner, project_id, settings)
    result = _run_git(
        path,
        ["for-each-ref", "--format=%(refname:short)", "refs/heads"],
        timeout=settings.git_status_timeout_seconds,
    )
    branches = sorted(line.strip() for line in result.stdout.splitlines() if line.strip())
    return GitBranchesRead(current=_current_branch(path, settings) or None, branches=branches)


def list_worktrees(
    db: Session, owner: User, project_id: int, settings: Settings
) -> list[GitWorktreeRead]:
    """Return every git worktree registered for the project, primary first."""
    path = _project_repository(db, owner, project_id, settings)
    result = _run_git(
        path,
        ["worktree", "list", "--porcelain"],
        timeout=settings.git_status_timeout_seconds,
    )
    if result.returncode != 0:
        _raise_status_error(result)
        raise api_error(
            ErrorCode.GIT_COMMAND_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return parse_worktrees(result.stdout, primary=path)


def find_worktree(path: Path, name: str, settings: Settings) -> Path | None:
    """Resolve a worktree directory by its basename, or ``None`` if unknown.

    The name comes from the client, so it is matched against git's own worktree
    registry instead of being treated as a filesystem path.
    """
    try:
        result = _run_git(
            path,
            ["worktree", "list", "--porcelain"],
            timeout=settings.git_status_timeout_seconds,
        )
    except HTTPException:
        return None
    if result.returncode != 0:
        return None
    for worktree in parse_worktrees(result.stdout, primary=path):
        if worktree.name == name:
            return Path(worktree.path)
    return None


def parse_worktrees(output: str, primary: Path) -> list[GitWorktreeRead]:
    """Parse ``git worktree list --porcelain`` output.

    Each worktree is a blank-line separated block whose first line is
    ``worktree <path>`` and optionally a ``branch <ref>`` line.
    """
    primary_resolved = primary.resolve()
    worktrees: list[GitWorktreeRead] = []
    current: dict[str, str] | None = None

    for line in output.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(_build_worktree(current, primary_resolved))
            current = {"path": line[len("worktree ") :]}
        elif current is not None and line.startswith("branch "):
            current["branch"] = line[len("branch ") :]

    if current is not None:
        worktrees.append(_build_worktree(current, primary_resolved))

    worktrees.sort(key=lambda worktree: (not worktree.is_primary, worktree.name.lower()))
    return worktrees


def _build_worktree(raw: dict[str, str], primary_resolved: Path) -> GitWorktreeRead:
    path = Path(raw["path"])
    branch_ref = raw.get("branch")
    branch = (
        branch_ref[len(_WORKTREE_BRANCH_PREFIX) :]
        if branch_ref is not None and branch_ref.startswith(_WORKTREE_BRANCH_PREFIX)
        else None
    )
    try:
        is_primary = path.resolve() == primary_resolved
    except OSError:
        is_primary = False
    return GitWorktreeRead(name=path.name, path=str(path), branch=branch, is_primary=is_primary)


def create_branch(
    db: Session, owner: User, project_id: int, name: str, settings: Settings
) -> GitStatusRead:
    """Create and check out a new branch."""
    path = _project_repository(db, owner, project_id, settings)
    _checkout(path, name.strip(), create=True, settings=settings)
    return _read_status(path, settings)


def checkout_branch(
    db: Session, owner: User, project_id: int, name: str, settings: Settings
) -> GitStatusRead:
    """Switch to an existing local branch."""
    path = _project_repository(db, owner, project_id, settings)
    _checkout(path, name.strip(), create=False, settings=settings)
    return _read_status(path, settings)


def _checkout(path: Path, branch: str, *, create: bool, settings: Settings) -> None:
    if not _valid_branch_name(branch):
        raise api_error(ErrorCode.GIT_BRANCH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    args = ["checkout", "-b", branch] if create else ["checkout", branch]
    result = _run_git(
        path,
        args,
        timeout=settings.git_commit_timeout_seconds,
        error_code=ErrorCode.GIT_BRANCH_INVALID,
    )
    if result.returncode != 0:
        raise api_error(ErrorCode.GIT_BRANCH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)


def _unstage(path: Path, paths: list[str], settings: Settings) -> None:
    if not paths:
        return
    if _has_head(path, settings):
        args = ["restore", "--staged", "--", *paths]
    else:
        args = ["rm", "--cached", "-r", "--", *paths]

    result = _run_git(path, args, timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)


def _run_discard(path: Path, args: list[str], settings: Settings) -> None:
    result = _run_git(
        path,
        args,
        timeout=settings.git_commit_timeout_seconds,
        error_code=ErrorCode.GIT_DISCARD_FAILED,
    )
    _ensure_success(result, ErrorCode.GIT_DISCARD_FAILED)


def _partition_by_head(
    path: Path, paths: list[str], settings: Settings
) -> tuple[list[str], list[str]]:
    if not _has_head(path, settings):
        return [], list(paths)

    result = _run_git(
        path,
        ["ls-tree", "-r", "--name-only", "-z", "HEAD"],
        timeout=settings.git_status_timeout_seconds,
    )
    head_paths = set(result.stdout.split("\0"))
    return [p for p in paths if p in head_paths], [p for p in paths if p not in head_paths]


def _partition_tracked(
    path: Path, paths: list[str], settings: Settings
) -> tuple[list[str], list[str]]:
    result = _run_git(
        path,
        ["ls-files", "-z", "--", *paths],
        timeout=settings.git_status_timeout_seconds,
    )
    tracked = set(result.stdout.split("\0"))
    return [p for p in paths if p in tracked], [p for p in paths if p not in tracked]



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


def generate_commit_message(
    db: Session, owner: User, project_id: int, settings: Settings
) -> tuple[str, str]:
    """Generate a commit message for the current changes using the default agent.

    Returns ``(agent_id, message)``. The staged diff is preferred so the message
    describes what will actually be committed; otherwise the working tree diff
    (or the changed-file list) is used.
    """
    path = _project_repository(db, owner, project_id, settings)
    repo_status = _read_status(path, settings)
    if not (repo_status.staged or repo_status.unstaged or repo_status.untracked):
        raise api_error(ErrorCode.GIT_NOTHING_TO_COMMIT, status_code=status.HTTP_400_BAD_REQUEST)

    changes = _commit_message_changes(path, repo_status, settings)
    prompt = f"{_COMMIT_MESSAGE_PROMPT}\n\n{changes}"
    default_agent_id = agent_service.get_default_agent_id(db, owner)
    args = (
        agent_service.commit_message_args(
            db, owner, default_agent_id, settings.agent_commit_message_args
        )
        if default_agent_id
        else ""
    )
    agent_id, output = agent_service.run_agent_prompt(
        db,
        owner,
        prompt,
        path,
        settings.agent_commit_message_timeout_seconds,
        args,
    )

    message = _clean_commit_message(output)
    if not message:
        raise api_error(
            ErrorCode.AGENT_GENERATE_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return agent_id, message


def _clean_commit_message(output: str) -> str:
    """Strip wrapping markdown code fences and surrounding whitespace."""
    lines = output.strip().splitlines()
    if lines and _FENCE_LINE.match(lines[0].strip()):
        lines = lines[1:]
        if lines and _FENCE_LINE.match(lines[-1].strip()):
            lines = lines[:-1]
    return "\n".join(lines).strip()[:_COMMIT_MESSAGE_MAX_CHARS]


def _commit_message_changes(path: Path, repo_status: GitStatusRead, settings: Settings) -> str:
    staged = bool(repo_status.staged) or bool(repo_status.conflicted)
    args = ["diff", "--cached"] if staged else ["diff"]
    result = _run_git(path, args, timeout=settings.git_status_timeout_seconds)
    diff = result.stdout if result.returncode == 0 else ""
    if diff.strip():
        return diff[: settings.agent_commit_message_diff_max_bytes]

    paths = [change.path for change in repo_status.staged]
    paths += [change.path for change in repo_status.unstaged]
    paths += list(repo_status.untracked)
    return "Changed files:\n" + "\n".join(dict.fromkeys(paths))


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


def get_current_pull_request(
    db: Session, owner: User, project_id: int, settings: Settings
) -> GitPullRequestStatusRead:
    """Return the pull request for the current branch, or ``None`` when absent.

    Every failure (no GitHub remote, no ``gh`` CLI, unauthenticated, no open
    pull request) resolves to an empty result so the UI can show an empty state
    instead of an error.
    """
    path = _project_repository(db, owner, project_id, settings)
    if _github_remote(path, settings) is None:
        return GitPullRequestStatusRead()

    if not _current_branch(path, settings):
        return GitPullRequestStatusRead()

    result = _try_run_gh(
        path,
        [
            "pr",
            "view",
            "--json",
            "number,title,url,state,isDraft,headRefName,baseRefName",
        ],
        timeout=settings.github_pr_timeout_seconds,
    )
    if result is None or result.returncode != 0:
        return GitPullRequestStatusRead()

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return GitPullRequestStatusRead()
    if not isinstance(data, dict) or "number" not in data:
        return GitPullRequestStatusRead()
    try:
        number = int(data["number"])
    except (TypeError, ValueError):
        return GitPullRequestStatusRead()

    return GitPullRequestStatusRead(
        pull_request=GitPullRequestSummary(
            number=number,
            title=str(data.get("title", "")),
            url=str(data.get("url", "")),
            state=str(data.get("state", "")),
            is_draft=bool(data.get("isDraft", False)),
            head=data.get("headRefName") or None,
            base=data.get("baseRefName") or None,
        )
    )


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


def _upstream_branch(path: Path, branch: str, settings: Settings) -> str | None:
    result = _run_git(
        path,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{branch}@{{upstream}}"],
        timeout=settings.git_status_timeout_seconds,
    )
    upstream = result.stdout.strip()
    return upstream if result.returncode == 0 and upstream else None


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


def _try_run_gh(
    path: Path, args: list[str], *, timeout: int
) -> subprocess.CompletedProcess[str] | None:
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
    except (OSError, subprocess.TimeoutExpired):
        return None


def _raise_status_error(result: subprocess.CompletedProcess[str]) -> None:
    if "not a git repository" in result.stderr.lower():
        raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)
    raise api_error(ErrorCode.GIT_COMMAND_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
