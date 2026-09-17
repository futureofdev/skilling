"""Pure selection from validated append-order completion history.

Completed coordinates are a set; timestamps are observations, not sequence numbers.
Historical course versions remain meaningful after an explicit record upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..course import CompletionEntry, Course, Record


class ChronologyInvalid(ValueError):
    """Existing history or an explicit selection conflicts with the selected course."""


class CoordinateRequired(ValueError):
    """Legacy history cannot identify one completed lesson without an override."""


def completed_coordinate(
    course: Course,
    record: Record,
    log: Sequence[CompletionEntry],
    *,
    coordinate: str | None = None,
) -> str:
    """Validate the whole history before selecting even an explicit override.

    Exact duplicate events are tolerated without rewriting legacy data; conflicting
    duplicates are not. A nonempty log must account for the whole completed set.
    """
    if record.course_id != course.id or record.course_version != course.version:
        raise ChronologyInvalid("record does not belong to the selected course/version")
    completed = set(record.completed)
    if any(course.lesson_at(item) is None for item in completed):
        raise ChronologyInvalid("record contains a completed coordinate outside this course")
    seen: dict[str, CompletionEntry] = {}
    for entry in log:
        if course.lesson_at(entry.coordinate) is None or entry.coordinate not in completed:
            raise ChronologyInvalid("completion log contains an unknown or uncompleted coordinate")
        if not entry.course_version.strip():
            raise ChronologyInvalid("completion log contains an empty course version")
        previous = seen.get(entry.coordinate)
        if previous is not None and previous != entry:
            raise ChronologyInvalid(f"conflicting completion entries for {entry.coordinate}")
        seen[entry.coordinate] = entry
    if log and set(seen) != completed:
        raise ChronologyInvalid("completion log and record completed set disagree")
    if coordinate is not None:
        if course.lesson_at(coordinate) is None or coordinate not in completed:
            raise ChronologyInvalid(f"{coordinate!r} is not a completed lesson in {course.id}")
        return coordinate
    if log:
        return log[-1].coordinate
    if len(completed) == 1:
        return next(iter(completed))
    raise CoordinateRequired("pass --coordinate for a known completed lesson; no unambiguous log")
