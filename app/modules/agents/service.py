from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import user_settings
from app.core.errors import ErrorCode, api_error
from app.modules.agents.base import Agent
from app.modules.agents.catalog import registry
from app.modules.agents.models import AgentSetting
from app.modules.agents.schemas import AgentDefinition
from app.modules.auth.models import User

DEFAULT_AGENT_KEY = "default_agent_id"

# Agent commands are bare executable names resolved on the server's PATH; reject
# anything that could escape the PATH lookup (slashes, whitespace, metacharacters).
COMMAND_MAX = 64
ARGS_MAX = 1024
# A built launch line is "command args"; keep the cap large enough that any
# accepted command/args pair still passes valid_launch.
LAUNCH_MAX = COMMAND_MAX + 1 + ARGS_MAX
_COMMAND_RE = re.compile(rf"^[A-Za-z0-9._+-]{{1,{COMMAND_MAX}}}$")


def valid_command(command: str) -> bool:
    """Only bare executable names may be probed or resolved on the PATH."""
    return _COMMAND_RE.fullmatch(command) is not None


def _has_control_chars(value: str) -> bool:
    return any(char in value for char in "\r\n\x00")


def valid_args(args: str) -> bool:
    """Agent arguments may contain spaces/flags but must stay on a single line."""
    return len(args) <= ARGS_MAX and not _has_control_chars(args)


def valid_launch(command_line: str) -> bool:
    """A launch line is typed verbatim into the shell: single non-empty line."""
    if not command_line.strip() or len(command_line) > LAUNCH_MAX:
        return False
    return not _has_control_chars(command_line)


def get_agent_settings(db: Session, user: User) -> list[AgentSetting]:
    return list(
        db.scalars(
            select(AgentSetting)
            .where(AgentSetting.user_id == user.id)
            .order_by(AgentSetting.agent_id)
        )
    )


def _overrides(db: Session, user: User) -> dict[str, AgentSetting]:
    return {setting.agent_id: setting for setting in get_agent_settings(db, user)}


def save_agent_setting(
    db: Session, user: User, agent_id: str, command: str, args: str
) -> AgentSetting:
    setting = db.scalar(
        select(AgentSetting).where(
            AgentSetting.user_id == user.id, AgentSetting.agent_id == agent_id
        )
    )
    if setting is None:
        setting = AgentSetting(user_id=user.id, agent_id=agent_id, command=command, args=args)
        db.add(setting)
    else:
        setting.command = command
        setting.args = args
    db.commit()
    db.refresh(setting)
    return setting


def list_agents(db: Session, user: User) -> list[AgentDefinition]:
    """Merge the registered catalog with the user's overrides and host detection."""
    overrides = _overrides(db, user)
    definitions: list[AgentDefinition] = []
    for agent in registry.all():
        spec = agent.spec
        override = overrides.get(spec.id)
        command = override.command if override else spec.command
        args = override.args if override else spec.args
        path = agent.detect(command)
        definitions.append(
            AgentDefinition(
                id=spec.id,
                label=spec.label,
                command=command,
                args=args,
                description=spec.description,
                homepage=spec.homepage,
                installed=path is not None,
                path=path,
            )
        )
    return definitions


def agent_exists(agent_id: str) -> bool:
    """Whether an id is registered in the catalog."""
    return registry.get(agent_id) is not None


def effective_config(db: Session, user: User, agent: Agent) -> tuple[str, str]:
    """Effective (command, args) for an agent, applying the user's override."""
    override = db.scalar(
        select(AgentSetting).where(
            AgentSetting.user_id == user.id, AgentSetting.agent_id == agent.id
        )
    )
    if override is None:
        return agent.spec.command, agent.spec.args
    return override.command, override.args


def resolve_launch(db: Session, user: User, agent_id: str) -> str | None:
    """Build the launch line for a registered agent, or ``None`` if unknown."""
    agent = registry.get(agent_id)
    if agent is None:
        return None
    return agent.build_launch(*effective_config(db, user, agent))


def get_default_agent_id(db: Session, user: User) -> str | None:
    """The agent the user selected as default, or ``None`` when unset."""
    return user_settings.get_value(db, user.id, DEFAULT_AGENT_KEY)


def set_default_agent(db: Session, user: User, agent_id: str | None) -> str | None:
    """Persist the user's default agent (``None`` clears the selection)."""
    if agent_id is None:
        user_settings.delete_value(db, user.id, DEFAULT_AGENT_KEY)
        return None
    user_settings.set_value(db, user.id, DEFAULT_AGENT_KEY, agent_id)
    return agent_id


def run_agent_prompt(
    db: Session,
    user: User,
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> tuple[str, str]:
    """Run the user's default agent once with ``prompt``.

    Returns ``(agent_id, stdout)`` with the raw output; callers own any
    formatting. Raises an API error when no default agent is selected, the
    agent cannot run prompts, or the command fails.
    """
    agent_id = get_default_agent_id(db, user)
    if not agent_id:
        raise api_error(ErrorCode.AGENT_NOT_CONFIGURED, status_code=status.HTTP_400_BAD_REQUEST)

    agent = registry.get(agent_id)
    if agent is None:
        raise api_error(ErrorCode.AGENT_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND)

    command, args = effective_config(db, user, agent)
    argv = agent.build_prompt_command(command, args, prompt)
    if argv is None:
        raise api_error(ErrorCode.AGENT_UNSUPPORTED, status_code=status.HTTP_400_BAD_REQUEST)

    env = os.environ.copy()
    env.update(agent.env_overrides())
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise api_error(
            ErrorCode.AGENT_GENERATE_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) from exc

    if result.returncode != 0:
        raise api_error(
            ErrorCode.AGENT_GENERATE_FAILED, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return agent_id, result.stdout


async def list_models(db: Session, user: User, agent_id: str, ttl_seconds: int) -> list[str] | None:
    """Models a registered agent can use, or ``None`` if the agent is unknown."""
    agent = registry.get(agent_id)
    if agent is None:
        return None
    command, args = effective_config(db, user, agent)
    return await _cached_models(agent, command, args, ttl_seconds)


# Model listing can spawn a CLI, so cache results to avoid a process per UI render.
_models_cache: dict[tuple[str, str, str], tuple[float, list[str]]] = {}


async def _cached_models(agent: Agent, command: str, args: str, ttl_seconds: int) -> list[str]:
    key = (agent.id, command, args)
    now = time.monotonic()
    cached = _models_cache.get(key)
    if cached is not None and ttl_seconds > 0 and now - cached[0] < ttl_seconds:
        return cached[1]
    models = await agent.list_models(command, args)
    _models_cache[key] = (now, models)
    return models


def clear_models_cache() -> None:
    """Drop all cached model lists (used by tests)."""
    _models_cache.clear()


def agent_env(agent_id: str) -> dict[str, str]:
    """Environment overrides the agent needs, empty for unknown agents."""
    agent = registry.get(agent_id)
    return agent.env_overrides() if agent is not None else {}
