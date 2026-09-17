"""Tests for the record verbs: ``homework check``/``submit``, ``progress``, ``telemetry``.

Thin wrappers over ``delivery/_runtime.py`` — ``submit_homework`` and
``set_telemetry_consent`` already do the write set, so these tests are about what the CLI
must *not* do (mutate on a read) as much as what it does.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Course
from skilling.delivery import Dispatcher, JsonlSink, complete_lesson
from skilling.store import LOCAL_LEARNER, FileProgressStore

runner = CliRunner()


def run(args: list[str], tmp: Path):
    return runner.invoke(app, [*args, "--state", str(tmp)], catch_exceptions=False)


def _advance(course: Path, tmp: Path, given: str):
    result = run(["advance", "--course", str(course), "--input", given], tmp)
    assert result.exit_code == 0, result.output
    return result


# Mirrors test_cli_runtime.py's LESSON_WITH_EXERCISE walk: both 0.1 and 0.2 in the
# clean-course fixture declare an exercise.
LESSON_WITH_EXERCISE = [
    "next",
    "next",
    "next",
    "proceed",
    "next",
    "attempted",
    "answer-correct",
    "answer-correct",
    "answer-correct",
]


def complete_lesson_one(clean_dir: Path, tmp_path: Path) -> None:
    """Walk 0.1 to its completion beat, then complete it."""
    for given in LESSON_WITH_EXERCISE:
        _advance(clean_dir, tmp_path, given)
    result = run(["complete", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0, result.output


def complete_lesson_two(clean_dir: Path, tmp_path: Path) -> None:
    """Complete 0.1, then 0.2 — the phase-final, homework-bearing lesson: homework lands
    in the slot as a side effect of completing it."""
    complete_lesson_one(clean_dir, tmp_path)
    for given in LESSON_WITH_EXERCISE:
        _advance(clean_dir, tmp_path, given)
    result = run(["complete", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0, result.output


# ------------------------------------------------------------------------------- homework


def test_check_cannot_complete_anything(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_two(clean_dir, tmp_path)
    before = (tmp_path / "clean-course" / "record.yaml").read_bytes()
    result = run(["homework", "check", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "clean-course" / "record.yaml").read_bytes() == before


def test_check_reports_the_active_slot(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_two(clean_dir, tmp_path)
    out = json.loads(run(["homework", "check", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["ok"] is True
    assert out["active"]["coordinate"] == "0.2"
    assert out["active"]["title"] == "Practise Both Things"
    assert len(out["active"]["requirements"]) == 2


def test_check_reports_no_active_slot_honestly(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_one(clean_dir, tmp_path)  # 0.1 has no homework section
    out = json.loads(run(["homework", "check", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["active"] is None


def test_retried_submit_returns_the_archived_result(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_two(clean_dir, tmp_path)
    token = json.loads(run(["homework", "check", "--course", str(clean_dir)], tmp_path).stdout)[
        "submission_token"
    ]
    a = json.loads(
        run(["homework", "submit", "--course", str(clean_dir), "--token", token], tmp_path).stdout
    )
    b = json.loads(
        run(["homework", "submit", "--course", str(clean_dir), "--token", token], tmp_path).stdout
    )
    assert b == a
    assert len(list((tmp_path / "clean-course" / "homework" / "archive").iterdir())) == 1


def test_submit_with_nothing_active_or_archived_is_refused(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_one(clean_dir, tmp_path)  # no homework placed yet
    result = run(["homework", "submit", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid-submission-token"


# -------------------------------------------------------------------------------- progress


def test_counts_are_derived_not_stored(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_one(clean_dir, tmp_path)
    # corrupt a would-be cached count: the record has no count field to corrupt — prove it
    record = yaml.safe_load((tmp_path / "clean-course" / "record.yaml").read_text())
    assert "lesson_count" not in record and "completed_count" not in record
    out = json.loads(run(["progress", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["completed_count"] == 1 and out["lesson_count"] == 3  # computed at print time


def test_progress_is_read_only(clean_dir: Path, tmp_path: Path) -> None:
    complete_lesson_one(clean_dir, tmp_path)
    before = (tmp_path / "clean-course" / "record.yaml").read_bytes()
    run(["progress", "--course", str(clean_dir)], tmp_path)
    assert (tmp_path / "clean-course" / "record.yaml").read_bytes() == before


# ------------------------------------------------------------------------------- telemetry


def test_telemetry_ask_reports_the_ternary_honestly(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["telemetry", "ask", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["opt_in"] is None  # never asked; no invented default
    assert isinstance(out["question"], str) and out["question"]


def test_telemetry_ask_never_writes(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)  # creates the record
    before = (tmp_path / "clean-course" / "record.yaml").read_bytes()
    run(["telemetry", "ask", "--course", str(clean_dir)], tmp_path)
    assert (tmp_path / "clean-course" / "record.yaml").read_bytes() == before


def test_telemetry_on_assigns_an_anonymous_id(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["telemetry", "on", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["opt_in"] is True
    assert out["anonymous_id"]

    record = yaml.safe_load((tmp_path / "clean-course" / "record.yaml").read_text())
    assert record["telemetry"]["opt_in"] is True
    assert record["telemetry"]["anonymous_id"] == out["anonymous_id"]


def test_telemetry_off_records_a_decline(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["telemetry", "off", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["opt_in"] is False
    assert out["anonymous_id"] is None


def test_consent_gates_the_sink_not_the_other_way(clean_dir: Path, tmp_path: Path) -> None:
    run(["telemetry", "off", "--course", str(clean_dir)], tmp_path)

    course = Course.load(clean_dir)
    store = FileProgressStore(tmp_path)
    found = store.get_record(LOCAL_LEARNER, course.id)
    assert found is not None
    record, revision = found
    assert record.telemetry.opt_in is False

    sink_path = tmp_path / "telemetry.jsonl"
    hooks = Dispatcher(telemetry=[JsonlSink(sink_path)])
    lesson = course.lesson_at(record.position.coordinate)
    assert lesson is not None

    # complete_lesson never checks opt_in itself — the Dispatcher enforces it before any
    # sink is handed an event, which is exactly what this proves.
    complete_lesson(store, course, record, revision, lesson, hooks=hooks)

    assert not sink_path.is_file(), "declined telemetry must never reach a sink"
