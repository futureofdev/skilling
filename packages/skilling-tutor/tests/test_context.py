import json
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime

import pytest

from skilling.delivery import Beat
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
from skilling_tutor import HomeworkAdviceContext, LearnerEvidence, NarrationContext, TutorError


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
