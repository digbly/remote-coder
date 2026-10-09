from __future__ import annotations

from collections.abc import Iterator

from app.modules.agents.base import Agent


class AgentRegistry:
    """Central lookup mapping agent ids to their :class:`Agent` strategies.

    Agents are registered once (see :mod:`app.modules.agents.catalog`) and
    resolved by id everywhere else, so routing, persistence and the terminal
    never need to know about concrete agents.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> Agent:
        if agent.id in self._agents:
            raise ValueError(f"agent '{agent.id}' is already registered")
        self._agents[agent.id] = agent
        return agent

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def ids(self) -> list[str]:
        return list(self._agents)

    def __contains__(self, agent_id: object) -> bool:
        return agent_id in self._agents

    def __iter__(self) -> Iterator[Agent]:
        return iter(self._agents.values())
