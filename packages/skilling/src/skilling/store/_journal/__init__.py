"""Mechanical completion recovery under the existing course lock.

The runtime supplies semantics. This module validates and persists a portable byte write
set, preflighting every descriptor and target before publishing or applying any intent.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictBytes,
    field_validator,
)

from ...course import CompletionEntry, HomeworkSlot, Record
from .._io import _fsync_dir
from .._io import _write_bytes_atomic as _write_bytes_atomic
from .._paths import checked_path
from .._protocol import (
    CompletionCommit,
    CompletionCommitResult,
    CompletionReceipt,
    Conflict,
    HomeworkWrite,
    RecoveryRequired,
    StatePathError,
)

# The shared entrypoint validates both journals before either is allowed to recover.
from ._transition import (
    IdempotencyKeyConflict as IdempotencyKeyConflict,
)
from ._transition import Prepared as PreparedTransition
from ._transition import (
    RuntimeSnapshot as RuntimeSnapshot,
)
from ._transition import (
    TransitionCommit as TransitionCommit,
)
from ._transition import (
    TransitionIdentity as TransitionIdentity,
)
from ._transition import (
    TransitionJournal as TransitionJournal,
)
from ._transition import (
    TransitionResult as TransitionResult,
)
from ._transition import (
    TransitionVerb as TransitionVerb,
)


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Receipt(Boundary):
    operation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_version: str
    coordinate: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    completed_at: AwareDatetime
    badges_awarded: tuple[str, ...]
    phase_completed: int | None = Field(ge=0)
    homework_placed: StrictBool
    homework_queued: StrictBool

    def value(self) -> CompletionReceipt:
        return CompletionReceipt(**self.model_dump())


class Target(StrEnum):
    LOG = "log"
    RECORD = "record"
    HOMEWORK = "homework"
    RUNTIME = "runtime-state"


TARGETS = {
    Target.LOG: ("completed.yaml",),
    Target.RECORD: ("record.yaml",),
    Target.HOMEWORK: ("homework", "active.yaml"),
    Target.RUNTIME: ("scratch.yaml",),
}


class Mutation(Boundary):
    target: Target
    before: StrictBytes | None
    after: StrictBytes | None


class Metadata(Boundary):
    version: Literal[1]

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("journal version must be an integer")
        return value


class Prepared(Metadata):
    version: Literal[1]
    kind: Literal["prepared"]
    receipt: Receipt
    mutations: list[Mutation]


class Committed(Metadata):
    version: Literal[1]
    kind: Literal["committed"]
    receipt: Receipt


def _revision(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest()[:16] if raw is not None else None


def _dump(value: object) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100).encode("utf-8")


def _log(raw: bytes | None) -> list[CompletionEntry]:
    value = yaml.safe_load(raw) if raw is not None else []
    if not isinstance(value, list):
        raise ValueError("completion log must be a sequence")
    return [CompletionEntry.model_validate(item) for item in value]


def _stream(record: Record, receipt: Receipt) -> None:
    if (record.learner_id, record.course_id, record.course_version) != (
        receipt.learner_id,
        receipt.course_id,
        receipt.course_version,
    ):
        raise ValueError("completion record stream differs from receipt")


def _entry(entry: CompletionEntry, receipt: Receipt) -> None:
    if (entry.coordinate, entry.course_version, entry.completed_at) != (
        receipt.coordinate,
        receipt.course_version,
        receipt.completed_at,
    ):
        raise ValueError("completion entry identity differs from receipt")


def validate_commit(commit: CompletionCommit, root: Path) -> CompletionCommit:
    """Revalidate copied model instances too, before creating even a lock file."""
    try:
        receipt = Receipt.model_validate(asdict(commit.receipt))
        checked_path(root, receipt.course_id, "completion.yaml")
        for parts in TARGETS.values():
            checked_path(root, receipt.course_id, *parts)
        record = Record.model_validate(commit.record.model_dump(mode="json"))
        entry = CompletionEntry.model_validate(commit.entry.model_dump(mode="json"))
        expected_log = tuple(
            CompletionEntry.model_validate(item.model_dump(mode="json"))
            for item in commit.expected_log
        )
        if (
            not isinstance(commit.expected_record_revision, str)
            or not commit.expected_record_revision
        ):
            raise ValueError("completion requires an existing record revision")
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
        _stream(record, receipt)
        _entry(entry, receipt)
        return CompletionCommit(
            receipt.value(), commit.expected_record_revision, record, expected_log, entry, homework
        )
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise RecoveryRequired(f"Invalid completion input: {exc}") from exc


class Journal:
    def __init__(self, root: Path, course_id: str) -> None:
        self.root = root
        self.course_id = course_id

    def _path(self, *parts: str) -> Path:
        return checked_path(self.root, self.course_id, *parts)

    def _raw(self, target: Target) -> bytes | None:
        path = self._path(*TARGETS[target])
        if path.exists() and not path.is_file():
            raise ValueError(f"completion target {target} is not a file")
        return path.read_bytes() if path.is_file() else None

    def _identity(self, receipt: Receipt) -> None:
        if receipt.course_id != self.course_id:
            raise ValueError("completion receipt differs from selected stream")

    def _load(self) -> Prepared | Committed | None:
        path = self._path("completion.yaml")
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError("completion metadata is not a file")
        data = yaml.safe_load(path.read_bytes())
        if isinstance(data, dict) and data.get("kind") == "prepared":
            value = Prepared.model_validate(data)
        else:
            value = Committed.model_validate(data)
        self._identity(value.receipt)
        return value

    def _publish(self, value: Prepared | Committed) -> None:
        data = value.model_dump(mode="python")
        data["receipt"] = value.receipt.model_dump(mode="json")
        if isinstance(value, Prepared):
            data["mutations"] = [
                {"target": m.target.value, "before": m.before, "after": m.after}
                for m in value.mutations
            ]
        _write_bytes_atomic(self._path("completion.yaml"), _dump(data))

    def _preflight(self, prepared: Prepared) -> None:
        self._identity(prepared.receipt)
        targets = [item.target for item in prepared.mutations]
        expected = [Target.LOG, Target.RECORD]
        if Target.HOMEWORK in targets:
            expected.append(Target.HOMEWORK)
        expected.append(Target.RUNTIME)
        if targets != expected:
            raise ValueError("completion targets must occur exactly once in commit order")
        paths = [self._path(*TARGETS[item.target]) for item in prepared.mutations]
        if len(set(paths)) != len(paths):
            raise ValueError("completion target paths collide")
        for item in prepared.mutations:
            if item.target == Target.LOG:
                before, after = _log(item.before), _log(item.after)
                if len(after) != len(before) + 1 or after[:-1] != before:
                    raise ValueError("completion must append exactly one unchanged-history entry")
                _entry(after[-1], prepared.receipt)
            elif item.target == Target.RECORD:
                if item.after is None:
                    raise ValueError("completion record cannot be deleted")
                record = Record.model_validate(yaml.safe_load(item.after))
                _stream(record, prepared.receipt)
                if item.before is None:
                    raise ValueError("completion requires an existing record")
                _stream(Record.model_validate(yaml.safe_load(item.before)), prepared.receipt)
            elif item.target == Target.HOMEWORK:
                for raw in (item.before, item.after):
                    if raw is not None:
                        HomeworkSlot.model_validate(yaml.safe_load(raw))
            elif item.after != b"":
                raise ValueError("completion runtime state must reset to empty bytes")
            elif item.before:
                TransitionJournal(self.root, self.course_id).legacy_reservation(item.before)
            if self._raw(item.target) not in (item.before, item.after):
                raise ValueError(f"unexpected bytes at completion target {item.target}")

    def _apply(self, prepared: Prepared) -> None:
        for item in prepared.mutations:
            if item.target == Target.RUNTIME and item.before:
                TransitionJournal(self.root, self.course_id).reserve_legacy(item.before)
        for item in prepared.mutations:
            if self._raw(item.target) == item.after:
                continue
            path = self._path(*TARGETS[item.target])
            if item.after is None:
                path.unlink(missing_ok=True)
                _fsync_dir(path.parent)
            else:
                _write_bytes_atomic(path, item.after)
        self._publish(Committed(version=1, kind="committed", receipt=prepared.receipt))

    def recover(self) -> None:
        try:
            value = self._load()
            if isinstance(value, Prepared):
                self._preflight(value)
                self._apply(value)
        except (ValueError, TypeError, yaml.YAMLError, StatePathError) as exc:
            raise RecoveryRequired(
                f"Cannot recover completion: {exc}. "
                "Preserve state and completion.yaml for inspection."
            ) from exc

    def receipt(self) -> CompletionReceipt | None:
        try:
            value = self._load()
            return value.receipt.value() if value is not None else None
        except (ValueError, TypeError, yaml.YAMLError, StatePathError) as exc:
            raise RecoveryRequired(f"Invalid completion receipt: {exc}") from exc

    def _result(self, receipt: Receipt, replayed: bool) -> CompletionCommitResult:
        try:
            raw = self._raw(Target.RECORD)
            if raw is None:
                raise RecoveryRequired("Completion receipt has no current record")
            record = Record.model_validate(yaml.safe_load(raw))
            _stream(record, receipt)
        except (ValueError, TypeError, yaml.YAMLError) as exc:
            raise RecoveryRequired(
                f"Completion receipt has a replaced record stream: {exc}"
            ) from exc
        revision = _revision(raw)
        assert revision is not None
        return CompletionCommitResult(record, revision, receipt.value(), replayed)

    def commit(self, commit: CompletionCommit) -> CompletionCommitResult:
        receipt = Receipt.model_validate(asdict(commit.receipt))
        previous = self._load()
        if previous is not None and previous.receipt.operation_id == receipt.operation_id:
            if previous.receipt != receipt:
                # A retry can carry a different clock, but cannot substitute stream/target identity.
                fields = ("learner_id", "course_id", "course_version", "coordinate")
                old, new = previous.receipt.model_dump(), receipt.model_dump()
                if any(old[field] != new[field] for field in fields):
                    raise RecoveryRequired("Same operation id has inconsistent completion identity")
            return self._result(previous.receipt, True)
        before = {target: self._raw(target) for target in TARGETS}
        actual = _revision(before[Target.RECORD])
        if actual != commit.expected_record_revision:
            raise Conflict("record.yaml", commit.expected_record_revision, actual)
        current_log = _log(before[Target.LOG])
        if current_log != list(commit.expected_log):
            raise Conflict(
                "completed.yaml",
                _revision(_dump([e.model_dump(mode="json") for e in commit.expected_log])),
                _revision(_dump([e.model_dump(mode="json") for e in current_log])),
            )
        if commit.homework is not None:
            actual = _revision(before[Target.HOMEWORK])
            if actual != commit.homework.expected_revision:
                raise Conflict("active.yaml", commit.homework.expected_revision, actual)
        mutations = [
            Mutation(
                target=Target.LOG,
                before=before[Target.LOG],
                after=_dump([e.model_dump(mode="json") for e in [*current_log, commit.entry]]),
            ),
            Mutation(
                target=Target.RECORD,
                before=before[Target.RECORD],
                after=_dump(commit.record.model_dump(mode="json")),
            ),
        ]
        if commit.homework is not None:
            slot = commit.homework.slot
            mutations.append(
                Mutation(
                    target=Target.HOMEWORK,
                    before=before[Target.HOMEWORK],
                    after=_dump(slot.model_dump(mode="json")) if slot else None,
                )
            )
        mutations.append(Mutation(target=Target.RUNTIME, before=before[Target.RUNTIME], after=b""))
        prepared = Prepared(version=1, kind="prepared", receipt=receipt, mutations=mutations)
        try:
            self._preflight(prepared)
        except (ValueError, TypeError, yaml.YAMLError, StatePathError) as exc:
            raise RecoveryRequired(f"Invalid prepared completion: {exc}") from exc
        self._publish(prepared)
        self._apply(prepared)
        return self._result(receipt, False)


def recover_journals(root: Path, course_id: str) -> None:
    completion = Journal(root, course_id)
    transition = TransitionJournal(root, course_id)
    try:
        old = completion._load()
        if isinstance(old, Prepared):
            completion._preflight(old)
        new = transition.inspect()
        if isinstance(old, Prepared) and isinstance(new, PreparedTransition):
            raise ValueError("multiple prepared runtime journals")
        if isinstance(old, Prepared):
            completion._apply(old)
        if isinstance(new, PreparedTransition):
            transition.apply(new)
    except (ValueError, TypeError, yaml.YAMLError, StatePathError) as exc:
        raise RecoveryRequired(
            f"Cannot recover runtime journals: {exc}. Preserve state for inspection."
        ) from exc


def validate_transition_commit(commit: TransitionCommit, root: Path) -> TransitionCommit:
    from ._transition import validate_commit as validate

    return validate(commit, root)
