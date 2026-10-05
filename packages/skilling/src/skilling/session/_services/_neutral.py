"""Backend-neutral trusted controller, with namespace-bound captured handles."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from ... import store as storage
from ...course import Capability, Course, Record
from ...delivery import RollForward, preview_upgrade, roll_forward
from ...workspace import workspace_read
from .. import _companion, _workspace
from .._errors import RefusalKind, SessionRefusal, VersionMismatch
from .._loading import RuntimeSession, load_course, parse_scratch
from .._teaching import guard_feedback, prepare_action
from .._types import (
    ActionResult,
    ArtifactResult,
    ArtifactView,
    CeremonyView,
    CompletionResult,
    CourseView,
    HomeworkArchiveView,
    HomeworkCheck,
    ObjectiveResult,
    ObjectiveView,
    ProgressView,
    QuestionView,
    ScopedPendingFeedback,
    SessionSnapshot,
    TelemetryView,
    TrustedAction,
)
from ._file import commit_runtime, committed_session, view
from ._snapshot import SnapshotStore
from ._source import course_digest


@dataclass(frozen=True)
class Session:
    """Experimental per-scope authority; producer authentication stays outside the SDK."""

    _course: Course
    _store: storage.SessionStore
    scope: storage.SessionScope
    work_root: Path
    _initialize: bool
    _now: datetime | None
    _source_digest: str

    @classmethod
    def open(
        cls,
        course_path: Path,
        *,
        store: storage.SessionStore,
        scope: storage.SessionScope,
        work_root: Path,
        initialize: bool = True,
        now: datetime | None = None,
    ) -> Session:
        with workspace_read(course_path):
            storage.validate_scope(scope)
            if not work_root.is_absolute() or not work_root.is_dir() or work_root.is_symlink():
                raise SessionRefusal(
                    RefusalKind.INVALID,
                    "work-root-invalid",
                    "an existing absolute producer work directory is required",
                )
            course = load_course(course_path)
            if course.id != scope.course_id:
                raise SessionRefusal(RefusalKind.INVALID, "stream-mismatch", "scope course differs")
            service = cls(
                course,
                store,
                scope,
                work_root.resolve(),
                initialize,
                now,
                course_digest(course.root),
            )
            service._load()
            return service

    @property
    def course(self) -> CourseView:
        return _companion.course_view(self._course)

    def _read(self) -> storage.SessionRead:
        read = storage.validate_read(self._store.read(self.scope), self.scope)
        if read.kind is storage.SessionReadKind.DELETED:
            raise storage.SessionDeleted("Session stream is deleted")
        return read

    def _load(
        self, *, initialize: bool | None = None, snapshot: SessionSnapshot | None = None
    ) -> RuntimeSession:
        if snapshot is not None:
            self._check_snapshot(snapshot)
        if course_digest(self._course.root) != self._source_digest:
            raise SessionRefusal(
                RefusalKind.CONFLICT,
                "source-changed",
                "selected course bytes changed; reopen and explicitly upgrade",
            )
        read = self._read()
        if read.kind is storage.SessionReadKind.ABSENT and (
            self._initialize if initialize is None else initialize
        ):
            read = self._store.commit(
                storage.InitializeSession(
                    self.scope,
                    None,
                    Record.new(self._course, self.scope.learner_id, now=self._now),
                    self._source_digest,
                )
            ).read
            read = storage.validate_read(read, self.scope)
        if read.state is not None and read.state.record.course_version == self._course.version:
            if read.state.source_digest is None:
                assert read.session_revision is not None
                read = self._store.commit(
                    storage.BindSourceSession(
                        self.scope, read.session_revision, self._source_digest
                    )
                ).read
            elif read.state.source_digest != self._source_digest:
                raise SessionRefusal(
                    RefusalKind.CONFLICT,
                    "source-changed",
                    "recorded course bytes differ; explicit version upgrade required",
                )
        adapter = SnapshotStore(self._store, read, self._source_digest)
        if snapshot is not None and snapshot.session_revision != read.session_revision:
            raise storage.Conflict("session", snapshot.session_revision, read.session_revision)
        state = read.state
        record = (
            state.record
            if state
            else Record.new(self._course, self.scope.learner_id, now=self._now)
        )
        if record.course_version != self._course.version:
            plan = preview_upgrade(adapter, self._course, self.scope.learner_id).plan
            raise VersionMismatch(
                self._course.id,
                record.course_version,
                self._course.version,
                bool(plan and plan.ok),
                plan.refusal if plan else None,
                plan.refusal_message() if plan and not plan.ok else None,
            )
        lesson = self._course.lesson_at(record.position.coordinate)
        if lesson is None:
            raise SessionRefusal(
                RefusalKind.INVALID, "position-invalid", "current lesson is absent"
            )
        scratch = state.scratch if state else b""
        return RuntimeSession(
            self._course,
            lesson,
            adapter,
            record,
            state.record_revision if state else None,
            parse_scratch(scratch),
            scratch,
            storage.pending_session_feedback(read),
        )

    def _check_scope(self, scope: storage.SessionScope) -> None:
        if scope != self.scope:
            raise SessionRefusal(
                RefusalKind.CONFLICT, "scope-binding", "handle belongs to another scope"
            )

    def _check_snapshot(self, snapshot: SessionSnapshot) -> None:
        if snapshot.scope != self.scope or snapshot.session_revision is None:
            raise SessionRefusal(
                RefusalKind.CONFLICT, "scope-binding", "capture this session snapshot"
            )

    def _view(self, runtime: RuntimeSession) -> SessionSnapshot:
        assert isinstance(runtime.store, SnapshotStore)
        return replace(
            view(runtime), scope=self.scope, session_revision=runtime.store.read.session_revision
        )

    def snapshot(self) -> SessionSnapshot:
        with workspace_read(self._course.root):
            return self._view(self._load())

    def capture_action(
        self,
        snapshot: SessionSnapshot,
        *,
        event_id: str,
        operation: storage.ActionOperation,
        payload: str,
        origin: storage.ActionOrigin = storage.ActionOrigin.LEARNER,
    ) -> storage.ScopedAction:
        self._check_snapshot(snapshot)
        if snapshot.revision is None or snapshot.session_revision is None:
            raise ValueError("Initialize the session before capturing an action")
        question = snapshot.beat.question
        identity = storage.neutral_action_identity(
            storage.ActionIdentity(
                self.scope.learner_id,
                self.scope.course_id,
                snapshot.course.version,
                snapshot.position.coordinate,
                operation,
                payload.strip().lower() if operation is storage.ActionOperation.ANSWER else payload,
                storage.key_digest(event_id),
                origin,
                snapshot.revision,
                question.number
                if operation is storage.ActionOperation.ANSWER and question
                else None,
            )
        )
        if identity.verb is storage.ActionOperation.ACKNOWLEDGE:
            raise ValueError("Acknowledgement requires a ScopedFeedback")
        return storage.ScopedAction(self.scope, identity, snapshot.session_revision)

    def act(self, action: storage.ScopedAction) -> ActionResult:
        if not isinstance(action, storage.ScopedAction):
            raise SessionRefusal(RefusalKind.INVALID, "action-invalid", "use a scoped action")
        self._check_scope(action.scope)
        identity = storage.neutral_action_identity(action.identity)
        if (identity.learner_id, identity.course_id, identity.course_version) != (
            self.scope.learner_id,
            self.scope.course_id,
            self._course.version,
        ):
            raise SessionRefusal(RefusalKind.CONFLICT, "action-binding", "action stream differs")
        with workspace_read(self._course.root):
            runtime = self._load(initialize=False)
            assert isinstance(runtime.store, SnapshotStore)
            replay = storage.replay_action(runtime.store.read, identity)
            if replay is not None:
                return ActionResult(self._view(runtime), True, replay.outcome)
            if runtime.store.read.session_revision != action.session_revision:
                raise storage.Conflict(
                    "session", action.session_revision, runtime.store.read.session_revision
                )
            _companion.check_revision(runtime, identity.expected_revision)
            if runtime.lesson.coordinate != identity.coordinate:
                raise SessionRefusal(
                    RefusalKind.CONFLICT, "action-binding", "captured coordinate changed"
                )
            trusted = TrustedAction(
                identity.key or "",
                identity.origin,
                identity.learner_id,
                identity.course_id,
                identity.course_version,
                identity.coordinate,
                identity.question_number,
                identity.expected_revision,
                identity.verb,
                identity.input,
            )
            prepared = prepare_action(runtime, trusted, identity)
            result = commit_runtime(
                runtime, prepared.record, prepared.scratch, identity, prepared.outcome
            )
            return ActionResult(
                self._view(committed_session(runtime, result)), result.replayed, result.outcome
            )

    def question(self) -> QuestionView:
        with workspace_read(self._course.root):
            runtime = self._load()
            guard_feedback(runtime)
            snapshot = self._view(runtime)
            question = snapshot.beat.question
            if question is None:
                raise SessionRefusal(
                    RefusalKind.ILLEGAL, "illegal-transition", "no quiz question is open"
                )
            return question

    @classmethod
    def pending_feedback_at(
        cls, *, store: storage.SessionStore, scope: storage.SessionScope
    ) -> ScopedPendingFeedback | None:
        read = storage.validate_read(store.read(scope), scope)
        if read.kind is storage.SessionReadKind.DELETED:
            raise storage.SessionDeleted("Session stream is deleted")
        feedback = storage.pending_session_feedback(read)
        if feedback is None:
            return None
        assert read.session_revision is not None
        return ScopedPendingFeedback(
            storage.ScopedFeedback(
                scope, feedback.feedback_id, read.session_revision, feedback.revision
            ),
            feedback.outcome,
            feedback.revision,
        )

    def pending_feedback(self) -> ScopedPendingFeedback | None:
        return self.pending_feedback_at(store=self._store, scope=self.scope)

    @classmethod
    def acknowledge_feedback_at(
        cls,
        handle: storage.ScopedFeedback,
        *,
        store: storage.SessionStore,
        scope: storage.SessionScope,
    ) -> storage.FeedbackAcknowledgement:
        if not isinstance(handle, storage.ScopedFeedback) or handle.scope != scope:
            raise SessionRefusal(
                RefusalKind.CONFLICT, "scope-binding", "feedback belongs to another scope"
            )
        result = store.commit(
            storage.AcknowledgeSession(
                scope, handle.session_revision, handle.feedback, handle.record_revision
            )
        )
        if not isinstance(result.outcome, storage.FeedbackAcknowledgement):
            raise storage.RecoveryRequired("Acknowledgement returned no original outcome")
        return result.outcome

    def acknowledge_feedback(
        self, handle: storage.ScopedFeedback
    ) -> storage.FeedbackAcknowledgement:
        return self.acknowledge_feedback_at(handle, store=self._store, scope=self.scope)

    def complete(
        self, snapshot: SessionSnapshot, *, now: datetime | None = None
    ) -> CompletionResult:
        with workspace_read(self._course.root):
            self._check_snapshot(snapshot)
            runtime = self._load(initialize=False)
            assert isinstance(runtime.store, SnapshotStore)
            original = next(
                (
                    receipt
                    for receipt in runtime.store.state.completion_receipts
                    if receipt.coordinate == snapshot.position.coordinate
                    and receipt.course_version == snapshot.course.version
                ),
                None,
            )
            if original is not None:
                return CompletionResult(
                    self._view(runtime),
                    True,
                    original.badges_awarded,
                    original.phase_completed,
                    original.homework_placed,
                    original.homework_queued,
                )
            if snapshot.session_revision != runtime.store.read.session_revision:
                raise storage.Conflict(
                    "session", snapshot.session_revision, runtime.store.read.session_revision
                )
            guard_feedback(runtime)
            result = _companion.complete(runtime, snapshot.revision, now or self._now)
            assert isinstance(runtime.store, SnapshotStore)
            return replace(
                result,
                snapshot=replace(
                    result.snapshot,
                    scope=self.scope,
                    session_revision=runtime.store.read.session_revision,
                ),
            )

    def homework_check(self) -> HomeworkCheck:
        with workspace_read(self._course.root):
            runtime = self._load(initialize=False)
            guard_feedback(runtime)
            value = _companion.homework_check(runtime)
            assert isinstance(runtime.store, SnapshotStore)
            revision = runtime.store.read.session_revision
            return replace(
                value,
                scope=self.scope,
                session_revision=revision,
                submission=storage.ScopedSubmission(self.scope, value.submission_token, revision)
                if value.submission_token is not None and revision is not None
                else None,
            )

    def homework_submit(
        self, handle: storage.ScopedSubmission, *, now: datetime | None = None
    ) -> HomeworkArchiveView:
        with workspace_read(self._course.root):
            if not isinstance(handle, storage.ScopedSubmission):
                raise SessionRefusal(
                    RefusalKind.INVALID, "submission-invalid", "use a scoped submission"
                )
            self._check_scope(handle.scope)
            token = storage.SubmissionToken.parse(handle.token)
            if (token.learner_id, token.course_id, token.course_version) != (
                self.scope.learner_id,
                self.scope.course_id,
                self._course.version,
            ):
                raise storage.InvalidSubmissionToken("Token belongs to another stream")
            runtime = self._load(initialize=False)
            assert isinstance(runtime.store, SnapshotStore)
            old = runtime.store.get_submission_receipt(
                self.scope.learner_id, self.scope.course_id, handle.token
            )
            if old is None and handle.session_revision != runtime.store.read.session_revision:
                raise storage.Conflict(
                    "session", handle.session_revision, runtime.store.read.session_revision
                )
            if old is None:
                guard_feedback(runtime)
            return _companion.homework_submit(runtime, handle.token, now or self._now)

    def objectives(self, capabilities: Iterable[Capability] = ()) -> tuple[ObjectiveView, ...]:
        with workspace_read(self._course.root):
            return _companion.objective_views(self._load(), capabilities)

    def settle_objective(
        self,
        objective_id: str,
        capabilities: Iterable[Capability],
        *,
        snapshot: SessionSnapshot,
        checked: str | None = None,
        attested_by: str | None = None,
        now: datetime | None = None,
    ) -> ObjectiveResult:
        with workspace_read(self._course.root):
            runtime = self._load(snapshot=snapshot)
            assert isinstance(runtime.store, SnapshotStore)
            runtime.store.mutation_kind = storage.RecordMutationKind.OBJECTIVE
            return _companion.settle(
                runtime,
                objective_id,
                capabilities,
                checked,
                attested_by,
                snapshot.revision,
                now or self._now,
            )

    def progress(self) -> ProgressView:
        with workspace_read(self._course.root):
            return _companion.progress(self._load())

    def telemetry(
        self, opt_in: bool | None = None, *, snapshot: SessionSnapshot | None = None
    ) -> TelemetryView:
        with workspace_read(self._course.root):
            if opt_in is not None and snapshot is None:
                raise ValueError("Consent mutation requires a captured snapshot")
            runtime = self._load(snapshot=snapshot)
            assert isinstance(runtime.store, SnapshotStore)
            runtime.store.mutation_kind = storage.RecordMutationKind.CONSENT
            return _companion.telemetry(runtime, opt_in)

    def artifact_add(
        self,
        path: Path,
        title: str,
        *,
        snapshot: SessionSnapshot,
        coordinate: str | None = None,
        now: datetime | None = None,
    ) -> ArtifactResult:
        with workspace_read(self._course.root):
            runtime = self._load(initialize=False, snapshot=snapshot)
            assert isinstance(runtime.store, SnapshotStore)
            runtime.store.mutation_kind = storage.RecordMutationKind.ARTIFACT
            absolute = path if path.is_absolute() else self.work_root / path
            if any(
                part.is_symlink()
                for part in (absolute, *absolute.parents)
                if part != self.work_root.parent
            ):
                raise SessionRefusal(
                    RefusalKind.INVALID,
                    "artifact-outside-workspace",
                    "artifact aliases are refused",
                )
            return _workspace.artifact_add(
                runtime,
                path,
                title,
                self.work_root,
                self.work_root,
                coordinate,
                snapshot.revision,
                now or self._now,
            )

    def artifacts(self) -> tuple[ArtifactView, ...]:
        with workspace_read(self._course.root):
            return tuple(_workspace.artifact_view(a) for a in self._load().record.artifacts)

    def ceremony(self, coordinate: str | None = None) -> CeremonyView:
        with workspace_read(self._course.root):
            return _workspace.ceremony(self._load(initialize=False), coordinate, self.work_root)

    def upgrade(self) -> RollForward:
        return self.upgrade_at(self._course.root, store=self._store, scope=self.scope)

    @classmethod
    def upgrade_at(
        cls, course_path: Path, *, store: storage.SessionStore, scope: storage.SessionScope
    ) -> RollForward:
        with workspace_read(course_path):
            course = load_course(course_path)
            if course.id != scope.course_id:
                raise SessionRefusal(
                    RefusalKind.CONFLICT, "scope-binding", "course differs from scope"
                )
            read = storage.validate_read(store.read(scope), scope)
            if read.kind is storage.SessionReadKind.DELETED:
                raise storage.SessionDeleted("Session stream is deleted")
            digest = course_digest(course.root)
            if (
                read.state is not None
                and read.state.record.course_version == course.version
                and read.state.source_digest is not None
                and read.state.source_digest != digest
            ):
                raise SessionRefusal(
                    RefusalKind.CONFLICT,
                    "source-changed",
                    "same-version course changes require an explicit version upgrade",
                )
            return roll_forward(SnapshotStore(store, read, digest), course, scope.learner_id)
