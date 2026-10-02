"""The trusted, file-backed producer controller facade."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import yaml

from ..course import Capability, Course, QuizQuestion, Record, parse_lesson
from ..delivery import Beat, IllegalTransition, Input, LessonState, should_offer_revisit
from ..delivery import advance as apply_input
from ..store import (
    ActionIdentity,
    AdvanceOutcome,
    Conflict,
    IdempotencyKeyConflict,
    InvalidSubmissionToken,
    LegacyOutcomeUnavailable,
    QuizAnswerOutcome,
    RecoveryRequired,
    SubmissionToken,
    TransitionCommit,
    TransitionIdentity,
    TransitionResult,
    TransitionVerb,
)
from ..workspace import workspace_read
from . import _companion, _workspace
from ._errors import RefusalKind, SessionRefusal
from ._loading import RuntimeSession, Scratch, load_runtime, parse_scratch, serialize_scratch
from ._teaching import (
    _course_complete,
    _lesson_state,
    _questions,
    _shape,
    guard_feedback,
    prepare_action,
    question_view,
    snapshot_view,
)
from ._types import (
    ActionResult,
    ArtifactResult,
    ArtifactView,
    CeremonyView,
    CompletionResult,
    CourseView,
    FeedbackAcknowledgement,
    FeedbackRef,
    HomeworkArchiveView,
    HomeworkCheck,
    ObjectiveResult,
    ObjectiveView,
    PendingFeedback,
    ProgressView,
    QuestionView,
    QuizFeedback,
    SessionSnapshot,
    TelemetryView,
    TrustedAction,
)


def commit_runtime(
    session: RuntimeSession,
    record: Record,
    scratch: Scratch,
    identity: TransitionIdentity | ActionIdentity,
    outcome: AdvanceOutcome | QuizAnswerOutcome | None = None,
) -> TransitionResult:
    if session.revision is None:
        raise SessionRefusal(
            RefusalKind.ILLEGAL, "record-missing", "initialize the session before writing"
        )
    try:
        return session.store.commit_transition(
            TransitionCommit(
                identity,
                session.revision,
                session.scratch_bytes,
                record,
                serialize_scratch(scratch),
                outcome,
            )
        )
    except IdempotencyKeyConflict as exc:
        raise SessionRefusal(RefusalKind.CONFLICT, "idempotency-key-conflict", str(exc)) from exc
    except Conflict as exc:
        raise SessionRefusal(RefusalKind.CONFLICT, "conflict", str(exc)) from exc


def view(session: RuntimeSession) -> SessionSnapshot:
    return snapshot_view(
        session.course, session.record, session.revision, session.scratch, session.pending_feedback
    )


def committed_session(session: RuntimeSession, result: TransitionResult) -> RuntimeSession:
    snapshot = result.snapshot
    lesson = session.course.lesson_at(snapshot.record.position.coordinate)
    if lesson is None:
        raise SessionRefusal(
            RefusalKind.INVALID, "position-invalid", "current lesson does not exist"
        )
    return RuntimeSession(
        session.course,
        lesson,
        session.store,
        snapshot.record,
        snapshot.revision,
        parse_scratch(snapshot.scratch),
        snapshot.scratch,
        snapshot.feedback,
    )


@dataclass(frozen=True)
class FileSession:
    """Trusted action authority. Keep this object out of model dependencies and prompts."""

    _course: Course
    _state_root: Path
    _learner_id: str
    _workspace_root: Path | None
    _initialize: bool
    _now: datetime | None

    @classmethod
    def open(
        cls,
        course: Course,
        *,
        state_root: Path,
        learner_id: str,
        workspace_root: Path | None = None,
        initialize: bool = True,
        now: datetime | None = None,
    ) -> FileSession:
        if not isinstance(course, Course) or not course.root.is_absolute():
            raise SessionRefusal(
                RefusalKind.INVALID, "course-invalid", "a loaded absolute course is required"
            )
        if workspace_root is not None and (
            not workspace_root.is_absolute()
            or not course.root.resolve().is_relative_to(workspace_root.resolve())
        ):
            raise SessionRefusal(
                RefusalKind.INVALID, "course-invalid", "course is outside workspace"
            )
        service = cls(course, state_root, learner_id, workspace_root, initialize, now)
        with workspace_read(course.root):
            service._load()
        return service

    @property
    def course(self) -> CourseView:
        """Copied identity metadata; no raw Course crosses this boundary."""
        return _companion.course_view(self._course)

    def _load(self, *, initialize: bool | None = None) -> RuntimeSession:
        return load_runtime(
            self._course,
            self._state_root,
            self._learner_id,
            initialize=self._initialize if initialize is None else initialize,
            now=self._now,
        )

    def snapshot(self) -> SessionSnapshot:
        with workspace_read(self._course.root):
            return view(self._load())

    def question(self) -> QuestionView:
        with workspace_read(self._course.root):
            session = self._load()
            guard_feedback(session)
            parsed = parse_lesson(session.lesson.path)
            current = _lesson_state(
                session.record, session.scratch, _shape(session.course, session.lesson, parsed)
            )
            return question_view(
                self._open_question(current.beat, current.question_index, _questions(parsed))
            )

    @staticmethod
    def _open_question(beat: Beat, index: int, questions: list[QuizQuestion]) -> QuizQuestion:
        if beat is not Beat.QUIZ:
            raise SessionRefusal(
                RefusalKind.ILLEGAL,
                "illegal-transition",
                f"the lesson is at {beat!s}, not the quiz beat",
            )
        if index >= len(questions):
            raise SessionRefusal(RefusalKind.ILLEGAL, "quiz-finished", "no question is open")
        return questions[index]

    def act(self, action: TrustedAction) -> ActionResult:
        """Retry one complete captured identity; never silently rebase a new learner event."""
        try:
            if not isinstance(action, TrustedAction):
                raise ValueError("action must be a TrustedAction captured by the controller")
            identity = action.identity()
            action = replace(action, origin=identity.origin, operation=identity.verb)
        except (ValueError, TypeError, AttributeError) as exc:
            raise SessionRefusal(RefusalKind.INVALID, "action-invalid", str(exc)) from exc
        if (identity.learner_id, identity.course_id, identity.course_version) != (
            self._learner_id,
            self._course.id,
            self._course.version,
        ):
            raise SessionRefusal(
                RefusalKind.CONFLICT, "action-binding", "action belongs to another stream"
            )
        with workspace_read(self._course.root):
            session = self._load()
            _companion.require_record(session)
            try:
                replay = session.store.get_action_result(identity)
                if replay is not None:
                    return ActionResult(
                        view(committed_session(session, replay)), True, replay.outcome
                    )
                previous = session.store.get_transition_identity(
                    self._learner_id, self._course.id, action.event_id
                )
                if previous is not None:
                    raise IdempotencyKeyConflict(
                        "Version-one key has no full trusted action identity"
                    )
            except IdempotencyKeyConflict as exc:
                raise SessionRefusal(
                    RefusalKind.CONFLICT, "idempotency-key-conflict", str(exc)
                ) from exc
            if session.revision != action.expected_revision:
                raise SessionRefusal(
                    RefusalKind.CONFLICT, "conflict", "captured record revision is stale"
                )
            if session.lesson.coordinate != action.coordinate:
                raise SessionRefusal(
                    RefusalKind.CONFLICT, "action-binding", "captured coordinate changed"
                )
            prepared = prepare_action(session, action)
            result = commit_runtime(
                session, prepared.record, prepared.scratch, identity, prepared.outcome
            )
            return ActionResult(
                view(committed_session(session, result)), result.replayed, result.outcome
            )

    @classmethod
    def pending_feedback_at(
        cls, *, state_root: Path, learner_id: str, course_id: str
    ) -> PendingFeedback | None:
        """Read recorded-version feedback without selected course content or a remembered key."""
        from ._loading import file_store

        return file_store(state_root).pending_feedback(learner_id, course_id)

    def pending_feedback(self) -> PendingFeedback | None:
        return self.pending_feedback_at(
            state_root=self._state_root, learner_id=self._learner_id, course_id=self._course.id
        )

    @classmethod
    def acknowledge_feedback_at(
        cls,
        feedback_id: FeedbackRef,
        expected_revision: str,
        *,
        state_root: Path,
        learner_id: str,
        course_id: str,
    ) -> FeedbackAcknowledgement:
        from ._loading import file_store

        if not isinstance(feedback_id, FeedbackRef) or (
            feedback_id._learner_id,
            feedback_id._course_id,
        ) != (learner_id, course_id):
            raise SessionRefusal(
                RefusalKind.CONFLICT, "feedback-binding", "feedback belongs to another stream"
            )
        return file_store(state_root).acknowledge_feedback(feedback_id, expected_revision)

    def acknowledge_feedback(
        self, feedback_id: FeedbackRef, expected_revision: str
    ) -> FeedbackAcknowledgement:
        return self.acknowledge_feedback_at(
            feedback_id,
            expected_revision,
            state_root=self._state_root,
            learner_id=self._learner_id,
            course_id=self._course.id,
        )

    def advance(self, input: Input | str, *, event_id: str | None = None) -> ActionResult:
        with workspace_read(self._course.root):
            session = self._load()
            given_input = str(input)
            if event_id is not None:
                try:
                    previous = session.store.get_transition_identity(
                        self._learner_id, session.course.id, event_id
                    )
                    if previous is not None:
                        if previous.verb != "advance" or previous.input != given_input:
                            raise IdempotencyKeyConflict("Key already belongs to a different input")
                        result = commit_runtime(session, session.record, session.scratch, previous)
                        return ActionResult(
                            view(committed_session(session, result)),
                            True,
                            LegacyOutcomeUnavailable(),
                        )
                except IdempotencyKeyConflict as exc:
                    raise SessionRefusal(
                        RefusalKind.CONFLICT, "idempotency-key-conflict", str(exc)
                    ) from exc
            guard_feedback(session)
            if _course_complete(session.course, session.record):
                raise SessionRefusal(
                    RefusalKind.ILLEGAL,
                    "course-complete",
                    "the course is complete — nothing to advance",
                )
            parsed = parse_lesson(session.lesson.path)
            current = _lesson_state(
                session.record, session.scratch, _shape(session.course, session.lesson, parsed)
            )
            if current.beat in (Beat.COMPLETE, Beat.CEREMONY):
                raise SessionRefusal(
                    RefusalKind.ILLEGAL,
                    "illegal-transition",
                    f"{current.beat!s} is finished by 'skilling complete'/'skilling ceremony', "
                    "not 'advance'",
                )
            try:
                given = Input(given_input)
            except ValueError as exc:
                raise SessionRefusal(
                    RefusalKind.INVALID,
                    "unknown-input",
                    f"{given_input!r} is not a recognised input",
                ) from exc
            try:
                state = apply_input(current, given)
            except IllegalTransition as exc:
                raise SessionRefusal(RefusalKind.ILLEGAL, "illegal-transition", str(exc)) from exc
            result = self._commit_state(
                session, state, TransitionVerb.ADVANCE, given_input, event_id
            )
            return ActionResult(view(committed_session(session, result)), result.replayed)

    def answer(self, label: str) -> QuizFeedback:
        """Unkeyed compatibility answer. Repetition is a new action, not a safe retry."""
        with workspace_read(self._course.root):
            session = self._load()
            guard_feedback(session)
            parsed = parse_lesson(session.lesson.path)
            current = _lesson_state(
                session.record, session.scratch, _shape(session.course, session.lesson, parsed)
            )
            question = self._open_question(current.beat, current.question_index, _questions(parsed))
            normalized = label.strip().lower()
            if normalized not in question.labels:
                raise SessionRefusal(
                    RefusalKind.INVALID,
                    "unknown-option",
                    f"{label!r} is not one of the options for question {question.number}",
                )
            correct = normalized == question.answer_label
            state = apply_input(current, Input.ANSWER_CORRECT if correct else Input.ANSWER_WRONG)
            self._commit_state(session, state, TransitionVerb.ANSWER, normalized, None)
            fm = parsed.frontmatter
            objectives = (
                tuple(o.text for o in fm.objectives_for_question(question.number))
                if not correct and fm and fm.objectives
                else ()
            )
            return QuizFeedback(
                correct,
                question.answer_reason,
                False if correct else should_offer_revisit(state),
                objectives,
            )

    def _commit_state(
        self,
        session: RuntimeSession,
        state: LessonState,
        verb: TransitionVerb,
        payload: str,
        key: str | None,
    ) -> TransitionResult:
        position = session.record.position.model_copy(
            update={
                "beat": str(state.beat),
                "question_index": state.question_index
                if state.beat in (Beat.QUIZ, Beat.REMEDIATE)
                else None,
            }
        )
        return commit_runtime(
            session,
            session.record.model_copy(update={"position": position}),
            Scratch(wrong_count=state.wrong_count, returning_to_quiz=state.returning_to_quiz),
            TransitionIdentity(
                self._learner_id,
                session.course.id,
                session.course.version,
                session.lesson.coordinate,
                verb,
                payload,
                key,
            ),
        )

    def _chronology_load(self) -> RuntimeSession:
        try:
            return self._load(initialize=False)
        except (RecoveryRequired, ValueError, TypeError, OSError, yaml.YAMLError) as exc:
            raise SessionRefusal(
                RefusalKind.INVALID, "chronology-invalid", f"cannot read completion history: {exc}"
            ) from exc

    def complete(
        self, expected_revision: str | None, *, now: datetime | None = None
    ) -> CompletionResult:
        with workspace_read(self._course.root):
            session = self._load()
            guard_feedback(session)
            return _companion.complete(session, expected_revision, now or self._now)

    def ceremony(
        self, coordinate: str | None = None, *, workspace_root: Path | None = None
    ) -> CeremonyView:
        with workspace_read(self._course.root):
            return _workspace.ceremony(
                self._chronology_load(), coordinate, workspace_root or self._workspace_root
            )

    def homework_check(self) -> HomeworkCheck:
        """Read the active assignment and controller-only token; no evaluation or consent."""
        with workspace_read(self._course.root):
            session = self._load(initialize=False)
            guard_feedback(session)
            return _companion.homework_check(session)

    def homework_submit(self, token: str, *, now: datetime | None = None) -> HomeworkArchiveView:
        # Validate token binding before recovery or any learner-state access.
        identity = SubmissionToken.parse(token)
        if (identity.learner_id, identity.course_id, identity.course_version) != (
            self._learner_id,
            self._course.id,
            self._course.version,
        ):
            raise InvalidSubmissionToken("Token belongs to a different record stream")
        with workspace_read(self._course.root):
            session = self._load(initialize=False)
            guard_feedback(session)
            return _companion.homework_submit(session, token, now or self._now)

    def objectives(self, capabilities: Iterable[Capability] = ()) -> tuple[ObjectiveView, ...]:
        with workspace_read(self._course.root):
            return _companion.objective_views(self._load(), capabilities)

    def settle_objective(
        self,
        objective_id: str,
        capabilities: Iterable[Capability],
        *,
        checked: str | None = None,
        attested_by: str | None = None,
        expected_revision: str | None = None,
        now: datetime | None = None,
    ) -> ObjectiveResult:
        with workspace_read(self._course.root):
            return _companion.settle(
                self._load(),
                objective_id,
                capabilities,
                checked,
                attested_by,
                expected_revision,
                now or self._now,
            )

    def progress(self) -> ProgressView:
        with workspace_read(self._course.root):
            return _companion.progress(self._load())

    def telemetry(self, opt_in: bool | None = None) -> TelemetryView:
        """None reads the ternary answer; bool records actual learner consent via CAS."""
        with workspace_read(self._course.root):
            return _companion.telemetry(self._load(), opt_in)

    def artifact_add(
        self,
        path: Path,
        title: str,
        *,
        workspace_root: Path,
        path_base: Path,
        coordinate: str | None = None,
        expected_revision: str | None = None,
        now: datetime | None = None,
    ) -> ArtifactResult:
        with workspace_read(self._course.root):
            return _workspace.artifact_add(
                self._chronology_load(),
                path,
                title,
                workspace_root,
                path_base,
                coordinate,
                expected_revision,
                now or self._now,
            )

    def artifacts(self) -> tuple[ArtifactView, ...]:
        with workspace_read(self._course.root):
            return tuple(_workspace.artifact_view(a) for a in self._load().record.artifacts)
