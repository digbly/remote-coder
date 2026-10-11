from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import MAX_PASSWORD_BYTES
from app.modules.auth.pow import ALGORITHM


class PowChallenge(BaseModel):
    algorithm: str = ALGORITHM
    challenge: str
    difficulty: int


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)
    pow_challenge: str | None = Field(default=None, max_length=128)
    pow_nonce: str | None = Field(default=None, max_length=64)

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password must not exceed {MAX_PASSWORD_BYTES} bytes")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
