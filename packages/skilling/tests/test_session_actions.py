"""Synthetic controller receipts/feedback custody; no learner or teaching-quality claims."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import parse_lesson, parse_quiz
from skilling.delivery import UpgradeRefusal, complete_lesson, preview_upgrade, roll_forward
from skilling.session import (
    AcknowledgementStatus,
    ActionOperation,
    ActionOrigin,
    AdvanceOutcome,
    FileSession,
    LegacyOutcomeUnavailable,
    PresentationBeat,
    QuizAnswerOutcome,
    SessionRefusal,
    TrustedAction,
    load_course,
)
from skilling.store import Conflict, FileProgressStore, RecoveryRequired

from .conftest import REPO_ROOT
from .test_transition_recovery import bytes_at
from .test_version_roll_forward import patch_bump


def service(course: Path, state: Path, *, initialize: bool = True) -> FileSession:
    return FileSession.open(
        load_course(course), state_root=state, learner_id="local", initialize=initialize
    )


def at_quiz(session: FileSession) -> None:
    for _ in range(20):
        view = session.snapshot()
        if view.beat.name == "quiz":
            return
        given = {"gate-concept": "proceed", "gate-exercise": "attempted"}.get(
            view.beat.name, "next"
        )
        session.advance(given)
    raise AssertionError("fixture did not reach quiz")


def answer_action(
    session: FileSession, course: Path, key: str, *, correct: bool = True
) -> TrustedAction:
    view = session.snapshot()
    question = session.question()
    lesson = load_course(course).lesson_at(view.position.coordinate)
    assert lesson is not None
    quiz = parse_lesson(lesson.path).section("quiz")
    assert quiz is not None
    authored = next(q for q in parse_quiz(quiz.body, quiz.body_line) if q.number == question.number)
    label = (
        authored.answer_label
        if correct
        else next(o.label for o in authored.options if o.label != authored.answer_label)
    )
    assert label is not None
    return TrustedAction.create(
        view, event_id=key, operation=ActionOperation.ANSWER, payload=" " + label.upper() + " "
    )


def test_original_advance_outcome_and_complete_identity_replay(
    clean_dir: Path, tmp_path: Path
) -> None:
    session = service(clean_dir, tmp_path / "state")
    action = TrustedAction.create(
        session.snapshot(),
        event_id="secret-event",
        operation=ActionOperation.ADVANCE,
        payload="next",
    )
    first = session.act(action)
    assert isinstance(first.original_outcome, AdvanceOutcome)
    session.advance("next")
    replay = service(clean_dir, tmp_path / "state").act(action)
    assert replay.replayed and replay.original_outcome == first.original_outcome
    assert replay.snapshot.position != first.original_outcome.position
    assert replay.snapshot.beat.name == "concept"
    before = bytes_at(tmp_path / "state")
    for changed in (
        replace(action, payload="go-deeper"),
        replace(action, coordinate="9.9"),
        replace(action, expected_revision=replay.snapshot.revision or ""),
        replace(action, learner_id="other"),
        replace(action, question_number=1),
        replace(action, origin=ActionOrigin.PRESENTATION),
    ):
        with pytest.raises(SessionRefusal):
            session.act(changed)
        assert bytes_at(tmp_path / "state") == before
    assert all(b"secret-event" not in raw for raw in before.values())
    stale = TrustedAction.create(
        first.snapshot, event_id="new", operation=ActionOperation.ADVANCE, payload="next"
    )
    with pytest.raises(SessionRefusal) as error:
        session.act(stale)
    assert error.value.kind == "conflict"
    assert bytes_at(tmp_path / "state") == before


def test_q1_guard_restart_exact_reference_and_outcome_replay(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    action = answer_action(session, clean_dir, "answer-once")
    result = session.act(action)
    assert isinstance(result.original_outcome, QuizAnswerOutcome)
    assert result.snapshot.pending_feedback == result.original_outcome
    assert result.snapshot.beat.question is None and result.snapshot.legal_inputs == ()
    pending = FileSession.pending_feedback_at(
        state_root=state, learner_id="local", course_id=session.course.id
    )
    assert pending is not None and pending.outcome == result.original_outcome
    del session
    session = service(clean_dir, state)
    before = bytes_at(state)
    for attempt in (
        lambda: session.question(),
        lambda: session.answer("b"),
        lambda: session.advance("next"),
        lambda: session.complete(session.snapshot().revision),
        lambda: session.homework_check(),
    ):
        with pytest.raises(SessionRefusal) as error:
            attempt()
        assert error.value.code == "pending-feedback"
        assert bytes_at(state) == before
    assert session.act(action).original_outcome == pending.outcome
    assert bytes_at(state) == before
    with pytest.raises(SessionRefusal):
        session.act(
            replace(
                action, question_number=action.question_number + 1 if action.question_number else 2
            )
        )
    with pytest.raises(Conflict):
        session.acknowledge_feedback(
            replace(pending.feedback_id, _receipt_digest="0" * 64), pending.revision
        )
    with pytest.raises(Conflict):
        session.acknowledge_feedback(pending.feedback_id, "0" * 16)
    assert bytes_at(state) == before
    assert (
        session.acknowledge_feedback(pending.feedback_id, pending.revision).status
        is AcknowledgementStatus.PRESENTED
    )
    assert (
        session.acknowledge_feedback(pending.feedback_id, pending.revision).status
        is AcknowledgementStatus.ALREADY_PRESENTED
    )
    assert session.pending_feedback() is None
    assert session.question().number == 2
    before = bytes_at(state)
    second = TrustedAction.create(
        session.snapshot(),
        event_id=action.event_id,
        operation=ActionOperation.ANSWER,
        payload=action.payload,
    )
    with pytest.raises(SessionRefusal):
        session.act(second)
    assert bytes_at(state) == before
    assert session.act(action).original_outcome == result.original_outcome
    assert session.snapshot().pending_feedback is None


@pytest.mark.parametrize("correct", [True, False])
def test_feedback_keeps_authored_reason_and_remediation(
    clean_dir: Path, tmp_path: Path, correct: bool
) -> None:
    session = service(clean_dir, tmp_path / "state")
    at_quiz(session)
    result = session.act(answer_action(session, clean_dir, "answer", correct=correct))
    outcome = result.original_outcome
    assert isinstance(outcome, QuizAnswerOutcome) and outcome.correct is correct and outcome.reason
    pending = session.pending_feedback()
    assert pending is not None and pending.outcome == outcome
    assert result.snapshot.beat.question is None


def test_final_answer_render_failure_restart_ack_one_completion(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    for number in range(5):
        action = answer_action(session, clean_dir, "quiz-" + str(number))
        result = session.act(action)
        pending = session.pending_feedback()
        assert pending is not None
        if result.snapshot.position.beat == "complete":
            break
        session.acknowledge_feedback(pending.feedback_id, pending.revision)
    else:
        raise AssertionError("fixture has no final question")

    def renderer() -> None:
        raise RuntimeError("synthetic render cancellation after committed answer")

    with pytest.raises(RuntimeError):
        renderer()
    del session, action, pending
    session = service(clean_dir, state)
    recovered = session.pending_feedback()
    assert recovered is not None and recovered.outcome == result.original_outcome
    with pytest.raises(SessionRefusal):
        session.complete(session.snapshot().revision)
    before = bytes_at(state)
    session.acknowledge_feedback(recovered.feedback_id, recovered.revision)
    assert (state / "clean-course/record.yaml").read_bytes() == before["clean-course/record.yaml"]
    done = session.complete(session.snapshot().revision)
    assert session.complete(done.snapshot.revision).already_completed
    store = FileProgressStore(state)
    assert len(store.get_log("local", session.course.id)) == 1
    assert done.snapshot.completed_count == 1
    revision = done.snapshot.revision
    assert revision is not None
    before = bytes_at(state)
    assert (
        session.acknowledge_feedback(recovered.feedback_id, revision).status
        is AcknowledgementStatus.NO_PENDING
    )
    with pytest.raises(Conflict):
        session.acknowledge_feedback(
            replace(recovered.feedback_id, _receipt_digest="0" * 64), revision
        )
    assert bytes_at(state) == before


@pytest.mark.parametrize("damage", ["missing", "reason", "version", "question", "pointer"])
def test_corrupt_feedback_refuses_before_effects(
    clean_dir: Path, tmp_path: Path, damage: str
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    session.act(answer_action(session, clean_dir, "answer"))
    receipt = next((state / "clean-course/transition-receipts").glob("*.yaml"))
    if damage == "missing":
        receipt.unlink()
    elif damage == "pointer":
        scratch = state / "clean-course/scratch.yaml"
        data = yaml.safe_load(scratch.read_bytes())
        data["pending_feedback"]["origin_course_version"] = "8.0.0"
        scratch.write_text(yaml.safe_dump(data))
    else:
        data = yaml.safe_load(receipt.read_bytes())
        if damage == "reason":
            data["outcome"]["reason"] = "different valid string"
        if damage == "question":
            data["outcome"]["question_number"] = 99
        if damage == "version":
            data["version"] = 99
        receipt.write_text(yaml.safe_dump(data))
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired):
        FileSession.pending_feedback_at(
            state_root=state, learner_id="local", course_id=session.course.id
        )
    assert bytes_at(state) == before


def test_v1_outcome_unavailable_and_unkeyed_compatibility(clean_dir: Path, tmp_path: Path) -> None:
    session = service(clean_dir, tmp_path / "state")
    session.advance("next", event_id="v1")
    session.advance("next")
    replay = session.advance("next", event_id="v1")
    assert isinstance(replay.original_outcome, LegacyOutcomeUnavailable)
    assert replay.snapshot.beat.name == "concept"
    at_quiz(session)
    assert session.answer("b").reason
    assert session.pending_feedback() is None


@pytest.mark.parametrize("restart", [False, True])
def test_pending_feedback_blocks_upgrade_then_reserves_consumed_key(
    clean_dir: Path, tmp_path: Path, restart: bool
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    action = answer_action(session, clean_dir, "old-event")
    session.act(action)
    store = FileProgressStore(state)
    if restart:
        found = store.get_record("local", session.course.id)
        assert found is not None
        record, revision = found
        store.put_record(
            record.model_copy(
                update={"position": record.position.model_copy(update={"beat": "exercise"})}
            ),
            revision,
        )
    patch_bump(clean_dir)
    if restart:
        from . import fixtures as fx

        lesson = clean_dir / fx.LESSON_ONE_PATH
        text = lesson.read_text()
        start, end = text.index("## Hands-On Exercise"), text.index("## Quick Quiz")
        lesson.write_text(
            (text[:start] + text[end:]).replace(
                "  exercise: present\n",
                '  exercise:\n    status: none\n    intent: "Folded into concept."\n',
            )
        )
    newer = load_course(clean_dir)
    before = bytes_at(state)
    preview, refused = preview_upgrade(store, newer, "local"), roll_forward(store, newer, "local")
    assert preview.plan is not None and refused.plan is not None
    assert preview.plan.refusal is UpgradeRefusal.PENDING_FEEDBACK
    assert refused.plan.refusal is UpgradeRefusal.PENDING_FEEDBACK
    assert bytes_at(state) == before
    runner = CliRunner()
    check = runner.invoke(
        app,
        ["upgrade", "--course", str(clean_dir), "--state", str(state), "--check", "--json"],
        catch_exceptions=False,
    )
    assert (
        check.exit_code == 0
        and json.loads(check.stdout)["progress"]["reason"] == "pending-feedback"
    )
    apply = runner.invoke(
        app,
        ["upgrade", "--course", str(clean_dir), "--state", str(state), "--yes", "--json"],
        catch_exceptions=False,
    )
    assert apply.exit_code == 5 and json.loads(apply.stdout)["error"]["code"] == "version-mismatch"
    assert bytes_at(state) == before
    pending = FileSession.pending_feedback_at(
        state_root=state, learner_id="local", course_id=session.course.id
    )
    assert pending is not None
    FileSession.acknowledge_feedback_at(
        pending.feedback_id,
        pending.revision,
        state_root=state,
        learner_id="local",
        course_id=session.course.id,
    )
    upgraded = roll_forward(store, newer, "local")
    assert (
        upgraded.plan is not None and upgraded.plan.ok and upgraded.plan.lesson_restarted is restart
    )
    session = service(clean_dir, state)
    # Return to a legal welcome/teaching position if the patch retained Q2.
    view = session.snapshot()
    fresh = TrustedAction.create(
        view, event_id="old-event", operation=ActionOperation.ADVANCE, payload="next"
    )
    before = bytes_at(state)
    with pytest.raises(SessionRefusal):
        session.act(fresh)
    assert bytes_at(state) == before


def test_trusted_action_noninitializing_and_invalid_identity_create_no_state(
    clean_dir: Path, tmp_path: Path
) -> None:
    initialized = service(clean_dir, tmp_path / "original")
    captured = TrustedAction.create(
        initialized.snapshot(), event_id="event", operation=ActionOperation.ADVANCE, payload="next"
    )
    state = tmp_path / "absent"
    session = service(clean_dir, state, initialize=False)
    for action in (
        captured,
        replace(captured, event_id=" "),
        replace(captured, course_version="bad"),
        replace(captured, question_number=True),
        replace(captured, expected_revision="bad"),
    ):
        with pytest.raises(SessionRefusal):
            session.act(action)
        assert not state.exists()


def test_ordinary_presentation_origin_cannot_acknowledge_a_gate(
    clean_dir: Path, tmp_path: Path
) -> None:
    session = service(clean_dir, tmp_path / "state")
    for _ in range(3):
        view = session.snapshot()
        result = session.act(
            TrustedAction.create(
                view,
                event_id="render-" + view.beat.name,
                operation=ActionOperation.ADVANCE,
                payload="next",
                origin=ActionOrigin.PRESENTATION,
            )
        )
        assert isinstance(result.original_outcome, AdvanceOutcome)
    assert session.snapshot().beat.name == "gate-concept"
    before = bytes_at(tmp_path / "state")
    action = TrustedAction.create(
        session.snapshot(),
        event_id="gate",
        operation=ActionOperation.ADVANCE,
        payload="next",
        origin=ActionOrigin.PRESENTATION,
    )
    with pytest.raises(SessionRefusal) as error:
        session.act(action)
    assert error.value.code == "presentation-origin"
    assert bytes_at(tmp_path / "state") == before


def test_captured_submission_control_is_blocked_while_feedback_pending(
    clean_dir: Path, tmp_path: Path
) -> None:
    session = service(clean_dir, tmp_path / "state")
    for _ in range(2):
        at_quiz(session)
        while session.snapshot().beat.name == "quiz":
            session.answer(answer_action(session, clean_dir, "unused").payload)
        session.complete(session.snapshot().revision)
    checked = session.homework_check()
    assert checked.submission_token is not None
    at_quiz(session)
    session.act(answer_action(session, clean_dir, "pending"))
    before = bytes_at(tmp_path / "state")
    with pytest.raises(SessionRefusal) as error:
        session.homework_submit(checked.submission_token)
    assert error.value.code == "pending-feedback"
    assert bytes_at(tmp_path / "state") == before


def finish_quiz(session: FileSession, course: Path) -> None:
    at_quiz(session)
    while session.snapshot().beat.name == "quiz":
        session.answer(answer_action(session, course, "unkeyed-fixture").payload)


def test_historical_ceremony_keeps_successor_feedback_controls_hidden(tmp_path: Path) -> None:
    course = tmp_path / "course"
    shutil.copytree(REPO_ROOT / "examples/workbench", course)
    state = tmp_path / "state"
    session = service(course, state)
    for _ in range(2):
        finish_quiz(session, course)
        session.complete(session.snapshot().revision)
    assert session.snapshot().position.coordinate == "2.1"
    at_quiz(session)
    answer = session.act(answer_action(session, course, "successor-answer"))
    before = bytes_at(state)
    ceremony = session.ceremony("1.2")
    assert ceremony.coordinate == "1.2"
    assert ceremony.snapshot.position.coordinate == "2.1"
    assert ceremony.snapshot.pending_feedback == answer.original_outcome
    assert ceremony.snapshot.beat.name is PresentationBeat.PENDING_FEEDBACK
    assert ceremony.snapshot.beat.question is None and ceremony.snapshot.legal_inputs == ()
    assert bytes_at(state) == before


def test_completion_result_hides_interleaved_successor_feedback(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skilling.session import _companion

    state = tmp_path / "state"
    session = service(clean_dir, state)
    finish_quiz(session, clean_dir)
    original = complete_lesson
    answers: list[QuizAnswerOutcome] = []

    def interleave(*args, **kwargs):
        outcome = original(*args, **kwargs)
        successor = service(clean_dir, state)
        at_quiz(successor)
        answer = successor.act(answer_action(successor, clean_dir, "successor-answer"))
        assert isinstance(answer.original_outcome, QuizAnswerOutcome)
        answers.append(answer.original_outcome)
        return outcome

    monkeypatch.setattr(_companion, "complete_lesson", interleave)
    result = session.complete(session.snapshot().revision)
    assert result.already_completed is False and result.snapshot.completed_count == 1
    assert result.snapshot.pending_feedback == answers[0]
    assert result.snapshot.beat.name is PresentationBeat.PENDING_FEEDBACK
    assert result.snapshot.beat.question is None and result.snapshot.legal_inputs == ()
    assert result.snapshot.revision == service(clean_dir, state).snapshot().revision


@pytest.mark.parametrize("initialize", [True, False])
@pytest.mark.parametrize("reference", ["pending_feedback", "presented_feedback"])
def test_orphan_feedback_reference_refuses_before_initialization(
    clean_dir: Path, tmp_path: Path, initialize: bool, reference: str
) -> None:
    original = tmp_path / "original"
    session = service(clean_dir, original)
    at_quiz(session)
    session.act(answer_action(session, clean_dir, "answer"))
    data = yaml.safe_load((original / "clean-course/scratch.yaml").read_bytes())
    pointer = data.pop("pending_feedback")
    data[reference] = pointer
    state = tmp_path / "orphan"
    scratch = state / "clean-course/scratch.yaml"
    scratch.parent.mkdir(parents=True)
    scratch.write_text(yaml.safe_dump(data))
    before = bytes_at(state)
    with pytest.raises((RecoveryRequired, SessionRefusal)):
        service(clean_dir, state, initialize=initialize)
    assert bytes_at(state) == before
    assert not (scratch.parent / "record.yaml").exists()


@pytest.mark.parametrize(
    ("trusted_first", "claim_form"),
    [
        (True, "receipt"),
        (True, "reservation"),
        (True, "scratch"),
        (False, "receipt"),
        (False, "reservation"),
    ],
)
def test_cross_interface_roundtrip_cannot_rebind_event_key(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trusted_first: bool,
    claim_form: str,
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    for _ in range(3):
        session.advance("next")
    assert session.snapshot().beat.name == "gate-concept"
    captured = TrustedAction.create(
        session.snapshot(),
        event_id="shared-claim",
        operation=ActionOperation.ADVANCE,
        payload="proceed",
    )
    record = state / "clean-course/record.yaml"
    scratch = state / "clean-course/scratch.yaml"
    before_images = (record.read_bytes(), scratch.read_bytes())
    original = FileProgressStore.get_transition_identity
    injected = False
    after_claim: dict[str, bytes] = {}

    def interleave(store, learner, course_id, key):
        nonlocal injected
        result = original(store, learner, course_id, key)
        if not injected:
            injected = True
            assert result is None
            claimant = service(clean_dir, state)
            if trusted_first:
                claimant.advance("go-deeper", event_id=key)
            else:
                claimant.act(replace(captured, payload="go-deeper"))
            claimant.advance("next")
            assert (record.read_bytes(), scratch.read_bytes()) == before_images
            receipt = next((state / "clean-course/transition-receipts").glob("*.yaml"))
            if claim_form == "reservation":
                data = yaml.safe_load(receipt.read_bytes())
                owner = data["identity"]
                receipt.write_text(
                    yaml.safe_dump(
                        {
                            "version": data["version"],
                            "kind": "reserved",
                            **{
                                field: owner[field]
                                for field in ("learner_id", "course_id", "course_version", "key")
                            },
                        }
                    )
                )
                assert (record.read_bytes(), scratch.read_bytes()) == before_images
            elif claim_form == "scratch":
                receipt.unlink()
                data = yaml.safe_load(scratch.read_bytes())
                data["last_key"] = key
                scratch.write_text(yaml.safe_dump(data))
            after_claim.update(bytes_at(state))
        return result

    monkeypatch.setattr(FileProgressStore, "get_transition_identity", interleave)
    with pytest.raises(SessionRefusal) as error:
        if trusted_first:
            session.act(captured)
        else:
            session.advance("proceed", event_id="shared-claim")
    assert error.value.code == "idempotency-key-conflict"
    assert injected and bytes_at(state) == after_claim
    assert len(list((state / "clean-course/transition-receipts").glob("*.yaml"))) == (
        0 if claim_form == "scratch" else 1
    )


@pytest.mark.parametrize("legacy_form", ["receipt", "reservation", "scratch"])
@pytest.mark.parametrize("legacy_key", ["   ", "\t\n"])
def test_nonempty_legacy_whitespace_keys_keep_their_compatibility_contract(
    clean_dir: Path, tmp_path: Path, legacy_form: str, legacy_key: str
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    original = session.advance("next", event_id=legacy_key)
    assert not original.replayed
    before = bytes_at(state)
    replay = session.advance("next", event_id=legacy_key)
    assert replay.replayed and isinstance(replay.original_outcome, LegacyOutcomeUnavailable)
    assert bytes_at(state) == before
    receipt = next((state / "clean-course/transition-receipts").glob("*.yaml"))
    if legacy_form == "reservation":
        data = yaml.safe_load(receipt.read_bytes())
        owner = data["identity"]
        receipt.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "kind": "reserved",
                    **{
                        field: owner[field]
                        for field in ("learner_id", "course_id", "course_version", "key")
                    },
                }
            )
        )
    elif legacy_form == "scratch":
        receipt.unlink()
        scratch = state / "clean-course/scratch.yaml"
        data = yaml.safe_load(scratch.read_bytes())
        data["last_key"] = legacy_key
        scratch.write_text(yaml.safe_dump(data))
    action = TrustedAction.create(
        session.snapshot(),
        event_id="unrelated-trusted-event",
        operation=ActionOperation.ADVANCE,
        payload="next",
    )
    result = session.act(action)
    assert not result.replayed and isinstance(result.original_outcome, AdvanceOutcome)
    assert result.snapshot.beat.name == "concept"
    before = bytes_at(state)
    assert session.act(action).replayed
    assert bytes_at(state) == before
    if legacy_form != "receipt":
        with pytest.raises(SessionRefusal) as error:
            session.advance("next", event_id=legacy_key)
        assert error.value.code == "idempotency-key-conflict"
        assert bytes_at(state) == before
    with pytest.raises(ValueError):
        TrustedAction.create(
            session.snapshot(), event_id="   ", operation=ActionOperation.ADVANCE, payload="next"
        ).identity()
    assert bytes_at(state) == before
