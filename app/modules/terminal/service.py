import asyncio
import fcntl
import os
import re
import struct
import subprocess
import termios
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import User
from app.modules.auth.security import decode_access_token
from app.modules.projects.models import Project

_TERMINAL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_TMUX_CONFIG = Path(__file__).with_name("tmux.conf")


def valid_terminal_id(terminal_id: str) -> bool:
    """Terminal ids come from the client and are embedded in the tmux session
    name, so they must be restricted to a safe character set."""
    return _TERMINAL_ID_RE.fullmatch(terminal_id) is not None


def session_name(user_id: int, project_id: int, terminal_id: str) -> str:
    return f"rc-{user_id}-{project_id}-{terminal_id}"


def create_session(settings: Settings, name: str, cwd: Path) -> None:
    """Create the tmux session detached if it does not exist yet.

    Starting the server from this short-lived call (rather than from the PTY
    client) keeps the session independent of the WebSocket connection.
    """
    _tmux(
        settings,
        "-f",
        str(_TMUX_CONFIG),
        "new-session",
        "-d",
        "-s",
        name,
        "-c",
        str(cwd),
        settings.terminal_shell,
    )


def attach_command(settings: Settings, name: str) -> list[str]:
    """Command that attaches a PTY to the persistent tmux session."""
    return [
        settings.terminal_tmux_binary,
        "-L",
        settings.terminal_tmux_socket,
        "attach-session",
        "-t",
        name,
    ]


def kill_session(settings: Settings, name: str) -> None:
    _tmux(settings, "kill-session", "-t", name)


def reap_idle_sessions(settings: Settings) -> None:
    """Kill detached sessions that have been idle past the configured TTL."""
    if settings.terminal_session_ttl_seconds <= 0:
        return

    result = _tmux(
        settings,
        "list-sessions",
        "-F",
        "#{session_name}\t#{session_attached}\t#{session_activity}",
    )
    if result is None:
        return

    now = int(time.time())
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, attached, activity = parts
        if attached != "0" or not name.startswith("rc-"):
            continue
        try:
            idle_seconds = now - int(activity)
        except ValueError:
            continue
        if idle_seconds >= settings.terminal_session_ttl_seconds:
            kill_session(settings, name)


def _tmux(settings: Settings, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [settings.terminal_tmux_binary, "-L", settings.terminal_tmux_socket, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None


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
    """Bridge a host PTY to an asyncio consumer.

    The child command runs with the project directory as its working directory
    and in its own session. The command is normally ``tmux ... new-session -A``,
    so the actual shell outlives this object and can be re-attached later.
    """

    def __init__(self, command: list[str], cwd: Path, read_chunk_bytes: int) -> None:
        self._command = command
        self._cwd = cwd
        self._chunk = read_chunk_bytes
        self._process: subprocess.Popen[bytes] | None = None
        self._master_fd = -1
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        master_fd, slave_fd = os.openpty()
        env = os.environ.copy()
        env["TERM"] = env.get("TERM", "xterm-256color")

        try:
            process = subprocess.Popen(
                self._command,
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
            raise
        finally:
            os.close(slave_fd)

        self._process = process
        self._master_fd = master_fd

        self._loop = asyncio.get_running_loop()
        os.set_blocking(master_fd, False)
        self._loop.add_reader(master_fd, self._on_readable)

    def _on_readable(self) -> None:
        try:
            data = os.read(self._master_fd, self._chunk)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""

        if not data:
            self._remove_reader()
            self._queue.put_nowait(None)
            return
        self._queue.put_nowait(data)

    def _remove_reader(self) -> None:
        if self._loop is not None and self._master_fd >= 0:
            self._loop.remove_reader(self._master_fd)

    async def output(self) -> AsyncIterator[bytes]:
        while True:
            data = await self._queue.get()
            if data is None:
                return
            yield data

    def write(self, data: bytes) -> None:
        if self._master_fd < 0:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        if self._master_fd < 0:
            return
        if cols <= 0 or rows <= 0:
            return
        try:
            fcntl.ioctl(
                self._master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )
        except OSError:
            pass

    def close(self) -> None:
        self._remove_reader()
        self._queue.put_nowait(None)

        if self._master_fd >= 0:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = -1

        if self._process is not None:
            process = self._process
            # Closing the PTY master makes the tmux client detach; the tmux
            # session (and its shell) keeps running for a later re-attach.
            threading.Thread(target=process.wait, daemon=True).start()
            self._process = None
