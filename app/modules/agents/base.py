from __future__ import annotations

import shlex
import shutil
from abc import ABC
from dataclasses import dataclass

PROMPT_PLACEHOLDER = "{prompt}"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Declarative metadata describing a launchable coding agent."""

    id: str
    label: str
    command: str
    args: str = ""
    description: str = ""
    homepage: str | None = None
    # How to pass a one-shot prompt on the command line, e.g.
    # ``("-p", "{prompt}")`` or ``("exec", "{prompt}")``. Empty means the agent
    # has no known non-interactive prompt mode.
    prompt_args: tuple[str, ...] = ()


class Agent(ABC):
    """Strategy for a single launchable coding agent.

    Adding an agent to the product means declaring its :class:`AgentSpec` and
    registering an instance against the shared registry; no other module has to
    change. Subclasses override the behaviour hooks below only when the agent
    needs something other than the default "run ``command`` with ``args``".
    """

    spec: AgentSpec

    @property
    def id(self) -> str:
        return self.spec.id

    def detect(self, command: str | None = None) -> str | None:
        """Resolve the effective command on the host PATH, or ``None``."""
        return shutil.which(command or self.spec.command)

    def build_launch(self, command: str | None = None, args: str | None = None) -> str:
        """Return the single shell line used to start the agent for a session."""
        resolved_command = (command if command is not None else self.spec.command).strip()
        resolved_args = (args if args is not None else self.spec.args).strip()
        return f"{resolved_command} {resolved_args}".strip()

    def build_prompt_command(
        self, command: str | None, args: str | None, prompt: str
    ) -> list[str] | None:
        """Build the argv that runs the agent once with ``prompt`` and exits.

        Returns ``None`` when the agent declares no prompt mode (see
        :attr:`AgentSpec.prompt_args`) or the configured args cannot be parsed.
        """
        if not self.spec.prompt_args:
            return None
        resolved_command = (command if command is not None else self.spec.command).strip()
        if not resolved_command:
            return None
        try:
            extra = shlex.split(args if args is not None else self.spec.args)
        except ValueError:
            return None
        tail = [prompt if token == PROMPT_PLACEHOLDER else token for token in self.spec.prompt_args]
        return [resolved_command, *extra, *tail]

    async def list_models(self, command: str, args: str) -> list[str]:
        """Models this agent can use, given its effective command and args.

        The default agent has no way to enumerate models; agents that do
        override this (see :mod:`app.modules.agents.model_sources`).
        """
        return []

    def env_overrides(self) -> dict[str, str]:
        """Extra environment variables this agent needs when launched."""
        return {}
