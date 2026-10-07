from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbDep, SettingsDep
from app.models import User
from app.schemas import LoginRequest, Token, UserRead
from app.security import DUMMY_PASSWORD_HASH, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: DbDep, settings: SettingsDep) -> Token:
    user = db.scalar(select(User).where(User.username == payload.username))
    hashed_password = user.hashed_password if user else DUMMY_PASSWORD_HASH
    password_matches = verify_password(payload.password, hashed_password)

    if user is None or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    token = create_access_token(subject=user.username, settings=settings)
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> User:
    return current_user
