import asyncio
import json
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit

from anyio import ClosedResourceError
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth.deps import CsrfDep, CurrentUser
from app.modules.projects import service as projects_service
from app.modules.terminal import service

router = APIRouter(prefix="/projects", tags=["terminal"])

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404
WS_INTERNAL_ERROR = 4500


def _same_origin(websocket: WebSocket) -> bool:
    """Reject cross-site WebSocket handshakes (CSWSH)."""
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    host = websocket.headers.get("host")
    if not host:
        return False

    origin_host = urlsplit(origin).netloc
    return origin_host == host


def _token(websocket: WebSocket, settings: Settings) -> str | None:
    return websocket.cookies.get(settings.access_token_cookie_name)


@router.websocket("/{project_id}/terminal/{terminal_id}")
async def project_terminal(
    websocket: WebSocket,
    project_id: int,
    terminal_id: str,
    db: DbDep,
    settings: SettingsDep,
) -> None:
    if not _same_origin(websocket):
        await websocket.close(code=WS_FORBIDDEN)
        return

    if not service.valid_terminal_id(terminal_id):
        await websocket.close(code=WS_NOT_FOUND)
        return

    user = service.resolve_user(db, _token(websocket, settings), settings)
    if user is None:
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    project = service.get_project(db, user, project_id)
    if project is None:
        await websocket.close(code=WS_NOT_FOUND)
        return

    cwd = Path(project.path)
    if not cwd.is_dir():
        await websocket.close(code=WS_NOT_FOUND)
        return

    # Release the database connection: it is not needed for the (potentially
    # long-lived) terminal session and would otherwise exhaust the pool.
    db.close()

    await websocket.accept()

    try:
        session = await asyncio.to_thread(
            service.manager.attach,
            (user.id, project_id, terminal_id),
            cwd=cwd,
            shell=settings.terminal_shell,
            read_chunk_bytes=settings.terminal_read_chunk_bytes,
            replay_bytes=settings.terminal_replay_bytes,
        )
    except OSError:
        await websocket.close(code=WS_INTERNAL_ERROR)
        return

    # Replay buffered output so a reconnecting client sees the previous screen.
    queue, replay = session.subscribe(asyncio.get_running_loop())
    sender = asyncio.create_task(_pump_output(queue, websocket))
    receiver = asyncio.create_task(_pump_input(session, websocket))
    try:
        if replay:
            await websocket.send_bytes(replay)
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sender, receiver):
            task.cancel()
        # Only this client detaches; the session keeps running for a later
        # re-attach.
        session.unsubscribe(queue)


@router.delete(
    "/{project_id}/terminal/{terminal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
)
def kill_project_terminal(
    project_id: int,
    terminal_id: str,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> None:
    projects_service.get_project(db, current_user, project_id)
    if service.valid_terminal_id(terminal_id):
        service.manager.kill((current_user.id, project_id, terminal_id))


async def _pump_output(queue: asyncio.Queue[bytes | None], websocket: WebSocket) -> None:
    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                return
            await websocket.send_bytes(chunk)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        with suppress(RuntimeError, ClosedResourceError):
            await websocket.close()


async def _pump_input(session: service.TerminalSession, websocket: WebSocket) -> None:
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue

            kind = payload.get("type")
            if kind == "input":
                data = payload.get("data")
                if isinstance(data, str) and data:
                    session.write(data.encode("utf-8"))
            elif kind == "resize":
                cols = payload.get("cols")
                rows = payload.get("rows")
                if isinstance(cols, int) and isinstance(rows, int):
                    session.resize(cols, rows)
    except (WebSocketDisconnect, RuntimeError):
        return
