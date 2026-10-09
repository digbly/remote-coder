from __future__ import annotations

import os
import re
import shlex
import signal
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings

VSCodeKey = tuple[int, int, str]

LaunchBuilder = Callable[[int, Path, Path], list[str]]

_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class VSCodeError(RuntimeError):
    """Raised when a VS Code server session cannot be started."""


def safe_name(name: str) -> str:
    """Turn a client-supplied worktree name into a filesystem-safe component."""
    cleaned = _UNSAFE_NAME_RE.sub("-", name).strip("-.")
    return cleaned or "worktree"


def user_data_dir(settings: Settings, user_id: int, project_id: int, name: str) -> Path:
    root = Path(settings.vscode_user_data_root).expanduser()
    return root / f"u{user_id}" / f"p{project_id}" / safe_name(name)


def launch_command(port: int, cwd: Path, data_dir: Path, settings: Settings) -> list[str]:
    """Build the argv for a code-server instance bound to ``port``.

    ``--auth none`` is safe because the server only listens on the loopback
    interface; authentication is enforced by the FastAPI reverse proxy in front
    of it.
    """
    args = [
        settings.vscode_binary,
        "--bind-addr",
        f"{settings.vscode_bind_host}:{port}",
        "--auth",
        "none",
        "--disable-telemetry",
        "--disable-update-check",
        "--disable-workspace-trust",
        "--user-data-dir",
        str(data_dir),
    ]
    if settings.vscode_extra_args.strip():
        args.extend(shlex.split(settings.vscode_extra_args))
    args.append(str(cwd))
    return args


@dataclass
class VSCodeSession:
    """A live code-server process serving a single worktree."""

    cwd: Path
    host: str
    port: int
    data_dir: Path
    process: subprocess.Popen[bytes]
    last_seen: float = field(default_factory=time.monotonic)
    on_exit: Callable[[VSCodeSession], None] | None = None

    @property
    def http_base(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_base(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def alive(self) -> bool:
        return self.process.poll() is None

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def kill(self) -> None:
        process = self.process
        if process.poll() is None:
            for sig in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                    break
                except (ProcessLookupError, PermissionError):
                    break
            threading.Thread(target=process.wait, daemon=True).start()

    def track_exit(self) -> None:
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        self.process.wait()
        if self.on_exit is not None:
            self.on_exit(self)


def _free_port(host: str, start: int, end: int) -> int:
    if end <= start:
        end = start + 1
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise VSCodeError("no free port available for the VS Code server")


def _wait_ready(session: VSCodeSession, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        if not session.alive():
            return False
        try:
            with socket.create_connection((session.host, session.port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


class VSCodeManager:
    """Keeps code-server processes keyed by user, project and worktree."""

    def __init__(self) -> None:
        self._sessions: dict[VSCodeKey, VSCodeSession] = {}
        self._lock = threading.Lock()

    def get(self, key: VSCodeKey) -> VSCodeSession | None:
        with self._lock:
            return self._sessions.get(key)

    def ensure(
        self,
        key: VSCodeKey,
        *,
        cwd: Path,
        settings: Settings,
        launch_builder: LaunchBuilder | None = None,
    ) -> VSCodeSession:
        """Return the running session for ``key``, starting one if needed."""
        with self._lock:
            existing = self._sessions.get(key)
            if existing is not None and existing.alive():
                existing.touch()
                return existing
            if existing is not None:
                del self._sessions[key]

            self._evict_lru(settings.vscode_max_sessions)
            session = self._start(key, cwd=cwd, settings=settings, launch_builder=launch_builder)
            self._sessions[key] = session
            return session

    def _evict_lru(self, max_sessions: int) -> None:
        """Free a slot by stopping the least recently used session.

        Called with the lock held, before a new session is inserted.
        """
        if max_sessions <= 0:
            return
        while len(self._sessions) >= max_sessions:
            victim_key = min(self._sessions, key=lambda key: self._sessions[key].last_seen)
            session = self._sessions.pop(victim_key)
            session.kill()

    def _start(
        self,
        key: VSCodeKey,
        *,
        cwd: Path,
        settings: Settings,
        launch_builder: LaunchBuilder | None,
    ) -> VSCodeSession:
        _, _, name = key
        host = settings.vscode_bind_host
        port = _free_port(host, settings.vscode_port_start, settings.vscode_port_end)
        data_dir = user_data_dir(settings, key[0], key[1], name)
        data_dir.mkdir(parents=True, exist_ok=True)

        builder = launch_builder or (lambda p, c, d: launch_command(p, c, d, settings))
        command = builder(port, cwd, data_dir)

        env = os.environ.copy()
        env["BROWSER"] = "none"
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            raise VSCodeError("could not launch the VS Code server") from exc

        session = VSCodeSession(cwd=cwd, host=host, port=port, data_dir=data_dir, process=process)
        session.on_exit = lambda ended, key=key: self._discard(key, ended)

        if not _wait_ready(session, settings.vscode_start_timeout_seconds):
            session.kill()
            raise VSCodeError("the VS Code server did not become ready")

        session.track_exit()
        return session

    def _discard(self, key: VSCodeKey, session: VSCodeSession) -> None:
        with self._lock:
            if self._sessions.get(key) is session:
                del self._sessions[key]

    def kill(self, key: VSCodeKey) -> None:
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
                if now - session.last_seen >= ttl_seconds
            ]
        for key in victims:
            self.kill(key)

    def kill_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.kill()


manager = VSCodeManager()
