"""File-only course-version roll-forward: one recoverable write set under the course lock.

The runtime decides *whether* a record may move to a newer course version and supplies the
upgraded record (and, for a future coordinate map, a remapped homework slot). This journal
only persists that decision, plus the mechanical bookkeeping its own sibling journals need
so they stay valid once the record names a different version:

- keys bound under the old version stay bound — each becomes a ``reserved`` receipt in the
  new version's stream, so reusing one refuses instead of applying a second transition;
- committed completion/transition/submission markers, whose identities name the old version,
  are retired (their bytes are kept in the committed upgrade marker for inspection).

The durable order is prepared intent, reservations, retired markers, homework, scratch,
record, committed marker. Recovery validates every target first; bytes matching neither the
recorded before- nor after-image refuse rather than guess.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, StrictBytes, field_validator, model_validator

from ...course import HomeworkSlot, Record, is_semver
from .._io import _fsync_dir
from .._io import _write_bytes_atomic as _write_bytes_atomic
from .._paths import checked_path
from .._protocol import Conflict, HomeworkWrite, RecoveryRequired
from ._actions import ActionReservation, parse_receipt
from ._transition import (
    Boundary,
    Reservation,
    RuntimeSnapshot,
    Stream,
    TransitionJournal,
    dump,
    receipt_name,
    record_value,
    revision,
    scratch_value,
)

RECEIPTS = "transition-receipts"
MARKERS = ("completion.yaml", "transition.yaml", "submission.yaml")
HOMEWORK = "homework/active.yaml"


@dataclass(frozen=True)
class UpgradeIdentity:
    learner_id: str
    course_id: str
    from_version: str
    to_version: str


@dataclass(frozen=True)
class UpgradeCommit:
    """A runtime-prepared roll-forward. ``homework`` is absent unless the slot changes."""

    identity: UpgradeIdentity
    expected_record_revision: str
    expected_scratch: bytes
    record: Record
    scratch: bytes
    homework: HomeworkWrite | None = None


@dataclass(frozen=True)
class UpgradeResult:
    snapshot: RuntimeSnapshot
    replayed: bool


class Identity(Boundary):
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    from_version: str
    to_version: str

    @field_validator("from_version", "to_version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not is_semver(value):
            raise ValueError("invalid upgrade course version")
        return value

    @model_validator(mode="after")
    def distinct(self) -> Identity:
        if self.from_version == self.to_version:
            raise ValueError("an upgrade must change the course version")
        return self

    def stream(self, version: str) -> Stream:
        return Stream(learner_id=self.learner_id, course_id=self.course_id, course_version=version)

    def value(self) -> UpgradeIdentity:
        return UpgradeIdentity(**self.model_dump())


class Mutation(Boundary):
    path: str = Field(min_length=1)
    before: StrictBytes | None
    after: StrictBytes | None


class Prepared(Boundary):
    version: Literal[1]
    kind: Literal["prepared"]
    identity: Identity
    mutations: list[Mutation]


class Committed(Boundary):
    version: Literal[1]
    kind: Literal["committed"]
    identity: Identity
    retired: dict[str, StrictBytes]


def validate_upgrade_commit(commit: UpgradeCommit, root: Path) -> UpgradeCommit:
    """Validate untrusted copies before a store method can create a lock or directory."""
    try:
        identity = Identity.model_validate(asdict(commit.identity))
        for name in ("record.yaml", "scratch.yaml", "upgrade.yaml", RECEIPTS, *MARKERS):
            checked_path(root, identity.course_id, name)
        checked_path(root, identity.course_id, *HOMEWORK.split("/"))
        record = record_value(
            dump(commit.record.model_dump(mode="json")), identity.stream(identity.to_version)
        )
        if (
            not isinstance(commit.expected_record_revision, str)
            or not commit.expected_record_revision
        ):
            raise ValueError("an upgrade requires an existing record revision")
        if not isinstance(commit.expected_scratch, bytes) or not isinstance(commit.scratch, bytes):
            raise ValueError("upgrade scratch must be bytes")
        scratch_value(commit.expected_scratch)
        scratch_value(commit.scratch)
        homework = commit.homework
        if homework is not None:
            if homework.expected_revision is not None and not isinstance(
                homework.expected_revision, str
            ):
                raise ValueError("invalid homework revision")
            homework = HomeworkWrite(
                homework.expected_revision,
                HomeworkSlot.model_validate(homework.slot.model_dump(mode="json"))
                if homework.slot is not None
                else None,
            )
        return UpgradeCommit(
            identity.value(),
            commit.expected_record_revision,
            commit.expected_scratch,
            record,
            commit.scratch,
            homework,
        )
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise RecoveryRequired(f"Invalid upgrade input: {exc}") from exc


class UpgradeJournal:
    def __init__(self, root: Path, course_id: str) -> None:
        self.root, self.course_id = root, course_id
        self.transitions = TransitionJournal(root, course_id)

    def path(self, relative: str) -> Path:
        return checked_path(self.root, self.course_id, *relative.split("/"))

    def raw(self, relative: str) -> bytes | None:
        path = self.path(relative)
        if path.exists() and not path.is_file():
            raise ValueError("upgrade target must be a regular file")
        return path.read_bytes() if path.is_file() else None

    def load(self) -> Prepared | Committed | None:
        raw = self.raw("upgrade.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw)
        value = (
            Prepared.model_validate(data)
            if isinstance(data, dict) and data.get("kind") == "prepared"
            else Committed.model_validate(data)
        )
        if value.identity.course_id != self.course_id:
            raise ValueError("upgrade intent course mismatch")
        return value

    def inspect(self) -> Prepared | Committed | None:
        value = self.load()
        if isinstance(value, Prepared):
            self.preflight(value)
        return value

    def bound_keys(self, stream: Stream, scratch: bytes) -> list[Reservation | ActionReservation]:
        """Every key the old stream consumed: keyed receipts, reservations, legacy scratch."""
        keys: dict[tuple[int, str], Reservation | ActionReservation] = {}
        directory = self.path(RECEIPTS)
        if directory.is_dir():
            for child in sorted(directory.iterdir()):
                raw = self.raw(f"{RECEIPTS}/{child.name}")
                assert raw is not None
                data = yaml.safe_load(raw)
                found = parse_receipt(data)
                owner = (
                    found if isinstance(found, (Reservation, ActionReservation)) else found.identity
                )
                if owner.key is None or child.name != receipt_name(owner, owner.key):
                    raise ValueError("transition receipt name does not match its identity")
                if (owner.learner_id, owner.course_id, owner.course_version) == (
                    stream.learner_id,
                    stream.course_id,
                    stream.course_version,
                ):
                    reservation_type = ActionReservation if found.version == 2 else Reservation
                    keys[(found.version, owner.key)] = reservation_type.model_validate(
                        {
                            "version": found.version,
                            "kind": "reserved",
                            "key": owner.key,
                            **stream.model_dump(),
                        }
                    )
        legacy = self.transitions.legacy_reservation(scratch)
        if legacy is not None:
            keys[(1, legacy.key)] = legacy
        return [keys[k] for k in sorted(keys)]

    def preflight(self, value: Prepared) -> None:
        identity = value.identity
        paths = [m.path for m in value.mutations]
        if len(set(paths)) != len(paths) or not paths or paths[-1] != "record.yaml":
            raise ValueError("upgrade targets must be unique and end with the record")
        rank = {"scratch.yaml": 3, HOMEWORK: 2, **dict.fromkeys(MARKERS, 1)}
        order = [rank.get(p, 0) for p in paths[:-1]]
        if order != sorted(order):
            raise ValueError("upgrade targets are out of durable order")
        new_stream = identity.stream(identity.to_version)
        for item in value.mutations:
            if item.path == "record.yaml":
                if item.before is None or item.after is None:
                    raise ValueError("an upgrade rewrites an existing record")
                record_value(item.before, identity.stream(identity.from_version))
                record_value(item.after, new_stream)
            elif item.path == "scratch.yaml":
                scratch_value(item.before or b"")
                if item.after is None:
                    raise ValueError("upgrade scratch cannot be deleted")
                scratch_value(item.after)
            elif item.path == HOMEWORK:
                for raw in (item.before, item.after):
                    if raw is not None:
                        HomeworkSlot.model_validate(yaml.safe_load(raw))
            elif item.path in MARKERS:
                data = yaml.safe_load(item.before) if item.before is not None else None
                if item.after is not None or not isinstance(data, dict):
                    raise ValueError("an upgrade only retires existing markers")
                if data.get("kind") != "committed":
                    raise ValueError("an upgrade cannot retire a pending journal")
            elif item.path.startswith(RECEIPTS + "/"):
                if item.before is not None or item.after is None:
                    raise ValueError("an upgrade only adds key reservations")
                reserved = parse_receipt(yaml.safe_load(item.after))
                if not isinstance(reserved, (Reservation, ActionReservation)):
                    raise ValueError("upgrade target must be a key reservation")
                if (reserved.learner_id, reserved.course_id, reserved.course_version) != (
                    new_stream.learner_id,
                    new_stream.course_id,
                    new_stream.course_version,
                ) or item.path != f"{RECEIPTS}/{receipt_name(reserved, reserved.key)}":
                    raise ValueError("upgrade key reservation descriptor mismatch")
            else:
                raise ValueError(f"unknown upgrade target {item.path!r}")
            if self.raw(item.path) not in (item.before, item.after):
                raise ValueError(f"unexpected bytes at upgrade target {item.path}")

    def publish(self, value: Prepared | Committed) -> None:
        _write_bytes_atomic(self.path("upgrade.yaml"), dump(value.model_dump()))

    def apply(self, value: Prepared) -> None:
        for item in value.mutations:
            if self.raw(item.path) == item.after:
                continue
            path = self.path(item.path)
            if item.after is None:
                path.unlink(missing_ok=True)
                _fsync_dir(path.parent)
            else:
                _write_bytes_atomic(path, item.after)
        retired = {
            m.path: m.before for m in value.mutations if m.path in MARKERS and m.before is not None
        }
        self.publish(
            Committed(version=1, kind="committed", identity=value.identity, retired=retired)
        )

    def commit(self, commit: UpgradeCommit) -> UpgradeResult:
        identity = Identity.model_validate(asdict(commit.identity))
        current = self.transitions.snapshot(identity.learner_id)
        if current is None:
            raise Conflict("record.yaml", commit.expected_record_revision, None)
        previous = self.load()
        if (
            isinstance(previous, Committed)
            and previous.identity == identity
            and current.record.course_version == identity.to_version
        ):
            return UpgradeResult(current, True)
        if current.revision != commit.expected_record_revision:
            raise Conflict("record.yaml", commit.expected_record_revision, current.revision)
        if current.scratch != commit.expected_scratch:
            raise Conflict(
                "scratch.yaml", revision(commit.expected_scratch), revision(current.scratch)
            )
        old_stream = identity.stream(identity.from_version)
        new_stream = identity.stream(identity.to_version)
        record_value(dump(current.record.model_dump(mode="json")), old_stream)
        mutations: list[Mutation] = []
        for consumed in self.bound_keys(old_stream, current.scratch):
            key = consumed.key
            name = f"{RECEIPTS}/{receipt_name(new_stream, key, version=consumed.version)}"
            if self.raw(name) is None:
                reserved = consumed.model_copy(update=new_stream.model_dump())
                mutations.append(
                    Mutation(path=name, before=None, after=dump(reserved.model_dump()))
                )
        for name in MARKERS:
            raw = self.raw(name)
            if raw is not None:
                mutations.append(Mutation(path=name, before=raw, after=None))
        if commit.homework is not None:
            before = self.raw(HOMEWORK)
            actual = revision(before) if before is not None else None
            if actual != commit.homework.expected_revision:
                raise Conflict("active.yaml", commit.homework.expected_revision, actual)
            slot = commit.homework.slot
            after = dump(slot.model_dump(mode="json")) if slot is not None else None
            mutations.append(Mutation(path=HOMEWORK, before=before, after=after))
        mutations.append(
            Mutation(path="scratch.yaml", before=self.raw("scratch.yaml"), after=commit.scratch)
        )
        mutations.append(
            Mutation(
                path="record.yaml",
                before=self.raw("record.yaml"),
                after=dump(commit.record.model_dump(mode="json")),
            )
        )
        prepared = Prepared(version=1, kind="prepared", identity=identity, mutations=mutations)
        self.preflight(prepared)
        self.publish(prepared)
        self.apply(prepared)
        snapshot = self.transitions.snapshot(identity.learner_id)
        assert snapshot is not None
        return UpgradeResult(snapshot, False)
