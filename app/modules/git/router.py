from fastapi import APIRouter

from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth.deps import CurrentUser
from app.modules.git import service
from app.modules.git.schemas import GitStatusRead

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
