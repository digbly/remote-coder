from fastapi import APIRouter, status

from app.core.deps import DbDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.agents import service
from app.modules.agents.schemas import (
    AgentListResponse,
    AgentSettingItem,
    AgentSettingsResponse,
    AgentSettingUpdate,
)
from app.modules.auth.deps import CsrfDep, CurrentUser

router = APIRouter(tags=["agents"])

_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT


@router.get("/agents", responses=error_responses(401))
def list_agents(
    _current_user: CurrentUser,
    commands: str = "",
) -> AgentListResponse:
    requested = [command.strip() for command in commands.split(",") if command.strip()]
    return AgentListResponse(agents=service.detect_agents(requested[: service.MAX_AGENTS]))


@router.get("/agents/settings", responses=error_responses(401))
def read_agent_settings(current_user: CurrentUser, db: DbDep) -> AgentSettingsResponse:
    settings = service.get_agent_settings(db, current_user)
    return AgentSettingsResponse(
        settings=[
            AgentSettingItem(agent_id=setting.agent_id, command=setting.command, args=setting.args)
            for setting in settings
        ]
    )


@router.put(
    "/agents/settings/{agent_id}",
    responses=error_responses(401, 403, 422),
)
def update_agent_setting(
    agent_id: str,
    payload: AgentSettingUpdate,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> AgentSettingItem:
    if not service.valid_command(agent_id) or not service.valid_command(payload.command):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=_UNPROCESSABLE)
    if not service.valid_args(payload.args):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=_UNPROCESSABLE)

    setting = service.save_agent_setting(db, current_user, agent_id, payload.command, payload.args)
    return AgentSettingItem(agent_id=setting.agent_id, command=setting.command, args=setting.args)
