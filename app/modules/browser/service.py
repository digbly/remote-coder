from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import Settings

BrowserKey = tuple[int, int, str]

# A runner executes an agent-browser argv with its environment and returns
# stdout. It is injectable so tests never need the real binary.
CommandRunner = Callable[[list[str], dict[str, str]], str | None]

COMMAND_TIMEOUT_SECONDS = 30

NAVIGATION_ACTIONS = frozenset({"back", "forward", "reload"})

_SESSION_RE = re.compile(r"[^A-Za-z0-9._-]+")

DEFAULT_SESSION = "default"


class BrowserError(RuntimeError):
    """Raised when a browser session cannot be started or driven."""


def safe_session(name: str) -> str:
    """Turn a client-supplied session id into a filesystem-safe component."""
    cleaned = _SESSION_RE.sub("-", name).strip("-.")
    return cleaned[:64] or DEFAULT_SESSION


def session_name(user_id: int, project_id: int, session: str) -> str:
    return f"u{user_id}-p{project_id}-{session}"


def session_env(name: str, settings: Settings) -> dict[str, str]:
    """Environment for every agent-browser call in one session.

    The session name is carried through the environment so the argv stays free
    of repeated global options. The stream port is left to agent-browser, which
    auto-assigns one; ``stream status`` reports the real port.
    """
    env = os.environ.copy()
    env["AGENT_BROWSER_SESSION"] = name
    env["AGENT_BROWSER_STREAM_QUALITY"] = str(settings.browser_stream_quality)
    return env


def open_command(settings: Settings) -> list[str]:
    """Launch Chrome for the current session without navigating."""
    args = [settings.browser_binary, "open"]
    if not settings.browser_headless:
        args.append("--headed")
    if settings.browser_allowed_domains.strip():
        args.extend(["--allowed-domains", settings.browser_allowed_domains])
    # Keep new-tab links in the current tab: the panel has no tab bar, so a
    # spawned tab would be invisible.
    init_script = Path(__file__).with_name("force_same_tab.js")
    if init_script.is_file():
        args.extend(["--init-script", str(init_script)])
    if settings.browser_extra_args.strip():
        args.extend(shlex.split(settings.browser_extra_args))
    return args


def status_command(settings: Settings) -> list[str]:
    return [settings.browser_binary, "stream", "status", "--json"]


def stream_enable_command(settings: Settings) -> list[str]:
    return [settings.browser_binary, "stream", "enable"]


def close_command(settings: Settings) -> list[str]:
    return [settings.browser_binary, "close"]


def navigate_command(url: str, settings: Settings) -> list[str]:
    return [settings.browser_binary, "open", url]


def action_command(action: str, settings: Settings) -> list[str]:
    if action not in NAVIGATION_ACTIONS:
        raise BrowserError(f"unsupported browser action: {action}")
    return [settings.browser_binary, action]


def viewport_command(width: int, height: int, settings: Settings) -> list[str]:
    return [settings.browser_binary, "set", "viewport", str(width), str(height)]


def insert_text_command(text: str, settings: Settings) -> list[str]:
    # A NUL byte cannot be passed through argv; drop it defensively.
    return [settings.browser_binary, "keyboard", "inserttext", text.replace("\x00", "")]


# Returns the current selection: the focused input/textarea's selection, or the
# document selection otherwise.
SELECTION_JS = (
    "(function(){var a=document.activeElement;"
    "if(a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA')&&typeof a.selectionStart==='number')"
    "{return a.value.substring(a.selectionStart,a.selectionEnd);}"
    "return String(window.getSelection());})()"
)


def selection_command(settings: Settings) -> list[str]:
    return [settings.browser_binary, "eval", SELECTION_JS, "--json"]


def is_http_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _default_runner(command: list[str], env: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserError("could not run agent-browser") from exc
    if result.returncode != 0:
        raise BrowserError("agent-browser command failed")
    return result.stdout


def parse_status(output: str | None) -> dict[str, object] | None:
    """Extract the JSON status object from agent-browser stdout."""
    if not output:
        return None
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end < start:
        return None
    try:
        data = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _enabled_status(
    runner: CommandRunner, env: dict[str, str], settings: Settings
) -> dict[str, object] | None:
    """Return the stream ``data`` block when the session's stream is enabled.

    ``agent-browser stream status --json`` wraps its payload as
    ``{"success": true, "data": {...}, "error": null}``, so ``enabled`` and
    ``port`` live under ``data``.
    """
    status = parse_status(runner(status_command(settings), env))
    if status is None:
        return None
    data = status.get("data")
    if isinstance(data, dict) and data.get("enabled"):
        return data
    return None


@dataclass
class BrowserSession:
    """A live agent-browser session serving one project over a stream port."""

    host: str
    port: int
    name: str
    runner: CommandRunner
    settings: Settings
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    def alive(self) -> bool:
        try:
            return _enabled_status(self.runner, self._env(), self.settings) is not None
        except BrowserError:
            return False

    def run(self, command: list[str]) -> str | None:
        try:
            return self.runner(command, self._env())
        except BrowserError as exc:
            raise BrowserError("browser command failed") from exc

    def kill(self) -> None:
        try:
            self.runner(close_command(self.settings), self._env())
        except BrowserError:
            pass

    def _env(self) -> dict[str, str]:
        return session_env(self.name, self.settings)


class BrowserManager:
    """Keeps agent-browser sessions keyed by user and project."""

    def __init__(self) -> None:
        self._sessions: dict[BrowserKey, BrowserSession] = {}
        self._lock = threading.Lock()

    def get(self, key: BrowserKey) -> BrowserSession | None:
        with self._lock:
            return self._sessions.get(key)

    def ensure(
        self,
        key: BrowserKey,
        *,
        name: str,
        settings: Settings,
        runner: CommandRunner | None = None,
    ) -> BrowserSession:
        """Return the running session for ``key``, starting one if needed."""
        run = runner or _default_runner
        with self._lock:
            existing = self._sessions.get(key)
            if existing is not None and existing.alive():
                existing.touch()
                return existing
            if existing is not None:
                del self._sessions[key]

            self._evict_lru(settings.browser_max_sessions)
            session = self._start(name=name, settings=settings, runner=run)
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
        *,
        name: str,
        settings: Settings,
        runner: CommandRunner,
    ) -> BrowserSession:
        host = settings.browser_bind_host
        env = session_env(name, settings)
        runner(open_command(settings), env)

        status = _enabled_status(runner, env, settings)
        if status is None:
            # Streaming is on by default; enable explicitly if the session came
            # up without it (for example a reused daemon).
            with suppress(BrowserError):
                runner(stream_enable_command(settings), env)
            status = _enabled_status(runner, env, settings)

        port = status.get("port") if status is not None else None
        if not isinstance(port, int) or port <= 0:
            raise BrowserError("the browser stream server did not report a port")
        return BrowserSession(host=host, port=port, name=name, runner=runner, settings=settings)

    def kill(self, key: BrowserKey) -> None:
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


manager = BrowserManager()
