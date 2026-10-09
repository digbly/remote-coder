from fastapi import APIRouter

from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.git import service
from app.modules.git.schemas import (
    GitBranchCreate,
    GitBranchesRead,
    GitCommitCreate,
    GitCommitRead,
    GitPathsUpdate,
    GitPullRequestCreate,
    GitPullRequestRead,
    GitStatusRead,
    GitWorktreeRead,
)

router = APIRouter(prefix="/projects", tags=["git"])


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
) -> GitStatusRead:
    return service.get_git_status(db, current_user, project_id, settings)


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
) -> GitStatusRead:
    return service.stage_paths(db, current_user, project_id, payload.paths, settings)


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
) -> GitStatusRead:
    return service.unstage_paths(db, current_user, project_id, payload.paths, settings)


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
) -> GitStatusRead:
    return service.stage_all(db, current_user, project_id, settings)


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
) -> GitStatusRead:
    return service.unstage_all(db, current_user, project_id, settings)


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
) -> GitStatusRead:
    return service.discard_paths(db, current_user, project_id, payload.paths, settings)


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
) -> GitStatusRead:
    return service.push_branch(db, current_user, project_id, settings)


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
) -> GitStatusRead:
    return service.pull_branch(db, current_user, project_id, settings)


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
) -> GitBranchesRead:
    return service.list_branches(db, current_user, project_id, settings)


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
) -> GitStatusRead:
    return service.create_branch(db, current_user, project_id, payload.name, settings)


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
) -> GitStatusRead:
    return service.checkout_branch(db, current_user, project_id, payload.name, settings)


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
) -> GitCommitRead:
    return service.commit_staged(db, current_user, project_id, payload.message, settings)


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
) -> GitPullRequestRead:
    return service.create_pull_request(db, current_user, project_id, payload, settings)
