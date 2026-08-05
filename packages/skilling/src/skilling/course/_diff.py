"""Comparing two versions of a course, so a version number makes a checkable promise.

The format defines what each level of a course's semantic version means in terms of
*coordinate stability*: patch changes content only, minor appends without moving anything,
major moves or removes. That is what lets a runtime roll a learner forward automatically on
a patch or minor bump and pin them on a major one — but only if the promise is enforced,
which is what this module is for.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ._loader import Course

Level = Literal["none", "patch", "minor", "major"]

_RANK: dict[Level, int] = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def _digest(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _parse(version: str) -> tuple[int, int, int] | None:
    core = version.split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None


def declared_level(old: str, new: str) -> Level | Literal["downgrade", "unparseable"]:
    a, b = _parse(old), _parse(new)
    if a is None or b is None:
        return "unparseable"
    if b < a:
        return "downgrade"
    if b == a:
        return "none"
    if b[0] != a[0]:
        return "major"
    if b[1] != a[1]:
        return "minor"
    return "patch"


@dataclass
class DiffResult:
    old_version: str
    new_version: str
    required: Level = "none"
    declared: str = "none"
    removed: list[str] = field(default_factory=list)
    reassigned: list[tuple[str, str, str]] = field(default_factory=list)
    added_trailing: list[str] = field(default_factory=list)
    added_inserted: list[str] = field(default_factory=list)
    content_changed: list[str] = field(default_factory=list)
    manifest_changed: bool = False

    @property
    def coordinates_stable(self) -> bool:
        return not (self.removed or self.reassigned or self.added_inserted)

    @property
    def satisfied(self) -> bool:
        """Does the declared bump cover what actually changed?"""
        if self.declared in ("downgrade", "unparseable"):
            return False
        return _RANK[self.declared] >= _RANK[self.required]  # type: ignore[index]

    def reasons(self) -> list[str]:
        out: list[str] = []
        for coordinate in self.removed:
            out.append(f"{coordinate} was removed")
        for coordinate, old_slug, new_slug in self.reassigned:
            out.append(f"{coordinate} now points at {new_slug!r}, not {old_slug!r}")
        for coordinate in self.added_inserted:
            out.append(f"{coordinate} was inserted rather than appended, shifting what follows")
        for coordinate in self.added_trailing:
            out.append(f"{coordinate} was appended")
        if self.content_changed:
            out.append(f"{len(self.content_changed)} lesson file(s) changed content")
        if self.manifest_changed:
            out.append("course.yaml metadata changed")
        return out


def compare(old: Course, new: Course) -> DiffResult:
    old_map = {lesson.coordinate: lesson for lesson in old.lessons()}
    new_map = {lesson.coordinate: lesson for lesson in new.lessons()}

    result = DiffResult(old_version=old.version, new_version=new.version)
    result.declared = declared_level(old.version, new.version)

    result.removed = sorted(set(old_map) - set(new_map), key=_sort_key)

    for coordinate in sorted(set(old_map) & set(new_map), key=_sort_key):
        before, after = old_map[coordinate], new_map[coordinate]
        if before.slug != after.slug:
            result.reassigned.append((coordinate, before.slug, after.slug))
        elif _digest(before.path) != _digest(after.path):
            result.content_changed.append(coordinate)

    old_phase_numbers = {phase.number for phase in old.phases}
    highest_old_phase = max(old_phase_numbers) if old_phase_numbers else -1
    highest_lesson: dict[int, int] = {
        phase.number: max((entry.number for entry in phase.lessons), default=0)
        for phase in old.phases
    }

    for coordinate in sorted(set(new_map) - set(old_map), key=_sort_key):
        lesson = new_map[coordinate]
        if lesson.phase in old_phase_numbers:
            trailing = lesson.number > highest_lesson.get(lesson.phase, 0)
        else:
            trailing = lesson.phase > highest_old_phase
        (result.added_trailing if trailing else result.added_inserted).append(coordinate)

    result.manifest_changed = _manifest_metadata(old) != _manifest_metadata(new)

    if result.removed or result.reassigned or result.added_inserted:
        result.required = "major"
    elif result.added_trailing:
        result.required = "minor"
    elif result.content_changed or result.manifest_changed:
        result.required = "patch"
    else:
        result.required = "none"

    return result


def _manifest_metadata(course: Course) -> dict[str, object]:
    """Manifest fields whose change is a content change, excluding the version itself."""
    data = course.manifest.model_dump(mode="json")
    data.pop("version", None)
    return data


def _sort_key(coordinate: str) -> tuple[int, int]:
    phase, lesson = coordinate.split(".")
    return int(phase), int(lesson)


def compare_paths(old: Path | str, new: Path | str) -> DiffResult:
    return compare(Course.load(Path(old)), Course.load(Path(new)))
