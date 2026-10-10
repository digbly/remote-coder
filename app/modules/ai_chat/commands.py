import asyncio
import json
import os
import re
import shlex
import signal
from pathlib import Path

from app.modules.ai_chat.schemas import CommandPermission
from app.modules.ai_providers.base import ProviderTool, ToolCall

COMMAND_TIMEOUT_SECONDS = 20
COMMAND_OUTPUT_BYTES = 16_000
RUN_PROJECT_COMMAND_NAME = "run_project_command"
_SHELL_OPERATORS = re.compile(r"[;&|<>$`(){}*?\[\]\\\n\r]")
_READ_ONLY_COMMANDS = {"pwd", "ls"}
_READ_ONLY_LS_OPTIONS = {"-a", "-l", "-la", "-al", "-h", "-lh", "-1"}
_SENSITIVE_ENVIRONMENT_KEYS = {
    "SECRET_KEY",
    "ADMIN_PASSWORD",
    "AI_CREDENTIAL_ENCRYPTION_KEY",
}

RUN_PROJECT_COMMAND = ProviderTool(
    name=RUN_PROJECT_COMMAND_NAME,
    description=(
        "Run a command in the selected project directory. The user may need to approve it."
    ),
    parameters={
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
        "additionalProperties": False,
    },
)


def is_read_only_command(command: str) -> bool:
    if not command or len(command) > 2000 or _SHELL_OPERATORS.search(command):
        return False
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return False
    if not parts or any(not part for part in parts):
        return False
    executable = parts[0]
    if executable not in _READ_ONLY_COMMANDS:
        return False
    if executable == "pwd":
        return len(parts) == 1
    if executable == "ls":
        after_separator = False
        for part in parts[1:]:
            if part == "--":
                after_separator = True
            elif not after_separator and part.startswith("-"):
                if part not in _READ_ONLY_LS_OPTIONS:
                    return False
            elif not _is_safe_relative_path(part):
                return False
        return True
    return False


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not any(character in value for character in ("~", "^", ":", "\x00"))
    )


def command_needs_approval(command: str, permission: CommandPermission) -> bool:
    if permission is CommandPermission.ALLOW_ALL:
        return False
    if permission is CommandPermission.MANUAL:
        return True
    return not is_read_only_command(command)


async def execute_project_command(cwd: Path, command: str) -> str:
    if not command or len(command) > 2000 or "\x00" in command:
        return _encode({"error": "invalid_command"})

    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        parts = []
    if is_read_only_command(command):
        executable = "/bin/pwd" if parts[0] == "pwd" else "/bin/ls"
        arguments = [executable, *parts[1:]]
    else:
        arguments = ["/bin/sh", "-c", command]
    environment = os.environ.copy()
    for key in _SENSITIVE_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=cwd,
        env=environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    output = bytearray()
    truncated = False
    try:
        async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
            assert process.stdout is not None
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                remaining = COMMAND_OUTPUT_BYTES - len(output)
                output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True
                    _kill_process_group(process.pid)
                    break
            await process.wait()
    except TimeoutError:
        _kill_process_group(process.pid)
        await process.wait()
        return _encode(
            {
                "output": output.decode("utf-8", errors="replace"),
                "exit_code": process.returncode,
                "error": "command_timed_out",
            }
        )
    finally:
        if process.returncode is None:
            _kill_process_group(process.pid)
            await process.wait()

    return _encode(
        {
            "output": output.decode("utf-8", errors="replace"),
            "exit_code": process.returncode,
            "truncated": truncated,
        }
    )


def command_from_call(call: ToolCall) -> str | None:
    if call.name != RUN_PROJECT_COMMAND_NAME or set(call.arguments) != {"command"}:
        return None
    command = call.arguments.get("command")
    if not isinstance(command, str) or not command.strip() or len(command) > 2000:
        return None
    return command


def _encode(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _kill_process_group(process_id: int) -> None:
    try:
        os.killpg(process_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
