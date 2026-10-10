from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.modules.ai_providers.models import ProviderKind


class ProviderCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    kind: ProviderKind
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value() or len(value.get_secret_value()) > 4096:
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: SecretStr | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and (
            not value.get_secret_value() or len(value.get_secret_value()) > 4096
        ):
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value


class ProviderRead(BaseModel):
    id: int
    name: str
    kind: ProviderKind
    shared: bool
    credential_configured: bool
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
