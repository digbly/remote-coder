from __future__ import annotations

import asyncio
import fcntl
import os
import re
import signal
import struct
import subprocess
import termios
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.projects.models import Project

_TERMINAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

DEFAULT_COLS = 80
DEFAULT_ROWS = 24

TerminalKey = tuple[int, int, str]


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    if cols <= 0 or rows <= 0:
        return
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


def valid_terminal_id(terminal_id: str) -> bool:
    """Terminal ids come from the client and are used as session keys."""
    return _TERMINAL_ID_RE.fullmatch(terminal_id) is not None


def get_project(db: Session, user: User, project_id: int) -> Project | None:
    return db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))


def _acquire_controlling_tty() -> None:
    """Runs in the child before exec; makes the PTY slave its controlling terminal.

    ``subprocess`` has already wired the slave to fd 0/1/2 by this point, so fd 0
    refers to the tty we want job control on.
    """
    try:
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    except OSError:
        pass


class TerminalSession:
    """A host PTY that outlives any single WebSocket connection.

    Output is buffered so a client that reconnects (for example after a browser
    reload) can replay the screen and continue where it left off. The shell is
    only terminated by an explicit :meth:`kill`.
    """

    def __init__(
        self,
        cwd: Path,
        shell: str,
        read_chunk_bytes: int,
        replay_bytes: int,
        queue_chunks: int,
        env: dict[str, str] | None = None,
    ) -> None:
        self._cwd = cwd
        self._shell = shell
        self._env = env or {}
        self._chunk = read_chunk_bytes
        self._replay_bytes = replay_bytes
        self._queue_chunks = max(1, queue_chunks)
        self._process: subprocess.Popen[bytes] | None = None
        self._master_fd = -1
        self._cols = DEFAULT_COLS
        self._rows = DEFAULT_ROWS
        self._buffer: deque[bytes] = deque()
        self._buffer_bytes = 0
        self._trimmed = False
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[bytes | None]]] = []
        self._lock = threading.Lock()
        self.exited = False
        self.detached_at: float | None = time.monotonic()
        self.on_exit: Callable[[TerminalSession], None] | None = None

    def start(self) -> None:
        master_fd, slave_fd = os.openpty()
        _set_winsize(slave_fd, DEFAULT_COLS, DEFAULT_ROWS)
        env = os.environ.copy()
        env["TERM"] = env.get("TERM", "xterm-256color")
        env.update(self._env)

        try:
            process = subprocess.Popen(
                [self._shell],
                cwd=self._cwd,
                env=env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                preexec_fn=_acquire_controlling_tty,
                close_fds=True,
            )
        except OSError:
            os.close(master_fd)
            os.close(slave_fd)
            raise

        os.close(slave_fd)
        self._process = process
        self._master_fd = master_fd

        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self) -> None:
        while True:
            fd = self._master_fd
            if fd < 0:
                break
            try:
                data = os.read(fd, self._chunk)
            except (OSError, ValueError):
                break
            if not data:
                break

            with self._lock:
                self._append(data)
                subscribers = list(self._subscribers)

            for loop, queue in subscribers:
                self._post(loop, queue, data)

        self._finish()

    def _finish(self) -> None:
        self.exited = True
        with self._lock:
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            self._post(loop, queue, None)
        if self.on_exit is not None:
            self.on_exit(self)

    def _append(self, data: bytes) -> None:
        self._buffer.append(data)
        self._buffer_bytes += len(data)
        while self._buffer_bytes > self._replay_bytes and self._buffer:
            self._buffer_bytes -= len(self._buffer.popleft())
            self._trimmed = True

    def _replay(self) -> bytes:
        data = b"".join(self._buffer)
        if self._trimmed:
            # The oldest bytes were dropped, so the buffer may start in the
            # middle of an escape sequence. Start from the first escape to give
            # the client a byte stream it can render without misinterpreting an
            # orphaned sequence fragment.
            escape = data.find(b"\x1b")
            if escape > 0:
                data = data[escape:]
        return data

    @staticmethod
    def _deliver(queue: asyncio.Queue[bytes | None], item: bytes | None) -> None:
        if queue.full():
            # A slow subscriber must not grow without bound; drop the oldest
            # chunk so it always receives the most recent output.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    @staticmethod
    def _post(
        loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[bytes | None], item: bytes | None
    ) -> None:
        try:
            loop.call_soon_threadsafe(TerminalSession._deliver, queue, item)
        except RuntimeError:
            # The subscriber's event loop is already closed.
            pass

    def subscribe(
        self, loop: asyncio.AbstractEventLoop
    ) -> tuple[asyncio.Queue[bytes | None], bytes]:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=self._queue_chunks)
        with self._lock:
            replay = self._replay()
            if self.exited:
                queue.put_nowait(None)
            else:
                self._subscribers.append((loop, queue))
                self.detached_at = None
        return queue, replay

    def unsubscribe(self, queue: asyncio.Queue[bytes | None]) -> None:
        with self._lock:
            self._subscribers = [item for item in self._subscribers if item[1] is not queue]
            if not self._subscribers:
                self.detached_at = time.monotonic()

    def write(self, data: bytes) -> None:
        fd = self._master_fd
        if fd < 0:
            return
        try:
            os.write(fd, data)
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        fd = self._master_fd
        if fd < 0:
            return
        # TIOCSWINSZ delivers SIGWINCH to the shell even when the size is
        # unchanged, and the shell redraws its prompt on each SIGWINCH. Skip
        # no-op resizes so duplicate events do not spew repeated prompts.
        if cols == self._cols and rows == self._rows:
            return
        self._cols = cols
        self._rows = rows
        _set_winsize(fd, cols, rows)

    def kill(self) -> None:
        process = self._process
        self._process = None
        if process is not None:
            for sig in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
            threading.Thread(target=process.wait, daemon=True).start()

        fd = self._master_fd
        self._master_fd = -1
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


class TerminalManager:
    """Keeps live terminal sessions keyed by user, project and terminal id."""

    def __init__(self) -> None:
        self._sessions: dict[TerminalKey, TerminalSession] = {}
        self._lock = threading.Lock()

    def attach(
        self,
        key: TerminalKey,
        *,
        cwd: Path,
        shell: str,
        read_chunk_bytes: int,
        replay_bytes: int,
        queue_chunks: int,
        env: dict[str, str] | None = None,
    ) -> tuple[TerminalSession, bool]:
        """Return the live session for ``key`` and whether it was just created."""
        with self._lock:
            session = self._sessions.get(key)
            if session is not None and not session.exited:
                return session, False

            session = TerminalSession(cwd, shell, read_chunk_bytes, replay_bytes, queue_chunks, env)
            session.on_exit = lambda ended, key=key: self._discard(key, ended)
            session.start()
            self._sessions[key] = session
            return session, True

    def _discard(self, key: TerminalKey, session: TerminalSession) -> None:
        with self._lock:
            if self._sessions.get(key) is session:
                del self._sessions[key]

    def kill(self, key: TerminalKey) -> None:
        with self._lock:
            session = self._sessions.pop(key, None)
        if session is not None:
            session.kill()

    def reap_idle(self, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        now = time.monotonic()
        with self._lock:
            victims = [
                key
                for key, session in self._sessions.items()
                if session.detached_at is not None and now - session.detached_at >= ttl_seconds
            ]
        for key in victims:
            self.kill(key)

    def kill_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.kill()


manager = TerminalManager()
