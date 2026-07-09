# Plan: Minimal Coding Agent in Python

This plan is for learning purposes only. The goal is to build a small Python coding agent that can inspect a local project, reason about a task, edit files, and run basic verification commands.

## Goals

- Understand the core pieces of a coding agent.
- Build a minimal end-to-end loop: read task, inspect files, decide action, edit code, verify result.
- Keep the implementation simple, local, and easy to debug.
- Add only what is necessary for the current learning step.
- Avoid production concerns like sandbox hardening, multi-user isolation, billing, or distributed execution.

## Non-Goals

- Building a fully autonomous production agent.
- Supporting every programming language or framework.
- Handling complex security isolation.
- Implementing advanced memory, retrieval, or multi-agent coordination.
- Replacing human code review.

## Core Capabilities

1. Accept a user task in natural language.
2. Inspect the workspace using safe file tools.
3. Search files by name and content.
4. Read relevant source files.
5. Ask an LLM what action to take next.
6. Apply small file edits.
7. Run tests or validation commands.
8. Return a summary of what changed and what was verified.

## Suggested Architecture

```text
User Task
   |
   v
Agent Loop
   |
   +-- Workspace Tools
   |     +-- list files
   |     +-- search text
   |     +-- read file
   |     +-- write/edit file
   |
   +-- Shell Tool
   |     +-- run tests
   |     +-- run formatters
   |     +-- inspect git diff
   |
   +-- LLM Client
   |     +-- decide next step
   |     +-- produce edits
   |     +-- summarize result
   |
   v
Final Response
```

## Phase 1: Basic CLI

Build a Python command-line program that accepts a task.

Example:

```bash
python -m agent "Fix the failing test in this project"
```

Implementation steps:

- Create a small CLI entry point with `argparse`.
- Read the user task from command-line arguments.
- Use the current working directory as the workspace.
- Print the task and workspace path.
- Add basic logging so the first agent step is visible.

Suggested files:

```text
agent/
  __init__.py
  __main__.py
  loop.py
  llm.py
  tools.py
  safety.py
```

Milestone:

- You can run the agent from a terminal and see it receive a task.

## Phase 2: Workspace Inspection Tools

Add simple tools the agent can call.

Minimum tools:

- `list_files(path)`: list files in a directory.
- `search_files(pattern)`: find files matching a name pattern.
- `search_text(query)`: search file contents.
- `read_file(path)`: read a file.

Implementation notes:

- Keep all paths relative to the workspace root.
- Reject paths that escape the workspace.
- Ignore large folders like `.git`, `node_modules`, `dist`, `build`, and `.venv`.
- Limit file read size to avoid sending huge files to the model.

Milestone:

- The agent can inspect a project and gather relevant context.

## Phase 3: LLM Tool Loop

Create a loop where the model can choose tools.

Basic loop:

1. Send the user task and current context to the model.
2. Let the model request a tool call.
3. Execute the tool call locally.
4. Send the result back to the model.
5. Repeat until the model decides it has enough information.

Recommended limits:

- Maximum 10 to 20 tool calls per task.
- Maximum file read size.
- Maximum total context size.
- Stop if the same action repeats too often.

Milestone:

- The agent can search and read files based on the model's decisions.

## Phase 4: Editing Files

Add a minimal edit tool.

Start with one simple option:

- `replace_in_file(path, old_text, new_text)`

Rules:

- Only edit files inside the workspace.
- Require `old_text` to match exactly once.
- If it matches zero or multiple times, fail and ask the model to inspect more context.
- Save the previous file content in memory so changes can be shown or reverted during development.

Milestone:

- The agent can make small, precise code edits.

## Phase 5: Shell Commands

Add a shell command tool for verification.

Examples:

- `npm test`
- `npm run lint`
- `pytest`
- `go test ./...`
- `cargo test`

Safety rules:

- Run commands only from the workspace root.
- Use a timeout.
- Capture stdout, stderr, and exit code.
- Do not allow destructive commands in the first version.
- Block commands like `rm -rf`, `git reset`, `git clean`, `sudo`, and network-heavy installs unless explicitly allowed.

Milestone:

- The agent can edit code and run a verification command.

## Phase 6: Final Summary

Teach the agent to produce a useful final response.

The final response should include:

- What files changed.
- What problem was solved.
- What verification command ran.
- Whether verification passed or failed.
- Any remaining issues or next steps.

Milestone:

- The agent can complete a small coding task and explain the result clearly.

## Minimal System Prompt

Use a short system prompt at first:

```text
You are a minimal coding agent running in a local workspace.
Your job is to help complete the user's coding task.
Inspect the code before editing.
Make small, precise changes.
Verify your changes when possible.
Do not modify files outside the workspace.
When finished, summarize changed files and verification results.
```

## Suggested Data Structures

```python
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    ok: bool
    output: str
    error: str | None = None


@dataclass
class AgentMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
```

## Python Implementation Notes

Use the Python standard library as much as possible at first.

Recommended modules:

- `argparse` for CLI input.
- `pathlib` for filesystem paths.
- `subprocess` for shell commands.
- `dataclasses` for simple data structures.
- `json` for structured tool calls.
- `fnmatch` or `glob` for file matching.
- `logging` for debug output.

Avoid adding frameworks until the basic loop works.

## Example Agent Loop

```text
while not done:
  send task, history, and tool results to LLM
  receive assistant response

  if response asks for tool:
    validate tool input
    run tool
    append tool result to history
    continue

  if response says final:
    print final answer
    stop
```

## Recommended First Test Project

Create a tiny project with one failing test.

Example tasks:

- "Fix the failing add function test."
- "Rename this function and update its usage."
- "Add input validation to this helper."
- "Update the README based on the code."

Keep the first examples small so you can understand every agent decision.

## Implementation Order

1. CLI task input.
2. File listing and reading.
3. Text search.
4. LLM call without tools.
5. LLM tool-calling loop.
6. Exact text replacement edit tool.
7. Shell verification tool.
8. Final summary generation.
9. Basic safety checks.
10. Logging and debugging output.

## Current Progress

Implemented:

- Raw Python package at `agent/`.
- CLI entry point with `python -m agent "task"`.
- One required task argument.
- Current directory as the workspace.
- Basic info logging.
- Minimal OpenAI client using the official OpenAI Python SDK.
- `.env` loading with `python-dotenv`.
- One model call without tools.
- `OPENAI_API_KEY` read from the environment.
- Common tool interface in `agent/tools.py`.
- Tool registry for plug-and-play tool registration.
- Provider-neutral `ToolCall`, `ToolResult`, and `ToolDefinition` structures.
- Explicit tool registration with typed dataclasses.
- Simple Pydantic input models for validation and JSON schema generation.
- OpenAI adapter for converting internal tools to OpenAI-compatible tool definitions.
- Built-in `bash` tool registered at startup.
- Bash command validation that scans multiple command segments and command substitutions.
- Bash tool timeout and output limiting.
- OpenAI tool calling wired through the provider adapter.
- Tool calls normalized into internal `ToolCall` objects.
- Tool results sent back to OpenAI for the final response.

Next step:

- Add a read-only file inspection tool like `list_files` or `read_file`.

## Learning Checklist

- How does the agent choose which files to inspect?
- How much context does the model need before editing?
- What happens when an edit fails?
- How do you prevent accidental edits outside the workspace?
- How do you keep shell commands safe enough for local experimentation?
- How do verification results change the next agent step?
- What information should the final summary include?

## Optional Extensions

- Add a `git_diff()` tool.
- Add a `create_file(path, content)` tool.
- Add structured JSON tool calls.
- Add a planner step before execution.
- Add a todo list visible during execution.
- Add support for applying unified diffs.
- Add a simple permission prompt before edits or shell commands.
- Add project-specific instructions from an `AGENTS.md` file.

## Success Criteria

The project is successful when the agent can complete a simple task like this:

```text
User: Fix the failing test.

Agent:
1. Searches for test files.
2. Reads the failing test and related source file.
3. Identifies the bug.
4. Applies a small edit.
5. Runs the test command.
6. Reports the changed file and test result.
```

That is enough for a minimal learning-focused coding agent.
