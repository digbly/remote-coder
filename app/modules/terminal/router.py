import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.core.deps import DbDep, SettingsDep
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


@router.websocket("/{project_id}/terminal")
async def project_terminal(
    websocket: WebSocket,
    project_id: int,
    db: DbDep,
    settings: SettingsDep,
) -> None:
    if not _same_origin(websocket):
        await websocket.close(code=WS_FORBIDDEN)
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

    session = service.TerminalSession(
        cwd, settings.terminal_shell, settings.terminal_read_chunk_bytes
    )
    try:
        session.start()
    except OSError:
        await websocket.close(code=WS_INTERNAL_ERROR)
        return

    sender = asyncio.create_task(_pump_output(session, websocket))
    receiver = asyncio.create_task(_pump_input(session, websocket))
    try:
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (sender, receiver):
            task.cancel()
        session.close()


async def _pump_output(session: service.TerminalSession, websocket: WebSocket) -> None:
    try:
        async for chunk in session.output():
            await websocket.send_bytes(chunk)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


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
