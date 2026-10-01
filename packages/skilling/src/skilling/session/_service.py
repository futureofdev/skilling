"""The trusted, file-backed producer controller facade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..course import Course, QuizQuestion, Record, parse_lesson
from ..delivery import Beat, IllegalTransition, Input, LessonState, should_offer_revisit
from ..delivery import advance as apply_input
from ..store import (
    Conflict,
    IdempotencyKeyConflict,
    TransitionCommit,
    TransitionIdentity,
    TransitionResult,
    TransitionVerb,
)
from ..workspace import workspace_read
from ._errors import RefusalKind, SessionRefusal
from ._loading import RuntimeSession, Scratch, load_runtime, parse_scratch, serialize_scratch
from ._teaching import (
    _course_complete,
    _lesson_state,
    _questions,
    _shape,
    question_view,
    snapshot_view,
)
from ._types import ActionResult, QuestionView, QuizFeedback, SessionSnapshot


def commit_runtime(
    session: RuntimeSession,
    record: Record,
    scratch: Scratch,
    identity: TransitionIdentity,
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
            )
        )
    except IdempotencyKeyConflict as exc:
        raise SessionRefusal(RefusalKind.CONFLICT, "idempotency-key-conflict", str(exc)) from exc
    except Conflict as exc:
        raise SessionRefusal(RefusalKind.CONFLICT, "conflict", str(exc)) from exc


def view(session: RuntimeSession) -> SessionSnapshot:
    return snapshot_view(session.course, session.record, session.revision, session.scratch)


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

    def _load(self) -> RuntimeSession:
        return load_runtime(
            self._course,
            self._state_root,
            self._learner_id,
            initialize=self._initialize,
            now=self._now,
        )

    def snapshot(self) -> SessionSnapshot:
        with workspace_read(self._course.root):
            return view(self._load())

    def question(self) -> QuestionView:
        with workspace_read(self._course.root):
            session = self._load()
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
                        return ActionResult(view(committed_session(session, result)), True)
                except IdempotencyKeyConflict as exc:
                    raise SessionRefusal(
                        RefusalKind.CONFLICT, "idempotency-key-conflict", str(exc)
                    ) from exc
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
