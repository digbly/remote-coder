from __future__ import annotations

import asyncio
import shlex

from app.modules.agents.base import Agent, AgentSpec

MODELS_TIMEOUT_SECONDS = 10
MAX_MODELS = 200
MAX_OUTPUT_BYTES = 256 * 1024


class CliModelsAgent(Agent):
    """Lists models by running ``<command> [args] <subcommand>``.

    A CLI whose model listing is a subcommand only needs to declare that
    subcommand; no per-agent class is required. Override :meth:`parse_models`
    when the output is not one model id per line.
    """

    def __init__(self, spec: AgentSpec, subcommand: str = "models") -> None:
        self.spec = spec
        self._subcommand = subcommand

    async def list_models(self, command: str, args: str) -> list[str]:
        try:
            extra = shlex.split(args)
        except ValueError:
            return []
        argv = [command, *extra, self._subcommand]
        output = await _run(argv, MODELS_TIMEOUT_SECONDS)
        if output is None:
            return []
        return self.parse_models(output)

    def parse_models(self, output: bytes) -> list[str]:
        models: list[str] = []
        for line in output.decode("utf-8", errors="replace").splitlines():
            model = line.strip()
            if model and model not in models:
                models.append(model)
            if len(models) >= MAX_MODELS:
                break
        return models


async def _run(argv: list[str], timeout: float) -> bytes | None:
    """Run ``argv`` without a shell, returning at most ``MAX_OUTPUT_BYTES`` of stdout.

    ``None`` signals any failure — missing binary, non-zero exit, timeout, or more
    output than needed — which callers treat as "no models".
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        return None

    reader = process.stdout
    if reader is None:  # stdout=PIPE guarantees a reader
        _terminate(process)
        await process.wait()
        return None

    try:
        stdout = await asyncio.wait_for(reader.read(MAX_OUTPUT_BYTES + 1), timeout)
        if len(stdout) > MAX_OUTPUT_BYTES:
            # More output than a model list ever needs; stop reading to bound memory.
            _terminate(process)
            await process.wait()
            return stdout[:MAX_OUTPUT_BYTES]
        await process.wait()
    except (TimeoutError, OSError, ValueError):
        _terminate(process)
        await process.wait()
        return None

    if process.returncode != 0:
        return None
    return stdout


def _terminate(process: asyncio.subprocess.Process) -> None:
    try:
        process.kill()
    except ProcessLookupError:
        pass
