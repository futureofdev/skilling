"""Tests for the JSON transition verbs: ``next``, ``advance``, ``complete``, ``ceremony``.

One process per transition, so every assertion is about what got *persisted* — the record and
the scratch file beside it — not about what stayed in memory. That split is the entire reason
``cli/runtime/_common.py`` exists: a wrong answer or a resumed gate has to survive a process
exit, which the interactive walker never had to think about.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.store import Conflict, FileProgressStore

from . import fixtures as fx

runner = CliRunner()


def run(args: list[str], tmp: Path):
    return runner.invoke(app, [*args, "--state", str(tmp)], catch_exceptions=False)


def _advance(course: Path, tmp: Path, given: str, *, key: str | None = None):
    args = ["advance", "--course", str(course), "--input", given]
    if key is not None:
        args = [*args, "--key", key]
    return run(args, tmp)


def _record(tmp: Path, course_id: str = "clean-course") -> dict:
    return yaml.safe_load((tmp / course_id / "record.yaml").read_text(encoding="utf-8"))


# The clean-course fixture (tests/fixtures.py): lesson 0.1 has an exercise, lesson 0.2 has an
# exercise and unlocks 'alpha', lesson 1.1 (last in the course) declares its exercise absent.
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
LESSON_WITHOUT_EXERCISE = [
    "next",
    "next",
    "next",
    "proceed",
    "answer-correct",
    "answer-correct",
    "answer-correct",
]


def _walk_to_complete(course: Path, tmp: Path, inputs: list[str]) -> dict:
    """Drive ``advance`` through a whole lesson, from wherever it currently stands to the
    completion beat, and return the last emitted envelope."""
    out: dict = {}
    for given in inputs:
        result = _advance(course, tmp, given)
        assert result.exit_code == 0, result.output
        out = json.loads(result.stdout)
    return out


# --------------------------------------------------------------------------------------- next


def test_beats_deliver_in_order(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["next", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["beat"]["name"] == "welcome"
    assert out["legal_inputs"] == ["next"]

    for expected in ["objectives", "concept", "gate-concept"]:
        result = _advance(clean_dir, tmp_path, "next")
        assert result.exit_code == 0, result.output
        out = json.loads(result.stdout)
        assert out["beat"]["name"] == expected

    # The concept gate's legal inputs are what actually drive the walk from here: 'proceed'
    # moves on, 'go-deeper' loops back to the concept without moving position.
    assert set(out["legal_inputs"]) == {"go-deeper", "proceed"}

    looped = json.loads(_advance(clean_dir, tmp_path, "go-deeper").stdout)
    assert looped["beat"]["name"] == "concept"
    # Curiosity is not progress: the coordinate and question index hold even though the beat
    # itself legitimately moves back from the gate to the concept.
    assert looped["position"]["phase"] == out["position"]["phase"]
    assert looped["position"]["lesson"] == out["position"]["lesson"]
    assert looped["position"]["question_index"] == out["position"]["question_index"]


def test_json_envelope_is_stable(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["next", "--course", str(clean_dir)], tmp_path).stdout)
    assert set(out) == {
        "ok",
        "verb",
        "course",
        "position",
        "beat",
        "legal_inputs",
        "revision",
        "completed_count",
        "lesson_count",
        "tutor",
    }
    assert out["ok"] is True
    assert out["verb"] == "next"
    assert out["course"] == {"id": "clean-course", "version": "1.0.0", "title": "Clean Course"}
    assert out["position"] == {"phase": 0, "lesson": 1, "beat": None, "question_index": None}
    assert out["completed_count"] == 0
    assert out["lesson_count"] == 3


def test_envelope_carries_the_manifests_declared_persona(clean_dir: Path, tmp_path: Path) -> None:
    # The clean-course fixture declares a tutor block (tests/fixtures.py) — next's envelope
    # must surface it verbatim rather than a course.title-only summary.
    out = json.loads(run(["next", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["tutor"] == {"persona": "A calm instructor.", "tone": ["Direct"]}


def test_tutor_is_omitted_when_the_manifest_declares_none(tmp_path: Path) -> None:
    root = fx.build(tmp_path / "no-tutor-course")
    fx.edit(
        root,
        fx.MANIFEST_PATH,
        "tutor:\n  persona: A calm instructor.\n  tone:\n    - Direct\n",
        "",
    )
    out = json.loads(run(["next", "--course", str(root)], tmp_path).stdout)
    assert out["course"]["title"] == "Clean Course"
    assert "tutor" not in out


def test_next_is_read_only(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)
    run(["next", "--course", str(clean_dir)], tmp_path)
    # load_or_create writes the record once, on first use; a second read must not touch it.
    assert _record(tmp_path)["position"] == {
        "phase": 0,
        "lesson": 1,
        "beat": None,
        "question_index": None,
    }


# ------------------------------------------------------------------------------------ advance


def test_illegal_input_is_a_typed_refusal_not_a_noop(clean_dir: Path, tmp_path: Path) -> None:
    result = _advance(clean_dir, tmp_path, "attempted")
    assert result.exit_code == 4
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "illegal-transition"


def test_unknown_input_is_invalid_not_illegal(clean_dir: Path, tmp_path: Path) -> None:
    result = _advance(clean_dir, tmp_path, "teleport")
    assert result.exit_code == 2
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "unknown-input"


def test_a_gate_input_illegal_at_another_gate_is_refused(clean_dir: Path, tmp_path: Path) -> None:
    for given in ["next", "next", "next", "proceed", "next"]:  # welcome -> gate-exercise
        result = _advance(clean_dir, tmp_path, given)
        assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["beat"]["name"] == "gate-exercise"

    # 'proceed' is legal at gate-concept, never at gate-exercise.
    result = _advance(clean_dir, tmp_path, "proceed")
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "illegal-transition"


def test_replayed_advance_is_idempotent(clean_dir: Path, tmp_path: Path) -> None:
    a = _advance(clean_dir, tmp_path, "next", key="k1")
    b = _advance(clean_dir, tmp_path, "next", key="k1")
    assert a.exit_code == 0
    assert a.stdout == b.stdout  # byte-identical; applied once

    assert _record(tmp_path)["position"]["beat"] == "objectives"


def test_a_fresh_key_applies_again(clean_dir: Path, tmp_path: Path) -> None:
    a = _advance(clean_dir, tmp_path, "next", key="k1")
    b = _advance(clean_dir, tmp_path, "next", key="k2")
    assert json.loads(a.stdout)["beat"]["name"] == "objectives"
    assert json.loads(b.stdout)["beat"]["name"] == "concept"


def test_conflict_surfaces_as_exit_3(clean_dir: Path, tmp_path: Path, monkeypatch) -> None:
    # Prime the record first, unpatched, so open_session's own record-creation write is
    # unaffected — only this call's own advance write should ever hit the patched method.
    run(["next", "--course", str(clean_dir)], tmp_path)

    def _boom(self, record, expected_revision):  # noqa: ANN001
        raise Conflict("record.yaml", expected_revision, "elsewhere")

    monkeypatch.setattr(FileProgressStore, "put_record", _boom)

    result = _advance(clean_dir, tmp_path, "next")
    assert result.exit_code == 3
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "conflict"


def test_advance_refuses_at_the_completion_beat(clean_dir: Path, tmp_path: Path) -> None:
    out = _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    assert out["beat"]["name"] == "complete"

    result = _advance(clean_dir, tmp_path, "next")
    assert result.exit_code == 4
    body = json.loads(result.stdout)
    assert body["error"]["code"] == "illegal-transition"
    assert "complete" in body["error"]["message"]


def test_advance_refuses_once_the_course_is_complete(clean_dir: Path, tmp_path: Path) -> None:
    for inputs in [LESSON_WITH_EXERCISE, LESSON_WITH_EXERCISE, LESSON_WITHOUT_EXERCISE]:
        _walk_to_complete(clean_dir, tmp_path, inputs)
        run(["complete", "--course", str(clean_dir)], tmp_path)

    result = _advance(clean_dir, tmp_path, "next")
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "course-complete"


# ----------------------------------------------------------------------------------- complete


def test_complete_refuses_before_the_quiz_is_finished(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)
    result = run(["complete", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "illegal-transition"


def test_completion_writes_the_record_and_is_idempotent(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)

    first = json.loads(run(["complete", "--course", str(clean_dir)], tmp_path).stdout)
    assert first["ok"] is True
    assert first["already_completed"] is False
    assert first["badges_awarded"] == []
    assert first["position"] == {"phase": 0, "lesson": 2, "beat": None, "question_index": None}

    before = _record(tmp_path)
    again = json.loads(run(["complete", "--course", str(clean_dir)], tmp_path).stdout)
    assert again["already_completed"] is True
    assert _record(tmp_path) == before, "a replayed complete must change nothing"
    assert _record(tmp_path)["completed"] == ["0.1"]


def test_completing_a_lesson_that_unlocks_a_skill_awards_the_badge_and_places_homework(
    clean_dir: Path, tmp_path: Path
) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # 0.1, no badge

    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    outcome = json.loads(run(["complete", "--course", str(clean_dir)], tmp_path).stdout)

    assert outcome["badges_awarded"] == ["alpha"]
    assert outcome["phase_completed"] == 0
    assert outcome["homework_placed"] is True

    record = _record(tmp_path)
    assert record["completed"] == ["0.1", "0.2"]
    assert record["skills_unlocked"] == ["alpha"]
    assert (tmp_path / "clean-course" / "homework" / "active.yaml").is_file()


# ----------------------------------------------------------------------------------- ceremony


def test_ceremony_refuses_when_not_at_a_phase_boundary(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # completes 0.1: not phase-final

    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "not-a-phase-boundary"


def test_ceremony_refuses_before_anything_has_completed(clean_dir: Path, tmp_path: Path) -> None:
    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "not-a-phase-boundary"


def test_ceremony_reports_the_finished_phase(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # 0.1
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # 0.2, phase-final

    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["beat"]["name"] == "ceremony"
    assert body["beat"]["content"]["phase_number"] == 0
    assert body["beat"]["content"]["coordinate"] == "0.2"
    assert body["beat"]["content"]["course_complete"] is False
    # The clean-course manifest declares no ceremony/brand block, so there is no copy to
    # invent — the verb must say so honestly rather than manufacture something.
    assert body["beat"]["content"]["share_text"] is None


def test_ceremony_knows_when_the_whole_course_is_done(clean_dir: Path, tmp_path: Path) -> None:
    for inputs in [LESSON_WITH_EXERCISE, LESSON_WITH_EXERCISE, LESSON_WITHOUT_EXERCISE]:
        _walk_to_complete(clean_dir, tmp_path, inputs)
        run(["complete", "--course", str(clean_dir)], tmp_path)

    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["beat"]["content"]["course_complete"] is True


# ------------------------------------------------------------------------------- version guard


def test_a_course_version_mismatch_is_refused(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)  # creates the record at 1.0.0

    manifest = clean_dir / "course.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace('version: "1.0.0"', 'version: "2.0.0"'),
        encoding="utf-8",
    )

    result = run(["next", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 5
    assert json.loads(result.stdout)["error"]["code"] == "version-mismatch"
