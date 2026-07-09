from __future__ import annotations

import argparse
import logging
from pathlib import Path

from agent.llm import ask_model
from agent.tools import create_tool_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="A minimal coding agent for learning purposes.",
    )
    parser.add_argument("task", help="The coding task for the agent to work on.")
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    args = parse_args()
    configure_logging()

    workspace = Path.cwd()
    tool_registry = create_tool_registry(workspace)

    logging.info("Task: %s", args.task)
    logging.info("Workspace: %s", workspace)
    logging.info("Tools: %s registered", len(tool_registry.list()))

    try:
        response = ask_model(args.task, tool_registry)
    except RuntimeError as error:
        raise SystemExit(str(error)) from error

    print(response)


if __name__ == "__main__":
    main()
