"""Complete-session bridge over the portable cooperating file journals."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import Field

from ...course import Record, is_course_id
from .._file import FileProgressStore
from .._io import _write_bytes_atomic
from .._journal import (
    AcknowledgementStatus,
    ActionIdentity,
    FeedbackAcknowledgement,
    LegacyOutcomeUnavailable,
)
from .._journal import Receipt as CompletionBoundary
from .._journal._actions import ActionReceipt, ActionReservation, parse_receipt
from .._journal._submission import Receipt as SubmissionBoundary
from .._journal._submission import receipt_name as submission_receipt_name
from .._journal._transition import receipt_name as action_receipt_name
from .._journal._transition_types import Boundary, Reservation
from .._journal._transition_types import Receipt as LegacyReceipt
from .._journal._upgrade import Committed as UpgradeBoundary
from .._locking import locked_course
from .._paths import canonical_root, checked_path
from ._boundary import (
    replay_action,
    validate_command,
    validate_read,
    validate_scope,
    validate_scratch,
)
from ._file_delete import cleanup_deleted, publish_deleted, read_deleted
from ._file_source import (
    SOURCE,
    SourceBinding,
    initialize,
    source_bytes,
    unpublished_initialization,
)
from ._progress import CompletionReceipt, Conflict, RecoveryRequired, StatePathError
from ._session import (
    AcknowledgeSession,
    BindSourceSession,
    CompleteSession,
    DeleteSession,
    InitializeSession,
    MutateSession,
    SessionCommit,
    SessionCommitResult,
    SubmitSession,
    TransitionSession,
    UpgradeSession,
)
from ._types import (
    ReconciliationRequired,
    SessionActionReceipt,
    SessionDeleted,
    SessionKeyReservation,
    SessionRead,
    SessionReadKind,
    SessionScope,
    SessionState,
    SessionUpgradeReceipt,
)

BINDING = ".skilling-owner.json"


class RootBinding(Boundary):
    version: Literal[1]
    namespace: str = Field(min_length=1)
    learner_id: str = Field(min_length=1)


class FileSessionStore:
    """One immutable namespace/learner binding per producer-allocated state root."""

    def __init__(self, root: Path, namespace: str, learner_id: str) -> None:
        self.root = root
        self.namespace = namespace
        self.learner_id = learner_id
        self._file = FileProgressStore(root, learner_id)

    @classmethod
    def open(
        cls, root: Path, *, namespace: str, learner_id: str, bind_existing: bool = False
    ) -> FileSessionStore:
        if not root.is_absolute():
            raise StatePathError("File session root must be absolute")
        requested = RootBinding(version=1, namespace=namespace, learner_id=learner_id)
        selected = canonical_root(root)
        selected.mkdir(parents=True, exist_ok=True)
        if (selected / BINDING).is_symlink() or (selected / ".skilling.lock").is_symlink():
            raise StatePathError("Root ownership metadata must not be an alias")
        with locked_course(selected):
            path = selected / BINDING
            if path.exists():
                cls._binding(selected, requested)
            else:
                children = [p for p in selected.iterdir() if p.name != ".skilling.lock"]
                if children and not bind_existing:
                    raise StatePathError("Nonempty legacy root requires bind_existing=True")
                for child in children:
                    if not child.is_dir() or child.is_symlink() or not is_course_id(child.name):
                        raise StatePathError("Legacy root contains unrecognized ownership state")
                    record = checked_path(selected, child.name, "record.yaml")
                    if not record.is_file():
                        raise RecoveryRequired(
                            "Cannot bind legacy course without its learner record"
                        )
                    value = Record.model_validate(yaml.safe_load(record.read_bytes()))
                    if value.learner_id != learner_id or value.course_id != child.name:
                        raise StatePathError("Legacy root belongs to a different learner")
                _write_bytes_atomic(path, requested.model_dump_json().encode())
        return cls(selected, namespace, learner_id)

    @staticmethod
    def _binding(root: Path, requested: RootBinding) -> None:
        path = root / BINDING
        if path.is_symlink():
            raise StatePathError("Root ownership metadata must not be an alias")
        try:
            actual = RootBinding.model_validate_json(path.read_bytes())
        except (ValueError, OSError) as exc:
            raise RecoveryRequired("Invalid file root ownership binding") from exc
        if actual != requested:
            raise StatePathError("File root is bound to a different namespace or learner")

    def _scope(self, scope: SessionScope) -> None:
        validate_scope(scope)
        if (scope.namespace, scope.learner_id) != (self.namespace, self.learner_id):
            raise StatePathError("File root is bound to a different namespace or learner")
        self._binding(
            self.root, RootBinding(version=1, namespace=self.namespace, learner_id=self.learner_id)
        )

    def _deleted(self, scope: SessionScope) -> SessionRead | None:
        marker = read_deleted(self.root, scope.course_id)
        if marker is None:
            return None
        if (marker.namespace, marker.learner_id) != (scope.namespace, scope.learner_id):
            raise RecoveryRequired("Deleted stream scope differs from file root")
        cleanup_deleted(self.root, scope.course_id)
        return SessionRead(SessionReadKind.DELETED, scope, marker.generation)

    def read(self, scope: SessionScope) -> SessionRead:
        self._scope(scope)
        directory = self._file.course_dir(scope.course_id)
        if not directory.exists():
            return SessionRead(SessionReadKind.ABSENT, scope, None)
        with locked_course(directory):
            deleted = self._deleted(scope)
            if deleted is not None:
                return deleted
            with self._file._locked_course(scope.course_id):
                return self._read_locked(scope)

    def _fingerprint(self, scope: SessionScope) -> str:
        digest = hashlib.sha256()
        directory = self._file.course_dir(scope.course_id)
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(directory)
            checked_path(self.root, scope.course_id, *relative.parts)
            if path.is_dir() or path.name == ".skilling.lock":
                continue
            name, raw = relative.as_posix().encode(), path.read_bytes()
            digest.update(len(name).to_bytes(8, "big") + name + len(raw).to_bytes(8, "big") + raw)
        return "file-session:" + digest.hexdigest()

    def _read_locked(self, scope: SessionScope) -> SessionRead:
        try:
            return self._decode_locked(scope)
        except (ValueError, TypeError, AttributeError, OSError, yaml.YAMLError) as exc:
            raise RecoveryRequired("Invalid complete file session state") from exc

    def _decode_locked(self, scope: SessionScope) -> SessionRead:
        file = self._file
        snapshot = file.read_runtime_snapshot(scope.learner_id, scope.course_id)
        scratch = file.read_runtime_state(scope.course_id)
        validate_scratch(scratch)
        if snapshot is None:
            paths = [
                p
                for p in file.course_dir(scope.course_id).rglob("*")
                if p.is_file()
                and p.name != ".skilling.lock"
                and not unpublished_initialization(p.name)
            ]
            if paths:
                raise RecoveryRequired("Orphaned session state has no learner record")
            return SessionRead(SessionReadKind.ABSENT, scope, None)
        actions: list[SessionActionReceipt] = []
        reservations: dict[str, SessionKeyReservation] = {}
        for path in sorted(
            file.checked_path(scope.course_id, "transition-receipts").glob("*.yaml")
        ):
            value = parse_receipt(yaml.safe_load(path.read_bytes()))
            identity = (
                value if isinstance(value, (Reservation, ActionReservation)) else value.identity
            )
            if identity.key is None or path.name != action_receipt_name(identity, identity.key):
                raise RecoveryRequired("Action receipt filename differs from identity")
            if (identity.learner_id, identity.course_id) != (scope.learner_id, scope.course_id):
                raise RecoveryRequired("Receipt belongs to another stream")
            if isinstance(value, (Reservation, ActionReservation)):
                key = (
                    value.key
                    if isinstance(value, ActionReservation)
                    else hashlib.sha256(value.key.encode()).hexdigest()
                )
                reservations[key] = SessionKeyReservation(value.course_version, key)
            elif isinstance(value, ActionReceipt):
                actions.append(SessionActionReceipt(value.identity.value(), value.outcome.value()))
            elif isinstance(value, LegacyReceipt):
                actions.append(
                    SessionActionReceipt(value.identity.value(), LegacyOutcomeUnavailable())
                )
        submissions = []
        for path in sorted(
            file.checked_path(scope.course_id, "submission-receipts").glob("*.yaml")
        ):
            stored = SubmissionBoundary.model_validate(yaml.safe_load(path.read_bytes()))
            receipt = stored.value.value()
            if path.name != submission_receipt_name(receipt.token):
                raise RecoveryRequired("Submission receipt filename differs from token")
            parts = stored.archive_path.split("/")
            if len(parts) != 3 or parts[:2] != ["homework", "archive"]:
                raise RecoveryRequired("Submission archive reference is invalid")
            archive_path = file.checked_path(scope.course_id, *parts)
            if not archive_path.is_file():
                raise RecoveryRequired("Submission archive reference is missing")
            from ...course import HomeworkArchiveEntry

            archived = HomeworkArchiveEntry.model_validate(
                yaml.safe_load(archive_path.read_bytes())
            )
            if archived != receipt.archive:
                raise RecoveryRequired("Submission archive differs from original receipt")
            submissions.append(receipt)
        completions: dict[str, CompletionReceipt] = {}
        for path in sorted(
            file.checked_path(scope.course_id, "completion-receipts").glob("*.yaml")
        ):
            receipt = CompletionBoundary.model_validate(yaml.safe_load(path.read_bytes())).value()
            if path.name != receipt.operation_id + ".yaml":
                raise RecoveryRequired("Completion receipt filename differs from identity")
            completions[receipt.operation_id] = receipt
        latest = file.get_completion_receipt(scope.learner_id, scope.course_id)
        if latest is not None:
            completions[latest.operation_id] = latest
        upgrades = []
        path = file.checked_path(scope.course_id, "upgrade.yaml")
        if path.is_file():
            upgrade = UpgradeBoundary.model_validate(yaml.safe_load(path.read_bytes()))
            upgrades.append(SessionUpgradeReceipt(upgrade.identity.value()))
            retired = upgrade.retired.get("completion.yaml")
            if retired is not None:
                data = yaml.safe_load(retired)
                receipt = CompletionBoundary.model_validate(data["receipt"]).value()
                completions[receipt.operation_id] = receipt
        slot, slot_revision = file.get_homework(scope.learner_id, scope.course_id)
        source_path = file.checked_path(scope.course_id, SOURCE)
        source = (
            SourceBinding.model_validate_json(source_path.read_bytes())
            if source_path.exists()
            else None
        )
        if source is not None and (
            source.namespace,
            source.learner_id,
            source.course_id,
            source.course_version,
        ) != (scope.namespace, scope.learner_id, scope.course_id, snapshot.record.course_version):
            raise RecoveryRequired("Attached source differs from stream")
        state = SessionState(
            snapshot.record,
            snapshot.revision,
            snapshot.scratch,
            tuple(file.get_log(scope.learner_id, scope.course_id)),
            slot,
            slot_revision,
            tuple(file.get_homework_archive(scope.learner_id, scope.course_id)),
            tuple(sorted(completions.values(), key=lambda r: r.completed_at)),
            tuple(actions),
            tuple(reservations.values()),
            tuple(submissions),
            tuple(upgrades),
            source.digest if source else None,
        )
        return validate_read(
            SessionRead(SessionReadKind.LIVE, scope, self._fingerprint(scope), state), scope
        )

    def commit(self, command: SessionCommit) -> SessionCommitResult:
        try:
            return self._commit(command)
        except OSError as exc:
            raise ReconciliationRequired("File commit outcome requires read/reconcile") from exc

    def _commit(self, command: SessionCommit) -> SessionCommitResult:
        self._scope(command.scope)
        validate_command(command)
        scope = command.scope
        directory = self._file.course_dir(scope.course_id)
        directory.mkdir(parents=True, exist_ok=True)
        with locked_course(directory):
            if self._deleted(scope) is not None:
                raise SessionDeleted("Session stream is deleted")
            with self._file._locked_course(scope.course_id):
                current = self._read_locked(scope)
                replay = self._replay(current, command)
                if replay is not None:
                    return replay
                if command.expected_revision != current.session_revision:
                    raise Conflict("session", command.expected_revision, current.session_revision)
                if isinstance(command, DeleteSession):
                    publish_deleted(self.root, scope, "deleted:" + uuid4().hex)
                    deleted = self._deleted(scope)
                    assert deleted is not None
                    return SessionCommitResult(deleted)
                outcome = None
                replayed = False
                if isinstance(command, InitializeSession):
                    if current.kind is not SessionReadKind.ABSENT:
                        raise Conflict("session initialization", None, current.session_revision)
                    initialize(self.root, scope, command.record, command.source_digest)
                elif isinstance(command, BindSourceSession):
                    if current.state is None or current.state.source_digest is not None:
                        raise RecoveryRequired(
                            "Source attachment requires live legacy state with unknown source"
                        )
                    _write_bytes_atomic(
                        self._file.checked_path(scope.course_id, SOURCE),
                        source_bytes(scope, current.state.record, command.source_digest),
                    )
                elif isinstance(command, TransitionSession):
                    result = self._file.commit_transition(command.commit)
                    outcome, replayed = result.outcome, result.replayed
                elif isinstance(command, AcknowledgeSession):
                    outcome = self._file.acknowledge_feedback(
                        command.feedback, command.expected_record_revision
                    )
                elif isinstance(command, CompleteSession):
                    completed = self._file.commit_completion(command.commit)
                    outcome, replayed = completed.receipt, completed.replayed
                elif isinstance(command, SubmitSession):
                    submitted = self._file.commit_submission(command.commit)
                    outcome, replayed = submitted.receipt, submitted.replayed
                elif isinstance(command, MutateSession):
                    from ._boundary import validate_mutation

                    validate_mutation(current, command)
                    self._file.put_record(command.record, command.expected_record_revision)
                elif isinstance(command, UpgradeSession):
                    upgraded = self._file.commit_upgrade(
                        replace(
                            command.commit,
                            source_metadata=source_bytes(
                                scope, command.commit.record, command.source_digest
                            )
                            if command.source_digest
                            else None,
                        )
                    )
                    outcome, replayed = command.commit.identity, upgraded.replayed
                return SessionCommitResult(self._read_locked(scope), replayed, outcome)

    def _replay(self, current: SessionRead, command: SessionCommit) -> SessionCommitResult | None:
        state = current.state
        if state is None:
            return None
        if isinstance(command, TransitionSession) and isinstance(
            command.commit.identity, ActionIdentity
        ):
            receipt = replay_action(current, command.commit.identity)
            if receipt is not None:
                return SessionCommitResult(current, True, receipt.outcome)
        elif isinstance(command, SubmitSession):
            receipt = next(
                (r for r in state.submission_receipts if r.token == command.commit.receipt.token),
                None,
            )
            if receipt is not None:
                return SessionCommitResult(current, True, receipt)
        elif isinstance(command, CompleteSession):
            original = next(
                (
                    r
                    for r in state.completion_receipts
                    if r.operation_id == command.commit.receipt.operation_id
                ),
                None,
            )
            if original is not None:
                if (
                    original.learner_id,
                    original.course_id,
                    original.course_version,
                    original.coordinate,
                ) != (
                    command.commit.receipt.learner_id,
                    command.commit.receipt.course_id,
                    command.commit.receipt.course_version,
                    command.commit.receipt.coordinate,
                ):
                    raise RecoveryRequired("Completion operation identity differs")
                return SessionCommitResult(current, True, original)
        elif isinstance(command, UpgradeSession):
            if any(r.identity == command.commit.identity for r in state.upgrades):
                return SessionCommitResult(current, True, command.commit.identity)
        elif isinstance(command, AcknowledgeSession):
            scratch = validate_scratch(state.scratch)
            pointer = scratch.presented_feedback
            ref = command.feedback
            if pointer is not None and (
                pointer.origin_course_version,
                pointer.answer_key,
                pointer.receipt_digest,
            ) == (ref._course_version, ref._answer_key, ref._receipt_digest):
                return SessionCommitResult(
                    current,
                    True,
                    FeedbackAcknowledgement(
                        AcknowledgementStatus.ALREADY_PRESENTED, state.record_revision
                    ),
                )
        return None

    def list_records(self, namespace: str, course_id: str) -> tuple[Record, ...]:
        read = self.read(SessionScope(namespace, self.learner_id, course_id))
        return (read.state.record.model_copy(deep=True),) if read.state is not None else ()

    def export_progress(self, scope: SessionScope) -> Record | None:
        read = self.read(scope)
        return read.state.record.model_copy(deep=True) if read.state is not None else None
