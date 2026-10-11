from fastapi import APIRouter

from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.agent_sessions import service
from app.modules.agent_sessions.schemas import AgentSessionListResponse
from app.modules.auth.deps import CurrentUser

router = APIRouter(prefix="/projects", tags=["agent-sessions"])


@router.get(
    "/{project_id}/agent-sessions",
    response_model=AgentSessionListResponse,
    responses=error_responses(401, 403, 404),
)
def list_agent_sessions(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    worktree: str | None = None,
) -> AgentSessionListResponse:
    return AgentSessionListResponse(
        sessions=service.list_project_sessions(db, current_user, project_id, worktree, settings)
    )
