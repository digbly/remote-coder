"""Detached AI chat turns.

A chat turn used to run inside the client's HTTP stream, so a dropped connection
(a mobile app going to the background, a reload, a flaky network) cancelled the
generation and lost the rest of the answer. Here a turn runs as an asyncio task
that owns its own database session, buffers every event it produces and fans
those events out to whichever stream is currently attached. The client can
disconnect and later reconnect at the offset it had already consumed, so the
answer keeps being produced while the app is away and continues on return.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.ai_chat import service
from app.modules.ai_chat.context import ProjectContext
from app.modules.ai_chat.models import ChatMessage, MessageStatus
from app.modules.ai_chat.schemas import CommandPermission
from app.modules.ai_chat.streaming import stream_chat_turn
from app.modules.ai_providers.base import ChatMessage as ProviderMessage
from app.modules.ai_providers.base import ProviderAdapter
from app.modules.auth.models import User

logger = logging.getLogger(__name__)

# How long a finished turn stays in memory so a client that dropped right before
# the end can still replay the tail instead of refetching the conversation.
TURN_RETENTION_SECONDS = 120.0
# A subscriber that cannot keep up (for example a stream whose socket is backed
# up) is detached rather than slowing the provider down; it resumes by offset.
SUBSCRIBER_QUEUE_CHUNKS = 2048

_STREAM_END: None = None


@dataclass(frozen=True)
class TurnRequest:
    """The plain, session-independent inputs needed to run one turn."""

    assistant_message_id: int
    user_id: int
    project_id: int
    project_path: Path | None
    conversation_id: str
    conversation_title: str
    user_message_id: int
    user_content: str
    model_id: str
    api_key: str
    adapter: ProviderAdapter
    history: Sequence[ProviderMessage]
    permission: CommandPermission
    skill_body: str | None


class Turn:
    """One detached chat turn: an event log plus its live subscribers."""

    def __init__(self, manager: TurnManager, assistant_message_id: int) -> None:
        self._manager = manager
        self.assistant_message_id = assistant_message_id
        self._events: list[bytes] = []
        self._subscribers: list[asyncio.Queue[bytes | None]] = []
        self._finished = False
        self._task: asyncio.Task[None] | None = None

    @property
    def finished(self) -> bool:
        return self._finished

    def attach(self, offset: int) -> asyncio.Queue[bytes | None]:
        """Return a queue with the events from ``offset`` already enqueued."""
        start = max(0, min(offset, len(self._events)))
        backlog = self._events[start:]
        # Size the queue to hold the whole backlog so replaying a long turn (many
        # text deltas) never overflows; the consumer drains it as it reads.
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(
            maxsize=len(backlog) + SUBSCRIBER_QUEUE_CHUNKS
        )
        for chunk in backlog:
            queue.put_nowait(chunk)
        if self._finished:
            queue.put_nowait(_STREAM_END)
        else:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[bytes | None]) -> None:
        with suppress(ValueError):
            self._subscribers.remove(queue)

    def _publish(self, chunk: bytes) -> None:
        self._events.append(chunk)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                self._subscribers.remove(queue)
                queue.put_nowait(_STREAM_END)

    def _finish(self) -> None:
        self._finished = True
        for queue in self._subscribers:
            queue.put_nowait(_STREAM_END)
        self._subscribers.clear()

    async def run(self, session_factory: Callable[[], Session], request: TurnRequest) -> None:
        try:
            with session_factory() as db:
                user = db.get(User, request.user_id)
                assistant = db.get(ChatMessage, request.assistant_message_id)
                if user is None or assistant is None:
                    return
                stream = stream_chat_turn(
                    db=db,
                    adapter=request.adapter,
                    api_key=request.api_key,
                    model_id=request.model_id,
                    context=ProjectContext(
                        db,
                        user,
                        request.project_id,
                        request.conversation_id,
                        request.project_path,
                        request.permission,
                    ),
                    permission=request.permission,
                    conversation_id=request.conversation_id,
                    conversation_title=request.conversation_title,
                    user_message_id=request.user_message_id,
                    user_content=request.user_content,
                    assistant_message=assistant,
                    history=list(request.history),
                    skill_body=request.skill_body,
                )
                async for chunk in stream:
                    self._publish(chunk)
        except asyncio.CancelledError:
            # Shutdown: ``stream_chat_turn`` has already persisted the partial
            # answer as interrupted. Nothing left to do but stop.
            self._mark_interrupted(session_factory)
            raise
        except Exception:
            logger.exception("AI chat turn failed id=%s", self.assistant_message_id)
            self._mark_interrupted(session_factory)
        finally:
            self._finish()
            try:
                asyncio.get_running_loop().call_later(
                    TURN_RETENTION_SECONDS,
                    self._manager.discard,
                    self.assistant_message_id,
                    self,
                )
            except RuntimeError:
                # No running loop (should not happen); leave it for reset().
                pass

    def cancel(self) -> None:
        """Cancel the running task; ``run`` persists the partial answer."""
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def _mark_interrupted(self, session_factory: Callable[[], Session]) -> None:
        """Persist an interrupted status when a failure escaped the generator."""
        try:
            with session_factory() as db:
                assistant = db.get(ChatMessage, self.assistant_message_id)
                if assistant is not None and assistant.status is MessageStatus.STREAMING:
                    service.finish_assistant(
                        db, assistant, assistant.content, MessageStatus.INTERRUPTED
                    )
        except Exception:
            logger.exception("Could not mark turn interrupted id=%s", self.assistant_message_id)


class TurnManager:
    """Tracks live turns by assistant message id so a client can re-attach."""

    def __init__(self) -> None:
        self._turns: dict[int, Turn] = {}

    def get(self, assistant_message_id: int) -> Turn | None:
        return self._turns.get(assistant_message_id)

    def start(self, session_factory: Callable[[], Session], request: TurnRequest) -> Turn:
        turn = Turn(self, request.assistant_message_id)
        self._turns[request.assistant_message_id] = turn
        turn._task = asyncio.create_task(turn.run(session_factory, request))
        return turn

    def discard(self, assistant_message_id: int, turn: Turn) -> None:
        if self._turns.get(assistant_message_id) is turn:
            del self._turns[assistant_message_id]

    def cancel(self, assistant_message_id: int) -> bool:
        """Cancel a live turn; returns whether the turn was still tracked."""
        turn = self._turns.get(assistant_message_id)
        if turn is None:
            return False
        turn.cancel()
        return True

    def reset(self) -> None:
        """Drop every tracked turn; for tests and shutdown."""
        for turn in list(self._turns.values()):
            if turn._task is not None:
                turn._task.cancel()
        self._turns.clear()


manager = TurnManager()
