from functools import lru_cache
from typing import Literal

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

    database_url: str = "sqlite:///./database/database.sqlite"
    secret_key: str = DEFAULT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    admin_username: str = "admin"
    admin_password: str = DEFAULT_ADMIN_PASSWORD

    access_token_cookie_name: str = "access_token"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60

    projects_root: str = "~/projects"
    github_clone_timeout_seconds: int = 120
    git_status_timeout_seconds: int = 30
    git_commit_timeout_seconds: int = 30
    git_push_timeout_seconds: int = 120
    github_pr_timeout_seconds: int = 60

    terminal_shell: str = "/bin/bash"
    terminal_read_chunk_bytes: int = 65536
    terminal_replay_bytes: int = 262144
    terminal_subscriber_queue_chunks: int = 256
    terminal_session_ttl_seconds: int = 21600

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        if self.environment != "development":
            if self.secret_key == DEFAULT_SECRET_KEY:
                raise ValueError("SECRET_KEY must be set to a unique value outside development")
            if self.admin_password == DEFAULT_ADMIN_PASSWORD:
                raise ValueError("ADMIN_PASSWORD must be changed outside development")
            if not self.cookie_secure:
                self.cookie_secure = True

        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
