"""Controller custody across real restart, feedback acknowledgement and legacy writes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from skilling.session import (
    ActionOperation,
    FileSession,
    QuizAnswerOutcome,
    Session,
    SessionRefusal,
    load_course,
)
from skilling.store import (
    Conflict,
    FileSessionStore,
    SessionScope,
    StoreError,
)

from .conftest import StoreFactory


def open_session(
    course: Path, work: Path, store_factory: StoreFactory, namespace: str = "producer"
) -> Session:
    work.mkdir(exist_ok=True)
    scope = SessionScope(namespace, "local", load_course(course).id)
    return Session.open(course, store=store_factory(scope), scope=scope, work_root=work)


def advance(session: Session, key: str) -> None:
    snapshot = session.snapshot()
    payload = {"gate-concept": "proceed", "gate-exercise": "attempted"}.get(
        snapshot.beat.name, "next"
    )
    session.act(
        session.capture_action(
            snapshot, event_id=key, operation=ActionOperation.ADVANCE, payload=payload
        )
    )


def at_quiz(session: Session) -> None:
    for index in range(20):
        if session.snapshot().beat.name == "quiz":
            return
        advance(session, f"step-{index}")
    raise AssertionError("Course did not reach a quiz")


def test_c02_exact_retry_after_intervening_action_and_restart(
    clean_dir: Path, tmp_path: Path, store_factory: StoreFactory
) -> None:
    session = open_session(clean_dir, tmp_path / "work", store_factory)
    action = session.capture_action(
        session.snapshot(), event_id="first", operation=ActionOperation.ADVANCE, payload="next"
    )
    first = session.act(action)
    advance(session, "second")
    reopened = open_session(clean_dir, tmp_path / "work", store_factory)
    current = reopened.snapshot()
    retry = reopened.act(action)
    assert retry.replayed and retry.original_outcome == first.original_outcome
    assert retry.snapshot == current and retry.snapshot.position != first.snapshot.position
    with pytest.raises((SessionRefusal, StoreError)):
        reopened.act(replace(action, identity=replace(action.identity, input="go-deeper")))
    assert reopened.snapshot() == current


def test_c03_wrong_answer_survives_history_loss_until_render_ack(
    clean_dir: Path, tmp_path: Path, store_factory: StoreFactory
) -> None:
    session = open_session(clean_dir, tmp_path / "work", store_factory)
    at_quiz(session)
    # The fixture's first answer is b; a is deliberately wrong.
    action = session.capture_action(
        session.snapshot(), event_id="wrong-once", operation=ActionOperation.ANSWER, payload="a"
    )
    result = session.act(action)
    assert isinstance(result.original_outcome, QuizAnswerOutcome)
    assert not result.original_outcome.correct and result.original_outcome.reason
    restarted = open_session(clean_dir, tmp_path / "work", store_factory)
    feedback = restarted.pending_feedback()
    assert feedback is not None and feedback.outcome == result.original_outcome
    snapshot = restarted.snapshot()
    assert snapshot.beat.question is None and snapshot.legal_inputs == ()
    for attempt in (
        restarted.question,
        restarted.homework_check,
        lambda: restarted.complete(snapshot),
    ):
        with pytest.raises(SessionRefusal) as refusal:
            attempt()
        assert refusal.value.code == "pending-feedback"
    assert restarted.act(action).original_outcome == result.original_outcome
    acknowledgement = restarted.acknowledge_feedback(feedback.feedback_id)
    assert acknowledgement.status == "presented"
    assert restarted.pending_feedback() is None
    assert restarted.snapshot().revision == snapshot.revision
    assert restarted.snapshot().session_revision != snapshot.session_revision
    with pytest.raises(Conflict):
        restarted.telemetry(True, snapshot=snapshot)


def test_c01_copied_action_and_feedback_handles_refuse_other_namespace(
    clean_dir: Path, tmp_path: Path, store_factory: StoreFactory
) -> None:
    first = open_session(clean_dir, tmp_path / "work-a", store_factory, "producer-a")
    second = open_session(clean_dir, tmp_path / "work-b", store_factory, "producer-b")
    first_action = first.capture_action(
        first.snapshot(), event_id="same-key", operation=ActionOperation.ADVANCE, payload="next"
    )
    before = second.snapshot()
    with pytest.raises(SessionRefusal, match="scope"):
        second.act(first_action)
    assert second.snapshot() == before
    at_quiz(first)
    answer = first.capture_action(
        first.snapshot(), event_id="answer", operation=ActionOperation.ANSWER, payload="a"
    )
    first.act(answer)
    pending = first.pending_feedback()
    assert pending is not None
    with pytest.raises(SessionRefusal, match="scope"):
        second.acknowledge_feedback(pending.feedback_id)
    assert second.snapshot() == before


def test_legacy_file_write_invalidates_neutral_snapshot(clean_dir: Path, tmp_path: Path) -> None:
    root, work = tmp_path / "state", tmp_path / "work"
    work.mkdir()
    scope = SessionScope("producer", "local", load_course(clean_dir).id)
    store = FileSessionStore.open(root, namespace="producer", learner_id="local")
    neutral = Session.open(clean_dir, store=store, scope=scope, work_root=work)
    action = neutral.capture_action(
        neutral.snapshot(), event_id="stale", operation=ActionOperation.ADVANCE, payload="next"
    )
    legacy = FileSession.open(load_course(clean_dir), state_root=root, learner_id="local")
    legacy.advance("next")
    before = neutral.snapshot()
    with pytest.raises((Conflict, SessionRefusal)):
        neutral.act(action)
    assert neutral.snapshot() == before
    advance(neutral, "fresh")
    assert legacy.snapshot().position == neutral.snapshot().position


def finish_lesson(session: Session, course_path: Path) -> None:
    from skilling.course import parse_lesson, parse_quiz

    for index in range(35):
        snapshot = session.snapshot()
        if snapshot.beat.name == "complete":
            return
        if snapshot.beat.name == "quiz":
            assert snapshot.beat.question is not None
            lesson = load_course(course_path).lesson_at(snapshot.position.coordinate)
            assert lesson is not None
            section = parse_lesson(lesson.path).section("quiz")
            assert section is not None
            question = next(
                q
                for q in parse_quiz(section.body, section.body_line)
                if q.number == snapshot.beat.question.number
            )
            assert question.answer_label is not None
            action = session.capture_action(
                snapshot,
                event_id=f"{snapshot.position.coordinate}-answer-{index}",
                operation=ActionOperation.ANSWER,
                payload=question.answer_label,
            )
            session.act(action)
            pending = session.pending_feedback()
            assert pending is not None
            session.acknowledge_feedback(pending.feedback_id)
        else:
            advance(session, f"{snapshot.position.coordinate}-finish-{index}")
    raise AssertionError("Synthetic fixture did not reach completion")


def test_complete_course_homework_and_original_receipts_survive_restart(
    clean_dir: Path, tmp_path: Path, store_factory: StoreFactory
) -> None:
    session = open_session(clean_dir, tmp_path / "work", store_factory)
    scope = SessionScope("producer", "local", session.course.id)
    for _ in range(2):
        finish_lesson(session, clean_dir)
        completed = session.complete(session.snapshot())
        assert not completed.already_completed
        assert session.complete(session.snapshot()).already_completed
        # The completed snapshot advances only after its next presentation/control.
        if session.snapshot().completed_count < 2:
            advance(session, "next-lesson")
    read = store_factory(scope).read(scope)
    assert read.state is not None
    assert len(read.state.log) == 2 and len(read.state.completion_receipts) == 2
    checked = session.homework_check()
    assert checked.submission is not None
    submitted = session.homework_submit(checked.submission)
    reopened = open_session(clean_dir, tmp_path / "work", store_factory)
    assert reopened.homework_submit(checked.submission) == submitted
    final = store_factory(scope).read(scope)
    assert final.state is not None
    assert len(final.state.archive) == 1 and len(final.state.submission_receipts) == 1
    assert final.state.homework is None


def test_pending_feedback_blocks_upgrade_then_consumed_key_stays_reserved(
    clean_dir: Path, tmp_path: Path, store_factory: StoreFactory
) -> None:
    session = open_session(clean_dir, tmp_path / "work", store_factory)
    at_quiz(session)
    action = session.capture_action(
        session.snapshot(), event_id="used-answer", operation=ActionOperation.ANSWER, payload="a"
    )
    session.act(action)
    pending = session.pending_feedback()
    assert pending is not None
    scope = SessionScope("producer", "local", session.course.id)
    store = store_factory(scope)
    before = store.read(scope)
    manifest = clean_dir / "course.yaml"
    manifest.write_text(manifest.read_text().replace('version: "1.0.0"', 'version: "1.0.1"'))
    refused = Session.upgrade_at(clean_dir, store=store, scope=scope)
    assert refused.plan is not None and not refused.plan.ok
    assert store.read(scope) == before
    Session.acknowledge_feedback_at(pending.feedback_id, store=store, scope=scope)
    upgraded = Session.upgrade_at(clean_dir, store=store, scope=scope)
    assert upgraded.plan is not None and upgraded.plan.ok
    reopened = open_session(clean_dir, tmp_path / "work", store_factory)
    assert reopened.course.version == "1.0.1"
    current = store.read(scope)
    assert current.state is not None and current.state.reservations
    with pytest.raises((SessionRefusal, StoreError)):
        reopened.act(action)
    assert store.read(scope) == current
