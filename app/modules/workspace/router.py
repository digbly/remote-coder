import asyncio
import json
from contextlib import suppress

from anyio import ClosedResourceError
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import DbDep, SettingsDep
from app.core.errors import error_responses
from app.modules.auth.deps import CurrentUser
from app.modules.auth.websocket import same_origin, websocket_user
from app.modules.workspace import service

router = APIRouter(prefix="/workspace", tags=["workspace"])

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_TOO_LARGE = 1009
MAX_MESSAGE_BYTES = 1_000_000


class WorkspaceState(BaseModel):
    state: dict | None


@router.get("", responses=error_responses(401))
def get_workspace(current_user: CurrentUser, db: DbDep) -> WorkspaceState:
    return WorkspaceState(state=service.load_state(db, current_user.id))


@router.websocket("/ws")
async def sync_workspace(websocket: WebSocket, db: DbDep, settings: SettingsDep) -> None:
    if not same_origin(websocket):
        await websocket.close(code=WS_FORBIDDEN)
        return

    user = websocket_user(websocket, db, settings)
    if user is None:
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    user_id = user.id
    await websocket.accept()

    queue = service.hub.subscribe(asyncio.get_running_loop(), user_id)
    sender = asyncio.create_task(_pump_output(queue, websocket))
    receiver = asyncio.create_task(_pump_input(db, user_id, websocket, queue))
    try:
        await websocket.send_text(
            json.dumps({"type": "state", "state": service.load_state(db, user_id)})
        )
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        service.hub.unsubscribe(user_id, queue)
        for task in (sender, receiver):
            task.cancel()


async def _pump_output(queue: asyncio.Queue[str], websocket: WebSocket) -> None:
    try:
        while True:
            message = await queue.get()
            await websocket.send_text(message)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        with suppress(RuntimeError, ClosedResourceError):
            await websocket.close()


async def _pump_input(
    db: Session,
    user_id: int,
    websocket: WebSocket,
    own_queue: asyncio.Queue[str],
) -> None:
    try:
        while True:
            message = await websocket.receive_text()
            if len(message) > MAX_MESSAGE_BYTES:
                await websocket.close(code=WS_TOO_LARGE)
                return

            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue

            if not isinstance(payload, dict) or payload.get("type") != "update":
                continue

            state = payload.get("state")
            if not isinstance(state, dict):
                continue

            origin = payload.get("origin")
            service.save_state(db, user_id, state)
            service.hub.broadcast(
                user_id,
                json.dumps({"type": "state", "state": state, "origin": origin}),
                exclude=own_queue,
            )
    except (WebSocketDisconnect, RuntimeError):
        return
