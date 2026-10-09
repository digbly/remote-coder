import pytest

from app.modules.agents.base import Agent, AgentSpec
from app.modules.agents.catalog import CliAgent
from app.modules.agents.registry import AgentRegistry


class _ProbeAgent(Agent):
    """Exercises the behaviour hooks a specialised agent would override."""

    def __init__(self, spec: AgentSpec) -> None:
        self.spec = spec

    def build_launch(self, command: str | None = None, args: str | None = None) -> str:
        return "probe --special"

    def env_overrides(self) -> dict[str, str]:
        return {"PROBE_MODE": "1"}


def _spec(agent_id: str = "probe") -> AgentSpec:
    return AgentSpec(id=agent_id, label="Probe", command="probe")


def test_registry_registers_and_resolves_by_id() -> None:
    registry = AgentRegistry()
    agent = _ProbeAgent(_spec())

    registry.register(agent)

    assert registry.get("probe") is agent
    assert "probe" in registry
    assert registry.ids() == ["probe"]
    assert registry.all() == [agent]


def test_registry_rejects_duplicate_ids() -> None:
    registry = AgentRegistry()
    registry.register(_ProbeAgent(_spec()))

    with pytest.raises(ValueError):
        registry.register(_ProbeAgent(_spec()))


def test_unknown_agent_is_not_registered() -> None:
    assert AgentRegistry().get("missing") is None


def test_cli_agent_builds_launch_from_command_and_args() -> None:
    agent = CliAgent(AgentSpec(id="x", label="X", command="cmd", args="--flag"))

    assert agent.build_launch() == "cmd --flag"
    assert agent.build_launch("other", "--x") == "other --x"
    assert agent.build_launch("other", "") == "other"


def test_cli_agent_detects_on_path() -> None:
    assert CliAgent(AgentSpec(id="sh", label="Sh", command="sh")).detect() is not None
    missing = CliAgent(AgentSpec(id="nope", label="Nope", command="definitely-missing-xyz"))
    assert missing.detect() is None


def test_subclass_overrides_default_behaviour() -> None:
    agent = _ProbeAgent(_spec())

    assert agent.build_launch("ignored", "ignored") == "probe --special"
    assert agent.env_overrides() == {"PROBE_MODE": "1"}


async def test_default_agent_lists_no_models() -> None:
    agent = CliAgent(AgentSpec(id="x", label="X", command="cmd"))

    assert await agent.list_models("cmd", "") == []
