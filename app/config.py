from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-secret-key-change-me-in-production-0123456789"
DEFAULT_ADMIN_PASSWORD = "admin"
MAX_PASSWORD_BYTES = 72


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "remote-coder"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./remote_coder.db"
    secret_key: str = DEFAULT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    admin_username: str = "admin"
    admin_password: str = DEFAULT_ADMIN_PASSWORD

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        if self.environment == "development":
            return self
        if self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError("SECRET_KEY must be set to a unique value outside development")
        if self.admin_password == DEFAULT_ADMIN_PASSWORD:
            raise ValueError("ADMIN_PASSWORD must be changed outside development")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
