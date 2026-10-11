import pytest

from app.core.config import DEFAULT_SECRET_KEY, Settings


def test_production_rejects_default_secrets() -> None:
    with pytest.raises(ValueError):
        Settings(environment="production")


def test_production_accepts_overridden_secrets() -> None:
    settings = Settings(
        environment="production",
        secret_key="a-strong-and-unique-production-secret-key",
        admin_password="a-strong-admin-password",
    )
    assert settings.environment == "production"
    assert settings.secret_key != DEFAULT_SECRET_KEY
    assert settings.cookie_secure is True


def test_samesite_none_requires_secure_cookie() -> None:
    with pytest.raises(ValueError):
        Settings(cookie_samesite="none")


def test_vscode_user_data_root_derives_from_data_root(monkeypatch) -> None:
    monkeypatch.delenv("VSCODE_USER_DATA_ROOT", raising=False)
    settings = Settings(remote_coder_data_root="~/.remote-coder")
    assert settings.vscode_user_data_root == "~/.remote-coder/vscode/cache"


def test_vscode_user_data_root_derives_from_env_data_root(monkeypatch) -> None:
    monkeypatch.delenv("VSCODE_USER_DATA_ROOT", raising=False)
    monkeypatch.setenv("REMOTE_CODER_DATA_ROOT", "/srv/remote-coder")
    settings = Settings()
    assert settings.vscode_user_data_root == "/srv/remote-coder/vscode/cache"


def test_vscode_user_data_root_can_be_overridden() -> None:
    settings = Settings(
        remote_coder_data_root="/data/remote-coder",
        vscode_user_data_root="/custom/vscode",
    )
    assert settings.vscode_user_data_root == "/custom/vscode"
