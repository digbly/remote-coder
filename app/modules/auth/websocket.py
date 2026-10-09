from urllib.parse import urlsplit

import jwt
from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import User
from app.modules.auth.security import decode_access_token


def same_origin(websocket: WebSocket) -> bool:
    """Reject cross-site WebSocket handshakes (CSWSH)."""
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    host = websocket.headers.get("host")
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
