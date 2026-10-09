from __future__ import annotations

import re
import shutil

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.models import AgentSetting
from app.modules.agents.schemas import AgentStatus
from app.modules.auth.models import User

# Agent commands are bare executable names resolved on the server's PATH; reject
# anything that could escape the PATH lookup (slashes, whitespace, metacharacters).
_COMMAND_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
MAX_AGENTS = 50
ARGS_MAX = 1024
LAUNCH_MAX = 1024


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


def detect_agents(commands: list[str]) -> list[AgentStatus]:
    """Report which of the requested commands are installed on the server's PATH."""
    agents: list[AgentStatus] = []
    seen: set[str] = set()
    for command in commands:
        if command in seen or not valid_command(command):
            continue
        seen.add(command)
        path = shutil.which(command)
        agents.append(AgentStatus(command=command, installed=path is not None, path=path))
    return agents


def get_agent_settings(db: Session, user: User) -> list[AgentSetting]:
    return list(
        db.scalars(
            select(AgentSetting)
            .where(AgentSetting.user_id == user.id)
            .order_by(AgentSetting.agent_id)
        )
    )


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
