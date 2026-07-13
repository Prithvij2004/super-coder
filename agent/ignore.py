from __future__ import annotations

from pathlib import Path

from pathspec import PathSpec


IGNORE_FILE_NAME = ".agentignore"
ALWAYS_IGNORED_PATTERNS = (".git/",)


def load_ignore_spec(workspace: Path) -> PathSpec:
    ignore_file = workspace / IGNORE_FILE_NAME
    patterns = ignore_file.read_text().splitlines() if ignore_file.is_file() else []
    patterns.extend(ALWAYS_IGNORED_PATTERNS)
    return PathSpec.from_lines("gitwildmatch", patterns)


def is_ignored(
    ignore_spec: PathSpec,
    relative_path: Path,
    *,
    is_directory: bool,
) -> bool:
    path = relative_path.as_posix()
    if is_directory:
        path += "/"
    return ignore_spec.match_file(path)
