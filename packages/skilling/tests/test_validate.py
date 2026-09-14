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
