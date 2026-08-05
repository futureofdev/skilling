"""The completion write set: what it writes, in what order, and what it refuses to repeat."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from skilling import delivery as runtime
from skilling.course import Course, Record
from skilling.store import LOCAL_LEARNER, Conflict, FileProgressStore

NOW = datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> FileProgressStore:
    return FileProgressStore(tmp_path / "state")


def _fresh(store: FileProgressStore, course: Course) -> tuple[Record, str | None]:
    return runtime.load_or_create(store, course, LOCAL_LEARNER, now=NOW)


# ------------------------------------------------------------------------------- streak


@pytest.mark.parametrize(
    ("last", "current", "expected", "why"),
    [
        (date(2026, 8, 2), 3, 4, "yesterday increments"),
        (date(2026, 8, 3), 3, 3, "same day is unchanged"),
        (date(2026, 7, 28), 9, 1, "a gap resets to one"),
        (None, 5, 1, "never active resets to one"),
        (date(2026, 8, 3), 0, 1, "a first completion today counts as one"),
    ],
)
def test_streak_algorithm(last: date | None, current: int, expected: int, why: str) -> None:
    assert runtime.next_streak(last, date(2026, 8, 3), current) == expected, why


def test_streak_is_counted_in_the_records_timezone() -> None:
    late = datetime(2026, 8, 3, 23, 30, tzinfo=UTC)
    assert runtime.today_in("UTC", late) == date(2026, 8, 3)
    assert runtime.today_in("Pacific/Auckland", late) == date(2026, 8, 4)


def test_an_unknown_timezone_falls_back_to_utc_rather_than_failing() -> None:
    assert runtime.today_in("Mars/Olympus", NOW) == date(2026, 8, 3)


# --------------------------------------------------------------------------- new records


def test_a_new_record_starts_at_the_first_lesson(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    assert record.position.coordinate == "0.1"
    assert record.completed == []
    assert record.streak_days == 0
    assert revision


def test_load_or_create_is_stable_across_calls(store: FileProgressStore, clean: Course) -> None:
    first, _ = _fresh(store, clean)
    second, _ = _fresh(store, clean)
    assert first == second


# ---------------------------------------------------------------------------- completion


def test_completion_writes_the_whole_set(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    lesson = clean.lesson_at("0.1")
    assert lesson

    outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)

    assert not outcome.already_completed
    assert outcome.record.completed == ["0.1"]
    assert outcome.record.position.coordinate == "0.2"
    assert outcome.record.last_activity == date(2026, 8, 3)
    assert outcome.record.streak_days == 1

    log = store.get_log(LOCAL_LEARNER, clean.id)
    assert [e.coordinate for e in log] == ["0.1"]
    assert log[0].title == "One"
    assert log[0].course_version == "1.0.0"


def test_declared_badges_reach_the_record(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    for coordinate in ("0.1", "0.2"):
        lesson = clean.lesson_at(coordinate)
        assert lesson
        outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)
        record, revision = outcome.record, outcome.revision

    assert record.skills_unlocked == ["alpha"]


def test_completion_is_idempotent(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    lesson = clean.lesson_at("0.1")
    assert lesson

    first = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)
    later = NOW + timedelta(days=1)
    second = runtime.complete_lesson(store, clean, first.record, first.revision, lesson, now=later)

    assert second.already_completed
    assert second.record.completed == ["0.1"]
    assert second.record.streak_days == 1, "a revisit must not extend a streak"
    assert second.record.last_activity == date(2026, 8, 3)
    assert len(store.get_log(LOCAL_LEARNER, clean.id)) == 1


def test_position_never_leaves_the_manifest(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    for coordinate in clean.coordinates:
        lesson = clean.lesson_at(coordinate)
        assert lesson
        outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)
        record, revision = outcome.record, outcome.revision
        assert clean.lesson_at(record.position.coordinate) is not None

    assert record.position.coordinate == clean.coordinates[-1]


def test_the_log_is_written_before_the_record(store: FileProgressStore, clean: Course) -> None:
    """No observable state may show a completion without its log entry.

    The file backend cannot write both atomically, so it must write the log first. A store
    that fails on the record write should leave a log entry and an unchanged record — never
    the other way round.
    """
    record, revision = _fresh(store, clean)
    lesson = clean.lesson_at("0.1")
    assert lesson

    class RecordWritesFail(type(store)):  # type: ignore[misc]
        def put_record(self, record, expected_revision):  # noqa: ANN001, ANN201
            raise Conflict("record.yaml", expected_revision, "someone-else")

    breaking = RecordWritesFail(store.state_root)
    with pytest.raises(Conflict):
        runtime.complete_lesson(breaking, clean, record, revision, lesson, now=NOW)

    assert [e.coordinate for e in store.get_log(LOCAL_LEARNER, clean.id)] == ["0.1"]
    reread = store.get_record(LOCAL_LEARNER, clean.id)
    assert reread is not None
    assert reread[0].completed == [], "the record must not show a completion it failed to write"


# ------------------------------------------------------------------------------ ceremony


def test_finishing_a_phase_fills_the_homework_slot(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    for coordinate in ("0.1", "0.2"):
        lesson = clean.lesson_at(coordinate)
        assert lesson
        outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)
        record, revision = outcome.record, outcome.revision

    assert outcome.phase_completed == 0
    assert outcome.homework_placed

    slot, _ = store.get_homework(LOCAL_LEARNER, clean.id)
    assert slot is not None
    assert slot.coordinate == "0.2"
    assert slot.title == "Practise Both Things"
    assert [r.text for r in slot.requirements] == ["Use the first thing", "Use the second thing"]
    assert [g.text for g in slot.stretch_goals] == ["Use them at the same time"]
    assert all(r.verdict is None for r in slot.requirements), "an unchecked slot has no verdicts"


def test_phase_completion_is_derived_not_stored(store: FileProgressStore, clean: Course) -> None:
    record, revision = _fresh(store, clean)
    assert not clean.phase_is_complete(0, record.completed)
    for coordinate in ("0.1", "0.2"):
        lesson = clean.lesson_at(coordinate)
        assert lesson
        outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)
        record, revision = outcome.record, outcome.revision

    assert clean.phase_is_complete(0, record.completed)
    assert "phase" not in {f for f in Record.model_fields if f.startswith("phases")}


def test_a_mid_course_lesson_does_not_fire_ceremony(
    store: FileProgressStore, clean: Course
) -> None:
    record, revision = _fresh(store, clean)
    lesson = clean.lesson_at("0.1")
    assert lesson
    outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)
    assert outcome.phase_completed is None
    assert not outcome.homework_placed


# ------------------------------------------------------------------------------ homework


def _finish_phase_zero(store: FileProgressStore, course: Course):
    record, revision = _fresh(store, course)
    outcome = None
    for coordinate in ("0.1", "0.2"):
        lesson = course.lesson_at(coordinate)
        assert lesson
        outcome = runtime.complete_lesson(store, course, record, revision, lesson, now=NOW)
        record, revision = outcome.record, outcome.revision
    return record, revision


def test_submitting_archives_and_clears_the_slot(store: FileProgressStore, clean: Course) -> None:
    _finish_phase_zero(store, clean)

    entry = runtime.submit_homework(store, LOCAL_LEARNER, clean.id, "0.2", now=NOW)
    assert entry is not None
    assert entry.coordinate == "0.2"

    assert store.get_homework(LOCAL_LEARNER, clean.id) == (None, None)
    assert [e.coordinate for e in store.get_homework_archive(LOCAL_LEARNER, clean.id)] == ["0.2"]


def test_submitting_twice_is_a_no_op_that_returns_the_archived_result(
    store: FileProgressStore, clean: Course
) -> None:
    _finish_phase_zero(store, clean)
    first = runtime.submit_homework(store, LOCAL_LEARNER, clean.id, "0.2", now=NOW)
    second = runtime.submit_homework(store, LOCAL_LEARNER, clean.id, "0.2", now=NOW)

    assert first == second
    assert len(store.get_homework_archive(LOCAL_LEARNER, clean.id)) == 1


def test_submitting_something_that_was_never_assigned_returns_nothing(
    store: FileProgressStore, clean: Course
) -> None:
    assert runtime.submit_homework(store, LOCAL_LEARNER, clean.id, "9.9", now=NOW) is None


def test_a_second_assignment_queues_rather_than_overwriting(
    store: FileProgressStore, clean: Course
) -> None:
    record, revision = _finish_phase_zero(store, clean)

    # Pretend a later phase also carries homework by re-running ceremony for the same lesson
    # against a record that has not submitted the first assignment.
    lesson = clean.lesson_at("0.2")
    assert lesson
    slot, slot_revision = store.get_homework(LOCAL_LEARNER, clean.id)
    assert slot is not None
    second = runtime.assignment_from_lesson(lesson, now=NOW)
    assert second is not None
    store.put_homework(
        LOCAL_LEARNER,
        clean.id,
        slot.model_copy(update={"queued": [second.model_copy(update={"coordinate": "1.1"})]}),
        slot_revision,
    )

    runtime.submit_homework(store, LOCAL_LEARNER, clean.id, "0.2", now=NOW)

    loaded, _ = store.get_homework(LOCAL_LEARNER, clean.id)
    assert loaded is not None
    assert loaded.coordinate == "1.1", "the queued assignment loads when the slot resets"
    assert loaded.queued == []


def test_checking_is_not_implemented_but_the_slot_carries_verdict_fields(
    store: FileProgressStore, clean: Course
) -> None:
    """The core does mailbox mechanics; judgement is a runtime duty. The fields exist so a
    tutor that can judge has somewhere to put its verdicts."""
    _finish_phase_zero(store, clean)
    slot, _ = store.get_homework(LOCAL_LEARNER, clean.id)
    assert slot is not None
    for requirement in slot.requirements:
        assert requirement.verdict is None
        assert requirement.reason == ""


def test_example_course_homework_parses(example: Course) -> None:
    lesson = example.lesson_at("1.3")
    assert lesson and lesson.homework
    assignment = runtime.assignment_from_lesson(lesson, now=NOW)
    assert assignment is not None
    assert assignment.title == "Write Your Own Course"
    assert len(assignment.requirements) == 7
    assert len(assignment.stretch_goals) == 3


def test_spec_version_is_stamped_on_new_records(store: FileProgressStore, clean: Course) -> None:
    record, _ = _fresh(store, clean)
    assert record.spec_version == runtime.SPEC_VERSION


def test_loading_a_real_example_course_works() -> None:
    course = Course.load(Path(__file__).resolve().parents[3] / "examples" / "hello-skilling")
    assert course.lesson_count == 3
