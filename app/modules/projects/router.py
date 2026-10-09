from fastapi import APIRouter, Query, status

from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.projects import service
from app.modules.projects.models import Project
from app.modules.projects.schemas import (
    DirectoryListing,
    FileContentRead,
    FileTreeRead,
    FileWriteRequest,
    GithubProjectCreate,
    LocalProjectCreate,
    ProjectRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead], responses=error_responses(401, 403))
def list_projects(
    current_user: CurrentUser,
    db: DbDep,
    limit: int = Query(service.DEFAULT_LIST_LIMIT, ge=1, le=service.MAX_LIST_LIMIT),
    offset: int = Query(0, ge=0),
) -> list[Project]:
    return service.list_projects(db, current_user, limit=limit, offset=offset)


@router.post(
    "/github",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 401, 403, 409, 422),
)
def create_github_project(
    payload: GithubProjectCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> Project:
    return service.create_github_project(db, current_user, payload, settings)


@router.post(
    "/local",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 401, 403, 409, 422),
)
def create_local_project(
    payload: LocalProjectCreate,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> Project:
    return service.create_local_project(db, current_user, payload)


@router.get(
    "/browse",
    response_model=DirectoryListing,
    responses=error_responses(400, 401, 403),
)
def browse_directories(
    current_user: CurrentUser,
    path: str | None = Query(None, max_length=4096),
) -> DirectoryListing:
    return service.browse_directories(path)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    responses=error_responses(401, 403, 404),
)
def read_project(project_id: int, current_user: CurrentUser, db: DbDep) -> Project:
    return service.get_project(db, current_user, project_id)


@router.get(
    "/{project_id}/files",
    response_model=FileTreeRead,
    responses=error_responses(400, 401, 403, 404),
)
def list_project_files(project_id: int, current_user: CurrentUser, db: DbDep) -> FileTreeRead:
    return service.list_files(db, current_user, project_id)


@router.get(
    "/{project_id}/file",
    response_model=FileContentRead,
    responses=error_responses(400, 401, 403, 404),
)
def read_project_file(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    path: str = Query(min_length=1, max_length=4096),
) -> FileContentRead:
    return service.read_file(db, current_user, project_id, path)


@router.put(
    "/{project_id}/file",
    response_model=FileContentRead,
    responses=error_responses(400, 401, 403, 404, 422),
)
def write_project_file(
    project_id: int,
    payload: FileWriteRequest,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> FileContentRead:
    return service.write_file(db, current_user, project_id, payload.path, payload.content)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
)
def delete_project(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> None:
    service.delete_project(db, current_user, project_id, settings)
