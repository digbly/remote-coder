import asyncio
import json
import logging
from contextlib import suppress

import websockets
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error, error_responses
from app.modules.auth.deps import CurrentUser
from app.modules.auth.models import User
from app.modules.auth.websocket import reject, same_origin, websocket_user
from app.modules.browser import service
from app.modules.projects import service as projects_service

router = APIRouter(prefix="/projects", tags=["browser"])

logger = logging.getLogger(__name__)

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404
WS_INTERNAL_ERROR = 4500


class NavigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)


class ViewportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(ge=200, le=4000)
    height: int = Field(ge=200, le=4000)


class InsertTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=100_000)


@router.post(
    "/{project_id}/browser/navigate",
    responses=error_responses(400, 401, 404, 502),
)
async def navigate(
    request: Request,
    project_id: int,
    payload: NavigateRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    session: str = Query(service.DEFAULT_SESSION),
) -> dict[str, bool]:
    if not same_origin(request):
        raise api_error(ErrorCode.BROWSER_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    url = payload.url.strip()
    if not service.is_http_url(url):
        raise api_error(
            ErrorCode.BROWSER_NAVIGATION_FAILED, status_code=status.HTTP_400_BAD_REQUEST
        )

    browser = await _ensure_session(db, settings, current_user, project_id, session)
    db.close()
    await _run(service.navigate_command(url, settings), browser)
    return {"ok": True}


@router.post(
    "/{project_id}/browser/viewport",
    responses=error_responses(400, 401, 404, 502),
)
async def set_viewport(
    request: Request,
    project_id: int,
    payload: ViewportRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    session: str = Query(service.DEFAULT_SESSION),
) -> dict[str, bool]:
    if not same_origin(request):
        raise api_error(ErrorCode.BROWSER_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    browser = await _ensure_session(db, settings, current_user, project_id, session)
    db.close()
    await _run(
        service.viewport_command(payload.width, payload.height, settings),
        browser,
        code=ErrorCode.BROWSER_COMMAND_FAILED,
    )
    return {"ok": True}


@router.post(
    "/{project_id}/browser/insert",
    responses=error_responses(400, 401, 404, 502),
)
async def insert_text(
    request: Request,
    project_id: int,
    payload: InsertTextRequest,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    session: str = Query(service.DEFAULT_SESSION),
) -> dict[str, bool]:
    if not same_origin(request):
        raise api_error(ErrorCode.BROWSER_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    browser = await _ensure_session(db, settings, current_user, project_id, session)
    db.close()
    await _run(
        service.insert_text_command(payload.text, settings),
        browser,
        code=ErrorCode.BROWSER_COMMAND_FAILED,
    )
    return {"ok": True}


@router.get(
    "/{project_id}/browser/selection",
    responses=error_responses(401, 404, 502),
)
async def get_selection(
    request: Request,
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    session: str = Query(service.DEFAULT_SESSION),
) -> dict[str, str]:
    if not same_origin(request):
        raise api_error(ErrorCode.BROWSER_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    browser = await _ensure_session(db, settings, current_user, project_id, session)
    db.close()
    try:
        output = await asyncio.to_thread(browser.run, service.selection_command(settings))
    except service.BrowserError as exc:
        raise api_error(
            ErrorCode.BROWSER_COMMAND_FAILED, status_code=status.HTTP_502_BAD_GATEWAY
        ) from exc
    payload = service.parse_status(output)
    data = payload.get("data") if isinstance(payload, dict) else None
    text = data.get("result") if isinstance(data, dict) else None
    return {"text": text if isinstance(text, str) else ""}


@router.post(
    "/{project_id}/browser/{action}",
    responses=error_responses(400, 401, 404, 502),
)
async def control(
    request: Request,
    project_id: int,
    action: str,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    session: str = Query(service.DEFAULT_SESSION),
) -> dict[str, bool]:
    if action not in service.NAVIGATION_ACTIONS:
        raise api_error(
            ErrorCode.BROWSER_NAVIGATION_FAILED, status_code=status.HTTP_400_BAD_REQUEST
        )
    if not same_origin(request):
        raise api_error(ErrorCode.BROWSER_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    browser = await _ensure_session(db, settings, current_user, project_id, session)
    db.close()
    await _run(service.action_command(action, settings), browser)
    return {"ok": True}


@router.delete(
    "/{project_id}/browser/session",
    responses=error_responses(401, 404),
)
async def close_session(
    request: Request,
    project_id: int,
    current_user: CurrentUser,
    db: DbDep,
    session: str = Query(service.DEFAULT_SESSION),
) -> dict[str, bool]:
    if not same_origin(request):
        raise api_error(ErrorCode.BROWSER_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    # Confirms the project exists and belongs to the user (raises 404 otherwise).
    projects_service.get_project(db, current_user, project_id)
    key = (current_user.id, project_id, service.safe_session(session))
    # Kill only; never start a session just to close it.
    await asyncio.to_thread(service.manager.kill, key)
    return {"ok": True}


@router.websocket("/{project_id}/browser/stream")
async def proxy_stream(
    websocket: WebSocket,
    project_id: int,
    db: DbDep,
    settings: SettingsDep,
) -> None:
    if not same_origin(websocket):
        await reject(websocket, WS_FORBIDDEN)
        return

    user = websocket_user(websocket, db, settings)
    if user is None:
        await reject(websocket, WS_UNAUTHORIZED)
        return

    # Accept before starting the session so a slow or failing startup reaches
    # the client as a message instead of a handshake that never completes.
    await websocket.accept()

    try:
        browser = await _ensure_session(
            db,
            settings,
            user,
            project_id,
            websocket.query_params.get("session", service.DEFAULT_SESSION),
        )
    except HTTPException as exc:
        await _send_error_and_close(websocket, exc)
        return
    except Exception:  # noqa: BLE001 - unexpected failures still close cleanly
        await _send_error_and_close(
            websocket,
            api_error(
                ErrorCode.BROWSER_PROXY_FAILED,
                status_code=status.HTTP_502_BAD_GATEWAY,
            ),
        )
        return

    db.close()

    try:
        upstream = await _open_upstream(browser.host, browser.port, settings)
    except (OSError, websockets.WebSocketException):
        await _send_error_and_close(
            websocket,
            api_error(
                ErrorCode.BROWSER_PROXY_FAILED,
                status_code=status.HTTP_502_BAD_GATEWAY,
            ),
        )
        return

    browser.touch()

    sender = asyncio.create_task(_pump_client_to_server(websocket, upstream))
    receiver = asyncio.create_task(_pump_server_to_client(websocket, upstream))
    try:
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sender, receiver):
            task.cancel()
        with suppress(Exception):
            await upstream.close()


async def _open_upstream(host: str, port: int, settings: Settings):
    """Connect to the session's stream server, trying every loopback spelling.

    The server may bind IPv4 or IPv6, so a refused connection on the configured
    host falls through to the other loopback forms instead of failing outright.
    """
    last_error: Exception | None = None
    tried: list[str] = []
    for candidate in (host, "127.0.0.1", "::1", "localhost"):
        if candidate in tried:
            continue
        tried.append(candidate)
        netloc = f"[{candidate}]" if ":" in candidate else candidate
        target = f"ws://{netloc}:{port}/?pacing=push&maxFps={settings.browser_stream_max_fps}"
        try:
            return await websockets.connect(
                target,
                max_size=None,
                open_timeout=settings.browser_start_timeout_seconds,
                origin=f"http://{netloc}:{port}",
            )
        except (OSError, websockets.WebSocketException) as exc:
            last_error = exc
            logger.warning("browser stream connect failed at %s: %s", target, exc)
    assert last_error is not None
    raise last_error


async def _ensure_session(
    db: Session,
    settings: Settings,
    user: User,
    project_id: int,
    session: str,
) -> service.BrowserSession:
    if not settings.browser_enabled:
        raise api_error(ErrorCode.BROWSER_DISABLED, status_code=status.HTTP_403_FORBIDDEN)

    # Confirms the project exists and belongs to the user (raises 404 otherwise).
    projects_service.get_project(db, user, project_id)

    session = service.safe_session(session)
    key = (user.id, project_id, session)
    name = service.session_name(user.id, project_id, session)
    try:
        return await asyncio.to_thread(
            service.manager.ensure, key, name=name, settings=settings
        )
    except service.BrowserError as exc:
        raise api_error(
            ErrorCode.BROWSER_START_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from exc


async def _run(
    command: list[str],
    session: service.BrowserSession,
    *,
    code: ErrorCode = ErrorCode.BROWSER_NAVIGATION_FAILED,
) -> None:
    try:
        await asyncio.to_thread(session.run, command)
    except service.BrowserError as exc:
        raise api_error(code, status_code=status.HTTP_502_BAD_GATEWAY) from exc


def _ws_close_code(exc: Exception) -> int:
    if isinstance(exc, HTTPException):
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return WS_UNAUTHORIZED
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return WS_NOT_FOUND
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return WS_FORBIDDEN
    return WS_INTERNAL_ERROR


async def _send_error_and_close(websocket: WebSocket, exc: HTTPException) -> None:
    """Report the failure reason over the accepted socket, then close."""
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    with suppress(RuntimeError, WebSocketDisconnect):
        await websocket.send_text(
            json.dumps(
                {
                    "type": "error",
                    "code": detail.get("code", ErrorCode.BROWSER_PROXY_FAILED.value),
                    "message": detail.get("message", ""),
                }
            )
        )
    with suppress(RuntimeError):
        await websocket.close(code=_ws_close_code(exc))


async def _pump_client_to_server(websocket: WebSocket, upstream) -> None:
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if (text := message.get("text")) is not None:
                await upstream.send(text)
            elif (data := message.get("bytes")) is not None:
                await upstream.send(data)
    except (WebSocketDisconnect, RuntimeError):
        return


async def _pump_server_to_client(websocket: WebSocket, upstream) -> None:
    try:
        async for message in upstream:
            if isinstance(message, str):
                await websocket.send_text(message)
            else:
                await websocket.send_bytes(message)
    except (WebSocketDisconnect, RuntimeError, websockets.WebSocketException):
        return
