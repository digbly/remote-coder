from fastapi import APIRouter

from app.core.errors import error_responses
from app.modules.agents.schemas import AgentListResponse
from app.modules.agents.service import MAX_AGENTS, detect_agents
from app.modules.auth.deps import CurrentUser

router = APIRouter(tags=["agents"])


@router.get("/agents", responses=error_responses(401))
def list_agents(
    _current_user: CurrentUser,
    commands: str = "",
) -> AgentListResponse:
    requested = [command.strip() for command in commands.split(",") if command.strip()]
    return AgentListResponse(agents=detect_agents(requested[:MAX_AGENTS]))
