from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from agent.tools import ToolDefinition, ToolResult


MAX_COMMANDS = 2
MAX_OUTPUT_CHARS = 20_000
COMMAND_OPERATORS = {"&&", "||", ";", "|"}
BLOCKED_COMMANDS = {
    "sudo",
    "su",
    "doas",
    "rm",
    "rmdir",
    "shred",
    "mkfs",
    "dd",
    "chmod",
    "chown",
    "eval",
    "source",
}
BLOCKED_INLINE_EXECUTION = {
    "bash",
    "sh",
    "zsh",
    "python",
    "python3",
    "node",
    "perl",
    "ruby",
}


class BashInput(BaseModel):
    command: str
    timeout_seconds: int = Field(default=30, ge=1, le=120)


def create_bash_tool(workspace: Path) -> ToolDefinition:
    def run_bash(input: BaseModel) -> ToolResult:
        bash_input = BashInput.model_validate(input)
        error = validate_bash_command(bash_input.command)
        if error:
            return ToolResult(ok=False, output="", error=error)

        try:
            completed = subprocess.run(
                bash_input.command,
                cwd=workspace,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=bash_input.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(ok=False, output="", error="Command timed out")

        stdout = _limit_output(completed.stdout)
        stderr = _limit_output(completed.stderr)
        output = f"exit_code: {completed.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        return ToolResult(ok=completed.returncode == 0, output=output)

    return ToolDefinition(
        name="bash",
        description="Run a bash command in the workspace after basic safety checks.",
        input_model=BashInput,
        run=run_bash,
    )


def validate_bash_command(command: str, depth: int = 0) -> str | None:
    if not command.strip():
        return "Command cannot be empty"
    if depth > 3:
        return "Command nesting is too deep"

    for inner_command in _extract_command_substitutions(command):
        error = validate_bash_command(inner_command, depth + 1)
        if error:
            return error

    try:
        tokens = _tokenize(command)
    except ValueError as error:
        return f"Could not parse command: {error}"

    simple_commands = _split_simple_commands(tokens)
    if len(simple_commands) > MAX_COMMANDS:
        return f"Only {MAX_COMMANDS} commands are allowed at a time"

    for simple_command in simple_commands:
        error = _validate_simple_command(simple_command)
        if error:
            return error

    return None


def _tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _split_simple_commands(tokens: list[str]) -> list[list[str]]:
    commands: list[list[str]] = [[]]
    for token in tokens:
        if token in COMMAND_OPERATORS:
            commands.append([])
        else:
            commands[-1].append(token)

    return [command for command in commands if command]


def _validate_simple_command(tokens: list[str]) -> str | None:
    for token in tokens:
        command_name = os.path.basename(token)
        if command_name in BLOCKED_COMMANDS:
            return f"Blocked command: {command_name} is not allowed"

    command_name = _first_command_name(tokens)
    if not command_name:
        return "Could not find command name"

    if command_name in BLOCKED_INLINE_EXECUTION and _has_inline_execution_flag(tokens):
        return f"Blocked command: inline execution with {command_name} is not allowed"

    return None


def _first_command_name(tokens: list[str]) -> str | None:
    for token in tokens:
        if "=" in token and not token.startswith("="):
            continue
        return os.path.basename(token)

    return None


def _has_inline_execution_flag(tokens: list[str]) -> bool:
    return "-c" in tokens or "-e" in tokens


def _extract_command_substitutions(command: str) -> list[str]:
    substitutions = _extract_backtick_substitutions(command)
    substitutions.extend(_extract_dollar_paren_substitutions(command))
    return substitutions


def _extract_backtick_substitutions(command: str) -> list[str]:
    substitutions: list[str] = []
    index = 0
    while index < len(command):
        if command[index] != "`":
            index += 1
            continue

        end = command.find("`", index + 1)
        if end == -1:
            break

        substitutions.append(command[index + 1 : end])
        index = end + 1

    return substitutions


def _extract_dollar_paren_substitutions(command: str) -> list[str]:
    substitutions: list[str] = []
    index = 0
    while index < len(command):
        start = command.find("$(", index)
        if start == -1:
            break

        depth = 1
        position = start + 2
        while position < len(command) and depth > 0:
            if command[position] == "(":
                depth += 1
            elif command[position] == ")":
                depth -= 1
            position += 1

        if depth == 0:
            substitutions.append(command[start + 2 : position - 1])
            index = position
        else:
            break

    return substitutions


def _limit_output(output: str) -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output

    return output[:MAX_OUTPUT_CHARS] + "\n... output truncated ..."
