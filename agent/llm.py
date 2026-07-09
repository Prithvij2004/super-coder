from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from agent.providers.openai_provider import to_openai_tools
from agent.tools import ToolCall, ToolRegistry


MODEL = "gpt-4.1-mini"
MAX_TOOL_ROUNDS = 5


def ask_model(task: str, tool_registry: ToolRegistry) -> str:
    load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    openai_tools = to_openai_tools(tool_registry.list())

    try:
        response = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "system",
                    "content": "You are a minimal coding agent. Use available tools when they help answer the user's task. Do not edit files yet.",
                },
                {"role": "user", "content": task},
            ],
            tools=openai_tools,
        )

        for _ in range(MAX_TOOL_ROUNDS):
            tool_calls = _get_tool_calls(response)
            if not tool_calls:
                break

            tool_outputs = []
            for tool_call in tool_calls:
                logging.info("Running tool: %s", tool_call.name)
                result = tool_registry.run(tool_call)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.id,
                        "output": _format_tool_result(result.ok, result.output, result.error),
                    }
                )

            response = client.responses.create(
                model=MODEL,
                previous_response_id=response.id,
                input=tool_outputs,
                tools=openai_tools,
            )
    except OpenAIError as error:
        raise RuntimeError(f"OpenAI request failed: {error}") from error

    if not response.output_text:
        raise RuntimeError("OpenAI returned an empty response")

    return response.output_text


def _get_tool_calls(response: object) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    for item in getattr(response, "output", []):
        if getattr(item, "type", None) != "function_call":
            continue

        try:
            arguments = json.loads(item.arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}

        tool_calls.append(
            ToolCall(
                name=item.name,
                arguments=arguments,
                id=item.call_id,
            )
        )

    return tool_calls


def _format_tool_result(ok: bool, output: str, error: str | None) -> str:
    return json.dumps(
        {
            "ok": ok,
            "output": output,
            "error": error,
        }
    )
