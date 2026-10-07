import asyncio
import fcntl
import os
import signal
import struct
import termios
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import User
from app.modules.auth.security import decode_access_token
from app.modules.projects.models import Project


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


def _reap_child(pid: int) -> None:
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass


class TerminalSession:
    """Bridge a host PTY to an asyncio consumer.

    The child shell runs with the project directory as its working directory and
    in its own session (so the whole process group can be signalled on teardown).
    """

    def __init__(self, cwd: Path, shell: str, read_chunk_bytes: int) -> None:
        self._cwd = cwd
        self._shell = shell
        self._chunk = read_chunk_bytes
        self._pid = -1
        self._master_fd = -1
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        master_fd, slave_fd = os.openpty()
        pid = os.fork()
        if pid == 0:
            self._exec_child(master_fd, slave_fd)
            os._exit(1)

        os.close(slave_fd)
        self._pid = pid
        self._master_fd = master_fd

        self._loop = asyncio.get_running_loop()
        os.set_blocking(master_fd, False)
        self._loop.add_reader(master_fd, self._on_readable)

    def _exec_child(self, master_fd: int, slave_fd: int) -> None:
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        env = os.environ.copy()
        env["TERM"] = env.get("TERM", "xterm-256color")
        try:
            os.chdir(self._cwd)
            os.execvpe(self._shell, [self._shell], env)
        except OSError:
            os._exit(1)

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

        if self._pid > 0:
            for sig in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.killpg(self._pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
            threading.Thread(target=_reap_child, args=(self._pid,), daemon=True).start()
            self._pid = -1
