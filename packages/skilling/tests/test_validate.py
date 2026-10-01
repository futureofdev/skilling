"""The validator's completeness gate.

Two claims are under test, and they only mean something together: every error code fires on
its own corruption, and a conforming course produces nothing at all. A validator that
catches everything but also cries wolf is unusable, and one that never complains is a
decoration.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from skilling.conformance import CATALOGUE, Code, Severity, validate_course
from skilling.conformance._errors import missing_from_catalogue
from skilling.course import scan_quiz

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE
from .corruptions import CORRUPTIONS


def test_catalogue_covers_every_code() -> None:
    assert missing_from_catalogue() == set()


def test_every_code_has_a_corruption() -> None:
    """A new code without a corruption fails here rather than going untested."""
    assert set(Code) - set(CORRUPTIONS) == set()


def test_clean_fixture_has_no_findings(clean_dir: Path) -> None:
    report = validate_course(clean_dir)
    assert report.findings == [], [f.as_dict() for f in report.findings]


def test_example_course_has_no_findings() -> None:
    report = validate_course(EXAMPLE_COURSE)
    assert report.findings == [], [f.as_dict() for f in report.findings]


@pytest.mark.parametrize("code", sorted(CORRUPTIONS, key=str))
def test_corruption_fires_its_code(
    code: Code, corrupt: Callable[[Callable[[Path], None]], Path]
) -> None:
    root = corrupt(CORRUPTIONS[code])
    report = validate_course(root)
    assert code in report.codes(), (
        f"{code} did not fire. Findings: {[str(f.code) for f in report.findings]}"
    )


@pytest.mark.parametrize("code", sorted(CORRUPTIONS, key=str))
def test_every_finding_carries_a_spec_anchor(
    code: Code, corrupt: Callable[[Callable[[Path], None]], Path]
) -> None:
    root = corrupt(CORRUPTIONS[code])
    for finding in validate_course(root).findings:
        assert finding.anchor.startswith("spec/"), finding.as_dict()
        assert "#" in finding.anchor, finding.as_dict()


def test_errors_and_warnings_are_separated(
    corrupt: Callable[[Callable[[Path], None]], Path],
) -> None:
    report = validate_course(corrupt(CORRUPTIONS[Code.NEXT_UP_TOO_LONG]))
    assert report.ok, "a warning alone must not make a course non-conforming"
    assert not report.clean
    assert report.warnings and not report.errors


def test_missing_manifest_reports_once_and_stops(
    corrupt: Callable[[Callable[[Path], None]], Path],
) -> None:
    report = validate_course(corrupt(CORRUPTIONS[Code.MANIFEST_MISSING]))
    assert [f.code for f in report.findings] == [Code.MANIFEST_MISSING]


def test_every_catalogue_entry_is_well_formed() -> None:
    for code, entry in CATALOGUE.items():
        assert entry.severity in (Severity.ERROR, Severity.WARNING), code
        assert entry.summary, code
        assert not entry.summary.endswith("."), f"{code}: summaries are labels, not sentences"
        assert entry.anchor.startswith("spec/") and "#" in entry.anchor, code


@pytest.mark.parametrize("numbers", [("1.", "1.", "1."), ("1.", "2.", "2."), ("1.", "2.", "4.")])
def test_quiz_numbering_must_be_1_2_3(clean_dir: Path, numbers: tuple[str, str, str]) -> None:
    """Markdown renders 1./1./1. as 1,2,3 — no human sees this, so the validator must."""
    lesson = clean_dir / fx.LESSON_ONE_PATH
    text = lesson.read_text(encoding="utf-8")
    for typed, original in zip(numbers, ("1.", "2.", "3."), strict=True):
        # rewrite only the quiz's question-number prefixes, first occurrence each
        text = text.replace(f"\n{original} ", f"\n{typed} ", 1)
    lesson.write_text(text, encoding="utf-8")
    report = validate_course(clean_dir)
    assert Code.QUIZ_QUESTION_NUMBERING in {f.code for f in report.errors}


def test_course_id_terminal_newline_is_invalid(clean_dir: Path) -> None:
    import yaml

    path = clean_dir / "course.yaml"
    data = yaml.safe_load(path.read_text())
    data["id"] = "valid\n"
    path.write_text(yaml.safe_dump(data))
    report = validate_course(clean_dir)
    assert Code.COURSE_ID_INVALID in {finding.code for finding in report.errors}


# ------------------------------------------------------------------- wrapped quiz lines (#98)

_WRAPPED_QUIZ = """\
1. `compose_greeting` is in `tools.py` and registered in `safe.yaml`, but `hello-chat` still
   can't call it. What's most likely missing?
   - a) A new model provider
   - b) A line in the agent's tool list
     naming the new tool
   - c) A restart of the terminal
   - d) A second copy of `tools.py`

   **Answer:** b) A line in the agent's tool list naming the new tool — registering a
   tool makes it available, but each agent still opts in.
"""


def test_wrapped_stem_and_option_are_joined_not_dropped() -> None:
    scan = scan_quiz(_WRAPPED_QUIZ, 10)
    assert scan.unconsumed == []
    (question,) = scan.questions
    assert question.text == (
        "`compose_greeting` is in `tools.py` and registered in `safe.yaml`, but `hello-chat` "
        "still can't call it. What's most likely missing?"
    )
    assert question.labels == ["a", "b", "c", "d"]
    option_b = question.option("b")
    assert option_b is not None
    assert option_b.text == "A line in the agent's tool list naming the new tool"
    assert option_b.line == 13  # an option keeps the line it starts on
    assert question.answer_label == "b"
    assert question.answer_reason == (
        "registering a tool makes it available, but each agent still opts in."
    )


def test_clean_fixture_wraps_a_stem_and_an_option(clean_dir: Path) -> None:
    """The clean course carries both wraps, so every CLI test reads joined text."""
    text = fx.read(clean_dir, fx.LESSON_ONE_PATH)
    body = text.split("## Quick Quiz\n", 1)[1].split("\n## ", 1)[0]
    first = scan_quiz(body, 1).questions[0]
    assert (
        first.text
        == "What is the first thing, the one every later lesson assumes you already know?"
    )
    option_a = first.option("a")
    assert option_a is not None
    assert option_a.text.endswith("wrapped it onto a second line")


@pytest.mark.parametrize(
    ("old", "new", "stray"),
    [
        # prose before the first question
        (
            "## Quick Quiz\n",
            "## Quick Quiz\nAnswer these from memory.\n",
            "Answer these from memory.",
        ),
        # a fifth option must not be folded silently into the fourth
        ("   - d) Wrong four\n", "   - d) Wrong four\n   - e) Wrong five\n", "- e) Wrong five"),
        # text after a blank line belongs to nothing
        (
            "   - d) Wrong four\n",
            "   - d) Wrong four\n\n   An afterthought about option d.\n",
            "An afterthought about option d.",
        ),
    ],
)
def test_a_quiz_line_nothing_consumes_is_reported(
    clean_dir: Path, old: str, new: str, stray: str
) -> None:
    fx.edit(clean_dir, fx.LESSON_ONE_PATH, old, new)
    report = validate_course(clean_dir)
    findings = [f for f in report.errors if f.code == Code.QUIZ_LINE_UNCONSUMED]
    assert len(findings) == 1, findings
    lines = fx.read(clean_dir, fx.LESSON_ONE_PATH).splitlines()
    assert findings[0].line is not None
    assert lines[findings[0].line - 1].strip() == stray
