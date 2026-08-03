"""The store conformance suite.

Written against the protocol rather than the backend and parametrised over implementations,
so the eventual database backend costs nothing to test: add it to ``BACKENDS`` and the same
assertions run. That is the whole promise of the store interface — one suite, any backend.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from skilling.models import (
    CompletionEntry,
    HomeworkArchiveEntry,
    HomeworkSlot,
    Position,
    Record,
    Requirement,
)
from skilling.store import Conflict, FileProgressStore, ProgressStore

LEARNER = "local"
COURSE = "clean-course"
OTHER_COURSE = "other-course"


def _file_backend(tmp_path: Path) -> ProgressStore:
    return FileProgressStore(tmp_path / "state", learner_id=LEARNER)


BACKENDS: dict[str, Callable[[Path], ProgressStore]] = {
    "file": _file_backend,
}


@pytest.fixture(params=sorted(BACKENDS), ids=sorted(BACKENDS))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> ProgressStore:
    return BACKENDS[request.param](tmp_path)


def a_record(course_id: str = COURSE, **kwargs) -> Record:
    base = {
        "learner_id": LEARNER,
        "course_id": course_id,
        "course_version": "1.0.0",
        "spec_version": "1.0",
        "position": Position(phase=0, lesson=1),
        "completed": [],
        "skills_unlocked": [],
        "started_at": date(2026, 8, 3),
        "last_activity": date(2026, 8, 3),
        "timezone": "Europe/London",
        "streak_days": 0,
    }
    return Record(**{**base, **kwargs})


def an_entry(coordinate: str, when: int = 1) -> CompletionEntry:
    return CompletionEntry(
        coordinate=coordinate,
        title=f"Lesson {coordinate}",
        completed_at=datetime(2026, 8, 3, 10, when, 0, tzinfo=UTC),
        course_version="1.0.0",
    )


def a_slot(coordinate: str = "0.2", queued: list | None = None) -> HomeworkSlot:
    return HomeworkSlot(
        coordinate=coordinate,
        title="Practise Both Things",
        objective="Use them together.",
        requirements=[Requirement(text="Use the first thing")],
        stretch_goals=[Requirement(text="Use them at once")],
        submission="Tell your tutor.",
        unlocked_at=datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC),
        queued=queued or [],
    )


# ------------------------------------------------------------------------------- record


def test_absent_record_reads_as_absent(store: ProgressStore) -> None:
    assert store.get_record(LEARNER, COURSE) is None


def test_write_then_read_round_trips(store: ProgressStore) -> None:
    record = a_record(completed=["0.1"], skills_unlocked=["alpha"], streak_days=3)
    store.put_record(record, None)

    found = store.get_record(LEARNER, COURSE)
    assert found is not None
    stored, revision = found
    assert stored == record
    assert revision


def test_a_stale_revision_conflicts_and_does_not_write(store: ProgressStore) -> None:
    first = a_record()
    store.put_record(first, None)
    found = store.get_record(LEARNER, COURSE)
    assert found is not None
    _, revision = found

    store.put_record(a_record(streak_days=1), revision)

    with pytest.raises(Conflict):
        store.put_record(a_record(streak_days=99), revision)

    reread = store.get_record(LEARNER, COURSE)
    assert reread is not None
    assert reread[0].streak_days == 1, "the losing write must leave no trace"


def test_creating_over_an_existing_record_conflicts(store: ProgressStore) -> None:
    store.put_record(a_record(), None)
    with pytest.raises(Conflict):
        store.put_record(a_record(streak_days=5), None)


def test_updating_an_absent_record_conflicts(store: ProgressStore) -> None:
    with pytest.raises(Conflict):
        store.put_record(a_record(), "some-revision")


def test_revision_changes_on_write(store: ProgressStore) -> None:
    store.put_record(a_record(), None)
    found = store.get_record(LEARNER, COURSE)
    assert found is not None
    _, first = found
    second = store.put_record(a_record(streak_days=2), first)
    assert second != first


def test_courses_are_isolated(store: ProgressStore) -> None:
    store.put_record(a_record(COURSE, streak_days=1), None)
    store.put_record(a_record(OTHER_COURSE, streak_days=7), None)

    one = store.get_record(LEARNER, COURSE)
    two = store.get_record(LEARNER, OTHER_COURSE)
    assert one is not None and two is not None
    assert one[0].streak_days == 1
    assert two[0].streak_days == 7


# ---------------------------------------------------------------------------------- log


def test_empty_log_reads_as_empty(store: ProgressStore) -> None:
    assert store.get_log(LEARNER, COURSE) == []


def test_log_preserves_append_order(store: ProgressStore) -> None:
    for n, coordinate in enumerate(["0.1", "0.2", "1.1"], start=1):
        store.append_completion(LEARNER, COURSE, an_entry(coordinate, n))

    assert [e.coordinate for e in store.get_log(LEARNER, COURSE)] == ["0.1", "0.2", "1.1"]


def test_completed_set_is_reconstructible_from_the_log_alone(store: ProgressStore) -> None:
    coordinates = ["0.1", "0.2", "1.1"]
    for n, coordinate in enumerate(coordinates, start=1):
        store.append_completion(LEARNER, COURSE, an_entry(coordinate, n))
    store.put_record(a_record(completed=coordinates), None)

    from_log = [e.coordinate for e in store.get_log(LEARNER, COURSE)]
    found = store.get_record(LEARNER, COURSE)
    assert found is not None
    assert sorted(from_log) == sorted(found[0].completed)


def test_appending_never_rewrites_earlier_entries(store: ProgressStore) -> None:
    store.append_completion(LEARNER, COURSE, an_entry("0.1", 1))
    before = store.get_log(LEARNER, COURSE)[0]
    store.append_completion(LEARNER, COURSE, an_entry("0.2", 2))
    after = store.get_log(LEARNER, COURSE)[0]
    assert before == after


# ----------------------------------------------------------------------------- homework


def test_empty_slot_reads_as_absent(store: ProgressStore) -> None:
    assert store.get_homework(LEARNER, COURSE) == (None, None)


def test_slot_round_trips(store: ProgressStore) -> None:
    store.put_homework(LEARNER, COURSE, a_slot(), None)
    slot, revision = store.get_homework(LEARNER, COURSE)
    assert slot is not None and revision
    assert slot.coordinate == "0.2"
    assert [r.text for r in slot.requirements] == ["Use the first thing"]


def test_slot_write_is_optimistically_concurrent(store: ProgressStore) -> None:
    store.put_homework(LEARNER, COURSE, a_slot(), None)
    _, revision = store.get_homework(LEARNER, COURSE)
    store.put_homework(LEARNER, COURSE, a_slot("0.3"), revision)

    with pytest.raises(Conflict):
        store.put_homework(LEARNER, COURSE, a_slot("0.4"), revision)

    slot, _ = store.get_homework(LEARNER, COURSE)
    assert slot is not None and slot.coordinate == "0.3"


def test_clearing_the_slot_makes_it_absent_again(store: ProgressStore) -> None:
    store.put_homework(LEARNER, COURSE, a_slot(), None)
    _, revision = store.get_homework(LEARNER, COURSE)
    assert store.put_homework(LEARNER, COURSE, None, revision) is None
    assert store.get_homework(LEARNER, COURSE) == (None, None)


def test_a_queued_assignment_survives_the_round_trip(store: ProgressStore) -> None:
    queued = [a_slot("1.1")]
    store.put_homework(LEARNER, COURSE, a_slot("0.2", queued=queued), None)
    slot, _ = store.get_homework(LEARNER, COURSE)
    assert slot is not None
    assert [q.coordinate for q in slot.queued] == ["1.1"]


# ------------------------------------------------------------------------------ archive


def test_archive_is_append_only_and_ordered(store: ProgressStore) -> None:
    for n, coordinate in enumerate(["0.2", "1.1"], start=1):
        store.append_homework_archive(
            LEARNER,
            COURSE,
            HomeworkArchiveEntry(
                coordinate=coordinate,
                title=f"Assignment {coordinate}",
                requirements=[Requirement(text="Do it", verdict="met", reason="It was done")],
                submitted_at=datetime(2026, 8, 3, 10, n, 0, tzinfo=UTC),
            ),
        )

    archive = store.get_homework_archive(LEARNER, COURSE)
    assert [e.coordinate for e in archive] == ["0.2", "1.1"]
    assert archive[0].requirements[0].verdict == "met"


def test_two_submissions_of_the_same_coordinate_both_survive(store: ProgressStore) -> None:
    for n in (1, 2):
        store.append_homework_archive(
            LEARNER,
            COURSE,
            HomeworkArchiveEntry(
                coordinate="0.2",
                title="Assignment",
                requirements=[Requirement(text="Do it")],
                submitted_at=datetime(2026, 8, 3, 10, n, 0, tzinfo=UTC),
            ),
        )
    assert len(store.get_homework_archive(LEARNER, COURSE)) == 2


# -------------------------------------------------------------------------- enumeration


def test_list_records_finds_what_was_written(store: ProgressStore) -> None:
    assert store.list_records(COURSE) == []
    store.put_record(a_record(), None)
    rows = store.list_records(COURSE)
    assert [learner for learner, _ in rows] == [LEARNER]


# --------------------------------------------------------------- file-backend specifics


def test_file_backend_uses_the_specified_layout(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    store.append_completion(LEARNER, COURSE, an_entry("0.1"))
    store.put_homework(LEARNER, COURSE, a_slot(), None)
    store.append_homework_archive(
        LEARNER,
        COURSE,
        HomeworkArchiveEntry(
            coordinate="0.2",
            title="Assignment",
            requirements=[Requirement(text="Do it")],
            submitted_at=datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC),
        ),
    )

    root = tmp_path / "state" / COURSE
    assert (root / "record.yaml").is_file()
    assert (root / "completed.yaml").is_file()
    assert (root / "homework" / "active.yaml").is_file()
    assert (root / "homework" / "archive" / "0.2-2026-08-03.yaml").is_file()


def test_file_backend_leaves_no_temporary_files(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    leftovers = [p.name for p in (tmp_path / "state" / COURSE).iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_file_backend_state_is_human_readable(tmp_path: Path) -> None:
    """Local state is meant to be readable — that is half the reason it is YAML on disk."""
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(completed=["0.1"]), None)
    text = (tmp_path / "state" / COURSE / "record.yaml").read_text(encoding="utf-8")
    assert "learner_id: local" in text
    assert "course_id: clean-course" in text
    assert "- '0.1'" in text


def _iter_backends() -> Iterator[str]:  # pragma: no cover - documentation helper
    """Add a backend name here and every assertion above runs against it."""
    yield from BACKENDS
