from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.git import service
from app.modules.git.schemas import (
    GitBranchCreate,
    GitBranchesRead,
    GitCommitCreate,
    GitCommitMessageRead,
    GitCommitRead,
    GitDiffRead,
    GitPathsUpdate,
    GitPullRequestCreate,
    GitPullRequestRead,
    GitPullRequestStatusRead,
    GitStatusRead,
    GitWorktreeCreate,
    GitWorktreeRead,
)

router = APIRouter(prefix="/projects", tags=["git"])

# Selects a linked worktree by name; absent means the primary worktree.
WorktreeQuery = Annotated[str | None, Query(max_length=255)]


@router.get(
    "/{project_id}/git/status",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def read_git_status(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.get_git_status(db, current_user, project_id, settings, worktree)


@router.get(
    "/{project_id}/git/diff",
    response_model=GitDiffRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def read_git_diff(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    path: str = Query(min_length=1, max_length=4096),
    staged: bool = False,
    orig_path: str | None = Query(default=None, max_length=4096),
    worktree: WorktreeQuery = None,
) -> GitDiffRead:
    return service.get_file_diff(
        db, current_user, project_id, path, staged, orig_path, settings, worktree
    )


@router.post(
    "/{project_id}/git/stage",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def stage_paths(
    project_id: int,
    payload: GitPathsUpdate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.stage_paths(db, current_user, project_id, payload.paths, settings, worktree)


@router.post(
    "/{project_id}/git/unstage",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def unstage_paths(
    project_id: int,
    payload: GitPathsUpdate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.unstage_paths(db, current_user, project_id, payload.paths, settings, worktree)


@router.post(
    "/{project_id}/git/stage-all",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def stage_all(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.stage_all(db, current_user, project_id, settings, worktree)


@router.post(
    "/{project_id}/git/unstage-all",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def unstage_all(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.unstage_all(db, current_user, project_id, settings, worktree)


@router.post(
    "/{project_id}/git/discard",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def discard_paths(
    project_id: int,
    payload: GitPathsUpdate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.discard_paths(db, current_user, project_id, payload.paths, settings, worktree)


@router.post(
    "/{project_id}/git/push",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def push_branch(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.push_branch(db, current_user, project_id, settings, worktree)


@router.post(
    "/{project_id}/git/pull",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def pull_branch(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.pull_branch(db, current_user, project_id, settings, worktree)


@router.get(
    "/{project_id}/git/worktrees",
    response_model=list[GitWorktreeRead],
    responses=error_responses(400, 401, 403, 404, 500),
)
def list_worktrees(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> list[GitWorktreeRead]:
    return service.list_worktrees(db, current_user, project_id, settings)


@router.post(
    "/{project_id}/git/worktrees",
    response_model=GitWorktreeRead,
    responses=error_responses(400, 401, 403, 404, 409, 422, 500),
)
def create_worktree(
    project_id: int,
    payload: GitWorktreeCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> GitWorktreeRead:
    return service.create_worktree(db, current_user, project_id, payload, settings)


@router.delete(
    "/{project_id}/git/worktrees/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def delete_worktree(
    project_id: int,
    name: str,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> None:
    service.delete_worktree(db, current_user, project_id, name, settings)


@router.get(
    "/{project_id}/git/branches",
    response_model=GitBranchesRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def list_branches(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    worktree: WorktreeQuery = None,
) -> GitBranchesRead:
    return service.list_branches(db, current_user, project_id, settings, worktree)


@router.post(
    "/{project_id}/git/branches",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def create_branch(
    project_id: int,
    payload: GitBranchCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.create_branch(db, current_user, project_id, payload.name, settings, worktree)


@router.post(
    "/{project_id}/git/checkout",
    response_model=GitStatusRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def checkout_branch(
    project_id: int,
    payload: GitBranchCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitStatusRead:
    return service.checkout_branch(db, current_user, project_id, payload.name, settings, worktree)


@router.post(
    "/{project_id}/git/commit",
    response_model=GitCommitRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def commit_staged(
    project_id: int,
    payload: GitCommitCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitCommitRead:
    return service.commit_staged(db, current_user, project_id, payload.message, settings, worktree)


@router.post(
    "/{project_id}/git/commit-message",
    response_model=GitCommitMessageRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def generate_commit_message(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitCommitMessageRead:
    agent_id, message = service.generate_commit_message(
        db, current_user, project_id, settings, worktree
    )
    return GitCommitMessageRead(message=message, agent_id=agent_id)


@router.post(
    "/{project_id}/git/pull-request",
    response_model=GitPullRequestRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def create_pull_request(
    project_id: int,
    payload: GitPullRequestCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitPullRequestRead:
    return service.create_pull_request(db, current_user, project_id, payload, settings, worktree)


@router.post(
    "/{project_id}/git/pull-request/merge",
    response_model=GitPullRequestStatusRead,
    responses=error_responses(400, 401, 403, 404, 422, 500),
)
def merge_pull_request(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
    worktree: WorktreeQuery = None,
) -> GitPullRequestStatusRead:
    return service.merge_pull_request(db, current_user, project_id, settings, worktree)


@router.get(
    "/{project_id}/git/pull-request",
    response_model=GitPullRequestStatusRead,
    responses=error_responses(400, 401, 403, 404, 500),
)
def read_current_pull_request(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    worktree: WorktreeQuery = None,
) -> GitPullRequestStatusRead:
    return service.get_current_pull_request(db, current_user, project_id, settings, worktree)
