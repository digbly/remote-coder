from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth import service
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.auth.models import User
from app.modules.auth.rate_limit import login_rate_limit
from app.modules.auth.schemas import LoginRequest, UserRead
from app.modules.auth.security import create_access_token, generate_csrf_token

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


@router.post(
    "/login",
    response_model=UserRead,
    dependencies=[Depends(login_rate_limit)],
    responses=error_responses(401, 403, 422, 429),
)
def login(
    payload: LoginRequest,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> User:
    user = service.authenticate_user(db, payload.username, payload.password)
    _set_auth_cookies(response, user.username, settings)
    return user


@router.get("/me", response_model=UserRead, responses=error_responses(401, 403))
def read_current_user(current_user: CurrentUser) -> User:
    return current_user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(403),
)
def logout(response: Response, settings: SettingsDep, _csrf: CsrfDep) -> None:
    response.delete_cookie(settings.access_token_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
