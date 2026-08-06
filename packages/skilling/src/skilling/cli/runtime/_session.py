"""The session verbs: ``next``, ``advance``, ``complete``, ``ceremony``.

One process, one transition, one line of JSON on stdout — never anything else, so a driving
pack can pipe this straight into a parser without scraping prose. ``advance`` drives the pure
per-beat walk (welcome through remediate); reaching the completion beat is where the pure
machine's job ends and ``complete`` — which alone knows how to write the completion write set
— takes over. ``ceremony`` is read-only, presentational, and keyed off the most recently
completed lesson rather than the record's current position, because by the time a phase
boundary is worth showing, ``complete`` has already moved the position past it.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import (
    Course,
    ParsedLesson,
    QuizQuestion,
    Record,
    ResolvedLesson,
    parse_lesson,
    parse_quiz,
)
from ...delivery import (
    Beat,
    IllegalTransition,
    Input,
    LessonShape,
    LessonState,
    complete_lesson,
    legal_inputs,
    share_text,
    should_offer_revisit,
)
from ...delivery import advance as apply_input
from ...store import LOCAL_LEARNER, Conflict
from ._common import ExitCode, Scratch, emit, fail, now_override, open_session, save_scratch

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)


# ------------------------------------------------------------------------------- reading state


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


# ------------------------------------------------------------------------------ beat rendering


def _section_content(parsed: ParsedLesson, slot: str) -> dict[str, object]:
    section = parsed.section(slot)
    return {"body": section.body} if section else {}


def _objectives_content(parsed: ParsedLesson) -> dict[str, object]:
    fm = parsed.frontmatter
    if fm and fm.objectives:
        return {"objectives": [o.text for o in fm.objectives]}
    if section := parsed.section("objectives"):
        return {"body": section.body}
    return {}


def _concept_content(parsed: ParsedLesson) -> dict[str, object]:
    content: dict[str, object] = {}
    if section := parsed.section("concept"):
        content["body"] = section.body
    if terms := parsed.section("key_terms"):
        content["key_terms"] = terms.body
    return content


def _quiz_content(state: LessonState, questions: list[QuizQuestion]) -> dict[str, object]:
    index = state.question_index
    if index >= len(questions):
        return {}
    question = questions[index]
    return {
        "number": question.number,
        "text": question.text,
        "options": [{"label": o.label, "text": o.text} for o in question.options],
    }


def _remediate_content(
    state: LessonState, parsed: ParsedLesson, questions: list[QuizQuestion]
) -> dict[str, object]:
    content: dict[str, object] = {"offer_revisit": should_offer_revisit(state)}
    fm = parsed.frontmatter
    index = state.question_index
    if fm and fm.objectives and index < len(questions):
        matched = fm.objectives_for_question(questions[index].number)
        if matched:
            content["objective"] = matched[0].text
    return content


def _beat_content(
    state: LessonState,
    lesson: ResolvedLesson,
    parsed: ParsedLesson,
    questions: list[QuizQuestion],
) -> dict[str, object]:
    """Only what ``next`` needs to print a beat — nothing speculative beyond it."""
    match state.beat:
        case Beat.WELCOME:
            return {"coordinate": lesson.coordinate, "title": lesson.title}
        case Beat.OBJECTIVES:
            return _objectives_content(parsed)
        case Beat.CONCEPT:
            return _concept_content(parsed)
        case Beat.EXERCISE:
            return _section_content(parsed, "exercise")
        case Beat.QUIZ:
            return _quiz_content(state, questions)
        case Beat.REMEDIATE:
            return _remediate_content(state, parsed, questions)
        case _:
            return {}


# --------------------------------------------------------------------------------- the envelope


def _envelope(
    verb: str,
    course: Course,
    record: Record,
    revision: str | None,
    *,
    beat_name: str,
    content: dict[str, object],
    legal: tuple[Input, ...],
) -> dict[str, object]:
    """Shared by ``next``/``advance``/``complete``/``ceremony``.

    ``course.title`` and the top-level ``tutor`` block are sourced straight from the
    manifest already loaded to build this response — never a second lookup. ``tutor`` is
    ``None`` when the manifest declares none; a driving skill falls back to a neutral
    voice rather than inventing a persona.
    """
    return {
        "ok": True,
        "verb": verb,
        "course": {
            "id": course.id,
            "title": course.manifest.title,
            "version": course.version,
        },
        "tutor": course.manifest.tutor.model_dump() if course.manifest.tutor else None,
        "position": {
            "phase": record.position.phase,
            "lesson": record.position.lesson,
            "beat": record.position.beat,
            "question_index": record.position.question_index,
        },
        "beat": {"name": beat_name, "content": content},
        "legal_inputs": [str(i) for i in legal],
        "revision": revision,
        "completed_count": course.completed_count(record.completed),
        "lesson_count": course.lesson_count,
    }


def _resume_envelope(
    verb: str, course: Course, record: Record, revision: str | None, scratch: Scratch
) -> dict[str, object]:
    """The envelope for "here is where the record now stands" — shared by every verb, since
    ``advance``, ``complete``, and ``ceremony`` all report it alongside whatever else they add."""
    if _course_complete(course, record):
        return _envelope(verb, course, record, revision, beat_name="done", content={}, legal=())

    lesson = course.lesson_at(record.position.coordinate)
    if lesson is None:
        fail(
            ExitCode.INVALID,
            "position-invalid",
            f"{record.position.coordinate} is not a lesson in {course.id}",
        )
    parsed = parse_lesson(lesson.path)
    shape = _shape(course, lesson, parsed)
    state = _lesson_state(record, scratch, shape)
    questions = _questions(parsed)
    return _envelope(
        verb,
        course,
        record,
        revision,
        beat_name=str(state.beat),
        content=_beat_content(state, lesson, parsed, questions),
        legal=legal_inputs(state),
    )


# --------------------------------------------------------------------------------------- next


def next(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Resume info: the current beat's content and the inputs legal from here. Read-only."""
    session = open_session(course, state, learner)
    emit(
        _resume_envelope("next", session.course, session.record, session.revision, session.scratch)
    )


# ------------------------------------------------------------------------------------ advance


def advance(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
    given_input: str = typer.Option(..., "--input", help="The Input this transition applies."),
    key: str | None = typer.Option(
        None, "--key", help="Idempotency key: a repeated key exits 0 without reapplying."
    ),
) -> None:
    """Apply exactly one transition and persist the resulting position."""
    session = open_session(course, state, learner)

    if key is not None and key == session.scratch.last_key:
        assert session.scratch.last_result is not None
        emit(session.scratch.last_result)
        return

    if _course_complete(session.course, session.record):
        fail(ExitCode.ILLEGAL, "course-complete", "the course is complete — nothing to advance")

    lesson = session.lesson
    parsed = parse_lesson(lesson.path)
    shape = _shape(session.course, lesson, parsed)
    current = _lesson_state(session.record, session.scratch, shape)

    if current.beat in (Beat.COMPLETE, Beat.CEREMONY):
        fail(
            ExitCode.ILLEGAL,
            "illegal-transition",
            f"{current.beat!s} is finished by 'skilling complete'/'skilling ceremony', "
            "not 'advance'",
        )

    try:
        given = Input(given_input)
    except ValueError:
        fail(ExitCode.INVALID, "unknown-input", f"{given_input!r} is not a recognised input")

    try:
        new_state = apply_input(current, given)
    except IllegalTransition as exc:
        fail(ExitCode.ILLEGAL, "illegal-transition", str(exc))

    new_position = session.record.position.model_copy(
        update={
            "beat": str(new_state.beat),
            "question_index": (
                new_state.question_index if new_state.beat in (Beat.QUIZ, Beat.REMEDIATE) else None
            ),
        }
    )
    updated_record = session.record.model_copy(update={"position": new_position})

    try:
        new_revision = session.store.put_record(updated_record, session.revision)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))

    questions = _questions(parsed)
    envelope = _envelope(
        "advance",
        session.course,
        updated_record,
        new_revision,
        beat_name=str(new_state.beat),
        content=_beat_content(new_state, lesson, parsed, questions),
        legal=legal_inputs(new_state),
    )

    save_scratch(
        session,
        Scratch(
            wrong_count=new_state.wrong_count,
            returning_to_quiz=new_state.returning_to_quiz,
            last_key=key if key is not None else session.scratch.last_key,
            last_result=envelope if key is not None else session.scratch.last_result,
        ),
    )
    emit(envelope)


# ----------------------------------------------------------------------------------- complete


def complete(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Complete the current lesson: the write set, done once and idempotent after.

    A retried call after position has already moved on replays against the coordinate that
    was actually completed (``record.completed[-1]``), not the new one, so
    ``complete_lesson``'s own idempotency (checking ``has_completed``) is what answers it —
    not a second, separate cache.
    """
    session = open_session(course, state, learner)
    lesson = session.lesson
    parsed = parse_lesson(lesson.path)
    shape = _shape(session.course, lesson, parsed)
    current = _lesson_state(session.record, session.scratch, shape)

    if current.beat is not Beat.COMPLETE:
        if not session.record.completed:
            fail(
                ExitCode.ILLEGAL,
                "illegal-transition",
                f"the lesson is at {current.beat!s}, not the completion beat",
            )
        replay = session.course.lesson_at(session.record.completed[-1])
        assert replay is not None
        lesson = replay

    try:
        outcome = complete_lesson(
            session.store,
            session.course,
            session.record,
            session.revision,
            lesson,
            now=now_override(),
        )
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))

    if not outcome.already_completed:
        save_scratch(
            session,
            Scratch(last_key=session.scratch.last_key, last_result=session.scratch.last_result),
        )

    envelope = _resume_envelope(
        "complete", session.course, outcome.record, outcome.revision, session.scratch
    )
    envelope.update(
        {
            "already_completed": outcome.already_completed,
            "badges_awarded": outcome.badges_awarded,
            "phase_completed": outcome.phase_completed,
            "homework_placed": outcome.homework_placed,
            "homework_queued": outcome.homework_queued,
        }
    )
    emit(envelope)


# ----------------------------------------------------------------------------------- ceremony


def ceremony(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Resolved ceremony facts and copy for the phase the learner just finished.

    Keyed off ``record.completed[-1]`` rather than the record's current position: by the
    time a ceremony is worth showing, ``complete`` has already moved the position on to the
    next lesson (or a following phase entirely), so "the position" cannot be where this looks.
    """
    session = open_session(course, state, learner)

    if not session.record.completed:
        fail(ExitCode.ILLEGAL, "not-a-phase-boundary", "no lesson has been completed yet")

    coordinate = session.record.completed[-1]
    finished = session.course.lesson_at(coordinate)
    if finished is None or not session.course.is_last_in_phase(coordinate):
        fail(
            ExitCode.ILLEGAL,
            "not-a-phase-boundary",
            f"{coordinate} is not the last lesson of its phase",
        )

    phase = session.course.phase_of(coordinate)
    course_complete = _course_complete(session.course, session.record)
    text = share_text(session.course, session.record, phase, course_complete=course_complete)

    envelope = _resume_envelope(
        "ceremony", session.course, session.record, session.revision, session.scratch
    )
    envelope["beat"] = {
        "name": "ceremony",
        "content": {
            "coordinate": coordinate,
            "phase_number": phase.number if phase else None,
            "phase_name": phase.name if phase else None,
            "phase_highlight": phase.highlight if phase else None,
            "share_text": text,
            "course_complete": course_complete,
        },
    }
    emit(envelope)
