from urllib.parse import urlsplit

import jwt
from fastapi import Request, WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import User
from app.modules.auth.security import decode_access_token


def same_origin(source: Request | WebSocket) -> bool:
    """Reject cross-site requests from a different origin.

    Covers both WebSocket handshakes (CSWSH) and same-origin proxy requests; a
    missing ``Origin`` is treated as same-origin for non-browser clients.
    """
    origin = source.headers.get("origin")
    if not origin:
        return True

    host = source.headers.get("host")
    if not host:
        return False

    return urlsplit(origin).netloc == host


def resolve_user(db: Session, token: str | None, settings: Settings) -> User | None:
    if not token:
        return None

    try:
        payload = decode_access_token(token, settings)
    except jwt.PyJWTError:
        return None

    username = payload.get("sub")
    if not username:
        return None

    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        return None
    return user


def websocket_user(websocket: WebSocket, db: Session, settings: Settings) -> User | None:
    """Resolve the authenticated user from the access-token cookie."""
    return resolve_user(db, websocket.cookies.get(settings.access_token_cookie_name), settings)


async def reject(websocket: WebSocket, code: int) -> None:
    """Accept the handshake, then close with an application close code.

    Uvicorn turns a close *before* ``accept()`` into an HTTP 403 during the
    handshake, which browsers surface as an opaque ``1006`` and never expose the
    code to. Accepting first lets the client observe ``code`` (4401/4403/4404)
    and react — for example by refreshing an expired session and reconnecting.
    """
    await websocket.accept()
    await websocket.close(code=code)
