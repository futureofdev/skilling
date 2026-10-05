"""A captured complete snapshot used by existing pure runtime preparation.

All reads below use one captured state. One prepared write crosses SessionStore.commit;
its returned coherent state replaces the capture. No backend transaction holds a lesson,
clock, callback, or producer wait.
"""

from __future__ import annotations

from ... import store as storage
from ...course import CompletionEntry, HomeworkArchiveEntry, HomeworkSlot, Record
from .. import _errors


class SnapshotStore:
    def __init__(
        self,
        store: storage.SessionStore,
        read: storage.SessionRead,
        source_digest: str | None = None,
    ) -> None:
        self.source_digest = source_digest
        self.store = store
        self.read = read
        self.mutation_kind = storage.RecordMutationKind.RECORD

    @property
    def state(self) -> storage.SessionState:
        if self.read.kind is storage.SessionReadKind.DELETED:
            raise storage.SessionDeleted("Session stream is deleted")
        if self.read.state is None:
            raise _errors.SessionRefusal(
                _errors.RefusalKind.ILLEGAL, "record-missing", "initialize before writing"
            )
        return self.read.state

    @property
    def expectation(self) -> str:
        revision = self.read.session_revision
        if revision is None:
            raise storage.RecoveryRequired("Existing session requires a whole-session revision")
        return revision

    def _stream(self, learner: str, course: str) -> None:
        if (learner, course) != (self.read.scope.learner_id, self.read.scope.course_id):
            raise storage.StatePathError("Captured snapshot belongs to another stream")

    def _commit(self, command: storage.SessionCommit) -> storage.SessionCommitResult:
        result = self.store.commit(command)
        self.read = storage.validate_read(result.read, self.read.scope)
        return result

    def get_record(self, learner_id: str, course_id: str) -> tuple[Record, str] | None:
        self._stream(learner_id, course_id)
        if self.read.state is None:
            return None
        return self.state.record.model_copy(deep=True), self.state.record_revision

    def put_record(self, record: Record, expected_revision: str | None) -> str:
        self._stream(record.learner_id, record.course_id)
        if self.read.state is None:
            self._commit(storage.InitializeSession(self.read.scope, None, record))
        else:
            if expected_revision is None:
                raise storage.Conflict("record", None, self.state.record_revision)
            self._commit(
                storage.MutateSession(
                    self.read.scope, self.expectation, record, expected_revision, self.mutation_kind
                )
            )
        return self.state.record_revision

    def get_log(self, learner_id: str, course_id: str) -> list[CompletionEntry]:
        self._stream(learner_id, course_id)
        return [v.model_copy(deep=True) for v in self.state.log] if self.read.state else []

    def get_homework(
        self, learner_id: str, course_id: str
    ) -> tuple[HomeworkSlot | None, str | None]:
        self._stream(learner_id, course_id)
        if self.read.state is None:
            return None, None
        return (
            self.state.homework.model_copy(deep=True) if self.state.homework else None,
            self.state.homework_revision,
        )

    def get_homework_archive(self, learner_id: str, course_id: str) -> list[HomeworkArchiveEntry]:
        self._stream(learner_id, course_id)
        return [v.model_copy(deep=True) for v in self.state.archive] if self.read.state else []

    def list_records(self, course_id: str) -> list[tuple[str, Record]]:
        self._stream(self.read.scope.learner_id, course_id)
        return [(self.read.scope.learner_id, self.state.record.model_copy(deep=True))]

    def append_completion(self, learner_id: str, course_id: str, entry: CompletionEntry) -> None:
        raise storage.NotSupported("Use one prepared completion")

    def append_homework_archive(
        self, learner_id: str, course_id: str, entry: HomeworkArchiveEntry
    ) -> None:
        raise storage.NotSupported("Use one prepared submission")

    def put_homework(
        self,
        learner_id: str,
        course_id: str,
        slot: HomeworkSlot | None,
        expected_revision: str | None,
    ) -> str | None:
        raise storage.NotSupported("Use one prepared completion, submission, or upgrade")

    def get_completion_receipt(
        self, learner_id: str, course_id: str
    ) -> storage.CompletionReceipt | None:
        self._stream(learner_id, course_id)
        receipts = self.state.completion_receipts
        return receipts[-1] if receipts else None

    def commit_completion(self, commit: storage.CompletionCommit) -> storage.CompletionCommitResult:
        result = self._commit(storage.CompleteSession(self.read.scope, self.expectation, commit))
        if not isinstance(result.outcome, storage.CompletionReceipt):
            raise storage.RecoveryRequired("Completion commit returned no original receipt")
        return storage.CompletionCommitResult(
            self.state.record, self.state.record_revision, result.outcome, result.replayed
        )

    def get_submission_receipt(
        self, learner_id: str, course_id: str, token: str
    ) -> storage.SubmissionReceipt | None:
        self._stream(learner_id, course_id)
        return next((v for v in self.state.submission_receipts if v.token == token), None)

    def commit_submission(self, commit: storage.SubmissionCommit) -> storage.SubmissionCommitResult:
        result = self._commit(storage.SubmitSession(self.read.scope, self.expectation, commit))
        if not isinstance(result.outcome, storage.SubmissionReceipt):
            raise storage.RecoveryRequired("Submission commit returned no original receipt")
        return storage.SubmissionCommitResult(result.outcome, result.replayed)

    def read_runtime_snapshot(
        self, learner_id: str, course_id: str
    ) -> storage.RuntimeSnapshot | None:
        self._stream(learner_id, course_id)
        if self.read.state is None:
            return None
        return storage.RuntimeSnapshot(
            self.state.record.model_copy(deep=True),
            self.state.record_revision,
            self.state.scratch,
            storage.pending_session_feedback(self.read),
        )

    def get_transition_identity(
        self, learner_id: str, course_id: str, key: str
    ) -> storage.TransitionIdentity | None:
        self._stream(learner_id, course_id)
        for receipt in self.state.action_receipts:
            identity = receipt.identity
            if isinstance(identity, storage.TransitionIdentity) and identity.key == key:
                return identity
        return None

    def get_action_result(
        self, identity: storage.ActionIdentity
    ) -> storage.TransitionResult | None:
        receipt = storage.replay_action(self.read, identity)
        if receipt is None:
            return None
        snapshot = self.read_runtime_snapshot(identity.learner_id, identity.course_id)
        assert snapshot is not None
        outcome = receipt.outcome
        return storage.TransitionResult(
            snapshot,
            True,
            outcome
            if isinstance(outcome, (storage.AdvanceOutcome, storage.QuizAnswerOutcome))
            else None,
        )

    def commit_transition(self, commit: storage.TransitionCommit) -> storage.TransitionResult:
        result = self._commit(storage.TransitionSession(self.read.scope, self.expectation, commit))
        snapshot = self.read_runtime_snapshot(self.read.scope.learner_id, self.read.scope.course_id)
        assert snapshot is not None
        outcome = result.outcome
        return storage.TransitionResult(
            snapshot,
            result.replayed,
            outcome
            if isinstance(outcome, (storage.AdvanceOutcome, storage.QuizAnswerOutcome))
            else None,
        )

    def pending_feedback(self, learner_id: str, course_id: str) -> storage.PendingFeedback | None:
        self._stream(learner_id, course_id)
        return storage.pending_session_feedback(self.read)

    def acknowledge_feedback(
        self, ref: storage.FeedbackRef, expected_revision: str
    ) -> storage.FeedbackAcknowledgement:
        result = self._commit(
            storage.AcknowledgeSession(self.read.scope, self.expectation, ref, expected_revision)
        )
        if not isinstance(result.outcome, storage.FeedbackAcknowledgement):
            raise storage.RecoveryRequired("Acknowledgement returned no outcome")
        return result.outcome

    def commit_upgrade(self, commit: storage.UpgradeCommit) -> storage.UpgradeResult:
        result = self._commit(
            storage.UpgradeSession(self.read.scope, self.expectation, commit, self.source_digest)
        )
        snapshot = self.read_runtime_snapshot(self.read.scope.learner_id, self.read.scope.course_id)
        assert snapshot is not None
        return storage.UpgradeResult(snapshot, result.replayed)
