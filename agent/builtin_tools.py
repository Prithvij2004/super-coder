from __future__ import annotations

import logging
import os
import shlex
import subprocess
from collections.abc import Iterator
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path

from pathspec import PathSpec
from pydantic import BaseModel, Field

from agent.ignore import IGNORE_FILE_NAME, is_ignored, load_ignore_spec
from agent.tools import ToolDefinition, ToolResult


MAX_COMMANDS = 2
MAX_OUTPUT_CHARS = 20_000
MAX_GLOB_RESULTS = 200
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


class GlobInput(BaseModel):
    pattern: str = Field(min_length=1)


def create_glob_tool(workspace: Path) -> ToolDefinition:
    workspace = workspace.resolve()
    try:
        ignore_spec = load_ignore_spec(workspace)
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeError(f"Could not load {IGNORE_FILE_NAME}: {error}") from error

    def run_glob(input: BaseModel) -> ToolResult:
        glob_input = GlobInput.model_validate(input)
        pattern_path = Path(glob_input.pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            return ToolResult(
                ok=False,
                output="",
                error="Glob pattern must stay inside the workspace",
            )

        matches: list[str] = []
        truncated = False
        try:
            directory_only = glob_input.pattern.endswith("/")
            pattern_parts = pattern_path.parts
            for candidate in _iter_workspace_paths(workspace, ignore_spec):
                relative_path = candidate.relative_to(workspace)
                if directory_only and not candidate.is_dir():
                    continue
                if not _matches_glob(relative_path.parts, pattern_parts):
                    continue

                display_path = relative_path.as_posix()
                if candidate.is_dir():
                    display_path += "/"
                matches.append(display_path)

                if len(matches) > MAX_GLOB_RESULTS:
                    matches.pop()
                    truncated = True
                    break
        except (OSError, ValueError) as error:
            return ToolResult(ok=False, output="", error=f"Glob failed: {error}")

        if not matches:
            return ToolResult(ok=True, output="No paths matched the pattern")

        output = "\n".join(sorted(matches))
        if truncated:
            output += f"\n... results limited to {MAX_GLOB_RESULTS} paths ..."
        return ToolResult(ok=True, output=output)

    return ToolDefinition(
        name="glob",
        description=(
            "Find workspace paths matching a glob pattern such as '**/*.py'. "
            "Paths configured in .agentignore are excluded."
        ),
        input_model=GlobInput,
        run=run_glob,
    )


def _iter_workspace_paths(workspace: Path, ignore_spec: PathSpec) -> Iterator[Path]:
    for current_path, directory_names, file_names in os.walk(
        workspace,
        followlinks=False,
    ):
        current_directory = Path(current_path)
        directory_names.sort()
        file_names.sort()

        included_directories: list[str] = []
        for name in directory_names:
            candidate = current_directory / name
            relative_path = candidate.relative_to(workspace)
            if not _is_searchable_path(
                workspace,
                candidate,
                relative_path,
                ignore_spec,
                is_directory=True,
            ):
                continue
            included_directories.append(name)
            yield candidate
        directory_names[:] = included_directories

        for name in file_names:
            candidate = current_directory / name
            relative_path = candidate.relative_to(workspace)
            if _is_searchable_path(
                workspace,
                candidate,
                relative_path,
                ignore_spec,
                is_directory=False,
            ):
                yield candidate


def _is_searchable_path(
    workspace: Path,
    candidate: Path,
    relative_path: Path,
    ignore_spec: PathSpec,
    *,
    is_directory: bool,
) -> bool:
    try:
        candidate.resolve().relative_to(workspace)
    except (OSError, ValueError):
        return False
    return not is_ignored(
        ignore_spec,
        relative_path,
        is_directory=is_directory,
    )


def _matches_glob(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    @lru_cache(maxsize=None)
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)

        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and match(path_index + 1, pattern_index)
            )

        return path_index < len(path_parts) and fnmatchcase(
            path_parts[path_index],
            pattern_part,
        ) and match(
            path_index + 1,
            pattern_index + 1,
        )

    return match(0, 0)


def create_bash_tool(workspace: Path) -> ToolDefinition:
    def run_bash(input: BaseModel) -> ToolResult:
        bash_input = BashInput.model_validate(input)
        logging.info("Bash command: %s", bash_input.command)
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
