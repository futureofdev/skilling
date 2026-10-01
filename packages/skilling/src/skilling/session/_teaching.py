"""One shared reconstruction and renderer; future quiz material stays private."""

from __future__ import annotations

from ..course import (
    Course,
    ParsedLesson,
    QuizQuestion,
    Record,
    ResolvedLesson,
    parse_lesson,
    parse_quiz,
)
from ..delivery import Beat, LessonShape, LessonState, legal_inputs, should_offer_revisit
from ._loading import Scratch
from ._types import (
    BeatView,
    CourseView,
    OptionView,
    PositionView,
    QuestionView,
    SessionSnapshot,
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
    course: Course, record: Record, revision: str | None, scratch: Scratch
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
    )
