"""JSON Schema generation — a convenience, not the specification.

The prose in ``spec/`` is the only normative source. These schemas exist so editors can
autocomplete a ``course.yaml`` and CI can do a cheap structural check, and they are
generated from the models so they cannot drift from the implementation. Committed copies
must be current; ``task schemas:check`` fails if they are not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..conformance import SPEC_MAJOR, SPEC_MINOR
from ..course import HomeworkSlot, LessonFrontmatter, Manifest, Record
from ..workspace import WorkspaceManifest

BASE_URI = f"https://startskill.ing/schemas/v{SPEC_MAJOR}.{SPEC_MINOR}"

TARGETS: dict[str, tuple[type[BaseModel], str]] = {
    "course.schema.json": (Manifest, "A Skilling course manifest (course.yaml)"),
    "lesson-frontmatter.schema.json": (LessonFrontmatter, "The YAML frontmatter of a lesson"),
    "progress-record.schema.json": (Record, "A learner's progress record (record.yaml)"),
    "homework-slot.schema.json": (HomeworkSlot, "The homework mailbox slot (active.yaml)"),
    "workspace.schema.json": (WorkspaceManifest, "A workspace manifest (workspace.yaml)"),
}

_BANNER = (
    "Generated from the Pydantic models by `task schemas`. Informative only — "
    "the specification in spec/ is normative."
)


def build(name: str) -> dict[str, Any]:
    model, title = TARGETS[name]
    schema = model.model_json_schema()
    # Pydantic puts the model's docstring in "description"; keep it, but lead with the
    # banner so nobody mistakes a generated file for the specification.
    inherited = schema.pop("description", "")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_URI}/{name}",
        **schema,
        "title": title,
        "description": f"{_BANNER}\n\n{inherited}".strip(),
    }


def render(name: str) -> str:
    return json.dumps(build(name), indent=2, sort_keys=True) + "\n"


def write_all(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in TARGETS:
        path = directory / name
        path.write_text(render(name), encoding="utf-8")
        written.append(path)
    return written


def stale(directory: Path) -> list[str]:
    out: list[str] = []
    for name in TARGETS:
        path = directory / name
        if not path.is_file() or path.read_text(encoding="utf-8") != render(name):
            out.append(name)
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    check = "--check" in args
    args = [a for a in args if a != "--check"]
    directory = Path(args[0]) if args else Path("schemas")

    if check:
        outdated = stale(directory)
        if outdated:
            print(
                "Committed schemas are stale: " + ", ".join(outdated) + "\nRun: task schemas",
                file=sys.stderr,
            )
            return 1
        print(f"Schemas in {directory} are current.")
        return 0

    for path in write_all(directory):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
