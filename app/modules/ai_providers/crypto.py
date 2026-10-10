from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class CredentialEncryptionError(Exception):
    """Raised when a provider credential cannot be safely encrypted or decrypted."""


def _fernet(settings: Settings) -> Fernet:
    key = settings.ai_credential_encryption_key
    if key is None or not key.get_secret_value():
        raise CredentialEncryptionError(
            "AI_CREDENTIAL_ENCRYPTION_KEY must be configured to use provider credentials"
        )

    try:
        return Fernet(key.get_secret_value().encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise CredentialEncryptionError("AI_CREDENTIAL_ENCRYPTION_KEY is invalid") from exc


def encrypt_secret(secret: str, settings: Settings) -> str:
    if not secret:
        raise CredentialEncryptionError("Provider credential must not be empty")
    return _fernet(settings).encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str, settings: Settings) -> str:
    fernet = _fernet(settings)
    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise CredentialEncryptionError("Stored provider credential cannot be decrypted") from exc
