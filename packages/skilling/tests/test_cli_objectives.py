"""Tests for ``objective settle`` / ``objective show``.

Capability-enforced, provenance-required: a host claims what it can observe through repeated
``--capability`` flags, and ``settle`` translates ``settle_objective``'s refusals (T5) into the
typed exits every other runtime verb already uses (T7's ``ExitCode``). ``show`` is read-only;
its ``check`` field is a proposal a host may run through its own permission model — this verb
must never run it itself.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.cli import app

from . import fixtures as fx

runner = CliRunner()


def run(args: list[str], tmp: Path):
    return runner.invoke(app, [*args, "--state", str(tmp)], catch_exceptions=False)


PRACTICE_OBJECTIVE = """\
objectives:
  - id: obj-id
    kind: practice
    text: Do the practiced thing
    verify: "The practiced thing exists where the learner made it"
"""

PRACTICE_OBJECTIVE_WITHOUT_VERIFY = """\
objectives:
  - id: obj-id
    kind: practice
    text: Do the practiced thing
"""

PRACTICE_OBJECTIVE_WITH_CHECK = """\
objectives:
  - id: obj-id
    kind: practice
    text: Do the practiced thing
    verify: "The practiced thing exists where the learner made it"
    check: "ls practiced-thing.txt"
"""


def _install(root: Path, declaration: str) -> None:
    """Replace the clean fixture's first lesson's prose objectives with a structured one."""
    fx.edit(
        root, fx.LESSON_ONE_PATH, "skills_unlocked: []\n", f"skills_unlocked: []\n{declaration}"
    )
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )


@pytest.fixture
def practice_course(clean_dir: Path) -> Path:
    _install(clean_dir, PRACTICE_OBJECTIVE)
    return clean_dir


@pytest.fixture
def practice_course_without_verify(clean_dir: Path) -> Path:
    _install(clean_dir, PRACTICE_OBJECTIVE_WITHOUT_VERIFY)
    return clean_dir


@pytest.fixture
def practice_course_with_check(clean_dir: Path) -> Path:
    _install(clean_dir, PRACTICE_OBJECTIVE_WITH_CHECK)
    return clean_dir


# --------------------------------------------------------------------------------------- settle


def test_practice_without_observe_is_refused(practice_course: Path, tmp_path: Path) -> None:
    r = run(
        [
            "objective",
            "settle",
            "obj-id",
            "--evidence",
            "observed",
            "--capability",
            "converse",
            "--attested-by",
            "x",
            "--checked",
            "y",
            "--course",
            str(practice_course),
        ],
        tmp_path,
    )
    assert r.exit_code == 4 and json.loads(r.stdout)["error"]["code"] == "capability-missing"


def test_observed_without_provenance_is_refused(practice_course: Path, tmp_path: Path) -> None:
    r = run(
        [
            "objective",
            "settle",
            "obj-id",
            "--evidence",
            "observed",
            "--capability",
            "observe",
            "--course",
            str(practice_course),
        ],
        tmp_path,
    )
    assert r.exit_code == 2 and "provenance" in r.stdout


def test_no_verify_means_unsettleable_by_any_path(
    practice_course_without_verify: Path, tmp_path: Path
) -> None:
    r = run(
        [
            "objective",
            "settle",
            "obj-id",
            "--evidence",
            "observed",
            "--capability",
            "observe",
            "--attested-by",
            "x",
            "--checked",
            "y",
            "--course",
            str(practice_course_without_verify),
        ],
        tmp_path,
    )
    assert r.exit_code == 4 and "verify" in json.loads(r.stdout)["error"]["message"]


def test_unknown_capability_is_a_typed_refusal(practice_course: Path, tmp_path: Path) -> None:
    r = run(
        [
            "objective",
            "settle",
            "obj-id",
            "--evidence",
            "observed",
            "--capability",
            "not-a-real-capability",
            "--course",
            str(practice_course),
        ],
        tmp_path,
    )
    assert r.exit_code == 2
    assert json.loads(r.stdout)["error"]["code"] == "capability-unknown"


def test_unknown_objective_id_is_refused(practice_course: Path, tmp_path: Path) -> None:
    r = run(
        [
            "objective",
            "settle",
            "nonexistent",
            "--evidence",
            "observed",
            "--capability",
            "observe",
            "--course",
            str(practice_course),
        ],
        tmp_path,
    )
    assert r.exit_code == 2
    assert json.loads(r.stdout)["error"]["code"] == "objective-unknown"


def test_settling_with_capability_and_provenance_succeeds(
    practice_course: Path, tmp_path: Path
) -> None:
    r = run(
        [
            "objective",
            "settle",
            "obj-id",
            "--evidence",
            "observed",
            "--capability",
            "observe",
            "--attested-by",
            "codex",
            "--checked",
            "ls output",
            "--course",
            str(practice_course),
        ],
        tmp_path,
    )
    assert r.exit_code == 0, r.output
    body = json.loads(r.stdout)
    assert body["ok"] is True
    assert body["objective"]["id"] == "obj-id"
    assert body["objective"]["evidence"] == "observed"
    assert body["objective"]["provenance"] == {
        "checked": "ls output",
        "verify": "The practiced thing exists where the learner made it",
        "attested_by": "codex",
    }
    assert body["newly_met"] is True


def test_settling_twice_is_idempotent(practice_course: Path, tmp_path: Path) -> None:
    args = [
        "objective",
        "settle",
        "obj-id",
        "--evidence",
        "observed",
        "--capability",
        "observe",
        "--attested-by",
        "codex",
        "--checked",
        "ls output",
        "--course",
        str(practice_course),
    ]
    first = run(args, tmp_path)
    second = run(args, tmp_path)
    assert first.exit_code == 0 and second.exit_code == 0
    assert json.loads(first.stdout)["newly_met"] is True
    assert json.loads(second.stdout)["newly_met"] is False


# ----------------------------------------------------------------------------------------- show


def test_no_capabilities_settles_nothing_and_conforms(
    practice_course: Path, tmp_path: Path
) -> None:
    r = run(["objective", "show", "--course", str(practice_course)], tmp_path)
    body = json.loads(r.stdout)
    assert r.exit_code == 0 and all(not o["settleable_now"] for o in body["objectives"])


def test_check_is_printed_never_executed(
    practice_course_with_check: Path, tmp_path: Path, monkeypatch
) -> None:
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    r = run(["objective", "show", "--course", str(practice_course_with_check)], tmp_path)
    assert calls == []  # the check command appears in output as a proposal only
    body = json.loads(r.stdout)
    assert body["objectives"][0]["check"] == "ls practiced-thing.txt"


def test_show_reports_settleable_now_when_capability_is_held(
    practice_course: Path, tmp_path: Path
) -> None:
    r = run(
        ["objective", "show", "--capability", "observe", "--course", str(practice_course)],
        tmp_path,
    )
    body = json.loads(r.stdout)
    assert body["objectives"][0]["settleable_now"] is True
