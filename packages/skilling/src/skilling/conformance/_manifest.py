"""Manifest rules: the document's own fields, ceremony copy, phase/lesson numbering, and
the check that the manifest and the files under ``phases/`` agree exactly.
"""

from __future__ import annotations

from ..course import (
    MANIFEST_NAME,
    Course,
    Manifest,
    discover_lesson_files,
    is_course_id,
    is_semver,
)
from ._counts import _BODY_COUNTS, _MANIFEST_COUNTS, _scan_counts
from ._errors import SPEC_MAJOR, SPEC_MINOR, Code
from ._findings import _Collector

# A working set of SPDX identifiers plus the escape hatch a private course needs. Not the
# full SPDX list: a curated set catches the typo ("Apache2", "CC-BY-4") that a permissive
# regex would wave through, which is the actual value of checking at all.
SPDX_IDS = frozenset(
    {
        "0BSD",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "BSL-1.0",
        "CC0-1.0",
        "CC-BY-3.0",
        "CC-BY-4.0",
        "CC-BY-NC-4.0",
        "CC-BY-NC-ND-4.0",
        "CC-BY-NC-SA-4.0",
        "CC-BY-ND-4.0",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "EPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "ISC",
        "LGPL-2.1-only",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "MIT",
        "MPL-2.0",
        "Unlicense",
        "Zlib",
    }
)
PROPRIETARY = "proprietary"


def _line_of(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return i
    return None


def _check_manifest(out: _Collector, manifest: Manifest, raw: str) -> None:
    parts = manifest.spec_version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        out.add(
            Code.SPEC_VERSION_UNSUPPORTED,
            f"spec_version {manifest.spec_version!r} is not a 'major.minor' version.",
            path=MANIFEST_NAME,
            line=_line_of(raw, "spec_version"),
        )
    else:
        if major != SPEC_MAJOR:
            out.add(
                Code.SPEC_VERSION_UNSUPPORTED,
                f"This course targets Skilling {manifest.spec_version}; this tool reads "
                f"{SPEC_MAJOR}.x.",
                path=MANIFEST_NAME,
                line=_line_of(raw, "spec_version"),
            )
        elif minor > SPEC_MINOR:
            out.add(
                Code.SPEC_VERSION_NEWER_MINOR,
                f"This course targets Skilling {manifest.spec_version}; this tool knows "
                f"{SPEC_MAJOR}.{SPEC_MINOR}. Newer optional fields will not be checked.",
                path=MANIFEST_NAME,
                line=_line_of(raw, "spec_version"),
            )

    if not is_course_id(manifest.id):
        out.add(
            Code.COURSE_ID_INVALID,
            f"id {manifest.id!r} must be 1-64 characters of lowercase letters, digits and "
            "single hyphens, not starting or ending with a hyphen.",
            path=MANIFEST_NAME,
            line=_line_of(raw, "id:"),
        )

    if not is_semver(manifest.version):
        out.add(
            Code.COURSE_VERSION_INVALID,
            f"version {manifest.version!r} is not a semantic version.",
            path=MANIFEST_NAME,
            line=_line_of(raw, "version:"),
        )

    if manifest.license is not None and manifest.license not in (*SPDX_IDS, PROPRIETARY):
        out.add(
            Code.LICENSE_UNKNOWN,
            f"license {manifest.license!r} is neither a known SPDX identifier nor {PROPRIETARY!r}.",
            path=MANIFEST_NAME,
            line=_line_of(raw, "license:"),
        )

    seen: set[str] = set()
    for skill in manifest.skills:
        if skill.id in seen:
            out.add(
                Code.BADGE_ID_DUPLICATE,
                f"Two registered skills share the id {skill.id!r}.",
                path=MANIFEST_NAME,
                line=_line_of(raw, skill.id),
            )
        seen.add(skill.id)

    for label, value in (
        ("The course title", manifest.title),
        ("The course description", manifest.description),
    ):
        if value:
            _scan_counts(
                out, value, _MANIFEST_COUNTS + _BODY_COUNTS, path=MANIFEST_NAME, where=label
            )
    for phase in manifest.phases:
        _scan_counts(
            out,
            phase.name,
            _MANIFEST_COUNTS + _BODY_COUNTS,
            path=MANIFEST_NAME,
            where=f"Phase {phase.number}'s name",
        )
        for entry in phase.lessons:
            _scan_counts(
                out,
                entry.title,
                _MANIFEST_COUNTS + _BODY_COUNTS,
                path=MANIFEST_NAME,
                where=f"The title of lesson {phase.number}.{entry.number}",
            )


def _check_ceremony(out: _Collector, manifest: Manifest, raw: str) -> None:
    """Ceremony copy is learner-facing, so it is held to the same rules as a lesson body."""
    # Deferred: delivery's own _runtime module imports conformance eagerly (for SPEC_MAJOR/
    # SPEC_MINOR), so an eager import here would close a conformance<->delivery cycle at
    # package-init time. By call time both packages are already loaded.
    from ..delivery import PLACEHOLDERS, placeholders_in, unknown_placeholders

    # Highlights are scanned whether or not a ceremony block exists: a highlight reaches a
    # learner through any runtime that composes its own copy, block or no block.
    for phase in manifest.phases:
        if phase.highlight:
            _scan_counts(
                out,
                phase.highlight,
                _MANIFEST_COUNTS + _BODY_COUNTS,
                path=MANIFEST_NAME,
                where=f"Phase {phase.number}'s highlight",
            )

    ceremony = manifest.ceremony
    if ceremony is None:
        return

    for field, template in ceremony.templates().items():
        for name in unknown_placeholders(template):
            out.add(
                Code.CEREMONY_UNKNOWN_PLACEHOLDER,
                f"{field} uses {{{name}}}, which no runtime can fill. Known placeholders: "
                + ", ".join(sorted(PLACEHOLDERS))
                + ".",
                path=MANIFEST_NAME,
                line=_line_of(raw, field),
            )

        if "phase_highlight" in placeholders_in(template):
            for phase in manifest.phases:
                if not (phase.highlight or "").strip():
                    out.add(
                        Code.CEREMONY_HIGHLIGHT_MISSING,
                        f"{field} uses {{phase_highlight}} but phase {phase.number} has no "
                        "highlight. A share post with a hole in the middle is worse than one "
                        "that never promised a highlight.",
                        path=MANIFEST_NAME,
                        line=_line_of(raw, phase.slug),
                    )

        _scan_counts(
            out,
            template,
            _MANIFEST_COUNTS + _BODY_COUNTS,
            path=MANIFEST_NAME,
            where=f"ceremony.{field}",
        )

    if ceremony.brand:
        for platform, handle in ceremony.brand.handles.items():
            if not handle.startswith("@"):
                out.add(
                    Code.CEREMONY_HANDLE_MALFORMED,
                    f"The {platform} handle {handle!r} does not begin with '@'.",
                    path=MANIFEST_NAME,
                    line=_line_of(raw, handle),
                )
        if ceremony.brand.mention and not ceremony.brand.mention.startswith("@"):
            out.add(
                Code.CEREMONY_HANDLE_MALFORMED,
                f"brand.mention {ceremony.brand.mention!r} does not begin with '@'.",
                path=MANIFEST_NAME,
                line=_line_of(raw, "mention:"),
            )


def _check_numbering(out: _Collector, manifest: Manifest, raw: str) -> None:
    numbers = [p.number for p in manifest.phases]
    seen: set[int] = set()
    for number in numbers:
        if number in seen:
            out.add(
                Code.PHASE_NUMBER_DUPLICATE,
                f"Two phases are numbered {number}.",
                path=MANIFEST_NAME,
                line=_line_of(raw, f"number: {number}"),
            )
        seen.add(number)

    if numbers and numbers[0] not in (0, 1):
        out.add(
            Code.PHASE_NUMBERING_GAP,
            f"The first phase is numbered {numbers[0]}; it must be 0 or 1.",
            path=MANIFEST_NAME,
            line=_line_of(raw, "phases:"),
        )
    for previous, current in zip(numbers, numbers[1:], strict=False):
        if current != previous + 1:
            out.add(
                Code.PHASE_NUMBERING_GAP,
                f"Phase {current} follows phase {previous}; phase numbers must ascend by "
                "exactly 1.",
                path=MANIFEST_NAME,
                line=_line_of(raw, f"number: {current}"),
            )

    for phase in manifest.phases:
        lesson_numbers = [entry.number for entry in phase.lessons]
        seen_lessons: set[int] = set()
        for number in lesson_numbers:
            if number in seen_lessons:
                entry = next(e for e in phase.lessons if e.number == number)
                out.add(
                    Code.LESSON_NUMBER_DUPLICATE,
                    f"Phase {phase.number} has more than one lesson numbered {number}.",
                    path=MANIFEST_NAME,
                    line=_line_of(raw, entry.slug),
                )
            seen_lessons.add(number)

        if lesson_numbers and lesson_numbers[0] != 1:
            out.add(
                Code.LESSON_NUMBERING_GAP,
                f"Phase {phase.number}'s first lesson is numbered {lesson_numbers[0]}; lesson "
                "numbers start at 1 in every phase.",
                path=MANIFEST_NAME,
                line=_line_of(raw, phase.slug),
            )
        for previous, current in zip(lesson_numbers, lesson_numbers[1:], strict=False):
            if current != previous + 1:
                out.add(
                    Code.LESSON_NUMBERING_GAP,
                    f"In phase {phase.number}, lesson {current} follows lesson {previous}; "
                    "lesson numbers must ascend by exactly 1.",
                    path=MANIFEST_NAME,
                    line=_line_of(raw, phase.slug),
                )


def _check_disk(out: _Collector, course: Course) -> None:
    expected = {lesson.path.resolve() for lesson in course.lessons()}
    for lesson in course.lessons():
        if not lesson.path.is_file():
            out.add(
                Code.LESSON_FILE_MISSING,
                f"The manifest lists lesson {lesson.coordinate} ({lesson.title!r}) but there "
                f"is no file at its derived path.",
                path=lesson.path,
            )
    for found in discover_lesson_files(course.root):
        if found.resolve() not in expected:
            out.add(
                Code.LESSON_FILE_ORPHAN,
                "This lesson file is not listed in the manifest. Every file under phases/ must "
                "appear in course.yaml.",
                path=found,
            )
