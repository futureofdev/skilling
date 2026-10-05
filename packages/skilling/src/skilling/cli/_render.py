"""Terminal output. Findings first, because that is what people run this for."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from rich.console import Console
from rich.text import Text

from ..conformance import Report, Severity
from ..course import Course, DiffResult, parse_lesson

console = Console()
err_console = Console(stderr=True)

_COLOUR = {Severity.ERROR: "red", Severity.WARNING: "yellow"}


def findings(report: Report, *, root: str) -> None:
    for finding in report.findings:
        colour = _COLOUR[finding.severity]
        head = Text()
        # 'warning' is exactly seven characters, so pad to eight or it runs into the location.
        head.append(f"{finding.severity!s:<8}", style=f"bold {colour}")
        head.append(finding.location, style="cyan")
        head.append("  ")
        head.append(str(finding.code), style="bold")
        console.print(head)
        console.print(Text(f"       {finding.message}"))
        console.print(Text(f"       → {finding.anchor}", style="dim"))
        console.print()

    n_errors, n_warnings = len(report.errors), len(report.warnings)
    if report.clean:
        console.print(f"[bold green]{root}: conforming[/] — no findings.")
        return

    summary = Text()
    summary.append(
        f"{n_errors} error{'' if n_errors == 1 else 's'}", style="bold red" if n_errors else "dim"
    )
    summary.append(", ")
    summary.append(
        f"{n_warnings} warning{'' if n_warnings == 1 else 's'}",
        style="bold yellow" if n_warnings else "dim",
    )
    console.print(summary)


def findings_json(report: Report) -> None:
    console.print_json(
        json.dumps(
            {
                "ok": report.ok,
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "findings": [f.as_dict() for f in report.findings],
            }
        ),
        ensure_ascii=True,
    )


@dataclass(frozen=True)
class LessonDuration:
    coordinate: str
    title: str
    duration_minutes: int | None


@dataclass(frozen=True)
class PhaseDuration:
    number: int
    name: str
    duration_minutes: int
    missing_duration_lessons: tuple[str, ...]
    lessons: tuple[LessonDuration, ...]


@dataclass(frozen=True)
class CourseDuration:
    id: str
    title: str
    version: str
    duration_minutes: int
    missing_duration_lessons: tuple[str, ...]
    phases: tuple[PhaseDuration, ...]

    @classmethod
    def from_course(cls, course: Course) -> CourseDuration:
        phases: list[PhaseDuration] = []
        for phase in course.phases:
            lessons: list[LessonDuration] = []
            for lesson in phase.lessons:
                try:
                    frontmatter = parse_lesson(lesson.path).frontmatter
                except (OSError, UnicodeError):
                    frontmatter = None
                minutes = frontmatter.duration_minutes if frontmatter is not None else None
                lessons.append(LessonDuration(lesson.coordinate, lesson.title, minutes))
            phases.append(
                PhaseDuration(
                    phase.number,
                    phase.name,
                    sum(lesson.duration_minutes or 0 for lesson in lessons),
                    tuple(
                        lesson.coordinate for lesson in lessons if lesson.duration_minutes is None
                    ),
                    tuple(lessons),
                )
            )
        return cls(
            course.id,
            course.manifest.title,
            course.version,
            sum(phase.duration_minutes for phase in phases),
            tuple(coordinate for phase in phases for coordinate in phase.missing_duration_lessons),
            tuple(phases),
        )


def _duration_label(minutes: int, missing: tuple[str, ...]) -> str:
    suffix = f"; incomplete ({len(missing)} lesson(s) without a usable duration)" if missing else ""
    return f"{minutes} min{suffix}"


def course_summary_json(course: Course, *, completed: list[str] | None = None) -> None:
    summary = asdict(CourseDuration.from_course(course))
    summary["completed"] = completed or []
    summary["lesson_count"] = course.lesson_count
    summary["phase_count"] = course.phase_count
    console.print_json(json.dumps(summary))


def course_summary(course: Course, *, completed: list[str] | None = None) -> None:
    done = completed or []
    durations = CourseDuration.from_course(course)
    console.print(f"[bold]{course.manifest.title}[/]  [dim]({course.id} {course.version})[/]")
    if course.manifest.description:
        console.print(f"[dim]{course.manifest.description}[/]")
    console.print()

    for phase, duration in zip(course.phases, durations.phases, strict=True):
        marker = "✓" if course.phase_is_complete(phase.number, done) else " "
        console.print(
            f"[bold]{marker} Phase {phase.number} — {phase.name}[/]  [dim]{phase.slug}[/]"
            f"  {_duration_label(duration.duration_minutes, duration.missing_duration_lessons)}"
        )
        for lesson, estimate in zip(phase.lessons, duration.lessons, strict=True):
            tick = "✓" if lesson.coordinate in done else "·"
            extras = " [magenta]homework[/]" if lesson.homework else ""
            missing = "" if lesson.path.is_file() else " [red](file missing)[/]"
            timing = (
                f"{estimate.duration_minutes} min"
                if estimate.duration_minutes is not None
                else "duration not declared or unavailable"
            )
            console.print(
                f"    {tick} [cyan]{lesson.coordinate}[/]  "
                f"{lesson.title}{extras}{missing}  {timing}"
            )
        console.print()

    console.print("[bold]Derived[/] [dim](never authored)[/]")
    console.print(f"  phases            {course.phase_count}")
    console.print(f"  lessons           {course.lesson_count}")
    console.print(
        "  duration          "
        + _duration_label(durations.duration_minutes, durations.missing_duration_lessons)
    )
    for phase in course.phases:
        console.print(f"  phase {phase.number} lessons    {phase.lesson_count}")
    if done:
        console.print(f"  completed         {course.completed_count(done)}")
        console.print(f"  remaining         {course.remaining_count(done)}")
        console.print(f"  percent complete  {course.percent_complete(done)}%")
    if course.manifest.skills:
        console.print("  badges            " + ", ".join(s.id for s in course.manifest.skills))


def diff_summary(result: DiffResult) -> None:
    console.print(
        f"[bold]{result.old_version}[/] → [bold]{result.new_version}[/]  "
        f"[dim](declared: {result.declared})[/]"
    )
    console.print()

    for reason in result.reasons():
        console.print(f"  • {reason}")
    if not result.reasons():
        console.print("  • nothing changed")
    console.print()

    stability = (
        "[green]all existing coordinates stable[/]"
        if result.coordinates_stable
        else "[red]coordinates moved — in-flight learners must pin[/]"
    )
    console.print(f"  {stability}")
    console.print(f"  minimum bump required: [bold]{result.required}[/]")

    if result.declared == "downgrade":
        console.print("[bold red]  the new version is lower than the old one[/]")
    elif result.declared == "unparseable":
        console.print("[bold red]  one of the versions is not a semantic version[/]")
    elif result.satisfied:
        console.print(f"[bold green]  declared {result.declared} bump is sufficient[/]")
    else:
        console.print(
            f"[bold red]  declared {result.declared} bump is not enough — needs "
            f"{result.required}[/]"
        )
