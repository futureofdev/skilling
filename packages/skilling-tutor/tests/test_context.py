import asyncio
import json
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skilling.delivery import Beat, Input
from skilling.session import (
    AssignmentView,
    BeatView,
    CourseView,
    HomeworkCheck,
    PositionView,
    RequirementView,
    SessionSnapshot,
    TutorView,
)
from skilling_tutor import (
    AdviceIdentity,
    ConversationContext,
    HomeworkAdviceContext,
    LearnerEvidence,
    NarrationContext,
    ObjectiveAdviceContext,
    ProgressContext,
    TutorError,
)


def test_snapshot_copy_and_homework_token_custody():
    snapshot = SessionSnapshot(
        CourseView("course", "1", "Course"),
        "PRIVATE_LEARNER",
        PositionView(1, 1, "welcome", None),
        "PRIVATE_REVISION",
        BeatView(Beat.WELCOME, body="Active material"),
        (),
        0,
        1,
        TutorView("Patient tutor", ("warm",)),
    )
    context = NarrationContext.from_snapshot(snapshot)
    assert "Active material" in context.material
    assert context.persona == "Patient tutor"
    assert context.beat is Beat.WELCOME and context.legal_inputs == ()
    copied = NarrationContext.from_snapshot(replace(snapshot, legal_inputs=(Input.NEXT,)))
    assert copied.legal_inputs == (Input.NEXT,)
    assert NarrationContext.from_snapshot(replace(snapshot, tutor=None)).persona is None
    assert "PRIVATE" not in json.dumps(asdict(context))
    with pytest.raises(FrozenInstanceError):
        context.persona = "changed"  # pyright: ignore[reportAttributeAccessIssue]
    assignment = AssignmentView(
        "1.1",
        "Build",
        "Practice",
        (RequirementView("Work", None, ""),),
        (RequirementView("Optional", None, ""),),
        "PRIVATE_SUBMISSION",
        datetime.now(UTC),
    )
    check = HomeworkCheck(snapshot.course, assignment, "revision", "PRIVATE_TOKEN")
    advice = HomeworkAdviceContext.from_check(
        check, evidence=LearnerEvidence.from_text("I built it")
    )
    assert advice.requirements[0].id == "1.1/required/1"
    assert advice.stretch_goals[0].id == "1.1/stretch/1"
    assert "PRIVATE" not in json.dumps(asdict(advice))


def test_malformed_context_refused():
    with pytest.raises(TutorError):
        LearnerEvidence("proof", "wrong digest")
    with pytest.raises(TutorError):
        NarrationContext("course", "1.1", "persona", [], "body")  # pyright: ignore[reportArgumentType]
    with pytest.raises(TutorError):
        LearnerEvidence.from_text("x" * 32_001)


@pytest.mark.parametrize("choices", [[Input.NEXT], ("next",), (Input.NEXT, Input.NEXT)])
def test_delivery_choices_require_typed_immutable_unique_values(choices):
    with pytest.raises(TutorError):
        NarrationContext("Course", "1.1", None, (), "body", legal_inputs=choices)


def test_optional_delivery_metadata_distinguishes_unknown_and_no_controls():
    context = NarrationContext("Course", "1.1", None, (), "body")
    assert context.legal_inputs is None
    assert replace(context, legal_inputs=()).legal_inputs == ()
    with pytest.raises(TutorError):
        replace(context, beat="exercise")  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("completed,total", [(-1, 2), (3, 2), (0, 0), (True, 2), (0, "2")])
def test_conversation_progress_bounds(completed, total):
    with pytest.raises(TutorError):
        ProgressContext(completed, total)


def test_conversation_snapshot_progress_copy_and_revision_scope():
    snapshot = SessionSnapshot(
        CourseView("course", "1", "Course"),
        "PRIVATE_LEARNER",
        PositionView(1, 1, "welcome", None),
        "current",
        BeatView(Beat.WELCOME, body="Current material"),
        (),
        1,
        2,
    )
    evidence = LearnerEvidence.from_text("Actual work")
    identities = (AdviceIdentity("required", "Explain"),)
    objective = ObjectiveAdviceContext(identities, evidence, "current")
    homework = HomeworkAdviceContext("Work", "Practice", identities, (), evidence, "current")
    context = ConversationContext.from_snapshot(snapshot, objectives=objective)
    context = replace(context, homework=homework, homework_revision="current")
    assert context.progress == ProgressContext(1, 2)
    assert context.teaching.persona is None and context.revision == "current"
    assert "PRIVATE" not in json.dumps(asdict(context))
    for field, advice in (("objectives", objective), ("homework", homework)):
        with pytest.raises(TutorError):
            replace(context, **{field: replace(advice, revision="stale")})
    with pytest.raises(TutorError):
        replace(context, revision=None)
    with pytest.raises(TutorError):
        replace(context, teaching=snapshot)  # pyright: ignore[reportArgumentType]
    with pytest.raises(TutorError):
        replace(context, progress=snapshot)  # pyright: ignore[reportArgumentType]


def test_conversation_real_homework_slot_revision_and_successor_refusal(tmp_path):
    from installed_child import ConversationJourney
    from pydantic_ai.models.function import FunctionModel

    from skilling.course import Course
    from skilling.session import FileSession
    from skilling_tutor import SkillingRunner

    course = Course.load(Path(__file__).resolve().parents[3] / "examples/workbench")
    session = FileSession.open(course, state_root=tmp_path / "state", learner_id="learner")
    for _ in range(4):
        for _ in range(30):
            snapshot = session.snapshot()
            if snapshot.beat.name.value == "complete":
                break
            given = {
                "gate-concept": "proceed",
                "gate-exercise": "attempted",
                "quiz": "answer-correct",
            }.get(snapshot.beat.name.value, "next")
            session.advance(given)
        else:
            raise AssertionError("Synthetic controller did not reach completion")
        session.complete(session.snapshot().revision)
    snapshot = session.snapshot()
    checked = session.homework_check()
    assert checked.active is not None and checked.active.queued
    assert checked.revision is not None and checked.revision != snapshot.revision
    evidence = LearnerEvidence.from_text("Actual synthetic learner work")
    homework = HomeworkAdviceContext.from_check(checked, evidence=evidence)
    context = ConversationContext.from_snapshot(snapshot, homework=homework, homework_check=checked)
    assert context.revision == snapshot.revision and context.homework_revision == checked.revision
    journey = ConversationJourney.create()
    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = asyncio.run(
        SkillingRunner.create(FunctionModel(journey.respond)).chat("Review my homework", context)
    )
    assert (
        result.output.homework is not None and result.output.homework.revision == checked.revision
    )
    assert before == {
        str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()
    }
    assert checked.submission_token is not None and checked.submission_token not in repr(
        journey.captures
    )
    with pytest.raises(TutorError):
        ConversationContext.from_snapshot(snapshot, homework=homework)
    with pytest.raises(TutorError):
        ConversationContext.from_snapshot(snapshot, homework=snapshot, homework_check=checked)  # pyright: ignore[reportArgumentType]
    with pytest.raises(TutorError):
        ConversationContext.from_snapshot(
            snapshot,
            homework=homework,
            homework_check=replace(checked, course=CourseView("other", "1", "Other")),
        )
    session.homework_submit(checked.submission_token)
    fresh_check = session.homework_check()
    assert fresh_check.active is not None and fresh_check.revision != checked.revision
    with pytest.raises(TutorError):
        ConversationContext.from_snapshot(
            session.snapshot(), homework=homework, homework_check=fresh_check
        )
    with pytest.raises(TutorError):
        replace(context, homework_revision=fresh_check.revision)
    successor = HomeworkAdviceContext.from_check(fresh_check, evidence=evidence)
    assert (
        ConversationContext.from_snapshot(
            session.snapshot(), homework=successor, homework_check=fresh_check
        ).homework
        == successor
    )
