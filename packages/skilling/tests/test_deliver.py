"""End-to-end tests of the CLI, including ``deliver`` as a Conforming Runtime.

The point of these is that a runtime with no language model in it satisfies the whole
delivery contract: beats in order, gates held on real input, feedback with reasons,
remediation offered, a correct record written, idempotent completion, and a gate that is
still open a fortnight later.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.errors import Code

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE
from .corruptions import CORRUPTIONS

runner = CliRunner()

# Correct answers for examples/hello-skilling, lesson by lesson.
LESSON_ONE = ["proceed", "done", "c", "a", "b"]
LESSON_TWO = ["proceed", "done", "c", "b", "c"]
LESSON_THREE = ["proceed", "c", "a", "b"]  # no exercise: declared absent

FULL_WALK = "\n".join([*LESSON_ONE, "y", *LESSON_TWO, "y", *LESSON_THREE, "n", "y"]) + "\n"


def _state(tmp_path: Path) -> Path:
    return tmp_path / "state"


def _record(state: Path, course_id: str = "hello-skilling") -> dict:
    return yaml.safe_load((state / course_id / "record.yaml").read_text(encoding="utf-8"))


def _log(state: Path, course_id: str = "hello-skilling") -> list[dict]:
    return yaml.safe_load((state / course_id / "completed.yaml").read_text(encoding="utf-8"))


def _deliver(state: Path, stdin: str, course: Path = EXAMPLE_COURSE):
    return runner.invoke(app, ["deliver", str(course), "--state", str(state)], input=stdin)


# ------------------------------------------------------------------------------ validate


def test_validate_exits_zero_on_a_conforming_course(clean_dir: Path) -> None:
    result = runner.invoke(app, ["validate", str(clean_dir)])
    assert result.exit_code == 0
    assert "conforming" in result.output


def test_validate_exits_non_zero_and_names_the_code(clean_dir: Path) -> None:
    CORRUPTIONS[Code.LESSON_NUMBER_DUPLICATE](clean_dir)
    result = runner.invoke(app, ["validate", str(clean_dir)])
    assert result.exit_code == 1
    assert "lesson-number-duplicate" in result.output
    assert "spec/course-format.md#" in result.output


def test_validate_json_is_machine_readable(clean_dir: Path) -> None:
    result = runner.invoke(app, ["validate", str(clean_dir), "--json"])
    assert result.exit_code == 0
    assert '"ok"' in result.output


def test_strict_treats_warnings_as_failures(clean_dir: Path) -> None:
    CORRUPTIONS[Code.NEXT_UP_TOO_LONG](clean_dir)
    assert runner.invoke(app, ["validate", str(clean_dir)]).exit_code == 0
    assert runner.invoke(app, ["validate", str(clean_dir), "--strict"]).exit_code == 1


def test_the_example_course_validates_through_the_cli() -> None:
    result = runner.invoke(app, ["validate", str(EXAMPLE_COURSE)])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------- init, show


def test_init_produces_a_course_that_validates(tmp_path: Path) -> None:
    target = tmp_path / "brewing-basics"
    result = runner.invoke(app, ["init", str(target)])
    assert result.exit_code == 0, result.output
    assert "validates clean" in result.output
    assert runner.invoke(app, ["validate", str(target)]).exit_code == 0


def test_init_refuses_a_non_empty_directory(tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "something.txt").write_text("hello", encoding="utf-8")
    assert runner.invoke(app, ["init", str(target)]).exit_code == 1


def test_show_prints_derived_counts_only(clean_dir: Path) -> None:
    result = runner.invoke(app, ["show", str(clean_dir)])
    assert result.exit_code == 0
    assert "Derived" in result.output
    assert "never authored" in result.output
    assert "lessons" in result.output


# -------------------------------------------------------------------------------- deliver


def test_a_full_walk_completes_the_course(tmp_path: Path) -> None:
    state = _state(tmp_path)
    result = _deliver(state, FULL_WALK)
    assert result.exit_code == 0, result.output

    record = _record(state)
    assert record["completed"] == ["1.1", "1.2", "1.3"]
    assert record["skills_unlocked"] == ["course-anatomy", "first-course"]
    assert record["streak_days"] == 1
    assert record["position"] == {"phase": 1, "lesson": 3, "beat": None}

    log = _log(state)
    assert [entry["coordinate"] for entry in log] == ["1.1", "1.2", "1.3"]
    assert all(entry["course_version"] == "1.0.0" for entry in log)


def test_the_walk_matches_the_specified_file_layout(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _deliver(state, FULL_WALK)
    course_state = state / "hello-skilling"
    assert (course_state / "record.yaml").is_file()
    assert (course_state / "completed.yaml").is_file()
    assert (course_state / "homework" / "active.yaml").is_file()


def test_ceremony_places_the_homework_assignment(tmp_path: Path) -> None:
    state = _state(tmp_path)
    result = _deliver(state, FULL_WALK)
    assert "Phase 1 complete" in result.output
    assert "Homework unlocked" in result.output

    slot = yaml.safe_load(
        (state / "hello-skilling" / "homework" / "active.yaml").read_text(encoding="utf-8")
    )
    assert slot["coordinate"] == "1.3"
    assert slot["title"] == "Write Your Own Course"


def test_re_delivering_a_finished_course_changes_nothing(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _deliver(state, FULL_WALK)
    before_record = _record(state)
    before_log = _log(state)

    result = _deliver(state, "y\n")
    assert result.exit_code == 0
    assert "Course complete" in result.output
    assert _record(state) == before_record
    assert _log(state) == before_log


def test_quiz_feedback_states_the_reason(tmp_path: Path) -> None:
    result = _deliver(_state(tmp_path), FULL_WALK)
    assert "Correct." in result.output
    assert "the path is" in result.output or "derived" in result.output


def test_a_wrong_answer_offers_remediation_without_blocking_completion(tmp_path: Path) -> None:
    state = _state(tmp_path)
    # Answer question 1 wrongly, decline the re-explanation, then answer the rest correctly.
    stdin = "\n".join(["proceed", "done", "a", "no", "a", "b", "y"]) + "\n"
    result = _deliver(state, stdin)

    assert "Not quite." in result.output
    assert "go over that idea again" in result.output
    assert _record(state)["completed"] == ["1.1"], "a wrong answer must not block completion"


def test_two_wrong_answers_offer_a_return_to_the_concept(tmp_path: Path) -> None:
    stdin = "\n".join(["proceed", "done", "a", "no", "d", "yes"]) + "\n"
    result = _deliver(_state(tmp_path), stdin)
    assert "Revisit the concept?" in result.output


def test_an_abandoned_gate_stays_open(tmp_path: Path) -> None:
    state = _state(tmp_path)
    # No input at all: the learner reaches the concept gate and walks away.
    result = _deliver(state, "")
    assert result.exit_code == 0
    assert "still open" in result.output

    record = _record(state)
    assert record["position"] == {"phase": 1, "lesson": 1, "beat": "gate-concept"}
    assert record["completed"] == []


def test_resuming_lands_on_the_same_open_gate(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _deliver(state, "")
    assert _record(state)["position"]["beat"] == "gate-concept"

    resumed = _deliver(state, "\n".join(LESSON_ONE + ["y"]) + "\n")
    assert resumed.exit_code == 0
    assert "Go deeper on any of that, or move on?" in resumed.output
    assert _record(state)["completed"] == ["1.1"]


def test_going_deeper_does_not_advance_the_record(tmp_path: Path) -> None:
    state = _state(tmp_path)
    stdin = "\n".join(["deeper", "deeper", *LESSON_ONE, "y"]) + "\n"
    result = _deliver(state, stdin)
    assert result.exit_code == 0
    assert result.output.count("The Concept") >= 3, "the concept is re-presented each time"
    assert _record(state)["completed"] == ["1.1"]


def test_a_declared_absence_is_surfaced_to_the_learner(tmp_path: Path) -> None:
    state = _state(tmp_path)
    _deliver(state, "\n".join([*LESSON_ONE, "y", *LESSON_TWO, "y"]) + "\n")
    result = _deliver(state, "\n".join([*LESSON_THREE, "n", "y"]) + "\n")
    assert "the homework is the exercise" in result.output.lower()


def test_deliver_refuses_a_non_conforming_course(tmp_path: Path, clean_dir: Path) -> None:
    CORRUPTIONS[Code.QUIZ_ANSWER_LINE_MISSING](clean_dir)
    result = _deliver(_state(tmp_path), "", course=clean_dir)
    assert result.exit_code == 1
    assert "does not conform" in result.output


def test_submitting_homework_needs_two_separate_confirmations(tmp_path: Path) -> None:
    state = _state(tmp_path)
    stdin = "\n".join([*LESSON_ONE, "y", *LESSON_TWO, "y", *LESSON_THREE, "y", "n", "y"]) + "\n"
    result = _deliver(state, stdin)

    assert "Do you want to submit this assignment now?" in result.output
    assert "Confirm: submitting archives" in result.output
    assert "Left in your mailbox" in result.output
    assert (state / "hello-skilling" / "homework" / "active.yaml").is_file()


def test_confirming_both_prompts_archives_the_assignment(tmp_path: Path) -> None:
    state = _state(tmp_path)
    stdin = "\n".join([*LESSON_ONE, "y", *LESSON_TWO, "y", *LESSON_THREE, "y", "y", "y"]) + "\n"
    result = _deliver(state, stdin)

    assert "Submitted" in result.output
    assert not (state / "hello-skilling" / "homework" / "active.yaml").exists()
    archive = list((state / "hello-skilling" / "homework" / "archive").glob("*.yaml"))
    assert len(archive) == 1
    assert archive[0].name.startswith("1.3-")


# ----------------------------------------------------------------------------------- diff


def test_diff_reports_a_sufficient_bump(tmp_path: Path) -> None:
    old = fx.build(tmp_path / "old")
    new = fx.build(tmp_path / "new")
    fx.edit(new, fx.LESSON_ONE_PATH, "The first thing is worth knowing.", "It matters.")
    fx.edit(new, fx.MANIFEST_PATH, 'version: "1.0.0"', 'version: "1.0.1"')

    result = runner.invoke(app, ["diff", str(old), str(new)])
    assert result.exit_code == 0
    assert "sufficient" in result.output


def test_diff_strict_fails_an_insufficient_bump(tmp_path: Path) -> None:
    old = fx.build(tmp_path / "old")
    new = fx.build(tmp_path / "new")
    fx.edit(new, fx.MANIFEST_PATH, "{ number: 2, slug: two", "{ number: 2, slug: renamed")

    result = runner.invoke(app, ["diff", str(old), str(new), "--strict"])
    assert result.exit_code == 1
    assert "coordinates moved" in result.output


# -------------------------------------------------------------------------------- version


def test_version_reports_both_versions() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "specification 1.0" in result.output


@pytest.mark.parametrize("command", ["validate", "init", "show", "deliver", "diff"])
def test_every_documented_command_exists(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0
