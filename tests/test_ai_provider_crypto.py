import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.modules.ai_providers.crypto import (
    CredentialEncryptionError,
    decrypt_secret,
    encrypt_secret,
)


def _settings(key: bytes | None = None) -> Settings:
    value = key or Fernet.generate_key()
    return Settings(ai_credential_encryption_key=value.decode("ascii"))


def test_encrypt_and_decrypt_secret() -> None:
    settings = _settings()
    plaintext = "provider-api-key"

    ciphertext = encrypt_secret(plaintext, settings)

    assert ciphertext != plaintext
    assert plaintext not in ciphertext
    assert decrypt_secret(ciphertext, settings) == plaintext


def test_encrypt_requires_configured_key() -> None:
    with pytest.raises(CredentialEncryptionError, match="AI_CREDENTIAL_ENCRYPTION_KEY"):
        encrypt_secret("provider-api-key", Settings())


def test_decrypt_rejects_wrong_key_without_leaking_ciphertext() -> None:
    ciphertext = encrypt_secret("provider-api-key", _settings())

    with pytest.raises(CredentialEncryptionError) as exc_info:
        decrypt_secret(ciphertext, _settings())

    assert ciphertext not in str(exc_info.value)


def test_decrypt_rejects_tampered_ciphertext() -> None:
    settings = _settings()
    ciphertext = encrypt_secret("provider-api-key", settings)
    tampered = f"{ciphertext[:-1]}{'A' if ciphertext[-1] != 'A' else 'B'}"

    with pytest.raises(CredentialEncryptionError):
        decrypt_secret(tampered, settings)


def test_invalid_encryption_key_is_reported_explicitly() -> None:
    settings = Settings(ai_credential_encryption_key="not-a-fernet-key")

    with pytest.raises(CredentialEncryptionError, match="invalid"):
        encrypt_secret("provider-api-key", settings)


def test_encrypt_rejects_empty_secret() -> None:
    with pytest.raises(CredentialEncryptionError, match="must not be empty"):
        encrypt_secret("", _settings())
