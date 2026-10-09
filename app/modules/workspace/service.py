from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.workspace.models import Workspace


def load_state(db: Session, user_id: int) -> dict | None:
    workspace = db.scalar(select(Workspace).where(Workspace.user_id == user_id))
    return dict(workspace.payload) if workspace is not None else None


def save_state(db: Session, user_id: int, payload: dict) -> None:
    workspace = db.scalar(select(Workspace).where(Workspace.user_id == user_id))
    if workspace is not None:
        workspace.payload = payload
        db.commit()
        return

    db.add(Workspace(user_id=user_id, payload=payload))
    try:
        db.commit()
    except IntegrityError:
        # Another worker inserted the row first (unique on user_id): fall back
        # to an update so concurrent writers do not lose the state.
        db.rollback()
        workspace = db.scalar(select(Workspace).where(Workspace.user_id == user_id))
        if workspace is None:
            raise
        workspace.payload = payload
        db.commit()


class WorkspaceHub:
    """Fans out workspace updates to every live connection of a user.

    Each connection owns a bounded queue; a dedicated pump task on the
    connection's event loop drains it, so a slow client can never block the
    broadcaster or the other connections. A subscriber may run on a different
    event loop (for example under the threaded test client), so delivery goes
    through ``call_soon_threadsafe``.
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]]] = (
            {}
        )

    def subscribe(self, loop: asyncio.AbstractEventLoop, user_id: int) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
        self._subscribers.setdefault(user_id, []).append((loop, queue))
        return queue

    def unsubscribe(self, user_id: int, queue: asyncio.Queue[str]) -> None:
        subscribers = self._subscribers.get(user_id)
        if subscribers is None:
            return
        remaining = [item for item in subscribers if item[1] is not queue]
        if remaining:
            self._subscribers[user_id] = remaining
        else:
            self._subscribers.pop(user_id, None)

    def broadcast(
        self,
        user_id: int,
        message: str,
        *,
        exclude: asyncio.Queue[str] | None = None,
    ) -> None:
        for loop, queue in list(self._subscribers.get(user_id, ())):
            if queue is exclude:
                continue
            self._post(loop, queue, message)

    @staticmethod
    def _deliver(queue: asyncio.Queue[str], message: str) -> None:
        if queue.full():
            # Keep only the freshest state for a slow subscriber.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _post(
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[str],
        message: str,
    ) -> None:
        try:
            loop.call_soon_threadsafe(WorkspaceHub._deliver, queue, message)
        except RuntimeError:
            # The subscriber's event loop is already closed.
            pass


hub = WorkspaceHub()
