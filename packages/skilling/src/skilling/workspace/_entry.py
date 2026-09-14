"""Marked-block entry files: how a host that reads ``CLAUDE.md``/``AGENTS.md`` learns what a
workspace folder is (spec/workspace.md#entry-files).

Writing is create-or-grow: the file is created when absent, and only the content between
this module's own markers is rewritten when present. Content outside the markers — anything
a learner or another tool wrote — is never touched, the same receipt philosophy
``skills/_install.py`` applies to files, applied here to a document.
"""

from __future__ import annotations

from pathlib import Path

ENTRY_BLOCK_START = "<!-- skilling:workspace -->"
ENTRY_BLOCK_END = "<!-- /skilling:workspace -->"

ENTRY_FILENAMES: tuple[str, ...] = ("CLAUDE.md", "AGENTS.md")

_BLOCK_CONTENT = """\
This folder is a Skilling workspace: an AI-tutored course for Claude Code or Codex.
Say "learn" to start or resume it — `/learn` in Claude Code, `$learn` in Codex.

Machinery — state, cached course content, the ref index — lives under `.skilling/`.
Never edit it directly; every command that needs it reads and writes it through
`skilling`. Work you produce for a course goes in `showcase/<course-id>/`, the one
folder here meant to be seen.

The `skilling` command must be installed and on PATH in the host's environment.
Opening or copying this folder does not install the CLI or its dependencies."""


def upsert_block(text: str, content: str = _BLOCK_CONTENT) -> str:
    """Create-or-grow ``text``: replace only the span between a valid marker pair when one
    is already present, append a fresh block otherwise. Pure, so the marker logic is testable
    without touching a filesystem."""
    block = f"{ENTRY_BLOCK_START}\n{content}\n{ENTRY_BLOCK_END}"
    start = text.find(ENTRY_BLOCK_START)
    end = text.find(ENTRY_BLOCK_END)
    if start != -1 and end != -1 and start < end:
        return f"{text[:start]}{block}{text[end + len(ENTRY_BLOCK_END) :]}"
    if not text:
        return block + "\n"
    separator = "" if text.endswith("\n\n") else "\n" if text.endswith("\n") else "\n\n"
    return f"{text}{separator}{block}\n"


def write_entry_file(path: Path) -> None:
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(upsert_block(existing), encoding="utf-8")


def refresh_entry_files(workspace: Path) -> tuple[Path, ...]:
    """Write or refresh ``CLAUDE.md`` and ``AGENTS.md`` at the workspace root, in
    ``ENTRY_FILENAMES`` order. Idempotent: re-running changes only the marked block."""
    paths = tuple(workspace / name for name in ENTRY_FILENAMES)
    for path in paths:
        write_entry_file(path)
    return paths
