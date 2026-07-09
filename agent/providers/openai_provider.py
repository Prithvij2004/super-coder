from __future__ import annotations

from typing import Any

from agent.tools import ToolDefinition


def to_openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_model.model_json_schema(),
    }


def to_openai_tools(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    return [to_openai_tool(tool) for tool in tools]
