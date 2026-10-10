from fastapi import APIRouter, status

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.ai_providers import service
from app.modules.ai_providers.schemas import (
    ProviderCreate,
    ProviderListResponse,
    ProviderModelRead,
    ProviderModelsResponse,
    ProviderRead,
    ProviderTestResult,
    ProviderUpdate,
)
from app.modules.auth.deps import CsrfDep, CurrentUser

router = APIRouter(prefix="/ai-providers", tags=["ai-providers"])

_PROVIDER_ERRORS = error_responses(401, 403, 404, 409, 422, 502, 503)


def _require_admin(user: CurrentUser, settings: Settings) -> None:
    if not service.can_manage_shared(user, settings):
        raise api_error(ErrorCode.AI_PROVIDER_ADMIN_REQUIRED, status_code=403)


@router.get("", response_model=ProviderListResponse, responses=error_responses(401))
def list_providers(
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> ProviderListResponse:
    return ProviderListResponse(
        providers=[
            service.provider_read(provider)
            for provider in service.list_available(db, current_user.id)
        ],
        can_manage_shared=service.can_manage_shared(current_user, settings),
    )


@router.post(
    "",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
    responses=_PROVIDER_ERRORS,
)
def create_personal_provider(
    payload: ProviderCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> ProviderRead:
    return service.create_personal(db, current_user.id, payload, settings)


@router.post(
    "/shared",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
    responses=_PROVIDER_ERRORS,
)
def create_shared_provider(
    payload: ProviderCreate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> ProviderRead:
    _require_admin(current_user, settings)
    return service.create_shared(db, payload, settings)


@router.patch("/{provider_id}", response_model=ProviderRead, responses=_PROVIDER_ERRORS)
def update_personal_provider(
    provider_id: int,
    payload: ProviderUpdate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> ProviderRead:
    return service.update_personal(db, current_user.id, provider_id, payload, settings)


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_PROVIDER_ERRORS,
)
def delete_personal_provider(
    provider_id: int,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> None:
    service.delete_personal(db, current_user.id, provider_id)


@router.patch(
    "/shared/{provider_id}",
    response_model=ProviderRead,
    responses=_PROVIDER_ERRORS,
)
def update_shared_provider(
    provider_id: int,
    payload: ProviderUpdate,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> ProviderRead:
    _require_admin(current_user, settings)
    return service.update_shared(db, provider_id, payload, settings)


@router.delete(
    "/shared/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_PROVIDER_ERRORS,
)
def delete_shared_provider(
    provider_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> None:
    _require_admin(current_user, settings)
    service.delete_shared(db, provider_id)


@router.get(
    "/{provider_id}/models", response_model=ProviderModelsResponse, responses=_PROVIDER_ERRORS
)
async def list_provider_models(
    provider_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> ProviderModelsResponse:
    models = await service.list_models(db, current_user.id, provider_id, settings)
    return ProviderModelsResponse(
        models=[ProviderModelRead(id=model.id, display_name=model.display_name) for model in models]
    )


@router.post("/{provider_id}/test", response_model=ProviderTestResult, responses=_PROVIDER_ERRORS)
async def test_provider(
    provider_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> ProviderTestResult:
    model_count = await service.test_connection(db, current_user.id, provider_id, settings)
    return ProviderTestResult(ok=True, model_count=model_count)
