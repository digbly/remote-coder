import asyncio
import json
import os
import shlex
import signal
from collections.abc import Sequence
from pathlib import Path

from app.modules.ai_chat.schemas import CommandPermission
from app.modules.ai_providers.base import ProviderTool, ToolCall

COMMAND_TIMEOUT_SECONDS = 20
COMMAND_OUTPUT_BYTES = 16_000
RUN_PROJECT_COMMAND_NAME = "run_project_command"
_SHELL_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "{", "}"}
_SHELL_CONTROL_WORDS = {
    "case",
    "do",
    "done",
    "elif",
    "else",
    "esac",
    "fi",
    "for",
    "if",
    "then",
    "until",
    "while",
    "!",
}
_REDIRECTION_OPERATORS = {
    ">",
    ">>",
    ">|",
    ">&",
    "<>",
    "&>",
    "&>>",
}
_GIT_GLOBAL_OPTIONS_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--config-env",
    "--exec-path",
}
_DANGEROUS_COMMANDS = {
    "ansible-playbook",
    "chgrp",
    "chmod",
    "chown",
    "cp",
    "dd",
    "deploy",
    "install",
    "ln",
    "mkfs",
    "mkdir",
    "mv",
    "npx",
    "publish",
    "release",
    "rm",
    "rmdir",
    "rsync",
    "scp",
    "shred",
    "srm",
    "sudo",
    "tar",
    "tee",
    "touch",
    "truncate",
    "unlink",
    "unzip",
    "wipefs",
}
_GIT_MUTATING_COMMANDS = {
    "add",
    "am",
    "apply",
    "checkout",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "filter-branch",
    "fetch",
    "gc",
    "prune",
    "repack",
    "replace",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "rm",
    "switch",
    "symbolic-ref",
    "update-ref",
}
_GIT_READ_ONLY_SUBCOMMANDS = {
    "branch": {
        "--all",
        "--contains",
        "--format",
        "--list",
        "--merged",
        "--no-merged",
        "--points-at",
        "--remotes",
        "--show-current",
        "--sort",
        "-a",
        "-l",
        "-r",
    },
    "remote": {"--verbose", "-v", "show"},
    "stash": {"list", "show"},
    "tag": {
        "--contains",
        "--list",
        "--merged",
        "--no-contains",
        "--no-merged",
        "--points-at",
        "--sort",
        "-l",
        "-n",
    },
    "worktree": {"list"},
}
_GIT_MUTATING_FLAGS = {
    "branch": {
        "-c",
        "-C",
        "-d",
        "-D",
        "-m",
        "-M",
        "--copy",
        "--delete",
        "--move",
    },
    "tag": {
        "-a",
        "-d",
        "-f",
        "-s",
        "-u",
        "--annotate",
        "--delete",
        "--force",
        "--sign",
    },
}
_COMMAND_OPTIONS_WITH_VALUE = {
    "apt": {"-o", "--option"},
    "apt-get": {"-o", "--option"},
    "docker": {
        "-c",
        "--context",
        "-H",
        "--host",
        "-f",
        "--file",
        "-p",
        "--project-name",
        "--profile",
        "--env-file",
        "--project-directory",
    },
    "corepack": {"--install-directory"},
    "npm": {
        "-w",
        "--workspace",
        "--prefix",
        "--registry",
        "--cache",
        "--userconfig",
    },
    "pnpm": {
        "-C",
        "--dir",
        "-F",
        "--filter",
        "--registry",
        "--store-dir",
    },
    "yarn": {
        "--cwd",
        "--registry",
        "--cache-folder",
        "--modules-folder",
    },
}
_MUTATING_PACKAGE_OR_DEPLOY_SUBCOMMANDS = {
    "apt": {"install", "update", "upgrade", "remove", "purge", "autoremove"},
    "apt-get": {
        "install",
        "update",
        "upgrade",
        "dist-upgrade",
        "remove",
        "purge",
        "autoremove",
    },
    "brew": {"install", "upgrade", "uninstall", "link", "unlink"},
    "bun": {
        "add",
        "exec",
        "install",
        "link",
        "remove",
        "unlink",
        "update",
        "upgrade",
        "x",
    },
    "cargo": {"install"},
    "conda": {"install", "update", "remove", "uninstall"},
    "apk": {"add", "del", "upgrade"},
    "corepack": {"disable", "enable", "prepare", "use"},
    "dnf": {"install", "upgrade", "remove", "erase", "update", "groupinstall"},
    "docker": {"build", "push", "run", "rm", "rmi", "up", "down"},
    "fly": {"deploy", "launch", "scale", "destroy"},
    "gem": {"install", "uninstall", "update"},
    "gcloud": {"deploy"},
    "helm": {"install", "upgrade", "uninstall", "rollback"},
    "kubectl": {"apply", "create", "delete", "edit", "patch", "replace", "scale"},
    "make": {"install", "deploy", "release"},
    "mamba": {"install", "update", "remove", "uninstall"},
    "micromamba": {"install", "update", "remove", "uninstall"},
    "yum": {"install", "update", "upgrade", "remove", "erase", "groupinstall"},
    "zypper": {"install", "update", "patch", "remove"},
    "npm": {
        "exec",
        "install",
        "i",
        "ci",
        "add",
        "update",
        "up",
        "uninstall",
        "remove",
        "publish",
    },
    "pacman": {"-S", "-R", "-U"},
    "pip": {"install", "uninstall"},
    "pip3": {"install", "uninstall"},
    "pnpm": {"install", "i", "add", "update", "up", "remove", "dlx", "exec"},
    "pulumi": {"up", "destroy", "refresh"},
    "pipx": {"install", "uninstall", "upgrade"},
    "railway": {"up", "deploy"},
    "rpm": {"-i", "-e", "-U", "-F"},
    "snap": {"install", "remove", "refresh"},
    "systemctl": {
        "enable",
        "disable",
        "start",
        "stop",
        "restart",
        "reload",
        "mask",
        "unmask",
    },
    "terraform": {"apply", "destroy", "import"},
    "uv": {"add", "remove", "sync"},
    "vercel": {"deploy", "prod", "remove"},
    "wrangler": {"deploy", "publish", "delete"},
    "yarn": {"install", "add", "remove", "up", "upgrade", "dlx", "exec"},
    "poetry": {"add", "remove", "install", "update"},
    "bundle": {"install", "update"},
    "composer": {"install", "update", "require", "remove"},
    "go": {"get", "install"},
    "service": {"start", "stop", "restart", "reload"},
}
_DEPLOYMENT_VERBS = {"deploy", "publish", "release"}
_SHELL_EXECUTABLES = {"bash", "dash", "ksh", "sh", "zsh"}
_COMMAND_WRAPPERS = {
    "command",
    "corepack",
    "env",
    "exec",
    "nohup",
    "time",
    "xargs",
}
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


def command_is_dangerous(command: str) -> bool:
    return _command_is_dangerous(command, depth=0)


def _command_is_dangerous(command: str, depth: int) -> bool:
    if not command or len(command) > 2000:
        return False
    if depth >= 32:
        return True
    if any(
        _command_is_dangerous(nested, depth + 1)
        for nested in _shell_subcommands(command)
    ):
        return True
    try:
        tokens = _shell_tokens(command)
    except ValueError:
        tokens = command.split()

    if any(token in _REDIRECTION_OPERATORS for token in tokens):
        return True
    if _pipes_into_shell(tokens):
        return True
    for index in _command_positions(tokens):
        name = _command_name(tokens[index]).lower()
        if name == "env":
            split_command = _env_split_command(tokens, index + 1)
            if split_command is not None and _command_is_dangerous(
                split_command, depth + 1
            ):
                return True
        if name in _COMMAND_WRAPPERS:
            index = _unwrap_command(tokens, index)
            if index >= len(tokens):
                continue
            name = _command_name(tokens[index]).lower()
        if name in _DANGEROUS_COMMANDS:
            return True
        if name in _SHELL_EXECUTABLES:
            nested_command = _shell_command_argument(tokens, index + 1)
            if nested_command is not None and _command_is_dangerous(
                nested_command, depth + 1
            ):
                return True
        if name in {"python", "python2", "python3", "pypy", "pypy3"}:
            if index + 2 < len(tokens) and tokens[index + 1] == "-m":
                module = _command_name(tokens[index + 2]).lower()
                if module in {"pip", "pip3"} and any(
                    argument in {"install", "uninstall"}
                    for argument in _arguments_until_separator(tokens, index + 3)
                ):
                    return True
        if name == "git" and _git_command_is_mutating(tokens, index):
            return True
        command_tokens = _tokens_until_separator(tokens, index + 1)
        if name == "xargs":
            target_index = _unwrap_command(tokens, index)
            if (
                target_index < len(tokens)
                and _command_is_dangerous(
                    " ".join(tokens[target_index:]), depth + 1
                )
            ):
                return True
        if name == "find" and any(
            option in {"-delete", "-exec", "-execdir"} for option in command_tokens
        ):
            return True
        if name in {"sed", "perl"} and any(
            argument in {"-i", "--in-place", "--inplace"}
            or argument.startswith(("-i.", "--in-place="))
            for argument in command_tokens
        ):
            return True
        if name in {"curl", "wget"} and any(
            argument in {"-o", "-O", "--output", "--output-document"}
            or argument.startswith(("--output=", "--output-document=", "-o"))
            for argument in command_tokens
        ):
            return True
        mutating_subcommands = _MUTATING_PACKAGE_OR_DEPLOY_SUBCOMMANDS.get(name)
        if mutating_subcommands is not None:
            command_arguments = _tokens_until_separator(tokens, index + 1)
            if name in {"pacman", "rpm"} and any(
                argument in mutating_subcommands
                or (
                    argument.startswith("-")
                    and not argument.startswith("--")
                    and any(
                        argument.startswith(flag)
                        for flag in mutating_subcommands
                    )
                )
                for argument in command_arguments
            ):
                return True
            subcommand, remaining_arguments = _first_command_argument(
                command_arguments, name
            )
            if subcommand in mutating_subcommands:
                return True
            if name in {"npm", "pnpm", "yarn"} and subcommand == "run":
                script, _ = _first_command_argument(remaining_arguments, name)
                if script in _DEPLOYMENT_VERBS:
                    return True
            if name == "docker" and subcommand in {"compose", "system", "volume"}:
                nested_subcommand, _ = _first_command_argument(
                    remaining_arguments, name
                )
                if _docker_nested_command_is_mutating(subcommand, nested_subcommand):
                    return True
            if name == "kubectl" and subcommand == "rollout":
                nested_subcommand, _ = _first_command_argument(
                    remaining_arguments, name
                )
                if nested_subcommand in {"pause", "restart", "resume", "undo"}:
                    return True
            if name == "uv" and subcommand == "pip":
                nested_subcommand, _ = _first_command_argument(
                    remaining_arguments, name
                )
                if nested_subcommand in {"install", "uninstall", "sync"}:
                    return True
    return False


def _shell_subcommands(command: str) -> list[str]:
    subcommands: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'":
            index += 2
            continue
        if character == "'" and quote != '"':
            quote = None if quote == "'" else "'"
            index += 1
            continue
        if character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
            index += 1
            continue
        if quote != "'" and command.startswith("$(", index):
            end = _shell_substitution_end(command, index + 1)
            if end is not None:
                subcommands.append(command[index + 2 : end])
                index = end + 1
                continue
        if character == "`" and quote != "'":
            end = index + 1
            while end < len(command):
                if command[end] == "\\":
                    end += 2
                    continue
                if command[end] == "`":
                    subcommands.append(command[index + 1 : end])
                    index = end + 1
                    break
                end += 1
            else:
                index += 1
            continue
        index += 1
    return subcommands


def _shell_substitution_end(command: str, opening: int) -> int | None:
    depth = 1
    quote: str | None = None
    index = opening + 1
    while index < len(command):
        character = command[index]
        if character == "\\" and quote != "'":
            index += 2
            continue
        if character == "'" and quote != '"':
            quote = None if quote == "'" else "'"
        elif character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
        elif quote is None:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    return None


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>{}")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _pipes_into_shell(tokens: Sequence[str]) -> bool:
    wrappers = _COMMAND_WRAPPERS
    for index, token in enumerate(tokens[:-1]):
        if token not in {"|", "||"}:
            continue
        command_index = index + 1
        name = _command_name(tokens[command_index]).lower()
        while name in wrappers:
            command_index = _unwrap_command(tokens, command_index)
            if command_index >= len(tokens):
                break
            name = _command_name(tokens[command_index]).lower()
        if name in _SHELL_EXECUTABLES:
            return True
    return False


def _command_name(token: str) -> str:
    return token.rsplit("/", maxsplit=1)[-1]


def _arguments_until_separator(tokens: Sequence[str], start: int) -> list[str]:
    return [
        token.lower()
        for token in _tokens_until_separator(tokens, start)
        if not token.startswith("-")
    ]


def _tokens_until_separator(tokens: Sequence[str], start: int) -> list[str]:
    arguments: list[str] = []
    for token in tokens[start:]:
        if token in _SHELL_SEPARATORS:
            break
        arguments.append(token)
    return arguments


def _command_positions(tokens: Sequence[str]) -> list[int]:
    positions: list[int] = []
    expect_command = True
    for index, token in enumerate(tokens):
        if expect_command and token in _SHELL_CONTROL_WORDS:
            continue
        if expect_command and _is_shell_assignment(token):
            continue
        if expect_command and token not in _SHELL_SEPARATORS:
            positions.append(index)
            expect_command = False
        elif token in _SHELL_SEPARATORS:
            expect_command = True
    return positions


def _is_shell_assignment(token: str) -> bool:
    name, separator, _ = token.partition("=")
    return bool(separator and name.isidentifier())


def _env_split_command(tokens: Sequence[str], start: int) -> str | None:
    for index, token in enumerate(tokens[start:], start):
        if token in _SHELL_SEPARATORS:
            return None
        if token in {"-S", "--split-string"}:
            next_index = index + 1
            return tokens[next_index] if next_index < len(tokens) else None
        for prefix in ("--split-string=", "-S"):
            if token.startswith(prefix) and len(token) > len(prefix):
                return token[len(prefix) :]
    return None


def _unwrap_command(tokens: Sequence[str], index: int) -> int:
    options_with_value = {
        "-C",
        "-S",
        "-a",
        "-n",
        "-P",
        "-s",
        "-d",
        "-E",
        "-I",
        "-L",
        "--chdir",
        "--split-string",
        "--argv0",
        "--max-args",
        "--max-procs",
        "--max-chars",
        "--delimiter",
        "--eof",
        "--replace",
        "--max-lines",
        "--arg-file",
        "--install-directory",
    }
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token in _SHELL_SEPARATORS:
            return index
        if token == "--":
            return index + 1
        if token.startswith("-"):
            if token in options_with_value or token in {"-u", "--unset"}:
                index += 2
            else:
                index += 1
            continue
        if "=" in token and not token.startswith("/"):
            index += 1
            continue
        return index
    return index


def _shell_command_argument(tokens: Sequence[str], start: int) -> str | None:
    index = start
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        if option in {"-c", "-lc", "--command"} or (
            option.startswith("-") and not option.startswith("--") and "c" in option[1:]
        ):
            return tokens[index + 1] if index + 1 < len(tokens) else None
        if option == "--":
            return tokens[index + 1] if index + 1 < len(tokens) else None
        index += 1
    return None


def _first_command_argument(
    arguments: Sequence[str], command: str
) -> tuple[str | None, list[str]]:
    index = 0
    options_with_value = _COMMAND_OPTIONS_WITH_VALUE.get(command, set())
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            index += 1
            break
        if argument.startswith("-"):
            index += 2 if argument in options_with_value else 1
            continue
        return argument.lower(), list(arguments[index + 1 :])
    if index < len(arguments):
        return arguments[index].lower(), list(arguments[index + 1 :])
    return None, []


def _docker_nested_command_is_mutating(group: str, command: str | None) -> bool:
    mutating_commands = {
        "compose": {"build", "down", "kill", "rm", "restart", "start", "stop", "up"},
        "system": {"prune"},
        "volume": {"create", "prune", "rm"},
    }
    return command in mutating_commands[group]


def _git_command_is_mutating(tokens: Sequence[str], git_index: int) -> bool:
    index = git_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token in _SHELL_SEPARATORS:
            return False
        if token in _GIT_GLOBAL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        command = token.lower()
        if command in _GIT_MUTATING_COMMANDS:
            return True
        if command in {"notes", "reflog", "maintenance"}:
            mutation_verbs = {
                "notes": {"add", "append", "copy", "prune", "remove", "rewrite"},
                "reflog": {"delete", "expire"},
                "maintenance": {"register", "run", "start", "stop", "unregister"},
            }
            remaining = tokens[index + 1 :]
            argument_index = 0
            while argument_index < len(remaining):
                argument = remaining[argument_index]
                if argument in _SHELL_SEPARATORS:
                    return False
                if argument.startswith("-"):
                    argument_index += 2 if argument in {"--ref", "-r", "--scheduler"} else 1
                    continue
                return argument in mutation_verbs[command]
            return False
        if command in _GIT_READ_ONLY_SUBCOMMANDS:
            remaining = tokens[index + 1 :]
            if not remaining:
                return command in {"stash"}
            if any(
                flag in _GIT_MUTATING_FLAGS.get(command, set())
                or any(
                    flag.startswith(option + "=")
                    for option in _GIT_READ_ONLY_SUBCOMMANDS[command]
                )
                for flag in remaining
                if flag.startswith("-")
            ):
                return True
            return not any(
                argument in _GIT_READ_ONLY_SUBCOMMANDS[command]
                or any(
                    argument.startswith(option + "=")
                    for option in _GIT_READ_ONLY_SUBCOMMANDS[command]
                )
                for argument in remaining
            )
        if command == "config":
            remaining = tokens[index + 1 :]
            if any(
                option in {
                    "--add",
                    "--edit",
                    "--replace-all",
                    "--unset",
                    "--unset-all",
                    "--rename-section",
                    "--remove-section",
                }
                or option.startswith(
                    (
                        "--add=",
                        "--edit=",
                        "--replace-all=",
                        "--unset=",
                        "--unset-all=",
                        "--rename-section=",
                        "--remove-section=",
                    )
                )
                for option in remaining
                if option.startswith("-")
            ):
                return True
            positional = [argument for argument in remaining if not argument.startswith("-")]
            return len(positional) > 1
        return False
    return False


def command_needs_approval(command: str, permission: CommandPermission) -> bool:
    if permission is CommandPermission.ALLOW_ALL:
        return False
    if permission is CommandPermission.MANUAL:
        return True
    return command_is_dangerous(command)


async def execute_project_command(cwd: Path, command: str) -> str:
    if not command or len(command) > 2000 or "\x00" in command:
        return _encode({"error": "invalid_command"})

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
    except asyncio.CancelledError:
        _kill_process_group(process.pid)
        await process.wait()
        raise
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
