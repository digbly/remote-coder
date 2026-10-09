from __future__ import annotations

from app.modules.agents.base import Agent, AgentSpec
from app.modules.agents.model_sources import CliModelsAgent
from app.modules.agents.registry import AgentRegistry


class CliAgent(Agent):
    """Default strategy: launch the command with its arguments as-is."""

    def __init__(self, spec: AgentSpec) -> None:
        self.spec = spec


DEFAULT_AGENT_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(id="claude", label="Claude Code", command="claude"),
    AgentSpec(id="agy", label="Antigravity", command="agy"),
    AgentSpec(id="opencode", label="OpenCode", command="opencode"),
    AgentSpec(id="codex", label="Codex", command="codex"),
    AgentSpec(id="gemini", label="Gemini CLI", command="gemini"),
    AgentSpec(id="aider", label="Aider", command="aider"),
    AgentSpec(id="goose", label="Goose", command="goose"),
    AgentSpec(id="cursor-agent", label="Cursor Agent", command="cursor-agent"),
    AgentSpec(id="crush", label="Crush", command="crush"),
)

# Agents that expose their model list through a ``models`` subcommand. Others
# keep the default behaviour (no known models).
CLI_MODELS_AGENT_IDS = frozenset({"claude", "opencode"})


def build_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for spec in DEFAULT_AGENT_SPECS:
        if spec.id in CLI_MODELS_AGENT_IDS:
            registry.register(CliModelsAgent(spec))
        else:
            registry.register(CliAgent(spec))
    return registry


registry = build_default_registry()
