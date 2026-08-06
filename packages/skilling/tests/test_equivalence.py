"""Byte-equivalence: the same lesson, driven two ways, must write the same bytes.

Two hosts can deliver a course through entirely different call paths — one embeds the
delivery core directly in a single long-lived process, one is CLI-mediated and shells out
once per transition — and the specification is not honoured unless both leave behind the
exact same ``record.yaml`` and ``completed.yaml``. This is the tripwire for choreography
drift: if a CLI verb ever reimplements a transition slightly differently from the pure
machine it is supposed to wrap, this test is where that first shows up as a byte diff
rather than as a subtle, later bug report.

``drive_machine_directly`` is the embedded host: it never touches ``skilling`` the
executable at all, only ``skilling.delivery``'s pure functions and the file store, keeping
per-quiz scratch (``wrong_count``, ``returning_to_quiz``) in an ordinary Python variable for
the lifetime of one process. ``drive_cli_subprocesses`` is the CLI-mediated host: one
``skilling`` subprocess per transition, exactly as a driving pack would, with
``cli/runtime/_common.py``'s ``scratch.yaml`` beside the record standing in for the
in-memory state that a fresh process cannot otherwise keep between calls. ``SKILLING_NOW``
freezes the one real-time write both paths make (the completion timestamp) so the run is
reproducible.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from skilling.course import Course, parse_lesson, parse_quiz
from skilling.delivery import Beat, Input, LessonShape, LessonState, complete_lesson, load_or_create
from skilling.delivery import advance as apply_input
from skilling.store import LOCAL_LEARNER, FileProgressStore

from .conftest import REPO_ROOT

EXAMPLE_COURSE = REPO_ROOT / "examples" / "hello-skilling"
FROZEN_NOW = "2026-08-05T12:00:00+00:00"

# One full delivery of hello-skilling's first lesson (1.1). Both gates are opened and
# resolved twice each — 'go-deeper'/'hint' loop back before 'proceed'/'attempted' actually
# leaves — and the quiz includes one wrong answer that triggers remediation and a
# 'continue' back into the quiz, before two correct answers reach the completion beat.
# Plain strings are ``Input`` values applied through ``advance``; ``("answer", label)``
# submits a quiz label; ``"complete"`` is the one non-machine step, the completion write set.
SCRIPT: list[str | tuple[str, str]] = [
    "next",
    "next",
    "next",
    "go-deeper",
    "next",
    "proceed",
    "next",
    "hint",
    "next",
    "attempted",
    ("answer", "b"),  # question 1 (correct is 'c') — wrong, triggers remediation
    "continue",
    ("answer", "a"),  # question 2 (correct is 'a') — correct
    ("answer", "b"),  # question 3 (correct is 'b') — correct, reaches the completion beat
    "complete",
]


def _skilling_executable() -> str:
    """The console script beside the interpreter running this test — resolves correctly
    whether pytest is invoked through ``uv run`` or any other virtualenv, without relying on
    ``PATH`` ordering."""
    return str(Path(sys.executable).parent / "skilling")


# ------------------------------------------------------------------------------- embedded host


def drive_machine_directly(
    state_root: Path, script: list[str | tuple[str, str]], *, now: str
) -> Path:
    """Drive ``script`` against ``state_root`` by calling ``skilling.delivery`` directly, in
    one process, the way an embedded (non-CLI-mediated) host would."""
    moment = datetime.fromisoformat(now)
    course = Course.load(EXAMPLE_COURSE)
    store = FileProgressStore(state_root)
    record, revision = load_or_create(store, course, LOCAL_LEARNER)

    lesson = course.lesson_at(record.position.coordinate)
    assert lesson is not None
    parsed = parse_lesson(lesson.path)
    quiz_section = parsed.section("quiz")
    assert quiz_section is not None
    questions = parse_quiz(quiz_section.body, quiz_section.body_line)
    shape = LessonShape(
        has_exercise=parsed.section("exercise") is not None,
        is_phase_end=course.is_last_in_phase(lesson.coordinate),
    )
    state = LessonState.start(shape)

    def persist(new_state: LessonState) -> None:
        nonlocal record, revision
        new_position = record.position.model_copy(
            update={
                "beat": str(new_state.beat),
                "question_index": (
                    new_state.question_index
                    if new_state.beat in (Beat.QUIZ, Beat.REMEDIATE)
                    else None
                ),
            }
        )
        updated = record.model_copy(update={"position": new_position})
        revision = store.put_record(updated, revision)
        record = updated

    for step in script:
        if step == "complete":
            outcome = complete_lesson(store, course, record, revision, lesson, now=moment)
            record, revision = outcome.record, outcome.revision
            continue
        if isinstance(step, tuple):
            _, label = step
            question = questions[state.question_index]
            given = Input.ANSWER_CORRECT if label == question.answer_label else Input.ANSWER_WRONG
        else:
            given = Input(step)
        state = apply_input(state, given)
        persist(state)

    return state_root


# --------------------------------------------------------------------------- CLI-mediated host


def drive_cli_subprocesses(
    state_root: Path, script: list[str | tuple[str, str]], *, env: dict[str, str]
) -> Path:
    """Drive ``script`` against ``state_root`` by shelling out to the real ``skilling``
    executable once per transition, exactly as a driving pack would."""
    executable = _skilling_executable()
    full_env = {**os.environ, **env}
    course = str(EXAMPLE_COURSE)

    def run(*args: str) -> dict[str, object]:
        result = subprocess.run(
            [executable, *args, "--course", course, "--state", str(state_root)],
            capture_output=True,
            text=True,
            env=full_env,
        )
        assert result.returncode == 0, f"{args}: {result.stderr or result.stdout}"
        return json.loads(result.stdout)

    for step in script:
        if step == "complete":
            run("complete")
        elif isinstance(step, tuple):
            _, label = step
            run("answer", label)
        else:
            run("advance", "--input", step)

    return state_root


# ------------------------------------------------------------------------------------- the test


def test_pack_run_and_embed_run_produce_the_same_record(tmp_path: Path) -> None:
    embed_root = drive_machine_directly(tmp_path / "embed", SCRIPT, now=FROZEN_NOW)
    cli_root = drive_cli_subprocesses(tmp_path / "cli", SCRIPT, env={"SKILLING_NOW": FROZEN_NOW})

    embed_record = (embed_root / "hello-skilling" / "record.yaml").read_bytes()
    cli_record = (cli_root / "hello-skilling" / "record.yaml").read_bytes()
    assert embed_record == cli_record

    embed_log = (embed_root / "hello-skilling" / "completed.yaml").read_bytes()
    cli_log = (cli_root / "hello-skilling" / "completed.yaml").read_bytes()
    assert embed_log == cli_log
