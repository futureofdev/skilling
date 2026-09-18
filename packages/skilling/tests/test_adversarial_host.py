"""The adversarial suite: every illegal sequence a misbehaving host prompt could issue.

A host prompt is the only thing standing between a learner's real input and a CLI call —
nothing stops a broken or dishonest one from calling a verb out of order, at the wrong beat,
or with a forged input. What the format actually guarantees is not that this cannot be
*attempted*, but that it cannot *succeed*: every row below is a call the CLI must refuse (a
typed error, never a bare non-zero exit with prose) or, where the CLI's own idempotency
already absorbs a retry harmlessly (the one 'double completion' row), a call that is a
provable no-op. Either way, the record left behind is byte-identical to the record already
there before the call — a misbehaving host cannot forge state, it can only fail loudly or be
ignored.

Table-driven: one row per illegal sequence, built on the ``clean_dir`` fixture course (two
phases; lesson 0.1 and 0.2 have an exercise, 0.2 unlocks a badge and homework, 1.1 has none of
either). Each row's ``setup`` performs only calls that are themselves legal, reaching the
precondition the row means to test; ``call`` is the one adversarial call under test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from typer.testing import CliRunner, Result

from skilling.cli import app
from skilling.skills import skill_dir

runner = CliRunner()


def run(args: list[str], tmp: Path):
    return runner.invoke(app, [*args, "--state", str(tmp)], catch_exceptions=False)


def _advance(course: Path, tmp: Path, given: str):
    result = run(["advance", "--course", str(course), "--input", given], tmp)
    assert result.exit_code == 0, result.output
    return result


def _answer(course: Path, tmp: Path, label: str):
    result = run(["answer", label, "--course", str(course)], tmp)
    assert result.exit_code == 0, result.output
    return result


def _complete(course: Path, tmp: Path):
    result = run(["complete", "--course", str(course)], tmp)
    assert result.exit_code == 0, result.output
    return result


def _record_bytes(tmp: Path, course_id: str = "clean-course") -> bytes:
    return (tmp / course_id / "record.yaml").read_bytes()


# Lessons 0.1 and 0.2 both declare an exercise; 1.1 declares its absence (tests/fixtures.py).
_TO_QUIZ_WITH_EXERCISE = ["next", "next", "next", "proceed", "next", "attempted"]
_TO_QUIZ_WITHOUT_EXERCISE = ["next", "next", "next", "proceed"]

# Correct labels per lesson, in question order (tests/fixtures.py's inline answer keys).
_ANSWERS_0_1 = ["b", "a", "c"]
_ANSWERS_0_2 = ["c", "a", "b"]
_ANSWERS_1_1 = ["b", "a", "b"]


def _walk_to_quiz(course: Path, tmp: Path) -> None:
    for given in _TO_QUIZ_WITH_EXERCISE:
        _advance(course, tmp, given)


def _complete_lesson_0_1(course: Path, tmp: Path) -> None:
    _walk_to_quiz(course, tmp)
    for label in _ANSWERS_0_1:
        _answer(course, tmp, label)
    _complete(course, tmp)


def _complete_lesson_0_2(course: Path, tmp: Path) -> None:
    for given in _TO_QUIZ_WITH_EXERCISE:
        _advance(course, tmp, given)
    for label in _ANSWERS_0_2:
        _answer(course, tmp, label)
    _complete(course, tmp)


def _complete_lesson_1_1(course: Path, tmp: Path) -> None:
    for given in _TO_QUIZ_WITHOUT_EXERCISE:
        _advance(course, tmp, given)
    for label in _ANSWERS_1_1:
        _answer(course, tmp, label)
    _complete(course, tmp)


def _complete_whole_course(course: Path, tmp: Path) -> None:
    _complete_lesson_0_1(course, tmp)
    _complete_lesson_0_2(course, tmp)
    _complete_lesson_1_1(course, tmp)


def _nothing(course: Path, tmp: Path) -> None:
    """No transition — but ``next`` still has to run once so a record exists on disk for the
    'before' snapshot to read; ``next`` is read-only (``test_next_is_read_only`` covers that
    claim), so this performs no transition of its own."""
    result = run(["next", "--course", str(course)], tmp)
    assert result.exit_code == 0, result.output


class Row(NamedTuple):
    name: str
    setup: Callable[[Path, Path], object]
    call: Callable[[Path, Path], Result]
    exit_code: int
    error_code: str | None
    """``None`` marks the one row where the CLI's own idempotency absorbs the call rather
    than refusing it outright (double completion) — the record-unchanged invariant still
    applies, but there is no ``error`` object to check."""


ROWS: tuple[Row, ...] = (
    Row(
        "completing before the quiz is finished",
        _walk_to_quiz,
        lambda c, t: run(["complete", "--course", str(c)], t),
        4,
        "illegal-transition",
    ),
    Row(
        "answering at the welcome beat",
        _nothing,
        lambda c, t: run(["answer", "b", "--course", str(c)], t),
        4,
        "illegal-transition",
    ),
    Row(
        "quiz next at the concept gate",
        lambda c, t: [_advance(c, t, i) for i in ["next", "next", "next"]],
        lambda c, t: run(["quiz", "next", "--course", str(c)], t),
        4,
        "illegal-transition",
    ),
    Row(
        "forged --input proceed at the exercise gate",
        lambda c, t: [_advance(c, t, i) for i in ["next", "next", "next", "proceed", "next"]],
        lambda c, t: run(["advance", "--course", str(c), "--input", "proceed"], t),
        4,
        "illegal-transition",
    ),
    Row(
        "forged --input hint at the concept gate",
        lambda c, t: [_advance(c, t, i) for i in ["next", "next", "next"]],
        lambda c, t: run(["advance", "--course", str(c), "--input", "hint"], t),
        4,
        "illegal-transition",
    ),
    Row(
        "answering again while remediation is open (skipping past it)",
        lambda c, t: (_walk_to_quiz(c, t), _answer(c, t, "a")),  # q1 wrong: real answer is 'b'
        lambda c, t: run(["answer", "c", "--course", str(c)], t),
        4,
        "illegal-transition",
    ),
    Row(
        "advancing past the completion beat instead of calling complete",
        lambda c, t: (_walk_to_quiz(c, t), [_answer(c, t, label) for label in _ANSWERS_0_1]),
        lambda c, t: run(["advance", "--course", str(c), "--input", "next"], t),
        4,
        "illegal-transition",
    ),
    Row(
        "advancing once the whole course is complete",
        _complete_whole_course,
        lambda c, t: run(["advance", "--course", str(c), "--input", "next"], t),
        4,
        "course-complete",
    ),
    Row(
        "ceremony before anything has completed",
        _nothing,
        lambda c, t: run(["ceremony", "--course", str(c)], t),
        2,
        "coordinate-required",
    ),
    Row(
        "ceremony after a lesson that is not the end of its phase",
        _complete_lesson_0_1,
        lambda c, t: run(["ceremony", "--course", str(c)], t),
        4,
        "not-a-phase-boundary",
    ),
    Row(
        "an unknown --input value",
        _nothing,
        lambda c, t: run(["advance", "--course", str(c), "--input", "teleport"], t),
        2,
        "unknown-input",
    ),
    Row(
        "an unknown quiz option label",
        _walk_to_quiz,
        lambda c, t: run(["answer", "z", "--course", str(c)], t),
        2,
        "unknown-option",
    ),
    Row(
        "settling an objective the lesson does not declare",
        _nothing,
        lambda c, t: run(
            ["objective", "settle", "bogus-id", "--evidence", "explained", "--course", str(c)], t
        ),
        2,
        "objective-unknown",
    ),
    Row(
        "settling a knowledge objective while holding no capability",
        _complete_lesson_0_1,  # moves position to 0.2, which declares 'second-thing'
        lambda c, t: run(
            ["objective", "settle", "second-thing", "--evidence", "explained", "--course", str(c)],
            t,
        ),
        4,
        "capability-missing",
    ),
    Row(
        "submitting homework when none was ever assigned",
        _nothing,
        lambda c, t: run(["homework", "submit", "--course", str(c)], t),
        2,
        "invalid-submission-token",
    ),
)


@pytest.mark.parametrize("row", ROWS, ids=[r.name for r in ROWS])
def test_illegal_sequence_is_refused_and_the_record_is_unchanged(
    row: Row, clean_dir: Path, tmp_path: Path
) -> None:
    row.setup(clean_dir, tmp_path)
    before = _record_bytes(tmp_path)

    result = row.call(clean_dir, tmp_path)
    assert result.exit_code == row.exit_code, result.output
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == row.error_code

    after = _record_bytes(tmp_path)
    assert after == before, "the record changed despite the refusal"


def test_double_completion_is_absorbed_not_reapplied(clean_dir: Path, tmp_path: Path) -> None:
    """Not a refusal — the CLI's own idempotency (``complete_lesson``'s ``has_completed``
    check) absorbs a retried completion as a safe no-op. Included here anyway because it is
    the same guarantee as every row above, proved a different way: a misbehaving host that
    calls ``complete`` twice — hoping to double a badge, a streak, or a homework placement —
    gets exactly one write, not two."""
    _complete_lesson_0_1(clean_dir, tmp_path)
    before = _record_bytes(tmp_path)

    result = run(["complete", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["ok"] is True
    assert body["already_completed"] is True

    after = _record_bytes(tmp_path)
    assert after == before, "a replayed complete must not write anything further"


class PromptContract(NamedTuple):
    name: str
    skill: str
    reference: str
    required: tuple[str, ...]


PROMPT_CONTRACTS: tuple[PromptContract, ...] = (
    PromptContract(
        "a stale workspace path requests the actual path or ref",
        "learn",
        "course-resolution.md",
        ("path is no longer usable", "ask the learner", "Never substitute another row"),
    ),
    PromptContract(
        "a recency tie is not silently broken",
        "learn",
        "course-resolution.md",
        ("tie on `last_activity`", "list the candidates by title and ask"),
    ),
    PromptContract(
        "a keyed replay does not authorize another transition",
        "learn",
        "delivery-loop.md",
        ("same key and input", "`replayed: true`", "do not announce another action"),
    ),
    PromptContract(
        "a gate waits for real learner input",
        "learn",
        "delivery-loop.md",
        ("Gates are open waits", "wait for their actual reply", "do not answer for them"),
    ),
    PromptContract(
        "quiz answers remain in CLI custody",
        "learn",
        "delivery-loop.md",
        ("Never read a lesson's quiz section", "collect their chosen label", "returns the verdict"),
    ),
    PromptContract(
        "an uncertain submission reuses its checked token",
        "homework",
        "workflows.md",
        ("same retained token", "Never check again just to replace a retry token"),
    ),
    PromptContract(
        "a ceremony artifact uses returned facts and existing work",
        "learn",
        "delivery-loop.md",
        ("ceremony.beat.content.coordinate", "response's `showcase`", "already created"),
    ),
    PromptContract(
        "a submitted-homework artifact does not expect showcase in submit",
        "homework",
        "workflows.md",
        ("`archived.coordinate`", "no `showcase`", "retained earlier"),
    ),
    PromptContract(
        "artifact refusals preserve the optional boundary and hidden state",
        "learn",
        "troubleshooting.md",
        (
            "`no-workspace`",
            "`course-not-found`",
            "`artifact-missing`",
            "`artifact-outside-workspace`",
            "`coordinate-required`",
            "optional: skip it and continue",
            "never substitute the current lesson position",
        ),
    ),
)


@pytest.mark.parametrize("contract", PROMPT_CONTRACTS, ids=[row.name for row in PROMPT_CONTRACTS])
def test_bundled_prompt_resists_adversarial_host_shortcuts(contract: PromptContract) -> None:
    """The runtime refuses illegal calls above; these rows keep the host instructions from
    recommending shortcuts the CLI cannot detect, such as silently choosing a tied course or
    inventing an artifact path after submission.
    """
    body = " ".join(
        (skill_dir(contract.skill) / "references" / contract.reference)
        .read_text(encoding="utf-8")
        .split()
    )
    for phrase in contract.required:
        assert phrase in body
