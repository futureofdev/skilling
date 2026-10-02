"""File-only record/scratch transactions and lifetime keyed identities.

The runtime supplies both after-images. The journal validates and applies bytes, never
deriving teaching effects. All methods run under the file store's course lock.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import yaml

from ...course import Record
from .._io import _write_bytes_atomic as _write_bytes_atomic
from .._paths import checked_path
from .._protocol import Conflict, RecoveryRequired, StoreError
from ._actions import (
    AcknowledgementStatus,
    ActionBoundary,
    ActionIdentity,
    ActionOperation,
    ActionOrigin,
    ActionReceipt,
    ActionReservation,
    AdvanceBoundary,
    AnswerBoundary,
    CommittedAction,
    FeedbackAcknowledgement,
    FeedbackRef,
    OriginalOutcome,
    PendingFeedback,
    PendingReference,
    PreparedAction,
    Scratch,
    outcome_boundary,
    parse_receipt,
    receipt_digest,
)
from ._transition_types import (
    Boundary as Boundary,
)
from ._transition_types import (
    Committed,
)
from ._transition_types import (
    Identity as Identity,
)
from ._transition_types import (
    Prepared as Prepared,
)
from ._transition_types import (
    Receipt as Receipt,
)
from ._transition_types import (
    Reservation as Reservation,
)
from ._transition_types import (
    Stream as Stream,
)
from ._transition_types import (
    TransitionIdentity as TransitionIdentity,
)
from ._transition_types import (
    TransitionVerb as TransitionVerb,
)


@dataclass(frozen=True)
class RuntimeSnapshot:
    record: Record
    revision: str
    scratch: bytes
    feedback: PendingFeedback | None = None


@dataclass(frozen=True)
class TransitionCommit:
    identity: TransitionIdentity | ActionIdentity
    expected_record_revision: str
    expected_scratch: bytes
    record: Record
    scratch: bytes
    outcome: OriginalOutcome | None = None


@dataclass(frozen=True)
class TransitionResult:
    snapshot: RuntimeSnapshot
    replayed: bool
    outcome: OriginalOutcome | None = None


class IdempotencyKeyConflict(StoreError):
    """A lifetime key is already bound to a different input, or untrusted legacy input."""


def dump(value: object) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100).encode("utf-8")


def raw_key_digest(key: str) -> str:
    """Hash legacy UTF-8 bytes without tightening their existing nonempty-key contract."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def scratch_value(raw: bytes) -> Scratch:
    return Scratch.model_validate(yaml.safe_load(raw) if raw else {})


def record_value(raw: bytes, stream: Stream) -> Record:
    record = Record.model_validate(yaml.safe_load(raw))
    if (record.learner_id, record.course_id, record.course_version) != (
        stream.learner_id,
        stream.course_id,
        stream.course_version,
    ):
        raise ValueError("transition record stream mismatch")
    return record


def receipt_version(stream: Stream, version: Literal[1, 2] | None = None) -> Literal[1, 2]:
    return (
        version
        if version is not None
        else 2
        if isinstance(stream, (ActionBoundary, ActionReservation))
        else 1
    )


def receipt_name(stream: Stream, key: str, *, version: Literal[1, 2] | None = None) -> str:
    identity = [stream.learner_id, stream.course_id, stream.course_version, key]
    if receipt_version(stream, version) == 2:
        identity.insert(0, "skilling-action-v2")
    return hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest() + ".yaml"


def validate_commit(commit: TransitionCommit, root: Path) -> TransitionCommit:
    """Validate untrusted copies before a store method can create a lock/directory."""
    try:
        identity = identity_boundary(commit.identity)
        for name in ("record.yaml", "scratch.yaml", "transition.yaml", "transition-receipts"):
            checked_path(root, identity.course_id, name)
        if identity.key is not None:
            checked_path(
                root,
                identity.course_id,
                "transition-receipts",
                receipt_name(identity, identity.key),
            )
        record = record_value(dump(commit.record.model_dump(mode="json")), identity)
        if (
            not isinstance(commit.expected_record_revision, str)
            or not commit.expected_record_revision
        ):
            raise ValueError("transition requires an existing record revision")
        if not isinstance(commit.expected_scratch, bytes) or not isinstance(commit.scratch, bytes):
            raise ValueError("transition scratch must be bytes")
        scratch_value(commit.expected_scratch)
        scratch_value(commit.scratch)
        return TransitionCommit(
            identity.value(),
            commit.expected_record_revision,
            commit.expected_scratch,
            record,
            commit.scratch,
            validate_outcome(identity, commit.outcome),
        )
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise RecoveryRequired(f"Invalid transition input: {exc}") from exc


class TransitionJournal:
    def __init__(self, root: Path, course_id: str) -> None:
        self.root, self.course_id = root, course_id

    def path(self, *parts: str) -> Path:
        return checked_path(self.root, self.course_id, *parts)

    def raw(self, *parts: str) -> bytes | None:
        path = self.path(*parts)
        if path.exists() and not path.is_file():
            raise ValueError("transition target must be a regular file")
        return path.read_bytes() if path.is_file() else None

    def snapshot(self, learner: str) -> RuntimeSnapshot | None:
        raw = self.raw("record.yaml")
        if raw is None:
            return None
        record = Record.model_validate(yaml.safe_load(raw))
        if record.course_id != self.course_id or record.learner_id != learner:
            raise ValueError("runtime snapshot stream mismatch")
        scratch = self.raw("scratch.yaml") or b""
        residual = scratch_value(scratch)
        if residual.presented_feedback is not None:
            self.resolve_feedback(record, residual.presented_feedback, revision(raw), pending=False)
        return RuntimeSnapshot(
            record, revision(raw), scratch, self.feedback(record, scratch, revision(raw))
        )

    def load_receipt(
        self, stream: Stream, key: str, *, version: Literal[1, 2] | None = None
    ) -> Receipt | ActionReceipt | Reservation | ActionReservation | None:
        wire_version = receipt_version(stream, version)
        raw = self.raw("transition-receipts", receipt_name(stream, key, version=wire_version))
        if raw is None:
            return None
        value = parse_receipt(yaml.safe_load(raw))
        if value.version != wire_version:
            raise ValueError("transition receipt wire namespace mismatch")
        identity = value if isinstance(value, (Reservation, ActionReservation)) else value.identity
        if (identity.learner_id, identity.course_id, identity.course_version, identity.key) != (
            stream.learner_id,
            stream.course_id,
            stream.course_version,
            key,
        ):
            raise ValueError("transition receipt stream/key mismatch")
        return value

    def refuse_other_key_namespace(
        self, identity: Identity | ActionBoundary, scratch: bytes
    ) -> None:
        """Both compatibility forms claim one event under the same course lock."""
        if identity.key is None:
            return
        if isinstance(identity, Identity):
            if self.load_receipt(identity, raw_key_digest(identity.key), version=2) is not None:
                raise IdempotencyKeyConflict("Key belongs to a trusted action or reservation")
            return
        legacy = self.legacy_reservation(scratch)
        if legacy is not None and raw_key_digest(legacy.key) == identity.key:
            raise IdempotencyKeyConflict("Legacy scratch already consumed this action key")
        directory = self.path("transition-receipts")
        if not directory.is_dir():
            return
        for child in sorted(directory.iterdir()):
            raw = self.raw("transition-receipts", child.name)
            assert raw is not None
            found = parse_receipt(yaml.safe_load(raw))
            owner = found if isinstance(found, (Reservation, ActionReservation)) else found.identity
            if owner.key is None or child.name != receipt_name(owner, owner.key):
                raise ValueError("transition receipt name does not match its identity")
            if found.version == 1 and (
                owner.learner_id,
                owner.course_id,
                owner.course_version,
                raw_key_digest(owner.key),
            ) == (identity.learner_id, identity.course_id, identity.course_version, identity.key):
                raise IdempotencyKeyConflict(
                    "Compatibility receipt already consumed this action key"
                )

    def feedback(self, record: Record, raw: bytes, rev: str) -> PendingFeedback | None:
        pointer = scratch_value(raw).pending_feedback
        if pointer is None:
            return None
        return self.resolve_feedback(record, pointer, rev, pending=True)

    def resolve_feedback(
        self,
        record: Record,
        pointer: PendingReference,
        rev: str,
        *,
        pending: bool,
        inline: ActionReceipt | None = None,
    ) -> PendingFeedback:
        if pending and pointer.origin_course_version != record.course_version:
            raise ValueError("pending feedback origin does not match record version")
        stream = Stream(
            learner_id=record.learner_id,
            course_id=record.course_id,
            course_version=pointer.origin_course_version,
        )
        inline_matches = inline is not None and (
            inline.identity.learner_id,
            inline.identity.course_id,
            inline.identity.course_version,
            inline.identity.key,
        ) == (
            record.learner_id,
            record.course_id,
            pointer.origin_course_version,
            pointer.answer_key,
        )
        receipt = (
            inline if inline_matches else self.load_receipt(stream, pointer.answer_key, version=2)
        )
        if not isinstance(receipt, ActionReceipt) or not isinstance(
            receipt.outcome, AnswerBoundary
        ):
            raise ValueError("pending feedback requires an immutable answer outcome")
        if pending and receipt.identity.coordinate != record.position.coordinate:
            raise ValueError("pending feedback coordinate mismatch")
        raw_receipt = self.raw(
            "transition-receipts", receipt_name(stream, pointer.answer_key, version=2)
        )
        if raw_receipt is None and inline_matches and inline is not None:
            raw_receipt = dump(inline.model_dump())
        if raw_receipt is None:
            raise ValueError("feedback requires its immutable outcome bytes")
        if hashlib.sha256(raw_receipt).hexdigest() != pointer.receipt_digest:
            raise ValueError("pending feedback outcome bytes changed")
        ref = FeedbackRef(
            record.learner_id,
            record.course_id,
            pointer.origin_course_version,
            pointer.answer_key,
            hashlib.sha256(raw_receipt).hexdigest(),
        )
        return PendingFeedback(ref, receipt.outcome.value(), rev)

    def action_result(self, identity: ActionIdentity) -> TransitionResult | None:
        boundary = identity_boundary(identity)
        current = self.snapshot(identity.learner_id)
        if current is None:
            return None
        raw_key = identity.key
        assert raw_key is not None
        found = self.load_receipt(boundary, raw_key)
        if isinstance(found, (Reservation, ActionReservation)):
            raise IdempotencyKeyConflict("Consumed key is reserved; use a fresh key")
        if found is None:
            return None
        if not isinstance(found, ActionReceipt) or found.identity != boundary:
            raise IdempotencyKeyConflict(
                "Key already belongs to a different complete action identity"
            )
        record_value(dump(current.record.model_dump(mode="json")), boundary)
        return TransitionResult(current, True, found.outcome.value())

    def identity(self, learner: str, key: str) -> TransitionIdentity | None:
        snapshot = self.snapshot(learner)
        if snapshot is None:
            return None
        stream = Stream(
            learner_id=snapshot.record.learner_id,
            course_id=snapshot.record.course_id,
            course_version=snapshot.record.course_version,
        )
        legacy = self.legacy_reservation(snapshot.scratch)
        if legacy is not None and legacy.key == key:
            raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
        hashed = self.load_receipt(stream, raw_key_digest(key), version=2)
        if hashed is not None:
            raise IdempotencyKeyConflict("Key belongs to a trusted action or consumed reservation")
        found = self.load_receipt(stream, key)
        if isinstance(found, (Reservation, ActionReservation, ActionReceipt)):
            raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
        return found.identity.value() if found is not None else None

    def inspect(self) -> Prepared | PreparedAction | Committed | CommittedAction | None:
        raw = self.raw("transition.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw)
        if isinstance(data, dict) and data.get("version") == 2:
            value = (
                PreparedAction.model_validate(data)
                if data.get("kind") == "prepared"
                else CommittedAction.model_validate(data)
            )
        else:
            value = (
                Prepared.model_validate(data)
                if isinstance(data, dict) and data.get("kind") == "prepared"
                else Committed.model_validate(data)
            )
        if value.identity.course_id != self.course_id:
            raise ValueError("transition intent course mismatch")
        if isinstance(value, (Prepared, PreparedAction)):
            self.preflight(value)
        else:
            raw_record = self.raw("record.yaml")
            if raw_record is None:
                raise ValueError("committed transition has no record stream")
            record = record_value(raw_record, value.identity)
            if isinstance(value, CommittedAction) and value.identity.key is not None:
                receipt = self.load_receipt(value.identity, value.identity.key)
                if not isinstance(receipt, ActionReceipt) or receipt.identity != value.identity:
                    raise ValueError("committed action requires its immutable original outcome")
            scratch = self.raw("scratch.yaml") or b""
            self.feedback(record, scratch, revision(raw_record))
            presented = scratch_value(scratch).presented_feedback
            if presented is not None:
                self.resolve_feedback(record, presented, revision(raw_record), pending=False)
        return value

    def preflight(self, value: Prepared | PreparedAction) -> None:
        identity = value.identity
        before = record_value(value.record_before, identity)
        after = record_value(value.record_after, identity)
        if before.position.coordinate != identity.coordinate:
            raise ValueError("transition before coordinate mismatch")
        self.refuse_other_key_namespace(identity, value.scratch_before or b"")
        before_scratch = scratch_value(value.scratch_before or b"")
        after_scratch = scratch_value(value.scratch_after)
        if isinstance(value, PreparedAction):
            identity = value.identity
            if identity.expected_revision != revision(value.record_before):
                raise ValueError("action revision does not bind its before-image")
            if identity.verb == "feedback-acknowledgement":
                pending = self.feedback(
                    before, value.scratch_before or b"", revision(value.record_before)
                )
                if pending is None or pending.feedback_id._receipt_digest != identity.input:
                    raise ValueError("acknowledgement does not bind pending receipt")
                if (
                    value.record_before != value.record_after
                    or after_scratch
                    != before_scratch.model_copy(
                        update={
                            "pending_feedback": None,
                            "presented_feedback": before_scratch.pending_feedback,
                        }
                    )
                ):
                    raise ValueError("acknowledgement may only clear matching feedback")
            else:
                if before_scratch.pending_feedback is not None:
                    raise ValueError("new action cannot bypass pending feedback")
                if value.receipt is None or value.receipt.identity != identity:
                    raise ValueError("keyed action requires matching original outcome")
                if isinstance(value.receipt.outcome, AdvanceBoundary):
                    if value.receipt.outcome.position.model_dump() != after.position.model_dump():
                        raise ValueError("original advance position does not match after-image")
                    if after_scratch.pending_feedback is not None:
                        raise ValueError("advance cannot invent feedback")
                elif identity.key is None or after_scratch.pending_feedback != PendingReference(
                    version=1,
                    origin_course_version=identity.course_version,
                    answer_key=identity.key,
                    receipt_digest=receipt_digest(value.receipt),
                ):
                    raise ValueError("answer after-image must retain its outcome pointer")
        legacy = self.legacy_reservation(value.scratch_before or b"")
        if legacy is not None and identity.key == legacy.key:
            raise ValueError("transition cannot rebind a legacy key")
        if self.raw("record.yaml") not in (value.record_before, value.record_after):
            raise ValueError("unexpected transition record bytes")
        if self.raw("scratch.yaml") not in (value.scratch_before, value.scratch_after):
            raise ValueError("unexpected transition scratch bytes")
        if identity.key is None:
            if value.receipt is not None or value.receipt_path is not None:
                raise ValueError("unkeyed transition cannot publish a receipt")
        else:
            expected = "transition-receipts/" + receipt_name(identity, identity.key)
            expected_receipt = value.receipt
            if isinstance(value, Prepared):
                expected_receipt = Receipt(version=1, kind="receipt", identity=value.identity)
            if value.receipt_path != expected or value.receipt != expected_receipt:
                raise ValueError("transition receipt descriptor mismatch")
            existing = self.load_receipt(identity, identity.key)
            if existing is not None and existing != value.receipt:
                raise ValueError("transition receipt already holds different bytes")
            if (
                isinstance(value, PreparedAction)
                and existing is not None
                and self.raw("transition-receipts", receipt_name(identity, identity.key))
                != dump(value.receipt.model_dump() if value.receipt else None)
            ):
                raise ValueError("transition outcome receipt bytes differ from prepared intent")
        # Validate both images before any write, including references a legacy step clears.
        # Only the after-image may reference its not-yet-published immutable answer receipt.
        for record, scratch, raw_record, inline in (
            (before, before_scratch, value.record_before, None),
            (
                after,
                after_scratch,
                value.record_after,
                value.receipt if isinstance(value, PreparedAction) else None,
            ),
        ):
            for pointer, pending in (
                (scratch.pending_feedback, True),
                (scratch.presented_feedback, False),
            ):
                if pointer is not None:
                    self.resolve_feedback(
                        record, pointer, revision(raw_record), pending=pending, inline=inline
                    )

    def publish(self, value: Prepared | PreparedAction | Committed | CommittedAction) -> None:
        _write_bytes_atomic(self.path("transition.yaml"), dump(value.model_dump()))

    def apply(self, value: Prepared | PreparedAction) -> None:
        self.reserve_legacy(value.scratch_before or b"")
        for name, raw in (
            ("record.yaml", value.record_after),
            ("scratch.yaml", value.scratch_after),
        ):
            if self.raw(name) != raw:
                _write_bytes_atomic(self.path(name), raw)
        if value.receipt is not None:
            key = value.identity.key
            assert key is not None
            if self.load_receipt(value.identity, key) is None:
                _write_bytes_atomic(
                    self.path("transition-receipts", receipt_name(value.identity, key)),
                    dump(value.receipt.model_dump()),
                )
        marker = (
            CommittedAction(version=2, kind="committed", identity=value.identity)
            if isinstance(value, PreparedAction)
            else Committed(version=1, kind="committed", identity=value.identity)
        )
        self.publish(marker)

    def legacy_reservation(self, raw: bytes) -> Reservation | None:
        data = yaml.safe_load(raw) if raw else None
        if not isinstance(data, dict) or data.get("last_key") is None:
            return None
        record_raw = self.raw("record.yaml")
        if record_raw is None:
            raise ValueError("legacy key has no record stream")
        record = Record.model_validate(yaml.safe_load(record_raw))
        reserved = Reservation(
            version=1,
            kind="reserved",
            learner_id=record.learner_id,
            course_id=record.course_id,
            course_version=record.course_version,
            key=data["last_key"],
        )
        if reserved.course_id != self.course_id:
            raise ValueError("legacy key stream mismatch")
        self.load_receipt(reserved, reserved.key)
        return reserved

    def reserve_legacy(self, raw: bytes) -> None:
        """Retain a legacy key only after validated durable intent exists."""
        reserved = self.legacy_reservation(raw)
        if reserved is not None and self.load_receipt(reserved, reserved.key) is None:
            _write_bytes_atomic(
                self.path("transition-receipts", receipt_name(reserved, reserved.key)),
                dump(reserved.model_dump()),
            )

    def acknowledge(self, ref: FeedbackRef, expected_revision: str) -> FeedbackAcknowledgement:
        current = self.snapshot(ref._learner_id)
        if current is None:
            return FeedbackAcknowledgement(AcknowledgementStatus.NO_PENDING, None)
        if current.record.course_version != ref._course_version:
            raise Conflict("feedback origin", ref._course_version, current.record.course_version)
        if current.revision != expected_revision:
            raise Conflict("record.yaml", expected_revision, current.revision)
        pending = current.feedback
        if pending is None:
            presented = scratch_value(current.scratch).presented_feedback
            stream = Stream(
                learner_id=ref._learner_id,
                course_id=ref._course_id,
                course_version=ref._course_version,
            )
            raw = self.raw("transition-receipts", receipt_name(stream, ref._answer_key, version=2))
            receipt = self.load_receipt(stream, ref._answer_key, version=2)
            if (
                not isinstance(receipt, ActionReceipt)
                or not isinstance(receipt.outcome, AnswerBoundary)
                or raw is None
                or hashlib.sha256(raw).hexdigest() != ref._receipt_digest
            ):
                raise Conflict("feedback", ref._receipt_digest, None)
            if presented is None:
                return FeedbackAcknowledgement(AcknowledgementStatus.NO_PENDING, current.revision)
            if (
                (presented.origin_course_version, presented.answer_key)
                != (ref._course_version, ref._answer_key)
                or raw is None
                or hashlib.sha256(raw).hexdigest() != ref._receipt_digest
            ):
                raise Conflict("feedback", ref._receipt_digest, None)
            return FeedbackAcknowledgement(
                AcknowledgementStatus.ALREADY_PRESENTED, current.revision
            )
        if pending.feedback_id != ref:
            raise Conflict("feedback", ref._receipt_digest, pending.feedback_id._receipt_digest)
        data = yaml.safe_load(current.scratch)
        data["presented_feedback"] = data["pending_feedback"]
        data["pending_feedback"] = None
        identity = ActionIdentity(
            ref._learner_id,
            ref._course_id,
            ref._course_version,
            current.record.position.coordinate,
            ActionOperation.ACKNOWLEDGE,
            ref._receipt_digest,
            None,
            ActionOrigin.PRESENTATION,
            expected_revision,
            pending.outcome.question_number,
        )
        self.commit(
            TransitionCommit(
                identity, expected_revision, current.scratch, current.record, dump(data)
            )
        )
        return FeedbackAcknowledgement(AcknowledgementStatus.PRESENTED, current.revision)

    def commit(self, commit: TransitionCommit) -> TransitionResult:
        identity = identity_boundary(commit.identity)
        current = self.snapshot(identity.learner_id)
        if current is None:
            raise Conflict("record.yaml", commit.expected_record_revision, None)
        self.refuse_other_key_namespace(identity, current.scratch)
        if isinstance(identity, ActionBoundary) and identity.key is not None:
            replay = self.action_result(identity.value())
            if replay is not None:
                return replay
        if identity.key is not None:
            legacy = self.legacy_reservation(current.scratch)
            if legacy is not None and legacy.key == identity.key:
                raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
            found = self.load_receipt(identity, identity.key)
            if isinstance(found, (Reservation, ActionReservation)):
                raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
            if found is not None:
                if isinstance(identity, ActionBoundary) or isinstance(found, ActionReceipt):
                    raise IdempotencyKeyConflict(
                        "Key already belongs to a different action identity"
                    )
                if (found.identity.verb, found.identity.input) != (identity.verb, identity.input):
                    raise IdempotencyKeyConflict(
                        "Key already belongs to a different transition input"
                    )
                record_value(dump(current.record.model_dump(mode="json")), identity)
                return TransitionResult(current, True)
        if current.revision != commit.expected_record_revision:
            raise Conflict("record.yaml", commit.expected_record_revision, current.revision)
        if current.scratch != commit.expected_scratch:
            raise Conflict(
                "scratch.yaml", revision(commit.expected_scratch), revision(current.scratch)
            )
        before = self.raw("record.yaml")
        assert before is not None
        receipt = (
            ActionReceipt(
                version=2,
                kind="receipt",
                identity=identity,
                outcome=outcome_boundary(commit.outcome),
            )
            if isinstance(identity, ActionBoundary) and commit.outcome is not None
            else Receipt(version=1, kind="receipt", identity=identity)
            if isinstance(identity, Identity) and identity.key is not None
            else None
        )
        record_after = dump(commit.record.model_dump(mode="json"))
        if isinstance(identity, ActionBoundary) and identity.verb == "feedback-acknowledgement":
            if commit.record.model_dump() != current.record.model_dump():
                raise ValueError("acknowledgement cannot change learner record")
            record_after = before
        data = {
            "version": 2 if isinstance(identity, ActionBoundary) else 1,
            "kind": "prepared",
            "identity": identity.model_dump(),
            "record_before": before,
            "record_after": record_after,
            "scratch_before": self.raw("scratch.yaml"),
            "scratch_after": commit.scratch,
            "receipt_path": "transition-receipts/" + receipt_name(identity, identity.key)
            if identity.key is not None
            else None,
            "receipt": receipt.model_dump() if receipt else None,
        }
        value = (
            PreparedAction.model_validate(data)
            if isinstance(identity, ActionBoundary)
            else Prepared.model_validate(data)
        )
        self.preflight(value)
        self.publish(value)
        self.apply(value)
        snapshot = self.snapshot(identity.learner_id)
        assert snapshot is not None
        return TransitionResult(snapshot, False, commit.outcome)


def identity_boundary(identity: TransitionIdentity | ActionIdentity) -> Identity | ActionBoundary:
    return (
        ActionBoundary.model_validate(asdict(identity))
        if isinstance(identity, ActionIdentity)
        else Identity.model_validate(asdict(identity))
    )


def validate_outcome(
    identity: Identity | ActionBoundary, outcome: OriginalOutcome | None
) -> OriginalOutcome | None:
    if isinstance(identity, ActionBoundary) and identity.key is not None:
        if outcome is None:
            raise ValueError("keyed action requires original outcome")
        return ActionReceipt(
            version=2, kind="receipt", identity=identity, outcome=outcome_boundary(outcome)
        ).outcome.value()
    if outcome is not None:
        raise ValueError("unkeyed transition cannot invent a keyed outcome")
    return None
