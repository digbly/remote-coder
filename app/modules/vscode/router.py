import asyncio
from contextlib import suppress
from pathlib import Path

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from starlette.datastructures import Headers
from starlette.responses import StreamingResponse

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
from app.core.errors import ErrorCode, api_error
from app.modules.auth.deps import CurrentUser
from app.modules.auth.models import User
from app.modules.auth.websocket import same_origin, websocket_user
from app.modules.git import service as git_service
from app.modules.projects import service as projects_service
from app.modules.vscode import service

router = APIRouter(prefix="/projects", tags=["vscode"])

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404
WS_INTERNAL_ERROR = 4500

_HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Hop-by-hop and identity headers are owned by each side of the proxy.
_DROP_REQUEST_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "cookie",
        "authorization",
        "accept-encoding",
        "origin",
        "referer",
        "content-length",
    }
)

# ``x-frame-options``/CSP would stop the server from rendering in an iframe, and
# the length/transfer headers no longer describe the streamed body.
_DROP_RESPONSE_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
        "x-frame-options",
        "content-security-policy",
        "content-security-policy-report-only",
    }
)


@router.api_route(
    "/{project_id}/vscode/{worktree}",
    methods=_HTTP_METHODS,
    include_in_schema=False,
)
@router.api_route(
    "/{project_id}/vscode/{worktree}/{subpath:path}",
    methods=_HTTP_METHODS,
    include_in_schema=False,
)
async def proxy_http(
    request: Request,
    project_id: int,
    worktree: str,
    current_user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    subpath: str = "",
) -> StreamingResponse:
    if not same_origin(request):
        raise api_error(ErrorCode.VSCODE_FORBIDDEN, status_code=status.HTTP_403_FORBIDDEN)

    session = await _ensure_session(db, settings, current_user, project_id, worktree)
    # The database connection is not needed while the body streams.
    db.close()
    return await _forward_http(
        request, session, subpath, prefix=_proxy_prefix(settings, project_id, worktree)
    )


@router.websocket("/{project_id}/vscode/{worktree}")
@router.websocket("/{project_id}/vscode/{worktree}/{subpath:path}")
async def proxy_ws(
    websocket: WebSocket,
    project_id: int,
    worktree: str,
    db: DbDep,
    settings: SettingsDep,
    subpath: str = "",
) -> None:
    if not same_origin(websocket):
        await websocket.close(code=WS_FORBIDDEN)
        return

    user = websocket_user(websocket, db, settings)
    if user is None:
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    try:
        session = await _ensure_session(db, settings, user, project_id, worktree)
    except Exception as exc:  # noqa: BLE001 - translate HTTP errors into WS codes
        await websocket.close(code=_ws_close_code(exc))
        return

    db.close()

    query = websocket.url.query
    target = f"{session.ws_base}/{subpath}"
    if query:
        target = f"{target}?{query}"

    protocols = _subprotocols(websocket)
    try:
        upstream = await websockets.connect(
            target,
            subprotocols=protocols or None,
            max_size=None,
            open_timeout=settings.vscode_start_timeout_seconds,
        )
    except (OSError, websockets.WebSocketException):
        await websocket.close(code=WS_INTERNAL_ERROR)
        return

    await websocket.accept(subprotocol=upstream.subprotocol)
    session.touch()

    sender = asyncio.create_task(_pump_client_to_server(websocket, upstream))
    receiver = asyncio.create_task(_pump_server_to_client(websocket, upstream))
    try:
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sender, receiver):
            task.cancel()
        with suppress(Exception):
            await upstream.close()


async def _ensure_session(
    db: Session,
    settings: Settings,
    user: User,
    project_id: int,
    worktree: str,
) -> service.VSCodeSession:
    if not settings.vscode_enabled:
        raise api_error(ErrorCode.VSCODE_DISABLED, status_code=status.HTTP_403_FORBIDDEN)

    project = projects_service.get_project(db, user, project_id)
    root = Path(project.path)
    if not root.is_dir():
        raise api_error(ErrorCode.VSCODE_WORKTREE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    resolved = await asyncio.to_thread(git_service.find_worktree, root, worktree, settings)
    if resolved is None or not resolved.is_dir():
        raise api_error(ErrorCode.VSCODE_WORKTREE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    key = (user.id, project_id, resolved.name)
    try:
        return await asyncio.to_thread(service.manager.ensure, key, cwd=resolved, settings=settings)
    except service.VSCodeError as exc:
        raise api_error(
            ErrorCode.VSCODE_START_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from exc


async def _forward_http(
    request: Request,
    session: service.VSCodeSession,
    subpath: str,
    *,
    prefix: str,
) -> StreamingResponse:
    session.touch()
    url = f"{session.http_base}/{subpath}"
    client = httpx.AsyncClient(timeout=None, follow_redirects=False)

    content = (
        request.stream() if request.method in _BODY_METHODS and _has_request_body(request) else None
    )
    upstream_request = client.build_request(
        request.method,
        url,
        params=request.url.query or None,
        headers=_request_headers(request),
        content=content,
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise api_error(
            ErrorCode.VSCODE_PROXY_FAILED, status_code=status.HTTP_502_BAD_GATEWAY
        ) from exc
    except BaseException:
        await client.aclose()
        raise

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            with suppress(Exception):
                await upstream.aclose()
            with suppress(Exception):
                await client.aclose()

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=_response_headers(upstream, prefix=prefix),
    )


def _has_request_body(request: Request) -> bool:
    length = request.headers.get("content-length")
    if length is not None and length != "0":
        return True
    return "transfer-encoding" in request.headers


def _request_headers(request: Request) -> list[tuple[str, str]]:
    headers = [
        (key, value)
        for key, value in request.headers.items()
        if key.lower() not in _DROP_REQUEST_HEADERS
    ]
    headers.append(("accept-encoding", "identity"))
    return headers


def _response_headers(upstream: httpx.Response, *, prefix: str) -> Headers:
    raw: list[tuple[bytes, bytes]] = []
    for key, value in upstream.headers.multi_items():
        lower = key.lower()
        if lower in _DROP_RESPONSE_HEADERS:
            continue
        if lower == "location":
            value = _rewrite_location(value, prefix)
        raw.append((key.encode("latin-1"), value.encode("latin-1")))
    return Headers(raw=raw)


def _rewrite_location(value: str, prefix: str) -> str:
    """Keep redirects inside the proxy prefix when the server emits an absolute path."""
    if value.startswith("/") and not value.startswith("//"):
        return f"{prefix}{value}"
    return value


def _proxy_prefix(settings: Settings, project_id: int, worktree: str) -> str:
    return f"{settings.api_prefix}/projects/{project_id}/vscode/{worktree}"


def _subprotocols(websocket: WebSocket) -> list[str]:
    header = websocket.headers.get("sec-websocket-protocol", "")
    return [item.strip() for item in header.split(",") if item.strip()]


def _ws_close_code(exc: Exception) -> int:
    if isinstance(exc, HTTPException):
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return WS_UNAUTHORIZED
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return WS_NOT_FOUND
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            return WS_FORBIDDEN
    return WS_INTERNAL_ERROR


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
