import pytest

from app.config import DEFAULT_SECRET_KEY, Settings


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
