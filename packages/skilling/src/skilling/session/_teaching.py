"""One shared reconstruction and renderer; future quiz material stays private."""

from __future__ import annotations

from typing import NamedTuple

from ..course import (
    Course,
    ParsedLesson,
    QuizQuestion,
    Record,
    ResolvedLesson,
    parse_lesson,
    parse_quiz,
)
from ..delivery import (
    Beat,
    IllegalTransition,
    Input,
    LessonShape,
    LessonState,
    advance,
    legal_inputs,
    should_offer_revisit,
)
from ..store import (
    ActionOperation,
    ActionOrigin,
    AdvanceOutcome,
    OutcomePosition,
    PendingFeedback,
    QuizAnswerOutcome,
    pending_pointer,
)
from ._errors import RefusalKind, SessionRefusal
from ._loading import RuntimeSession, Scratch
from ._types import (
    BeatView,
    CourseView,
    OptionView,
    PositionView,
    PresentationBeat,
    QuestionView,
    SessionSnapshot,
    TrustedAction,
    TutorView,
)


def _shape(course: Course, lesson: ResolvedLesson, parsed: ParsedLesson) -> LessonShape:
    return LessonShape(
        has_exercise=parsed.section("exercise") is not None,
        is_phase_end=course.is_last_in_phase(lesson.coordinate),
    )


def _questions(parsed: ParsedLesson) -> list[QuizQuestion]:
    quiz = parsed.section("quiz")
    return parse_quiz(quiz.body, quiz.body_line) if quiz else []


def _lesson_state(record: Record, scratch: Scratch, shape: LessonShape) -> LessonState:
    """Rebuild the machine's state from what the record and scratch remember.

    Deliberately not ``LessonState.resume`` — that classmethod always resets ``wrong_count``
    and ``returning_to_quiz``, which is correct for the interactive walker's cross-*session*
    resume (a whole lesson delivery lives in one process, so those fields never need to
    survive a restart mid-quiz). These verbs are cross-*process* on every single input, so
    the scratch file is where that residual actually has to survive between calls.
    """
    beat = record.position.beat
    if beat is None or beat not in set(Beat):
        return LessonState.start(shape)
    return LessonState(
        beat=Beat(beat),
        shape=shape,
        question_index=record.position.question_index or 0,
        wrong_count=scratch.wrong_count,
        returning_to_quiz=scratch.returning_to_quiz,
    )


def _course_complete(course: Course, record: Record) -> bool:
    return course.completed_count(record.completed) >= course.lesson_count


def question_view(question: QuizQuestion) -> QuestionView:
    return QuestionView(
        question.number, question.text, tuple(OptionView(o.label, o.text) for o in question.options)
    )


def snapshot_view(
    course: Course,
    record: Record,
    revision: str | None,
    scratch: Scratch,
    pending_feedback: PendingFeedback | None = None,
) -> SessionSnapshot:
    position = record.position
    if _course_complete(course, record):
        beat, legal = BeatView(Beat.DONE), ()
    else:
        lesson = course.lesson_at(record.position.coordinate)
        assert lesson is not None
        parsed = parse_lesson(lesson.path)
        state = _lesson_state(record, scratch, _shape(course, lesson, parsed))
        questions = _questions(parsed)
        fm = parsed.frontmatter
        body = key_terms = objective = None
        objectives = None
        coordinate = title = None
        question = None
        offered = None
        match state.beat:
            case Beat.WELCOME:
                coordinate, title = lesson.coordinate, lesson.title
            case Beat.OBJECTIVES:
                if fm and fm.objectives:
                    objectives = tuple(o.text for o in fm.objectives)
                elif section := parsed.section("objectives"):
                    body = section.body
            case Beat.CONCEPT:
                if section := parsed.section("concept"):
                    body = section.body
                if section := parsed.section("key_terms"):
                    key_terms = section.body
            case Beat.EXERCISE:
                if section := parsed.section("exercise"):
                    body = section.body
            case Beat.QUIZ:
                if state.question_index < len(questions):
                    question = question_view(questions[state.question_index])
            case Beat.REMEDIATE:
                offered = should_offer_revisit(state)
                if fm and fm.objectives and state.question_index < len(questions):
                    matched = fm.objectives_for_question(questions[state.question_index].number)
                    if matched:
                        objective = matched[0].text
        beat = BeatView(
            state.beat,
            coordinate,
            title,
            body,
            objectives,
            key_terms,
            question,
            offered,
            objective,
        )
        legal = legal_inputs(state)
    if pending_feedback is not None:
        beat, legal = BeatView(PresentationBeat.PENDING_FEEDBACK), ()
    tutor = course.manifest.tutor
    return SessionSnapshot(
        CourseView(course.id, course.version, course.manifest.title),
        record.learner_id,
        PositionView(position.phase, position.lesson, position.beat, position.question_index),
        revision,
        beat,
        legal,
        course.completed_count(record.completed),
        course.lesson_count,
        TutorView(tutor.persona, tuple(tutor.tone)) if tutor else None,
        pending_feedback.outcome if pending_feedback else None,
    )


class PreparedAction(NamedTuple):
    record: Record
    scratch: Scratch
    outcome: AdvanceOutcome | QuizAnswerOutcome


def guard_feedback(session: RuntimeSession) -> None:
    if session.pending_feedback is not None:
        raise SessionRefusal(
            RefusalKind.ILLEGAL,
            "pending-feedback",
            "present and acknowledge canonical quiz feedback before continuing",
        )


def prepare_action(session: RuntimeSession, action: TrustedAction) -> PreparedAction:
    """Runtime computes authored semantics; the journal only checks supplied descriptors."""
    guard_feedback(session)
    if _course_complete(session.course, session.record):
        raise SessionRefusal(RefusalKind.ILLEGAL, "course-complete", "the course is complete")
    parsed = parse_lesson(session.lesson.path)
    current = _lesson_state(
        session.record, session.scratch, _shape(session.course, session.lesson, parsed)
    )
    if action.origin is ActionOrigin.PRESENTATION and current.beat not in (
        Beat.WELCOME,
        Beat.OBJECTIVES,
        Beat.CONCEPT,
        Beat.EXERCISE,
    ):
        raise SessionRefusal(
            RefusalKind.ILLEGAL, "presentation-origin", "a gate requires learner control"
        )
    feedback = None
    if action.operation is ActionOperation.ANSWER:
        questions = _questions(parsed)
        if current.beat is not Beat.QUIZ or current.question_index >= len(questions):
            raise SessionRefusal(
                RefusalKind.ILLEGAL, "illegal-transition", "no quiz question is open"
            )
        question = questions[current.question_index]
        if question.number != action.question_number:
            raise SessionRefusal(
                RefusalKind.CONFLICT, "action-binding", "displayed question changed"
            )
        if action.payload not in question.labels:
            raise SessionRefusal(
                RefusalKind.INVALID, "unknown-option", "label is not an authored option"
            )
        correct = action.payload == question.answer_label
        state = advance(current, Input.ANSWER_CORRECT if correct else Input.ANSWER_WRONG)
        fm = parsed.frontmatter
        objectives = (
            tuple(o.text for o in fm.objectives_for_question(question.number))
            if not correct and fm and fm.objectives
            else ()
        )
        feedback = QuizAnswerOutcome(
            question.number,
            action.payload,
            correct,
            question.answer_reason,
            False if correct else should_offer_revisit(state),
            objectives,
        )
    else:
        if current.beat is Beat.QUIZ:
            raise SessionRefusal(
                RefusalKind.ILLEGAL,
                "quiz-answer-required",
                "capture a displayed answer label with the trusted answer operation",
            )
        if current.beat in (Beat.COMPLETE, Beat.CEREMONY):
            raise SessionRefusal(
                RefusalKind.ILLEGAL, "illegal-transition", "complete the finished lesson"
            )
        try:
            state = advance(current, Input(action.payload))
        except IllegalTransition as exc:
            raise SessionRefusal(RefusalKind.ILLEGAL, "illegal-transition", str(exc)) from exc
    position = session.record.position.model_copy(
        update={
            "beat": str(state.beat),
            "question_index": state.question_index
            if state.beat in (Beat.QUIZ, Beat.REMEDIATE)
            else None,
        }
    )
    pointer = pending_pointer(action.identity(), feedback) if feedback else None
    scratch = Scratch(
        state.wrong_count,
        state.returning_to_quiz,
        pending_feedback=pointer,
        presented_feedback=session.scratch.presented_feedback,
    )
    outcome = feedback or AdvanceOutcome(action.payload, OutcomePosition(**position.model_dump()))
    return PreparedAction(
        session.record.model_copy(update={"position": position}), scratch, outcome
    )
