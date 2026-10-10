from __future__ import annotations

import logging

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.ai_providers.anthropic import AnthropicAdapter
from app.modules.ai_providers.base import ProviderAdapter, ProviderAPIError, ProviderModel
from app.modules.ai_providers.crypto import (
    CredentialEncryptionError,
    decrypt_secret,
    encrypt_secret,
)
from app.modules.ai_providers.gemini import GeminiAdapter
from app.modules.ai_providers.models import AIProvider, ProviderKind
from app.modules.ai_providers.openai import OpenAIAdapter
from app.modules.ai_providers.schemas import (
    ProviderCreate,
    ProviderRead,
    ProviderUpdate,
)
from app.modules.auth.models import User

ADAPTERS: dict[ProviderKind, ProviderAdapter] = {
    ProviderKind.OPENAI: OpenAIAdapter(),
    ProviderKind.ANTHROPIC: AnthropicAdapter(),
    ProviderKind.GEMINI: GeminiAdapter(),
}
_SHARED_SCOPE_KEY = "shared"
_NAME_CONSTRAINT = "uq_ai_providers_scope_kind_name"
logger = logging.getLogger(__name__)


def can_manage_shared(user: User, settings: Settings) -> bool:
    return user.username == settings.admin_username


def list_available(db: Session, user_id: int) -> list[AIProvider]:
    return list(
        db.scalars(
            select(AIProvider)
            .where(or_(AIProvider.owner_id == user_id, AIProvider.owner_id.is_(None)))
            .order_by(AIProvider.name, AIProvider.id)
        )
    )


def provider_read(provider: AIProvider) -> ProviderRead:
    return ProviderRead(
        id=provider.id,
        name=provider.name,
        kind=provider.kind,
        shared=provider.owner_id is None,
        credential_configured=bool(provider.secret_ciphertext),
        created_at=provider.created_at,
    )


def create_personal(
    db: Session, user_id: int, payload: ProviderCreate, settings: Settings
) -> ProviderRead:
    return _create(db, user_id, payload, settings)


def create_shared(db: Session, payload: ProviderCreate, settings: Settings) -> ProviderRead:
    return _create(db, None, payload, settings)


def _create(
    db: Session, owner_id: int | None, payload: ProviderCreate, settings: Settings
) -> ProviderRead:
    scope_key = f"user:{owner_id}" if owner_id is not None else _SHARED_SCOPE_KEY
    _ensure_unique_name(db, scope_key, payload.kind, payload.name)
    try:
        ciphertext = encrypt_secret(payload.api_key.get_secret_value(), settings)
    except CredentialEncryptionError:
        raise api_error(
            ErrorCode.AI_CREDENTIAL_ENCRYPTION_UNAVAILABLE,
            status_code=503,
        ) from None

    provider = AIProvider(
        scope_key=scope_key,
        owner_id=owner_id,
        name=payload.name,
        kind=payload.kind,
        secret_ciphertext=ciphertext,
    )
    db.add(provider)
    _commit_provider(db, provider)
    return provider_read(provider)


def update_personal(
    db: Session, user_id: int, provider_id: int, payload: ProviderUpdate, settings: Settings
) -> ProviderRead:
    provider = _get_personal(db, user_id, provider_id)
    return _update(db, provider, payload, settings)


def update_shared(
    db: Session, provider_id: int, payload: ProviderUpdate, settings: Settings
) -> ProviderRead:
    provider = _get_shared(db, provider_id)
    return _update(db, provider, payload, settings)


def _update(
    db: Session, provider: AIProvider, payload: ProviderUpdate, settings: Settings
) -> ProviderRead:
    if payload.name is not None and payload.name != provider.name:
        _ensure_unique_name(
            db,
            provider.scope_key,
            provider.kind,
            payload.name,
            exclude_id=provider.id,
        )
        provider.name = payload.name
    if payload.api_key is not None:
        try:
            provider.secret_ciphertext = encrypt_secret(
                payload.api_key.get_secret_value(), settings
            )
        except CredentialEncryptionError:
            raise api_error(
                ErrorCode.AI_CREDENTIAL_ENCRYPTION_UNAVAILABLE,
                status_code=503,
            ) from None
    _commit_provider(db, provider)
    return provider_read(provider)


def delete_personal(db: Session, user_id: int, provider_id: int) -> None:
    provider = _get_personal(db, user_id, provider_id)
    db.delete(provider)
    db.commit()


def delete_shared(db: Session, provider_id: int) -> None:
    provider = _get_shared(db, provider_id)
    db.delete(provider)
    db.commit()


async def list_models(
    db: Session, user_id: int, provider_id: int, settings: Settings
) -> list[ProviderModel]:
    provider = _get_available(db, user_id, provider_id)
    api_key = _decrypt(provider, settings)
    try:
        async with httpx.AsyncClient() as client:
            return await ADAPTERS[provider.kind].list_models(client, api_key)
    except ProviderAPIError as exc:
        logger.warning(
            "AI provider model request failed provider=%s status=%s detail=%s",
            provider.kind.value,
            exc.status_code,
            exc.diagnostic or str(exc),
        )
        raise api_error(ErrorCode.AI_PROVIDER_FAILED, status_code=502) from None


async def test_connection(db: Session, user_id: int, provider_id: int, settings: Settings) -> int:
    return len(await list_models(db, user_id, provider_id, settings))


def _decrypt(provider: AIProvider, settings: Settings) -> str:
    try:
        return decrypt_secret(provider.secret_ciphertext, settings)
    except CredentialEncryptionError:
        raise api_error(
            ErrorCode.AI_CREDENTIAL_ENCRYPTION_UNAVAILABLE,
            status_code=503,
        ) from None


def chat_credentials(
    db: Session, user_id: int, provider_id: int, settings: Settings
) -> tuple[AIProvider, str, ProviderAdapter]:
    provider = _get_available(db, user_id, provider_id)
    return provider, _decrypt(provider, settings), ADAPTERS[provider.kind]


def _get_available(db: Session, user_id: int, provider_id: int) -> AIProvider:
    provider = db.scalar(
        select(AIProvider).where(
            AIProvider.id == provider_id,
            or_(AIProvider.owner_id == user_id, AIProvider.owner_id.is_(None)),
        )
    )
    if provider is None:
        raise api_error(ErrorCode.AI_PROVIDER_NOT_FOUND, status_code=404)
    return provider


def _get_personal(db: Session, user_id: int, provider_id: int) -> AIProvider:
    provider = db.scalar(
        select(AIProvider).where(
            AIProvider.id == provider_id,
            AIProvider.owner_id == user_id,
        )
    )
    if provider is None:
        raise api_error(ErrorCode.AI_PROVIDER_NOT_FOUND, status_code=404)
    return provider


def _get_shared(db: Session, provider_id: int) -> AIProvider:
    provider = db.scalar(
        select(AIProvider).where(
            AIProvider.id == provider_id,
            AIProvider.owner_id.is_(None),
        )
    )
    if provider is None:
        raise api_error(ErrorCode.AI_PROVIDER_NOT_FOUND, status_code=404)
    return provider


def _ensure_unique_name(
    db: Session,
    scope_key: str,
    kind: ProviderKind,
    name: str,
    *,
    exclude_id: int | None = None,
) -> None:
    statement = select(AIProvider.id).where(
        AIProvider.scope_key == scope_key,
        AIProvider.kind == kind,
        AIProvider.name == name,
    )
    if exclude_id is not None:
        statement = statement.where(AIProvider.id != exclude_id)
    if db.scalar(statement) is not None:
        raise api_error(ErrorCode.AI_PROVIDER_NAME_EXISTS, status_code=409)


def _commit_provider(db: Session, provider: AIProvider) -> None:
    try:
        db.commit()
        db.refresh(provider)
    except IntegrityError as exc:
        db.rollback()
        if _is_provider_name_conflict(exc):
            raise api_error(ErrorCode.AI_PROVIDER_NAME_EXISTS, status_code=409) from None
        raise


def _is_provider_name_conflict(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == _NAME_CONSTRAINT:
        return True
    return (
        str(exc.orig)
        == "UNIQUE constraint failed: ai_providers.scope_key, ai_providers.kind, ai_providers.name"
    )
