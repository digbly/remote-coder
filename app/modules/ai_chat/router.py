from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import sessionmaker

from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.ai_changes.router import router as ai_changes_router
from app.modules.ai_chat import approvals, service, skills, turns
from app.modules.ai_chat.models import MessageStatus
from app.modules.ai_chat.schemas import (
    ChatTurnRequest,
    CommandApprovalDecision,
    CommandPermissionRead,
    ConversationDetail,
    ConversationListResponse,
    SkillListResponse,
    SkillRead,
)
from app.modules.ai_providers import service as provider_service
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.projects import service as project_service

router = APIRouter(prefix="/projects/{project_id}/ai-chat", tags=["ai-chat"])
_CHAT_ERRORS = error_responses(401, 403, 404, 413, 422, 502, 503)


@router.get("/command-permission", response_model=CommandPermissionRead)
def get_command_permission(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
) -> CommandPermissionRead:
    project_service.get_project(db, current_user, project_id)
    return CommandPermissionRead(mode=service.get_command_permission(db, current_user.id))


@router.put("/command-permission", response_model=CommandPermissionRead)
def update_command_permission(
    project_id: int,
    payload: CommandPermissionRead,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> CommandPermissionRead:
    project_service.get_project(db, current_user, project_id)
    return CommandPermissionRead(
        mode=service.set_command_permission(db, current_user.id, payload.mode)
    )


@router.post(
    "/approvals/{approval_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
)
async def decide_approval(
    project_id: int,
    approval_id: str,
    payload: CommandApprovalDecision,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> None:
    project_service.get_project(db, current_user, project_id)
    if not approvals.resolve_approval(
        approval_id,
        current_user.id,
        project_id,
        payload.approved,
    ):
        raise api_error(ErrorCode.AI_APPROVAL_NOT_FOUND, status_code=404)


@router.get("/skills", response_model=SkillListResponse, responses=error_responses(401, 403, 404))
def list_skills(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
) -> SkillListResponse:
    project = project_service.get_project(db, current_user, project_id)
    return SkillListResponse(
        skills=[
            SkillRead(slug=skill.slug, name=skill.name, description=skill.description)
            for skill in skills.list_skills(Path(project.path))
        ]
    )


@router.get("/conversations", response_model=ConversationListResponse, responses=_CHAT_ERRORS)
def list_conversations(
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
) -> ConversationListResponse:
    return ConversationListResponse(
        conversations=service.list_conversations(db, current_user, project_id)
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    responses=_CHAT_ERRORS,
)
def get_conversation(
    project_id: int,
    conversation_id: str,
    current_user: CurrentUser,
    db: DbDep,
) -> ConversationDetail:
    return service.get_conversation_detail(db, current_user, project_id, conversation_id)


@router.post(
    "/messages/stream",
    status_code=status.HTTP_200_OK,
    responses=_CHAT_ERRORS,
)
async def stream_message(
    project_id: int,
    payload: ChatTurnRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> StreamingResponse:
    project = project_service.get_project(db, current_user, project_id)
    if payload.conversation_id is not None:
        service.require_conversation(db, current_user.id, project_id, payload.conversation_id)
    models = await provider_service.list_models(db, current_user.id, payload.provider_id, settings)
    if not any(model.id == payload.model_id for model in models):
        raise api_error(ErrorCode.AI_CHAT_MODEL_UNAVAILABLE, status_code=422)
    skill_body: str | None = None
    if payload.skill is not None:
        skill_body = skills.load_skill_body(payload.skill, Path(project.path))
        if skill_body is None:
            raise api_error(ErrorCode.AI_CHAT_SKILL_UNAVAILABLE, status_code=422)
    user_content = payload.message or f"/{payload.skill}"
    _, api_key, adapter = provider_service.chat_credentials(
        db, current_user.id, payload.provider_id, settings
    )
    permission = service.get_command_permission(db, current_user.id)
    (
        project,
        conversation,
        user_message,
        assistant_message,
        history,
    ) = service.prepare_turn(
        db,
        current_user,
        project_id,
        payload.conversation_id,
        payload.provider_id,
        payload.model_id,
        user_content,
        payload.edit_user_message_id,
    )
    # The turn runs as a detached task that owns its own session, so it survives
    # this request ending (a backgrounded app, a reload, a dropped socket). The
    # response only tails the turn's events.
    turn = turns.manager.start(
        sessionmaker(bind=db.get_bind()),
        turns.TurnRequest(
            assistant_message_id=assistant_message.id,
            user_id=current_user.id,
            project_id=project.id,
            project_path=Path(project.path),
            conversation_id=conversation.id,
            conversation_title=conversation.title,
            user_message_id=user_message.id,
            user_content=user_content,
            model_id=payload.model_id,
            api_key=api_key,
            adapter=adapter,
            history=history,
            permission=permission,
            skill_body=skill_body,
        ),
    )
    db.close()
    return _stream_response(turn, 0)


@router.get(
    "/messages/{message_id}/stream",
    status_code=status.HTTP_200_OK,
    responses=_CHAT_ERRORS,
)
def resume_message_stream(
    project_id: int,
    message_id: int,
    current_user: CurrentUser,
    db: DbDep,
    offset: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """Re-attach to an in-flight turn, replaying events after ``offset``."""
    message = service.require_message(db, current_user, project_id, message_id)
    turn = turns.manager.get(message_id)
    if turn is None:
        # The turn is gone (finished and evicted, or the worker restarted). A
        # message still marked streaming would otherwise spin forever, so settle
        # it and tell the client to refetch the conversation.
        if message.status is MessageStatus.STREAMING:
            service.finish_assistant(db, message, message.content, MessageStatus.INTERRUPTED)
        db.close()
        raise api_error(ErrorCode.AI_CHAT_MESSAGE_NOT_FOUND, status_code=404)
    db.close()
    return _stream_response(turn, offset)


@router.post(
    "/messages/{message_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
)
async def cancel_message(
    project_id: int,
    message_id: int,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> None:
    """Cancel an in-flight turn. A finished or evicted turn is a no-op."""
    service.require_message(db, current_user, project_id, message_id)
    turns.manager.cancel(message_id)


async def _stream_turn(turn: turns.Turn, offset: int) -> AsyncIterator[bytes]:
    queue = turn.attach(offset)
    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                return
            yield chunk
    finally:
        turn.unsubscribe(queue)


def _stream_response(turn: turns.Turn, offset: int) -> StreamingResponse:
    return StreamingResponse(
        _stream_turn(turn, offset),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


router.include_router(ai_changes_router)
