import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import TTLCache
from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.agents import service as agent_service
from app.modules.auth.models import User
from app.modules.git.schemas import (
    GitBranchesRead,
    GitChange,
    GitCommitRead,
    GitDiffRead,
    GitPullRequestCreate,
    GitPullRequestRead,
    GitPullRequestStatusRead,
    GitPullRequestSummary,
    GitStatusRead,
    GitWorktreeCreate,
    GitWorktreeRead,
)
from app.modules.projects.service import MAX_FILE_BYTES, get_project, parse_github_repository

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
_WORKTREE_NAME_RE = re.compile(r"^(?!-)[A-Za-z0-9._-]{1,255}$")
_DEFAULT_BRANCHES = ("main", "master")
_WORKTREE_BRANCH_PREFIX = "refs/heads/"

# The status endpoint is polled frequently and each read spawns several git
# subprocesses, so successful reads are memoized for a short TTL. Every write
# path drops the affected repository's entries immediately, so a mutation made
# through the API is never served stale. A key is ``<repo path>\0<name>`` so a
# repository can be invalidated as one prefix.
_git_cache: TTLCache = TTLCache()

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


def get_git_status(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> GitStatusRead:
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    return _git_cache.get_or_set(
        _cache_key(path, "status"),
        settings.git_status_cache_ttl_seconds,
        lambda: _read_status(path, settings),
    )


def _read_status(path: Path, settings: Settings) -> GitStatusRead:
    result = _run_git(path, _STATUS_ARGS, timeout=settings.git_status_timeout_seconds)
    if result.returncode != 0:
        _raise_status_error(result)
    status = parse_status(result.stdout)
    status.base = _cached_default_branch(path, settings)
    return status


def get_file_diff(
    db: Session,
    owner: User,
    project_id: int,
    path: str,
    staged: bool,
    orig_path: str | None,
    settings: Settings,
    worktree: str | None = None,
) -> GitDiffRead:
    """Return the old and new content of a single changed file for the diff view.

    A staged diff compares ``HEAD`` with the index; an unstaged diff compares the
    index (falling back to ``HEAD``) with the working tree. Rename targets use the
    original path on the "old" side. Untracked files diff against empty content.
    """
    repo = _resolve_repository(db, owner, project_id, settings, worktree)
    _validate_paths([path])
    old_path = orig_path if orig_path else path
    if orig_path:
        _validate_paths([orig_path])

    if staged:
        old = _read_revision(repo, "HEAD", old_path, settings) or ""
        new = _read_index(repo, path, settings) or ""
    else:
        index = _read_index(repo, path, settings)
        if index is not None:
            old = index
        else:
            old = _read_revision(repo, "HEAD", old_path, settings) or ""
        new = _read_worktree(repo, path, settings)

    return GitDiffRead(path=path, orig_path=orig_path, old_content=old, new_content=new)


def _read_revision(repo: Path, rev: str, file: str, settings: Settings) -> str | None:
    """Return the content of ``file`` at ``rev``, or ``None`` when it is absent."""
    result = _run_git(repo, ["show", f"{rev}:{file}"], timeout=settings.git_status_timeout_seconds)
    if result.returncode != 0:
        return None
    return _decode_blob(result.stdout)


def _read_index(repo: Path, file: str, settings: Settings) -> str | None:
    """Return the content of ``file`` in the index, or ``None`` when it is absent."""
    return _read_revision(repo, "", file, settings)


def _read_worktree(repo: Path, file: str, settings: Settings) -> str:
    """Return the working tree content of ``file``, or ``""`` when it is missing.

    A symlink is diffed as its link target (what git stores as the blob) instead
    of following it, so the read can never escape the repository.
    """
    target = repo / file
    if target.is_symlink():
        try:
            return os.readlink(target)
        except OSError:
            return ""
    if not target.is_file():
        return ""
    try:
        if not target.resolve().is_relative_to(repo.resolve()):
            raise api_error(ErrorCode.GIT_INVALID_PATH, status_code=status.HTTP_400_BAD_REQUEST)
        data = target.read_bytes()
    except OSError:
        return ""
    if len(data) > MAX_FILE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)
    if b"\x00" in data:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST) from exc


def _decode_blob(output: str) -> str:
    """Reject a binary revision blob so the editor never renders it."""
    if len(output) > MAX_FILE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=status.HTTP_400_BAD_REQUEST)
    if "\x00" in output:
        raise api_error(ErrorCode.FILE_BINARY, status_code=status.HTTP_400_BAD_REQUEST)
    return output


def stage_paths(
    db: Session,
    owner: User,
    project_id: int,
    paths: list[str],
    settings: Settings,
    worktree: str | None = None,
) -> GitStatusRead:
    """Stage the given paths, then return the refreshed status."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    _validate_paths(paths)

    result = _run_git(path, ["add", "--", *paths], timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)
    _invalidate_repo(path)
    return _read_status(path, settings)


def stage_all(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> GitStatusRead:
    """Stage every change in the working tree, then return the refreshed status."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)

    result = _run_git(path, ["add", "-A"], timeout=settings.git_commit_timeout_seconds)
    _ensure_success(result, ErrorCode.GIT_COMMAND_FAILED)
    _invalidate_repo(path)
    return _read_status(path, settings)


def unstage_paths(
    db: Session,
    owner: User,
    project_id: int,
    paths: list[str],
    settings: Settings,
    worktree: str | None = None,
) -> GitStatusRead:
    """Move the given paths back to the working tree, then return the status."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    _validate_paths(paths)

    _unstage(path, paths, settings)
    _invalidate_repo(path)
    return _read_status(path, settings)


def unstage_all(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> GitStatusRead:
    """Move every staged path back to the working tree."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    current = _read_status(path, settings)

    _unstage(path, [change.path for change in current.staged], settings)
    _invalidate_repo(path)
    return _read_status(path, settings)


def discard_paths(
    db: Session,
    owner: User,
    project_id: int,
    paths: list[str],
    settings: Settings,
    worktree: str | None = None,
) -> GitStatusRead:
    """Discard working tree and index changes for the given paths.

    Paths present in ``HEAD`` are restored from it; every other path is
    removed from the index (when staged) and from disk. Rename targets may be
    passed alongside their original path so both sides are reverted.
    """
    path = _resolve_repository(db, owner, project_id, settings, worktree)
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

    _invalidate_repo(path)
    return _read_status(path, settings)


def pull_branch(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> GitStatusRead:
    """Fast-forward the current branch from its upstream."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
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
    _invalidate_repo(path)
    return _read_status(path, settings)


def push_branch(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> GitStatusRead:
    """Push the current branch, setting its upstream on the first push."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
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
    _invalidate_repo(path)
    return _read_status(path, settings)


def list_branches(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> GitBranchesRead:
    """Return the current branch together with every local branch."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    return _git_cache.get_or_set(
        _cache_key(path, "branches"),
        settings.git_branches_cache_ttl_seconds,
        lambda: _read_branches(path, settings),
    )


def _read_branches(path: Path, settings: Settings) -> GitBranchesRead:
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
    worktrees = _cached_worktrees(path, settings)
    if worktrees is None:
        raise api_error(
            ErrorCode.GIT_COMMAND_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return worktrees


def _read_worktrees(path: Path, settings: Settings) -> list[GitWorktreeRead] | None:
    """Return the parsed worktree registry, or ``None`` when git reports failure."""
    result = _run_git(
        path,
        ["worktree", "list", "--porcelain"],
        timeout=settings.git_status_timeout_seconds,
    )
    if result.returncode != 0:
        return None
    return parse_worktrees(result.stdout, primary=path)


def _cached_worktrees(path: Path, settings: Settings) -> list[GitWorktreeRead] | None:
    return _git_cache.get_or_set(
        _cache_key(path, "worktrees"),
        settings.git_worktrees_cache_ttl_seconds,
        lambda: _read_worktrees(path, settings),
    )


def find_worktree(path: Path, name: str, settings: Settings) -> Path | None:
    """Resolve a worktree directory by its basename, or ``None`` if unknown.

    The name comes from the client, so it is matched against git's own worktree
    registry instead of being treated as a filesystem path.
    """
    try:
        entry = _worktree_entry(path, name, settings)
    except HTTPException:
        return None
    return Path(entry.path) if entry is not None else None


def _worktree_entry(path: Path, name: str, settings: Settings) -> GitWorktreeRead | None:
    """Return the registered worktree named ``name``, or ``None`` if absent."""
    worktrees = _cached_worktrees(path, settings)
    if worktrees is None:
        return None
    return next((worktree for worktree in worktrees if worktree.name == name), None)


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


def create_worktree(
    db: Session, owner: User, project_id: int, payload: GitWorktreeCreate, settings: Settings
) -> GitWorktreeRead:
    """Create a worktree under the configured root and return it.

    A new branch is created from ``HEAD`` when ``payload.create_branch`` is set;
    otherwise an existing branch is checked out into the new worktree.
    """
    path = _project_repository(db, owner, project_id, settings)

    name = payload.name.strip()
    branch = payload.branch.strip()
    if not _WORKTREE_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise api_error(ErrorCode.GIT_WORKTREE_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    if not _valid_branch_name(branch):
        raise api_error(ErrorCode.GIT_BRANCH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    root = _worktrees_root(settings)
    target = (root / str(project_id) / name).resolve()
    if not target.is_relative_to(root):
        raise api_error(ErrorCode.GIT_WORKTREE_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    if target.exists():
        raise api_error(ErrorCode.GIT_WORKTREE_EXISTS, status_code=status.HTTP_409_CONFLICT)

    target.parent.mkdir(parents=True, exist_ok=True)

    args = ["worktree", "add"]
    if payload.create_branch:
        args += ["-b", branch, str(target)]
    else:
        args += [str(target), branch]

    result = _run_git(
        path,
        args,
        timeout=settings.git_commit_timeout_seconds,
        error_code=ErrorCode.GIT_WORKTREE_FAILED,
    )
    if result.returncode != 0:
        raise api_error(ErrorCode.GIT_WORKTREE_FAILED, status_code=status.HTTP_400_BAD_REQUEST)

    _invalidate_repo(path)
    return GitWorktreeRead(name=target.name, path=str(target), branch=branch, is_primary=False)


def delete_worktree(
    db: Session, owner: User, project_id: int, name: str, settings: Settings
) -> None:
    """Remove a linked git worktree by name.

    The name comes from the client, so it is matched against git's own worktree
    registry instead of being treated as a filesystem path. The primary
    worktree cannot be removed.
    """
    path = _project_repository(db, owner, project_id, settings)
    target = _worktree_entry(path, name.strip(), settings)
    if target is None:
        raise api_error(ErrorCode.GIT_WORKTREE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)
    if target.is_primary:
        raise api_error(ErrorCode.GIT_WORKTREE_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    removal = _run_git(
        path,
        ["worktree", "remove", target.path],
        timeout=settings.git_commit_timeout_seconds,
        error_code=ErrorCode.GIT_WORKTREE_DELETE_FAILED,
    )
    if removal.returncode != 0:
        raise api_error(
            ErrorCode.GIT_WORKTREE_DELETE_FAILED, status_code=status.HTTP_400_BAD_REQUEST
        )
    _invalidate_repo(path)


def create_branch(
    db: Session,
    owner: User,
    project_id: int,
    name: str,
    settings: Settings,
    worktree: str | None = None,
) -> GitStatusRead:
    """Create and check out a new branch."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    _checkout(path, name.strip(), create=True, settings=settings)
    _invalidate_repo(path)
    return _read_status(path, settings)


def checkout_branch(
    db: Session,
    owner: User,
    project_id: int,
    name: str,
    settings: Settings,
    worktree: str | None = None,
) -> GitStatusRead:
    """Switch to an existing local branch."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)
    _checkout(path, name.strip(), create=False, settings=settings)
    _invalidate_repo(path)
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
    db: Session,
    owner: User,
    project_id: int,
    message: str,
    settings: Settings,
    worktree: str | None = None,
) -> GitCommitRead:
    """Commit whatever is already staged in the index."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)

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
    _invalidate_repo(path)

    revision = _run_git(
        path, ["rev-parse", "--short", "HEAD"], timeout=settings.git_commit_timeout_seconds
    )
    commit_hash = revision.stdout.strip() if revision.returncode == 0 else ""
    return GitCommitRead(commit=commit_hash, branch=current.branch)


def generate_commit_message(
    db: Session, owner: User, project_id: int, settings: Settings, worktree: str | None = None
) -> tuple[str, str]:
    """Generate a commit message for the current changes using the default agent.

    Returns ``(agent_id, message)``. The staged diff is preferred so the message
    describes what will actually be committed; otherwise the working tree diff
    (or the changed-file list) is used.
    """
    path = _resolve_repository(db, owner, project_id, settings, worktree)
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
    db: Session,
    owner: User,
    project_id: int,
    payload: GitPullRequestCreate,
    settings: Settings,
    worktree: str | None = None,
) -> GitPullRequestRead:
    """Push a branch and open a GitHub pull request for it via the ``gh`` CLI."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)

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
    _invalidate_repo(path)
    return GitPullRequestRead(url=url, branch=branch, base=base)


def get_current_pull_request(
    db: Session,
    owner: User,
    project_id: int,
    settings: Settings,
    worktree: str | None = None,
) -> GitPullRequestStatusRead:
    """Return the pull request for the current branch, or ``None`` when absent.

    Every failure (no GitHub remote, no ``gh`` CLI, unauthenticated, no open
    pull request) resolves to an empty result so the UI can show an empty state
    instead of an error.
    """
    primary = _project_repository(db, owner, project_id, settings)
    path = _path_for_worktree(primary, worktree, settings)
    return _git_cache.get_or_set(
        _cache_key(path, "pull-request"),
        settings.git_pull_request_cache_ttl_seconds,
        lambda: _read_pull_request(path, primary, settings),
    )


def _read_pull_request(path: Path, primary: Path, settings: Settings) -> GitPullRequestStatusRead:
    branch = _current_branch(path, settings)
    base = _cached_default_branch(path, settings)
    status_read = GitPullRequestStatusRead(
        branch=branch or None,
        is_default_branch=bool(branch) and branch == base,
        is_primary_worktree=path.resolve() == primary.resolve(),
    )

    if _github_remote(path, settings) is None:
        return status_read

    if not branch:
        return status_read

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
        return status_read

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return status_read
    if not isinstance(data, dict) or "number" not in data:
        return status_read
    try:
        number = int(data["number"])
    except (TypeError, ValueError):
        return status_read

    status_read.pull_request = GitPullRequestSummary(
        number=number,
        title=str(data.get("title", "")),
        url=str(data.get("url", "")),
        state=str(data.get("state", "")),
        is_draft=bool(data.get("isDraft", False)),
        head=data.get("headRefName") or None,
        base=data.get("baseRefName") or None,
    )
    return status_read


def merge_pull_request(
    db: Session,
    owner: User,
    project_id: int,
    settings: Settings,
    worktree: str | None = None,
) -> GitPullRequestStatusRead:
    """Merge the open pull request for the current branch via the ``gh`` CLI."""
    path = _resolve_repository(db, owner, project_id, settings, worktree)

    if _github_remote(path, settings) is None:
        raise api_error(ErrorCode.GIT_REMOTE_MISSING, status_code=status.HTTP_400_BAD_REQUEST)

    if not _current_branch(path, settings):
        raise api_error(ErrorCode.GIT_PULL_REQUEST_FAILED, status_code=status.HTTP_400_BAD_REQUEST)

    merged = _run_gh(
        path,
        ["pr", "merge", "--merge"],
        timeout=settings.github_pr_timeout_seconds,
    )
    if merged.returncode != 0:
        raise api_error(ErrorCode.GIT_PULL_REQUEST_FAILED, status_code=status.HTTP_400_BAD_REQUEST)

    _invalidate_repo(path)
    return get_current_pull_request(db, owner, project_id, settings, worktree)


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

    inside = _git_cache.get_or_set(
        _cache_key(path, "repo"),
        settings.git_repo_cache_ttl_seconds,
        lambda: _is_repository(path, settings),
    )
    if not inside:
        raise api_error(ErrorCode.GIT_NOT_A_REPOSITORY, status_code=status.HTTP_400_BAD_REQUEST)
    return path


def _is_repository(path: Path, settings: Settings) -> bool:
    result = _run_git(
        path, ["rev-parse", "--is-inside-work-tree"], timeout=settings.git_status_timeout_seconds
    )
    return result.returncode == 0


def _resolve_repository(
    db: Session,
    owner: User,
    project_id: int,
    settings: Settings,
    worktree: str | None = None,
) -> Path:
    """Resolve the repository path for a project, honoring an optional worktree.

    ``worktree`` is matched against git's own worktree registry; an unknown name
    is treated as a missing resource rather than a filesystem path.
    """
    primary = _project_repository(db, owner, project_id, settings)
    return _path_for_worktree(primary, worktree, settings)


def _path_for_worktree(primary: Path, worktree: str | None, settings: Settings) -> Path:
    if not worktree:
        return primary
    target = find_worktree(primary, worktree.strip(), settings)
    if target is None:
        raise api_error(ErrorCode.GIT_WORKTREE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)
    return target


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


def _worktrees_root(settings: Settings) -> Path:
    return Path(settings.worktrees_root).expanduser().resolve()


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
            path,
            ["rev-parse", "--verify", candidate],
            timeout=settings.git_status_timeout_seconds,
        )
        if exists.returncode == 0:
            return candidate
    return _DEFAULT_BRANCHES[0]


def _cached_default_branch(path: Path, settings: Settings) -> str:
    """Return the default branch, memoizing the stable result per repository.

    Callers on the polling path (git status) use this; the one-shot PR creation
    path resolves directly via ``_default_branch``.
    """
    return _git_cache.get_or_set(
        _cache_key(path, "base"),
        settings.git_repo_cache_ttl_seconds,
        lambda: _default_branch(path, settings),
    )


def _cache_key(path: Path, name: str) -> str:
    return f"{path.resolve()}\x00{name}"


def _invalidate_repo(path: Path) -> None:
    """Drop every cached git read for one repository/worktree after a mutation."""
    _git_cache.invalidate_prefix(f"{path.resolve()}\x00")


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
