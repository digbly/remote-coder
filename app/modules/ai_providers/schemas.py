from datetime import datetime
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.modules.ai_providers.models import BASE_URL_PROVIDER_KINDS, ProviderKind

MAX_BASE_URL_LENGTH = 2048


def _normalize_base_url(value: str) -> str:
    normalized = value.rstrip("/")
    if not normalized or len(normalized) > MAX_BASE_URL_LENGTH:
        raise ValueError("Base URL must contain between 1 and 2048 characters")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be a valid HTTP(S) URL")
    return normalized


class ProviderCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    kind: ProviderKind
    api_key: SecretStr
    base_url: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value() or len(value.get_secret_value()) > 4096:
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return _normalize_base_url(value) if value is not None else None

    @model_validator(mode="after")
    def validate_base_url_for_kind(self) -> "ProviderCreate":
        if self.kind in BASE_URL_PROVIDER_KINDS:
            if self.base_url is None:
                raise ValueError("A base URL is required for this provider type")
        else:
            self.base_url = None
        return self


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: SecretStr | None = None
    base_url: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and (
            not value.get_secret_value() or len(value.get_secret_value()) > 4096
        ):
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return _normalize_base_url(value) if value is not None else None


class ProviderRead(BaseModel):
    id: int
    name: str
    kind: ProviderKind
    shared: bool
    credential_configured: bool
    base_url: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderListResponse(BaseModel):
    providers: list[ProviderRead]
    can_manage_shared: bool


class ProviderModelRead(BaseModel):
    id: str
    display_name: str


class ProviderModelsResponse(BaseModel):
    models: list[ProviderModelRead]


class ProviderTestResult(BaseModel):
    ok: bool
    model_count: int
