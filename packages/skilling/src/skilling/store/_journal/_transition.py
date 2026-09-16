"""File-only record/scratch transactions and lifetime keyed identities.

The runtime supplies both after-images. The journal validates and applies bytes, never
deriving teaching effects. All methods run under the file store's course lock.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictBytes,
    StrictInt,
    field_validator,
    model_validator,
)

from ...course import Record, is_semver
from .._io import _write_bytes_atomic as _write_bytes_atomic
from .._paths import checked_path
from .._protocol import Conflict, RecoveryRequired, StoreError


@dataclass(frozen=True)
class RuntimeSnapshot:
    record: Record
    revision: str
    scratch: bytes


class TransitionVerb(StrEnum):
    ADVANCE = "advance"
    ANSWER = "answer"


@dataclass(frozen=True)
class TransitionIdentity:
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    verb: TransitionVerb
    input: str
    key: str | None


@dataclass(frozen=True)
class TransitionCommit:
    identity: TransitionIdentity
    expected_record_revision: str
    expected_scratch: bytes
    record: Record
    scratch: bytes


@dataclass(frozen=True)
class TransitionResult:
    snapshot: RuntimeSnapshot
    replayed: bool


class IdempotencyKeyConflict(StoreError):
    """A lifetime key is already bound to a different input, or untrusted legacy input."""


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("journal version must be an integer")
        return value


class Stream(Boundary):
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_version: str

    @field_validator("course_version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not is_semver(value):
            raise ValueError("invalid transition course version")
        return value


class Identity(Stream):
    coordinate: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    verb: Literal["advance", "answer"]
    input: str = Field(min_length=1)
    key: str | None = Field(min_length=1)

    @field_validator("input")
    @classmethod
    def valid_input(cls, value: str) -> str:
        if value not in {
            "next",
            "go-deeper",
            "proceed",
            "hint",
            "attempted",
            "answer-correct",
            "answer-wrong",
            "continue",
            "revisit-concept",
            "a",
            "b",
            "c",
            "d",
        }:
            raise ValueError("invalid transition input")
        return value

    @model_validator(mode="after")
    def valid_operation(self) -> Identity:
        if (self.verb == "answer") != (self.input in {"a", "b", "c", "d"}):
            raise ValueError("transition verb/input mismatch")
        if self.verb == "answer" and self.key is not None:
            raise ValueError("quiz answers are unkeyed")
        return self

    def value(self) -> TransitionIdentity:
        return TransitionIdentity(
            self.learner_id,
            self.course_id,
            self.course_version,
            self.coordinate,
            TransitionVerb(self.verb),
            self.input,
            self.key,
        )


class Scratch(Boundary):
    wrong_count: StrictInt = Field(default=0, ge=0)
    returning_to_quiz: StrictBool = False
    last_key: str | None = None
    last_result: dict[str, object] | None = None


class Reservation(Stream):
    version: Literal[1]
    kind: Literal["reserved"]
    key: str = Field(min_length=1)


class Receipt(Boundary):
    version: Literal[1]
    kind: Literal["receipt"]
    identity: Identity


class Prepared(Boundary):
    version: Literal[1]
    kind: Literal["prepared"]
    identity: Identity
    record_before: StrictBytes
    record_after: StrictBytes
    scratch_before: StrictBytes | None
    scratch_after: StrictBytes
    receipt_path: str | None
    receipt: Receipt | None


class Committed(Boundary):
    version: Literal[1]
    kind: Literal["committed"]
    identity: Identity


def dump(value: object) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100).encode("utf-8")


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


def receipt_name(stream: Stream, key: str) -> str:
    identity = [stream.learner_id, stream.course_id, stream.course_version, key]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode()).hexdigest() + ".yaml"


def validate_commit(commit: TransitionCommit, root: Path) -> TransitionCommit:
    """Validate untrusted copies before a store method can create a lock/directory."""
    try:
        identity = Identity.model_validate(asdict(commit.identity))
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
        scratch_value(scratch)
        return RuntimeSnapshot(record, revision(raw), scratch)

    def load_receipt(self, stream: Stream, key: str) -> Receipt | Reservation | None:
        raw = self.raw("transition-receipts", receipt_name(stream, key))
        if raw is None:
            return None
        data = yaml.safe_load(raw)
        value = (
            Reservation.model_validate(data)
            if isinstance(data, dict) and data.get("kind") == "reserved"
            else Receipt.model_validate(data)
        )
        identity = value if isinstance(value, Reservation) else value.identity
        if (identity.learner_id, identity.course_id, identity.course_version, identity.key) != (
            stream.learner_id,
            stream.course_id,
            stream.course_version,
            key,
        ):
            raise ValueError("transition receipt stream/key mismatch")
        return value

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
        found = self.load_receipt(stream, key)
        if isinstance(found, Reservation):
            raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
        return found.identity.value() if found is not None else None

    def inspect(self) -> Prepared | Committed | None:
        raw = self.raw("transition.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw)
        value = (
            Prepared.model_validate(data)
            if isinstance(data, dict) and data.get("kind") == "prepared"
            else Committed.model_validate(data)
        )
        if value.identity.course_id != self.course_id:
            raise ValueError("transition intent course mismatch")
        if isinstance(value, Prepared):
            self.preflight(value)
        else:
            raw_record = self.raw("record.yaml")
            if raw_record is None:
                raise ValueError("committed transition has no record stream")
            record_value(raw_record, value.identity)
        return value

    def preflight(self, value: Prepared) -> None:
        identity = value.identity
        before = record_value(value.record_before, identity)
        record_value(value.record_after, identity)
        if before.position.coordinate != identity.coordinate:
            raise ValueError("transition before coordinate mismatch")
        scratch_value(value.scratch_before or b"")
        scratch_value(value.scratch_after)
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
            if value.receipt_path != expected or value.receipt != Receipt(
                version=1, kind="receipt", identity=identity
            ):
                raise ValueError("transition receipt descriptor mismatch")
            existing = self.load_receipt(identity, identity.key)
            if existing is not None and existing != value.receipt:
                raise ValueError("transition receipt already holds different bytes")

    def publish(self, value: Prepared | Committed) -> None:
        _write_bytes_atomic(self.path("transition.yaml"), dump(value.model_dump()))

    def apply(self, value: Prepared) -> None:
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
        self.publish(Committed(version=1, kind="committed", identity=value.identity))

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

    def commit(self, commit: TransitionCommit) -> TransitionResult:
        identity = Identity.model_validate(asdict(commit.identity))
        current = self.snapshot(identity.learner_id)
        if current is None:
            raise Conflict("record.yaml", commit.expected_record_revision, None)
        if identity.key is not None:
            legacy = self.legacy_reservation(current.scratch)
            if legacy is not None and legacy.key == identity.key:
                raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
            found = self.load_receipt(identity, identity.key)
            if isinstance(found, Reservation):
                raise IdempotencyKeyConflict("Legacy key has no trustworthy input; use a fresh key")
            if found is not None:
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
        value = Prepared(
            version=1,
            kind="prepared",
            identity=identity,
            record_before=before,
            record_after=dump(commit.record.model_dump(mode="json")),
            scratch_before=self.raw("scratch.yaml"),
            scratch_after=commit.scratch,
            receipt_path="transition-receipts/" + receipt_name(identity, identity.key)
            if identity.key is not None
            else None,
            receipt=Receipt(version=1, kind="receipt", identity=identity)
            if identity.key is not None
            else None,
        )
        self.preflight(value)
        self.publish(value)
        self.apply(value)
        snapshot = self.snapshot(identity.learner_id)
        assert snapshot is not None
        return TransitionResult(snapshot, False)
