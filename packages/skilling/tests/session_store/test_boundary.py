"""Neutral values preserve opaque revisions and refuse corrupt replay state."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from skilling.course import Course, Record
from skilling.store import ActionIdentity, ActionOperation, ActionOrigin, QuizAnswerOutcome
from skilling.store._journal._actions import ActionBoundary, pending_pointer
from skilling.store._protocol import (
    RecoveryRequired,
    SessionActionReceipt,
    SessionDeleted,
    SessionRead,
    SessionReadKind,
    SessionScope,
    SessionState,
    neutral_action_identity,
    neutral_pending_pointer,
    pending_feedback,
    replay_action,
    validate_read,
    validate_scratch,
)


def action(revision: str = "opaque:7") -> ActionIdentity:
    return ActionIdentity(
        "learner",
        "test",
        "1.0.0",
        "1.1",
        ActionOperation.ANSWER,
        "b",
        "a" * 64,
        ActionOrigin.LEARNER,
        revision,
        1,
    )


def outcome() -> QuizAnswerOutcome:
    return QuizAnswerOutcome(1, "b", False, "Review the concept", True, ("understand",))


def test_neutral_revision_is_opaque_without_loosening_file_boundary() -> None:
    identity = action()
    assert neutral_action_identity(identity) == identity
    with pytest.raises(ValidationError):
        ActionBoundary.model_validate(asdict(identity))
    with pytest.raises(RecoveryRequired):
        neutral_action_identity(replace(identity, expected_revision=""))


def test_feedback_digest_remains_file_compatible() -> None:
    identity = action("1" * 16)
    assert neutral_pending_pointer(identity, outcome()) == pending_pointer(identity, outcome())


def test_complete_state_rejects_orphan_and_changed_feedback(clean_dir: Path) -> None:
    record = Record.new(Course.load(clean_dir), "learner")
    scope = SessionScope("producer", "learner", record.course_id)
    identity = replace(
        action(),
        course_id=record.course_id,
        course_version=record.course_version,
        coordinate=record.position.coordinate,
    )
    pointer = neutral_pending_pointer(identity, outcome())
    scratch = yaml.safe_dump({"pending_feedback": asdict(pointer)}).encode()
    state = SessionState(record, "opaque:7", scratch)
    read = SessionRead(SessionReadKind.LIVE, scope, "aggregate:8", state)
    with pytest.raises(RecoveryRequired, match="receipt"):
        validate_read(read)
    state = replace(state, action_receipts=(SessionActionReceipt(identity, outcome()),))
    read = replace(read, state=state)
    assert validate_read(read) == read
    for changed_record in (
        record.model_copy(update={"course_version": "9.9.9"}),
        record.model_copy(update={"position": record.position.model_copy(update={"lesson": 2})}),
    ):
        with pytest.raises(RecoveryRequired, match="current record"):
            validate_read(replace(read, state=replace(state, record=changed_record)))
    feedback = pending_feedback(read)
    assert feedback is not None and feedback.outcome == outcome()
    changed = replace(outcome(), reason="forged")
    with pytest.raises(RecoveryRequired, match="differs"):
        validate_read(
            replace(
                read,
                state=replace(state, action_receipts=(SessionActionReceipt(identity, changed),)),
            )
        )


def test_deleted_and_cross_scope_reads_refuse_before_replay() -> None:
    scope = SessionScope("producer", "learner", "test")
    deleted = SessionRead(SessionReadKind.DELETED, scope, "deleted:1")
    assert validate_read(deleted) == deleted
    with pytest.raises(SessionDeleted):
        replay_action(deleted, action())
    with pytest.raises(RecoveryRequired, match="scope"):
        validate_read(deleted, replace(scope, namespace="other"))


@pytest.mark.parametrize(
    "raw", [b"wrong_count: true", b"unknown: 1", b"- list", b"wrong_count: -1"]
)
def test_scratch_is_strict_before_effects(raw: bytes) -> None:
    with pytest.raises(RecoveryRequired):
        validate_scratch(raw)


def test_legacy_raw_event_key_stays_reserved_for_neutral_actions(clean_dir: Path) -> None:
    from skilling.store import (
        IdempotencyKeyConflict,
        LegacyOutcomeUnavailable,
        TransitionIdentity,
        TransitionVerb,
        key_digest,
    )

    record = Record.new(Course.load(clean_dir), "learner")
    scope = SessionScope("producer", "learner", record.course_id)
    legacy = TransitionIdentity(
        "learner",
        record.course_id,
        record.course_version,
        "1.1",
        TransitionVerb.ADVANCE,
        "next",
        "original-event",
    )
    state = SessionState(
        record,
        "opaque:7",
        action_receipts=(SessionActionReceipt(legacy, LegacyOutcomeUnavailable()),),
    )
    read = SessionRead(SessionReadKind.LIVE, scope, "aggregate:8", state)
    candidate = replace(
        action(),
        course_id=record.course_id,
        course_version=record.course_version,
        key=key_digest("original-event"),
    )
    with pytest.raises(IdempotencyKeyConflict):
        replay_action(read, candidate)


def test_source_binding_requires_a_real_digest() -> None:
    from skilling.store._protocol import BindSourceSession, validate_command

    scope = SessionScope("producer", "learner", "test")
    command = BindSourceSession(scope, "aggregate:7", "a" * 64)
    assert validate_command(command) == command
    with pytest.raises(RecoveryRequired, match="digest"):
        validate_command(replace(command, source_digest="not-a-digest"))
