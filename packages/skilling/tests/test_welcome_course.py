"""Contract and mechanical learner-flow checks for ``examples/welcome-skilling``.

The CLI walk proves the fixture can travel through the existing runtime, homework, artifact,
and workspace-relocation paths. It is mechanical coverage, not evidence of human tutoring.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from skilling import course as md
from skilling.cli import app
from skilling.conformance import validate_course
from skilling.course import Course

from .conftest import REPO_ROOT

WELCOME = REPO_ROOT / "examples" / "welcome-skilling"
GOAL_PATH = "showcase/welcome-skilling/goal.md"
runner = CliRunner()


def invoke(args: list[str], home: Path):
    return runner.invoke(app, args, env={"HOME": str(home)}, catch_exceptions=False)


def body(args: list[str], home: Path) -> dict:
    result = invoke(args, home)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def state_snapshot(workspace: Path) -> dict[str, bytes]:
    root = workspace / ".skilling" / "state"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and path.name != ".skilling.lock"
    }


def assert_current_beat_is_read_only(workspace: Path, home: Path, expected_beat: str) -> dict:
    before = state_snapshot(workspace)
    envelope = body(["next", "--course", "welcome-skilling"], home)
    assert envelope["beat"]["name"] == expected_beat
    assert state_snapshot(workspace) == before
    return envelope


def answer_quiz(workspace: Path, home: Path, labels: list[str]) -> None:
    for number, label in enumerate(labels, start=1):
        before = state_snapshot(workspace)
        first = body(["quiz", "next", "--course", "welcome-skilling"], home)
        question = first["question"]
        assert set(question) == {"number", "text", "options"}
        assert question["number"] == number
        assert set(question["options"]) == {"a", "b", "c", "d"}
        assert state_snapshot(workspace) == before

        repeated = body(["quiz", "next", "--course", "welcome-skilling"], home)
        assert repeated == first, "only the open question may be served before an answer"
        assert state_snapshot(workspace) == before

        verdict = body(["answer", label, "--course", "welcome-skilling"], home)
        assert verdict["correct"] is True
        assert verdict["reason"]


def test_welcome_course_validates_with_zero_findings() -> None:
    report = validate_course(WELCOME)
    assert report.findings == [], [finding.as_dict() for finding in report.findings]


def test_manifest_is_the_small_licensed_welcome_course() -> None:
    course = Course.load(WELCOME)
    assert course.manifest.spec_version == "1.4"
    assert (course.id, course.manifest.title, course.version) == (
        "welcome-skilling",
        "Welcome to Skilling",
        "1.0.0",
    )
    assert course.manifest.license == "CC-BY-4.0"
    assert [(phase.name, phase.lesson_count) for phase in course.phases] == [
        ("Learning with your tutor", 2)
    ]
    assert [(skill.id, skill.name) for skill in course.manifest.skills] == [
        ("ready-to-learn", "Ready to learn")
    ]


def test_lessons_are_brief_structured_and_reachable() -> None:
    course = Course.load(WELCOME)
    unlocked: set[str] = set()
    for lesson in course.lessons():
        parsed = md.parse_lesson(lesson.path)
        assert parsed.frontmatter
        assert parsed.frontmatter.duration_minutes == 5
        assert parsed.frontmatter.objectives
        assert parsed.section("objectives") is None
        unlocked.update(parsed.frontmatter.skills_unlocked)

        quiz = parsed.section("quiz")
        assert quiz
        questions = md.parse_quiz(quiz.body, quiz.body_line)
        assert len(questions) == 3
        for question in questions:
            assert sorted(question.labels) == ["a", "b", "c", "d"]
            assert question.answer_label
            assert question.has_reason

    assert unlocked == {"ready-to-learn"}


def test_lesson_contracts_keep_the_learner_in_control() -> None:
    course = Course.load(WELCOME)
    overview = course.phases[0].overview_path
    assert overview
    overview_text = " ".join(overview.read_text(encoding="utf-8").lower().split())
    for phrase in (
        "skilling learning workspace",
        "learning skills installed in your tutor",
        "stop at any point",
        "return when you are ready",
    ):
        assert phrase in overview_text

    first_lesson = course.lesson_at("1.1")
    assert first_lesson
    first = md.parse_lesson(first_lesson.path)
    first_text = " ".join(first.path.read_text(encoding="utf-8").lower().split())
    for phrase in (
        "explain → question → revisit",
        "everyday subject",
        "notice one gap",
        "ask a specific question",
        "different example",
        "change of pace",
        "should not supply the reflection",
        "waits for the learner's explicit reply",
    ):
        assert phrase in first_text

    second_lesson = course.lesson_at("1.2")
    assert second_lesson
    second = md.parse_lesson(second_lesson.path)
    second_frontmatter = second.frontmatter
    assert second_frontmatter
    second_text = " ".join(second.path.read_text(encoding="utf-8").lower().split())
    assert GOAL_PATH in second_text
    for phrase in (
        "return to their saved place",
        "lesson completion is separate from homework submission",
        "declared final lesson of its phase and carries homework",
        "completion does not submit the homework",
        "dictate your exact wording",
        "save those words verbatim",
        "must not invent, rewrite, or replace your words",
    ):
        assert phrase in second_text
    assert {objective.kind for objective in second_frontmatter.objectives} == {
        "knowledge",
        "practice",
    }
    practice = next(o for o in second_frontmatter.objectives if o.kind == "practice")
    knowledge = next(o for o in second_frontmatter.objectives if o.kind == "knowledge")
    assert knowledge.about == [1, 2, 3]
    assert practice.about == []
    assert practice.verify and "learner-authored" in practice.verify
    assert all(word in practice.verify.lower() for word in ("goal", "takeaway", "next action"))
    assert getattr(second_frontmatter.declaration("next_up"), "status", None) == "none"


def test_final_homework_requires_review_then_separate_confirmed_submission() -> None:
    course = Course.load(WELCOME)
    final = course.lesson_at("1.2")
    assert final and final.homework
    section = md.parse_lesson(final.path).section("homework")
    assert section
    homework = md.parse_homework(section.body)
    assert homework.complete
    assert homework.title == "Try the method"
    assert homework.objective and "explain, question, and revisit" in homework.objective.lower()
    assert len(homework.requirements) == 3
    assert homework.submission
    assert "show your work" in homework.submission.lower()
    assert "review the feedback on each requirement" in homework.submission.lower()
    assert "explicitly confirm" in homework.submission.lower()
    assert "separate from sharing the work" in homework.submission.lower()
    assert "token" not in homework.submission.lower()


def test_course_has_no_terminal_external_or_social_steps() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WELCOME.rglob("*")) if path.is_file()
    ).lower()
    for forbidden in (
        "http://",
        "https://",
        "terminal",
        "command line",
        "download",
        "create an account",
        "share on social",
        "post online",
    ):
        assert forbidden not in text
    assert "claude academy" not in text
    assert "futureofdev.com" not in text


def test_mechanical_walk_submission_artifact_and_relocation(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "unused-home"
    workspace = tmp_path / "learning"
    started = body(["start", str(WELCOME), str(workspace), "--json"], home)
    assert started["showcase"] == "showcase/welcome-skilling"

    monkeypatch.chdir(workspace)
    answers = {"1.1": ["b", "c", "b"], "1.2": ["a", "c", "b"]}
    for coordinate in ("1.1", "1.2"):
        for learner_input in ("next", "next", "next"):
            result = invoke(
                ["advance", "--course", "welcome-skilling", "--input", learner_input], home
            )
            assert result.exit_code == 0, f"{coordinate}/{learner_input}: {result.output}"

        gate = assert_current_beat_is_read_only(workspace, home, "gate-concept")
        assert set(gate["legal_inputs"]) == {"go-deeper", "proceed"}
        body(
            ["advance", "--course", "welcome-skilling", "--input", "proceed"],
            home,
        )
        body(["advance", "--course", "welcome-skilling", "--input", "next"], home)
        gate = assert_current_beat_is_read_only(workspace, home, "gate-exercise")
        assert set(gate["legal_inputs"]) == {"hint", "attempted"}

        if coordinate == "1.2":
            goal = workspace / GOAL_PATH
            goal.write_text(
                "# My learning direction\n\n"
                "**Goal:** Understand how to plan a small vegetable garden.\n\n"
                "**Takeaway:** A useful tutor asks me to explain an idea in my own words.\n\n"
                "**Next action:** Choose a sunny patch and list what already grows there.\n",
                encoding="utf-8",
            )
            saved = goal.read_text(encoding="utf-8")
            labels = ("**Goal:**", "**Takeaway:**", "**Next action:**")
            assert all(label in saved for label in labels)
            assert "vegetable garden" in saved and "sunny patch" in saved

        body(["advance", "--course", "welcome-skilling", "--input", "attempted"], home)
        answer_quiz(workspace, home, answers[coordinate])
        completed = body(["complete", "--course", "welcome-skilling"], home)

    assert completed["phase_completed"] == 1
    assert completed["completed_count"] == 2
    assert completed["badges_awarded"] == ["ready-to-learn"]
    assert completed["homework_placed"] is True
    ceremony = body(["ceremony", "--course", "welcome-skilling"], home)
    assert ceremony["beat"]["content"]["course_complete"] is True

    checked = body(["homework", "check", "--course", "welcome-skilling"], home)
    assert checked["active"]["title"] == "Try the method"
    token = checked["submission_token"]
    submitted = body(["homework", "submit", "--course", "welcome-skilling", "--token", token], home)
    assert submitted["archived"]["coordinate"] == "1.2"
    assert (
        body(["homework", "submit", "--course", "welcome-skilling", "--token", token], home)
        == submitted
    )

    artifact = body(
        [
            "artifact",
            "add",
            GOAL_PATH,
            "--title",
            "My learning direction",
            "--course",
            "welcome-skilling",
            "--coordinate",
            "1.2",
        ],
        home,
    )["artifact"]
    assert artifact["path"] == GOAL_PATH

    monkeypatch.chdir(tmp_path)
    moved = tmp_path / "learning-moved"
    workspace.rename(moved)
    nested = moved / "showcase" / "welcome-skilling" / "notes"
    nested.mkdir()
    monkeypatch.chdir(nested)

    progress = body(["progress", "--course", "welcome-skilling"], home)
    assert progress["completed"] == ["1.1", "1.2"]
    assert progress["skills_unlocked"] == ["ready-to-learn"]
    listed = body(["artifact", "list", "--course", "welcome-skilling"], home)
    assert listed["artifacts"] == [artifact]
    assert (moved / GOAL_PATH).is_file()
