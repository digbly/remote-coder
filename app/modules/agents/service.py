from __future__ import annotations

import re
import shutil

from app.modules.agents.schemas import AgentStatus

# Agent commands are bare executable names resolved on the server's PATH; reject
# anything that could escape the PATH lookup (slashes, whitespace, metacharacters).
_COMMAND_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
MAX_AGENTS = 50


def valid_command(command: str) -> bool:
    """Only bare executable names may be probed or typed into a shell."""
    return _COMMAND_RE.fullmatch(command) is not None


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
