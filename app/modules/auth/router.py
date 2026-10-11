from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.auth import service
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.auth.models import User
from app.modules.auth.pow import pow_store
from app.modules.auth.rate_limit import login_rate_limit, pow_rate_limit, refresh_rate_limit
from app.modules.auth.schemas import LoginRequest, PowChallenge, UserRead
from app.modules.auth.security import create_access_token, generate_csrf_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(
    response: Response, access_token: str, refresh_token: str, settings: Settings
) -> None:
    common = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        settings.access_token_cookie_name,
        access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        **common,
    )
    response.set_cookie(
        settings.refresh_token_cookie_name,
        refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        **common,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        generate_csrf_token(),
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=False,
        **common,
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.access_token_cookie_name, path="/")
    response.delete_cookie(settings.refresh_token_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


def _pow_required(settings: Settings) -> bool:
    return settings.pow_enabled and settings.pow_difficulty > 0


@router.get(
    "/pow",
    response_model=PowChallenge,
    dependencies=[Depends(pow_rate_limit)],
    responses=error_responses(429),
)
def pow_challenge(settings: SettingsDep) -> PowChallenge:
    if not _pow_required(settings):
        return PowChallenge(challenge="", difficulty=0)
    challenge = pow_store.issue(
        ttl_seconds=settings.pow_challenge_ttl_seconds,
        length_bytes=settings.pow_challenge_bytes,
    )
    return PowChallenge(challenge=challenge, difficulty=settings.pow_difficulty)


@router.post(
    "/login",
    response_model=UserRead,
    dependencies=[Depends(login_rate_limit)],
    responses=error_responses(400, 401, 403, 422, 429),
)
def login(
    payload: LoginRequest,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
) -> User:
    if _pow_required(settings) and not pow_store.verify(
        payload.pow_challenge, payload.pow_nonce, settings.pow_difficulty
    ):
        raise api_error(ErrorCode.POW_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    user = service.authenticate_user(db, payload.username, payload.password)
    access_token = create_access_token(user.username, settings)
    refresh_token = service.issue_refresh_token(db, user, settings)
    _set_auth_cookies(response, access_token, refresh_token, settings)
    return user


@router.post(
    "/refresh",
    response_model=UserRead,
    dependencies=[Depends(refresh_rate_limit)],
    responses=error_responses(401, 403, 429),
)
def refresh(
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> User:
    token = request.cookies.get(settings.refresh_token_cookie_name)
    user, new_refresh_token = service.rotate_refresh_token(db, token, settings)
    access_token = create_access_token(user.username, settings)
    _set_auth_cookies(response, access_token, new_refresh_token, settings)
    return user


@router.get("/me", response_model=UserRead, responses=error_responses(401, 403))
def read_current_user(current_user: CurrentUser) -> User:
    return current_user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(403),
)
def logout(
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    _csrf: CsrfDep,
) -> None:
    service.revoke_refresh_token(db, request.cookies.get(settings.refresh_token_cookie_name))
    _clear_auth_cookies(response, settings)
