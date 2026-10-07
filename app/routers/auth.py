from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from app.config import Settings
from app.deps import CsrfDep, CurrentUser, DbDep, SettingsDep
from app.models import User
from app.rate_limit import login_rate_limit
from app.schemas import LoginRequest, UserRead
from app.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_csrf_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, username: str, settings: Settings) -> None:
    max_age = settings.access_token_expire_minutes * 60
    common = {
        "max_age": max_age,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        settings.access_token_cookie_name,
        create_access_token(username, settings),
        httponly=True,
        **common,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        generate_csrf_token(),
        httponly=False,
        **common,
    )


@router.post("/login", response_model=UserRead, dependencies=[Depends(login_rate_limit)])
def login(
    payload: LoginRequest,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> User:
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

    _set_auth_cookies(response, user.username, settings)
    return user


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> User:
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: SettingsDep, _csrf: CsrfDep) -> None:
    response.delete_cookie(settings.access_token_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
