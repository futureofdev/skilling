"""Every YAML example in the specification must parse into the models and survive a
re-serialisation unchanged.

This is the gate that keeps the prose honest. It already earned its place: the first run
found that a lesson title ending in "?" inside a `{ … }` flow mapping is not valid YAML, so
the specification's own manifest example could not be loaded by any conforming tool.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from skilling.codegen import schemas
from skilling.course import (
    CompletionEntry,
    HomeworkSlot,
    LessonFrontmatter,
    Manifest,
    Position,
    Record,
)

from .conftest import SCHEMAS_DIR, SPEC_DIR

_FENCE = re.compile(r"^```ya?ml\s*$", re.MULTILINE)


def _yaml_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if _FENCE.match(lines[i]):
            j = i + 1
            body: list[str] = []
            while j < len(lines) and not lines[j].startswith("```"):
                body.append(lines[j])
                j += 1
            blocks.append("\n".join(body))
            i = j
        i += 1
    return blocks


def _strip_frontmatter_delimiters(block: str) -> str:
    """A frontmatter example is shown with its `---` fences; YAML sees two documents."""
    lines = block.splitlines()
    if lines and lines[0].strip() == "---":
        lines = lines[1:]
        if lines and lines[-1].strip() == "---":
            lines = lines[:-1]
    return "\n".join(lines)


def _all_blocks() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for path in sorted(SPEC_DIR.glob("*.md")):
        for n, block in enumerate(_yaml_blocks(path.read_text(encoding="utf-8")), start=1):
            out.append((path.name, n, block))
    return out


BLOCKS = _all_blocks()


def _classify(data: Any) -> type[BaseModel] | None:
    if isinstance(data, dict):
        if "spec_version" in data and "phases" in data:
            return Manifest
        if {"title", "phase", "lesson", "sections"} <= set(data):
            return LessonFrontmatter
        if "learner_id" in data:
            return Record
        if "unlocked_at" in data:
            return HomeworkSlot
    return None


def test_the_specification_actually_contains_examples() -> None:
    assert len(BLOCKS) >= 8, "the specification should be carrying worked examples"


@pytest.mark.parametrize(
    ("filename", "index", "block"), BLOCKS, ids=[f"{f}#{n}" for f, n, _ in BLOCKS]
)
def test_every_example_is_valid_yaml(filename: str, index: int, block: str) -> None:
    yaml.safe_load(_strip_frontmatter_delimiters(block))


@pytest.mark.parametrize(
    ("filename", "index", "block"), BLOCKS, ids=[f"{f}#{n}" for f, n, _ in BLOCKS]
)
def test_complete_examples_round_trip(filename: str, index: int, block: str) -> None:
    data = yaml.safe_load(_strip_frontmatter_delimiters(block))
    model = _classify(data)
    if model is None:
        pytest.skip("fragment, not a complete document")

    parsed = model.model_validate(data)
    once = parsed.model_dump(mode="json")
    again = model.model_validate(yaml.safe_load(yaml.safe_dump(once))).model_dump(mode="json")
    assert once == again


def test_the_completion_log_example_parses() -> None:
    found = 0
    for _, _, block in BLOCKS:
        data = yaml.safe_load(_strip_frontmatter_delimiters(block))
        if isinstance(data, list) and data and "completed_at" in data[0]:
            entries = [CompletionEntry.model_validate(item) for item in data]
            assert entries[0].coordinate
            found += 1
    assert found >= 1, "spec/runtime.md should show a completion log"


@pytest.mark.parametrize(
    ("model", "where"),
    [
        (Manifest, "a manifest"),
        (LessonFrontmatter, "lesson frontmatter"),
        (Record, "a progress record"),
        (HomeworkSlot, "a homework slot"),
    ],
)
def test_each_persisted_surface_has_a_worked_example(model: type[BaseModel], where: str) -> None:
    for _, _, block in BLOCKS:
        data = yaml.safe_load(_strip_frontmatter_delimiters(block))
        if _classify(data) is model:
            return
    raise AssertionError(f"the specification shows no complete example of {where}")


def test_committed_schemas_are_current() -> None:
    stale = schemas.stale(SCHEMAS_DIR)
    assert stale == [], f"run `task schemas` — stale: {stale}"


def test_generated_schemas_are_marked_informative() -> None:
    for name in schemas.TARGETS:
        built = schemas.build(name)
        assert "normative" in built["description"]
        assert built["$id"].endswith(name)


def test_no_example_authors_a_structural_count(tmp_path: Path) -> None:
    """The specification must not model the behaviour it forbids.

    Checked with the validator's own patterns rather than a hand-rolled regex, so this test
    and the tool it documents cannot disagree.
    """
    from skilling.conformance._counts import _BODY_COUNTS, _MANIFEST_COUNTS

    checked = 0
    for filename, index, block in BLOCKS:
        if block.lstrip().startswith("# Poor"):
            continue  # a deliberate counter-example; it is *meant* to break the rule
        checked += 1
        for line in block.splitlines():
            for pattern in _MANIFEST_COUNTS + _BODY_COUNTS:
                assert not pattern.search(line), f"{filename}#{index}: {line!r}"
    assert checked >= 8


def test_the_authored_count_counter_example_is_genuinely_caught() -> None:
    """The counter-example must actually fail the check it illustrates — otherwise the
    specification is teaching a rule the tool does not enforce.

    The other counter-examples (an undeclared `sections: {}`, for instance) are covered by
    the corruption suite in ``test_validate.py``, which runs the whole validator.
    """
    from skilling.conformance._counts import _BODY_COUNTS, _MANIFEST_COUNTS

    poor = [b for _, _, b in BLOCKS if b.lstrip().startswith("# Poor")]
    assert poor, "the specification should show counter-examples"
    assert any(
        pattern.search(line)
        for block in poor
        for line in block.splitlines()
        for pattern in _MANIFEST_COUNTS + _BODY_COUNTS
    ), "no counter-example demonstrates an authored count"


def test_position_roundtrips_question_index() -> None:
    pos = Position(phase=1, lesson=2, beat="quiz", question_index=2)
    assert Position.model_validate(pos.model_dump(mode="json")).question_index == 2


def test_pre_1_3_records_load_unchanged() -> None:
    """A 1.0/1.1/1.2 position has no question_index; it must load as None."""
    pos = Position.model_validate({"phase": 1, "lesson": 2, "beat": "quiz"})
    assert pos.question_index is None
