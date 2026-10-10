from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.ai_changes.router import router as ai_changes_router
from app.modules.ai_chat import service
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_chat.schemas import (
    ChatTurnRequest,
    ConversationDetail,
    ConversationListResponse,
)
from app.modules.ai_chat.streaming import stream_chat_turn
from app.modules.ai_providers import service as provider_service
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.projects import service as project_service

router = APIRouter(prefix="/projects/{project_id}/ai-chat", tags=["ai-chat"])
_CHAT_ERRORS = error_responses(401, 403, 404, 413, 422, 502, 503)


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
    _, api_key, adapter = provider_service.chat_credentials(
        db, current_user.id, payload.provider_id, settings
    )
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
        payload.message,
    )
    return StreamingResponse(
        stream_chat_turn(
            db=db,
            adapter=adapter,
            api_key=api_key,
            model_id=payload.model_id,
            context=ProjectContext(db, current_user, project.id, conversation.id),
            conversation_id=conversation.id,
            conversation_title=conversation.title,
            user_message_id=user_message.id,
            user_content=payload.message,
            assistant_message=assistant_message,
            history=history,
        ),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


router.include_router(ai_changes_router)
