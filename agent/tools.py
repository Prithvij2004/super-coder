from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

ToolArguments = dict[str, Any]


class EmptyToolInput(BaseModel):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: ToolArguments | None = None
    id: str | None = None


@dataclass
class ToolResult:
    ok: bool
    output: str
    error: str | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[BaseModel], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ValueError(f"Unknown tool: {name}") from error

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def run(self, tool_call: ToolCall) -> ToolResult:
        tool = self.get(tool_call.name)
        try:
            tool_input = tool.input_model.model_validate(tool_call.arguments or {})
        except ValidationError as error:
            return ToolResult(ok=False, output="", error=str(error))

        return tool.run(tool_input)


def create_tool_registry(workspace: Path) -> ToolRegistry:
    from agent.builtin_tools import create_bash_tool, create_glob_tool

    registry = ToolRegistry()
    registry.register(create_bash_tool(workspace))
    registry.register(create_glob_tool(workspace))
    return registry
