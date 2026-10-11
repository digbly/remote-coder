from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: str = "storage/logs"

    database_url: str = "sqlite:///./database/database.sqlite"
    secret_key: str = DEFAULT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 30

    admin_username: str = "admin"
    admin_password: str = DEFAULT_ADMIN_PASSWORD
    ai_credential_encryption_key: SecretStr | None = None

    access_token_cookie_name: str = "access_token"
    refresh_token_cookie_name: str = "refresh_token"
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    refresh_rate_limit_attempts: int = 30
    refresh_rate_limit_window_seconds: int = 60

    # Proof-of-work login challenge: the client must find a nonce whose
    # SHA-256(challenge + nonce) digest starts with `pow_difficulty` zero hex
    # nibbles. Each challenge is single-use and expires after its TTL.
    pow_enabled: bool = True
    pow_difficulty: int = Field(default=4, ge=0, le=64)
    pow_challenge_ttl_seconds: int = Field(default=300, ge=1)
    pow_challenge_bytes: int = Field(default=16, ge=16, le=64)
    pow_rate_limit_attempts: int = 60
    pow_rate_limit_window_seconds: int = 60

    projects_root: str = "~/projects"
    worktrees_root: str = "~/remote-coder/workspaces"
    remote_coder_data_root: str = "~/.remote-coder"
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

    agent_models_cache_ttl_seconds: int = 300
    agent_commit_message_timeout_seconds: int = 120
    agent_commit_message_diff_max_bytes: int = 100_000
    agent_commit_message_args: str = ""
    # OpenCode's data directory (holding ``opencode.db``). Empty resolves the
    # XDG default (``~/.local/share/opencode``).
    opencode_data_dir: str = ""

    vscode_enabled: bool = True
    vscode_binary: str = "code-server"
    vscode_bind_host: str = "127.0.0.1"
    vscode_port_start: int = 8800
    vscode_port_end: int = 8900
    vscode_user_data_root: str = ""
    vscode_start_timeout_seconds: int = 30
    vscode_session_ttl_seconds: int = 3600
    vscode_max_sessions: int = 4
    vscode_extra_args: str = ""

    browser_enabled: bool = True
    browser_binary: str = "agent-browser"
    browser_bind_host: str = "127.0.0.1"
    browser_stream_quality: int = 60
    browser_stream_max_fps: int = 30
    browser_headless: bool = True
    browser_start_timeout_seconds: int = 30
    browser_session_ttl_seconds: int = 3600
    browser_max_sessions: int = 2
    browser_allowed_domains: str = ""
    browser_extra_args: str = ""

    @model_validator(mode="after")
    def _derive_vscode_user_data_root(self) -> "Settings":
        if not self.vscode_user_data_root:
            self.vscode_user_data_root = str(Path(self.remote_coder_data_root) / "vscode" / "cache")
        return self

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
