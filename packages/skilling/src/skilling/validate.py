"""Course validation: every check the format makes, reported as coded findings.

A finding names a file, a line where one can be found, an immutable error code, and an
anchor into the specification. The anchor matters — an author who disagrees with a
finding should be one click from the text that motivated it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import lesson as md
from .errors import CATALOGUE, SPEC_MAJOR, SPEC_MINOR, Code, Severity
from .loader import (
    MANIFEST_NAME,
    Course,
    CourseLoadError,
    discover_lesson_files,
    load_manifest,
    resolve,
)
from .models import OPTIONAL_SECTION_KEYS, Manifest, SectionAbsence, is_course_id, is_semver

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

# Counts written into manifest prose. Any number attached to "lesson" or "phase" here is
# a count the manifest already knows.
_MANIFEST_COUNTS = (
    re.compile(r"\b\d+\s*[-–—]?\s*lessons?\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*[-–—]?\s*phases?\b", re.IGNORECASE),
)

# Counts written into teaching prose. Deliberately narrower: a lesson may legitimately
# discuss numbers, so only self-referential phrasings — the ones that describe *this*
# course or the learner's position in it — are findings.
_BODY_COUNTS = (
    re.compile(r"\blesson\s+\d+\s+of\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bphase\s+\d+\s+of\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*%\s*(?:complete|through|done|finished)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+of\s+\d+\s+lessons?\b", re.IGNORECASE),
    re.compile(r"\bthis\s+course\s+(?:has|contains|is)\s+\d+", re.IGNORECASE),
    re.compile(r"\b\d+\s+lessons?\s+(?:in|of)\s+this\s+(?:course|phase)\b", re.IGNORECASE),
)

_BULLET = re.compile(r"^\s*[-*]\s+\S")
_KEY_TERM = re.compile(r"^\s*[-*]\s*\*\*[^*]+\*\*\s*:\s*\S")
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

NEXT_UP_MAX_WORDS = 60
NEXT_UP_MAX_SENTENCES = 3


@dataclass(frozen=True)
class Finding:
    code: Code
    severity: Severity
    message: str
    anchor: str
    path: str | None = None
    line: int | None = None

    @property
    def location(self) -> str:
        if self.path and self.line:
            return f"{self.path}:{self.line}"
        return self.path or "(course)"

    def as_dict(self) -> dict[str, object]:
        return {
            "code": str(self.code),
            "severity": str(self.severity),
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "anchor": self.anchor,
        }


class Report:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def clean(self) -> bool:
        return not self.findings

    def codes(self) -> set[Code]:
        return {f.code for f in self.findings}


class _Collector:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def add(
        self,
        code: Code,
        message: str,
        *,
        path: Path | str | None = None,
        line: int | None = None,
    ) -> None:
        entry = CATALOGUE[code]
        rel: str | None
        if isinstance(path, Path):
            try:
                rel = str(path.relative_to(self.root))
            except ValueError:
                rel = str(path)
        else:
            rel = path
        self.findings.append(
            Finding(
                code=code,
                severity=entry.severity,
                message=message,
                anchor=entry.anchor,
                path=rel,
                line=line,
            )
        )


def _line_of(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return i
    return None


def _scan_counts(
    out: _Collector,
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    *,
    path: Path | str,
    offset: int = 1,
    where: str,
) -> None:
    for i, line in enumerate(md.strip_code(text).splitlines()):
        for pattern in patterns:
            m = pattern.search(line)
            if m:
                out.add(
                    Code.AUTHORED_COUNT,
                    f"{where} states {m.group(0).strip()!r}. Structural counts are derived "
                    "from the manifest; writing one down creates a second source of truth.",
                    path=path,
                    line=i + offset,
                )
                break


# ------------------------------------------------------------------------------ manifest


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


# -------------------------------------------------------------------------------- disk


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


# ------------------------------------------------------------------------------ lessons


def _check_lesson(out: _Collector, course: Course, resolved, parsed: md.ParsedLesson) -> None:
    path = parsed.path

    if parsed.frontmatter_missing:
        out.add(
            Code.LESSON_UNPARSEABLE,
            "The file does not open with a '---' YAML frontmatter block.",
            path=path,
            line=1,
        )
        return
    if parsed.frontmatter_error or parsed.frontmatter is None:
        out.add(
            Code.LESSON_FRONTMATTER_INVALID,
            parsed.frontmatter_error or "frontmatter could not be read.",
            path=path,
            line=1,
        )
        return

    fm = parsed.frontmatter

    mismatches = []
    if fm.title != resolved.title:
        mismatches.append(f"title {fm.title!r} vs manifest {resolved.title!r}")
    if fm.phase != resolved.phase:
        mismatches.append(f"phase {fm.phase} vs manifest {resolved.phase}")
    if fm.lesson != resolved.number:
        mismatches.append(f"lesson {fm.lesson} vs manifest {resolved.number}")
    if mismatches:
        out.add(
            Code.FRONTMATTER_MANIFEST_MISMATCH,
            "Frontmatter disagrees with the manifest: " + "; ".join(mismatches) + ".",
            path=path,
            line=1,
        )

    known = set(course.coordinates)
    for prerequisite in fm.prerequisites:
        if prerequisite not in known:
            out.add(
                Code.PREREQUISITE_UNRESOLVED,
                f"Prerequisite {prerequisite!r} is not a lesson in this course.",
                path=path,
                line=1,
            )

    registered = course.manifest.badge_ids
    for badge in fm.skills_unlocked:
        if badge not in registered:
            out.add(
                Code.BADGE_UNREGISTERED,
                f"skills_unlocked names {badge!r}, which is not registered in the manifest's "
                "skills list.",
                path=path,
                line=1,
            )

    _check_sections(out, resolved, parsed)
    _check_section_bodies(out, parsed)
    _check_assets(out, course, parsed)

    body_start = parsed.sections[0].line if parsed.sections else 1
    body = "\n".join(parsed.raw.splitlines()[body_start - 1 :])
    _scan_counts(out, body, _BODY_COUNTS, path=path, offset=body_start, where="This lesson")


def _check_sections(out: _Collector, resolved, parsed: md.ParsedLesson) -> None:
    path = parsed.path
    fm = parsed.frontmatter
    assert fm is not None

    for section in parsed.sections:
        if section.heading not in md.BY_HEADING:
            out.add(
                Code.SECTION_UNKNOWN_HEADING,
                f"'## {section.heading}' is not in the section registry. Use '###' subheadings "
                "inside a registered section instead.",
                path=path,
                line=section.line,
            )

    known = [s for s in parsed.sections if s.heading in md.BY_HEADING]
    positions = [md.REGISTRY_ORDER[s.heading] for s in known]
    for i in range(1, len(positions)):
        if positions[i] < positions[i - 1]:
            out.add(
                Code.SECTION_OUT_OF_ORDER,
                f"'## {known[i].heading}' appears after '## {known[i - 1].heading}'; sections "
                "must follow registry order.",
                path=path,
                line=known[i].line,
            )
            break

    present = parsed.slots
    for spec in md.SECTION_REGISTRY:
        if spec.required and spec.slot not in present:
            out.add(
                Code.SECTION_MISSING,
                f"'## {spec.heading}' is required and absent.",
                path=path,
                line=1,
            )

    for key in OPTIONAL_SECTION_KEYS:
        spec = md.BY_SLOT[key]
        declaration = fm.declaration(key)
        if declaration is None:
            out.add(
                Code.SECTION_ABSENCE_UNDECLARED,
                f"sections does not declare {key!r}. Every optional section must be declared "
                "present, or absent with an intent.",
                path=path,
                line=1,
            )
            continue
        if isinstance(declaration, SectionAbsence):
            if not declaration.intent.strip():
                out.add(
                    Code.SECTION_ABSENCE_MISSING_INTENT,
                    f"sections.{key} is declared absent but carries no intent. Say why, so a "
                    "reader can tell a decision from an oversight.",
                    path=path,
                    line=1,
                )
            if key in present:
                out.add(
                    Code.SECTION_DECLARED_PRESENT_BUT_ABSENT,
                    f"sections.{key} is declared absent, but '## {spec.heading}' is in the file.",
                    path=path,
                    line=1,
                )
        elif key not in present:
            out.add(
                Code.SECTION_DECLARED_PRESENT_BUT_ABSENT,
                f"sections.{key} is declared present, but '## {spec.heading}' is not in the file.",
                path=path,
                line=1,
            )

    homework_section = parsed.section("homework")
    if resolved.homework and homework_section is None:
        out.add(
            Code.HOMEWORK_DECLARATION_MISMATCH,
            "The manifest sets homework: true for this lesson, but there is no "
            "'## Homework Assignment' section.",
            path=path,
            line=1,
        )
    elif not resolved.homework and homework_section is not None:
        out.add(
            Code.HOMEWORK_DECLARATION_MISMATCH,
            "This lesson carries '## Homework Assignment' but the manifest does not set "
            "homework: true for it.",
            path=path,
            line=homework_section.line,
        )


def _check_section_bodies(out: _Collector, parsed: md.ParsedLesson) -> None:
    path = parsed.path

    objectives = parsed.section("objectives")
    if objectives and not any(_BULLET.match(line) for line in objectives.body.splitlines()):
        out.add(
            Code.OBJECTIVES_EMPTY,
            "Learning Objectives must contain a bullet list of outcomes.",
            path=path,
            line=objectives.line,
        )

    if key_terms := parsed.section("key_terms"):
        items = [
            (i, line) for i, line in enumerate(key_terms.body.splitlines()) if _BULLET.match(line)
        ]
        if not items:
            out.add(
                Code.KEY_TERMS_MALFORMED,
                "Key Terms contains no '- **Term**: definition' items.",
                path=path,
                line=key_terms.line,
            )
        for offset, line in items:
            if not _KEY_TERM.match(line):
                out.add(
                    Code.KEY_TERMS_MALFORMED,
                    "Key Terms items must read '- **Term**: definition'.",
                    path=path,
                    line=key_terms.body_line + offset,
                )

    exercise = parsed.section("exercise")
    if exercise and not exercise.body.strip():
        out.add(
            Code.EXERCISE_EMPTY,
            "Hands-On Exercise is present but empty. Declare it absent with an intent "
            "instead, or give the learner something to attempt.",
            path=path,
            line=exercise.line,
        )

    if quiz := parsed.section("quiz"):
        _check_quiz(out, path, quiz)

    if homework := parsed.section("homework"):
        parsed_hw = md.parse_homework(homework.body)
        if gaps := parsed_hw.missing():
            out.add(
                Code.HOMEWORK_SECTION_MALFORMED,
                "Homework Assignment is missing " + ", ".join(gaps) + ".",
                path=path,
                line=homework.line,
            )

    if next_up := parsed.section("next_up"):
        text = " ".join(next_up.body.split())
        words = len(text.split())
        sentences = len([m for m in _SENTENCE_END.finditer(text)])
        if words > NEXT_UP_MAX_WORDS or sentences > NEXT_UP_MAX_SENTENCES:
            out.add(
                Code.NEXT_UP_TOO_LONG,
                f"Next Up runs to {words} words in {sentences} sentences; it is meant to be a "
                "one or two sentence teaser.",
                path=path,
                line=next_up.line,
            )


def _check_quiz(out: _Collector, path: Path, section: md.Section) -> None:
    questions = md.parse_quiz(section.body, section.body_line)

    if len(questions) != 3:
        out.add(
            Code.QUIZ_WRONG_QUESTION_COUNT,
            f"Quick Quiz has {len(questions)} question(s); exactly 3 are required.",
            path=path,
            line=section.line,
        )

    for question in questions:
        if sorted(question.labels) != ["a", "b", "c", "d"]:
            out.add(
                Code.QUIZ_WRONG_OPTION_COUNT,
                f"Question {question.number} has options {question.labels or '[]'}; exactly "
                "four labelled a) to d) are required.",
                path=path,
                line=question.line,
            )
            continue

        if question.answer_line is None:
            out.add(
                Code.QUIZ_ANSWER_LINE_MISSING,
                f"Question {question.number} has no '**Answer:**' line. Informal courses carry "
                "the correct option inline.",
                path=path,
                line=question.line,
            )
            continue

        if question.answer_label is None:
            out.add(
                Code.QUIZ_ANSWER_AMBIGUOUS,
                f"Question {question.number}'s answer line does not open with one of its four "
                "option labels.",
                path=path,
                line=question.answer_line,
            )
            continue

        if not question.has_reason:
            out.add(
                Code.QUIZ_ANSWER_NO_REASON,
                f"Question {question.number}'s answer names the correct option but gives no "
                "reason. A learner who guessed right still needs the why.",
                path=path,
                line=question.answer_line,
            )


def _check_assets(out: _Collector, course: Course, parsed: md.ParsedLesson) -> None:
    for target, line in md.asset_references(parsed.raw):
        if target.startswith("/"):
            out.add(
                Code.ASSET_REFERENCE_ABSOLUTE,
                f"Asset reference {target!r} is absolute. Use a path relative to the lesson "
                "file so the course works wherever it is checked out.",
                path=parsed.path,
                line=line,
            )
            continue
        resolved_target = (parsed.path.parent / target).resolve()
        try:
            resolved_target.relative_to(course.root.resolve())
        except ValueError:
            out.add(
                Code.ASSET_REFERENCE_ABSOLUTE,
                f"Asset reference {target!r} escapes the course directory.",
                path=parsed.path,
                line=line,
            )
            continue
        if not resolved_target.exists():
            out.add(
                Code.ASSET_REFERENCE_DANGLING,
                f"Asset reference {target!r} does not exist.",
                path=parsed.path,
                line=line,
            )


# ------------------------------------------------------------------------------- entry


def validate_course(root: Path | str) -> Report:
    root = Path(root)
    out = _Collector(root)

    try:
        manifest = load_manifest(root)
    except CourseLoadError as exc:
        out.add(exc.code, exc.message, path=exc.path or MANIFEST_NAME)
        return Report(out.findings)

    raw = (root / MANIFEST_NAME).read_text(encoding="utf-8")
    _check_manifest(out, manifest, raw)
    _check_numbering(out, manifest, raw)

    course = resolve(root, manifest)
    _check_disk(out, course)

    for resolved in course.lessons():
        if not resolved.path.is_file():
            continue
        parsed = md.parse_lesson(resolved.path)
        _check_lesson(out, course, resolved, parsed)

    for phase in course.phases:
        overview = phase.overview_path
        if overview:
            _scan_counts(
                out,
                overview.read_text(encoding="utf-8"),
                _BODY_COUNTS,
                path=overview,
                where=f"Phase {phase.number}'s overview",
            )

    return Report(out.findings)
