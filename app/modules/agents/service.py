from __future__ import annotations

import re
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.base import Agent
from app.modules.agents.catalog import registry
from app.modules.agents.models import AgentSetting
from app.modules.agents.schemas import AgentDefinition
from app.modules.auth.models import User

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
