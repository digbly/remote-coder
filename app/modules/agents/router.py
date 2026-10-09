from fastapi import APIRouter, status

from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.agents import service
from app.modules.agents.schemas import (
    AgentDefaultResponse,
    AgentDefaultUpdate,
    AgentListResponse,
    AgentModelsResponse,
    AgentSettingItem,
    AgentSettingsResponse,
    AgentSettingUpdate,
)
from app.modules.auth.deps import CsrfDep, CurrentUser

router = APIRouter(tags=["agents"])

_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT


@router.get("/agents", responses=error_responses(401))
def list_agents(current_user: CurrentUser, db: DbDep) -> AgentListResponse:
    return AgentListResponse(agents=service.list_agents(db, current_user))


@router.get("/agents/{agent_id}/models", responses=error_responses(401, 404))
async def list_agent_models(
    agent_id: str,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> AgentModelsResponse:
    models = await service.list_models(
        db, current_user, agent_id, settings.agent_models_cache_ttl_seconds
    )
    if models is None:
        raise api_error(ErrorCode.AGENT_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)
    return AgentModelsResponse(models=models)


@router.get("/agents/settings", responses=error_responses(401))
def read_agent_settings(current_user: CurrentUser, db: DbDep) -> AgentSettingsResponse:
    agent_settings = service.get_agent_settings(db, current_user)
    commit_args = service.commit_message_args_map(db, current_user)
    return AgentSettingsResponse(
        settings=[
            AgentSettingItem(
                agent_id=setting.agent_id,
                command=setting.command,
                args=setting.args,
                commit_args=commit_args.get(setting.agent_id, ""),
            )
            for setting in agent_settings
        ],
        default_agent_id=service.get_default_agent_id(db, current_user),
    )


@router.put(
    "/agents/default",
    responses=error_responses(401, 403, 404, 422),
)
def update_default_agent(
    payload: AgentDefaultUpdate,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> AgentDefaultResponse:
    if payload.agent_id is not None and not service.agent_exists(payload.agent_id):
        raise api_error(ErrorCode.AGENT_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    default_agent_id = service.set_default_agent(db, current_user, payload.agent_id)
    return AgentDefaultResponse(default_agent_id=default_agent_id)


@router.put(
    "/agents/settings/{agent_id}",
    responses=error_responses(401, 403, 404, 422),
)
def update_agent_setting(
    agent_id: str,
    payload: AgentSettingUpdate,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> AgentSettingItem:
    if not service.agent_exists(agent_id):
        raise api_error(ErrorCode.AGENT_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)
    if not service.valid_command(payload.command):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=_UNPROCESSABLE)
    if not service.valid_args(payload.args):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=_UNPROCESSABLE)
    if not service.valid_args(payload.commit_args):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=_UNPROCESSABLE)

    try:
        setting = service.save_agent_setting(
            db, current_user, agent_id, payload.command, payload.args, payload.commit_args
        )
    except ValueError as exc:
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=_UNPROCESSABLE) from exc
    commit_args = service.get_commit_message_args(db, current_user, agent_id) or ""
    return AgentSettingItem(
        agent_id=setting.agent_id,
        command=setting.command,
        args=setting.args,
        commit_args=commit_args,
    )
