from __future__ import annotations

import asyncio
import base64
import binascii
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
from uuid import uuid4

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ErrorCode, api_error
from app.modules.auth.models import User
from app.modules.projects.models import Project
from app.modules.terminal.schemas import TerminalImageUpload

_TERMINAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Media types the terminal accepts for a pasted image, mapped to a file suffix.
_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}

# Pasted images are written under this hidden folder in the project so a pasted
# screenshot never becomes an untracked git file; the shell reads it by path.
_IMAGE_DIR = Path(".remote-coder") / "images"
_GITIGNORE_ENTRY = ".remote-coder/"

DEFAULT_COLS = 80
DEFAULT_ROWS = 24

# A user-defined command script is typed verbatim into the shell, one line at a
# time. Keep a generous cap and reject control characters that could not have
# come from a real "one command per line" list.
SCRIPT_MAX = 8192
_SCRIPT_FORBIDDEN = "\r\x00"

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


def valid_command_script(script: str) -> bool:
    """A command script is non-empty, bounded, and free of control characters.

    Newlines are allowed because each line is a separate command typed into the
    shell; carriage returns and NUL would corrupt the input line.
    """
    if not script.strip() or len(script) > SCRIPT_MAX:
        return False
    return not any(char in script for char in _SCRIPT_FORBIDDEN)


def get_project(db: Session, user: User, project_id: int) -> Project | None:
    return db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))


def save_image(project: Project, payload: TerminalImageUpload, settings: Settings) -> Path:
    """Validate and persist a pasted image under the project, returning its path.

    The image is written to the project's hidden ``.remote-coder/images`` folder
    (which is added to the project's ``.gitignore``) so the terminal shell can
    read it by the returned absolute path without polluting the git status.
    """
    extension = _IMAGE_EXTENSIONS.get(payload.media_type)
    if extension is None:
        raise api_error(ErrorCode.TERMINAL_IMAGE_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    # ``data`` is base64, so its decoded size is roughly 3/4 of the string.
    if len(payload.data) > settings.terminal_image_max_bytes // 3 * 4 + 16:
        raise api_error(
            ErrorCode.TERMINAL_IMAGE_TOO_LARGE,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    try:
        data = base64.b64decode(payload.data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise api_error(
            ErrorCode.TERMINAL_IMAGE_INVALID, status_code=status.HTTP_400_BAD_REQUEST
        ) from exc

    if not data:
        raise api_error(ErrorCode.TERMINAL_IMAGE_INVALID, status_code=status.HTTP_400_BAD_REQUEST)
    if len(data) > settings.terminal_image_max_bytes:
        raise api_error(
            ErrorCode.TERMINAL_IMAGE_TOO_LARGE,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    root = Path(project.path)
    if not root.is_dir():
        raise api_error(ErrorCode.PROJECT_PATH_INVALID, status_code=status.HTTP_400_BAD_REQUEST)

    directory = root / _IMAGE_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"image-{uuid4().hex}.{extension}"
        target.write_bytes(data)
    except OSError as exc:
        raise api_error(
            ErrorCode.FILE_WRITE_FAILED, status_code=status.HTTP_400_BAD_REQUEST
        ) from exc

    _ensure_gitignored(root)
    return target


def _ensure_gitignored(root: Path) -> None:
    """Add the image folder to the project's ``.gitignore`` once."""
    gitignore = root / ".gitignore"
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    except OSError:
        return
    if any(
        line.strip().rstrip("/") == _GITIGNORE_ENTRY.rstrip("/") for line in existing.splitlines()
    ):
        return
    try:
        with gitignore.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(f"{_GITIGNORE_ENTRY}\n")
    except OSError:
        return


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
        worktree: str | None = None,
    ) -> None:
        self._cwd = cwd
        self._shell = shell
        self._env = env or {}
        self.worktree = worktree
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

    def foreground_running(self) -> bool:
        """Whether a command (rather than the idle shell) owns the terminal.

        The shell holds the terminal's foreground process group while it waits
        at its prompt; a spawned command takes that group over for the duration
        it runs. ``tcgetpgrp`` reports the current foreground group, so a value
        differing from the shell's own process group means a command is
        actually executing.
        """
        fd = self._master_fd
        process = self._process
        if fd < 0 or process is None:
            return False
        try:
            foreground = os.tcgetpgrp(fd)
        except OSError:
            return False
        return foreground != process.pid

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
        worktree: str | None = None,
    ) -> tuple[TerminalSession, bool]:
        """Return the live session for ``key`` and whether it was just created."""
        with self._lock:
            session = self._sessions.get(key)
            if session is not None and not session.exited:
                return session, False

            session = TerminalSession(
                cwd, shell, read_chunk_bytes, replay_bytes, queue_chunks, env, worktree
            )
            session.on_exit = lambda ended, key=key: self._discard(key, ended)
            session.start()
            self._sessions[key] = session
            return session, True

    def running_worktrees_by_project(self, user_id: int) -> dict[int, list[str]]:
        """Return, per project, the worktrees with a foreground command running.

        A live shell sitting at its prompt is not "running": only sessions
        whose terminal is currently owned by a command are reported.
        """
        with self._lock:
            grouped: dict[int, set[str]] = {}
            for (uid, pid, _), session in self._sessions.items():
                if uid != user_id or session.worktree is None or session.exited:
                    continue
                if not session.foreground_running():
                    continue
                grouped.setdefault(pid, set()).add(session.worktree)
        return {pid: sorted(names) for pid, names in grouped.items()}

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
