"""Terminal output. Findings first, because that is what people run this for."""

from __future__ import annotations

import json

from rich.console import Console
from rich.text import Text

from ..conformance import Report, Severity
from ..course import Course, DiffResult

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
        )
    )


def course_summary(course: Course, *, completed: list[str] | None = None) -> None:
    done = completed or []
    console.print(f"[bold]{course.manifest.title}[/]  [dim]({course.id} {course.version})[/]")
    if course.manifest.description:
        console.print(f"[dim]{course.manifest.description}[/]")
    console.print()

    for phase in course.phases:
        marker = "✓" if course.phase_is_complete(phase.number, done) else " "
        console.print(
            f"[bold]{marker} Phase {phase.number} — {phase.name}[/]  [dim]{phase.slug}[/]"
        )
        for lesson in phase.lessons:
            tick = "✓" if lesson.coordinate in done else "·"
            extras = " [magenta]homework[/]" if lesson.homework else ""
            missing = "" if lesson.path.is_file() else " [red](file missing)[/]"
            console.print(
                f"    {tick} [cyan]{lesson.coordinate}[/]  {lesson.title}{extras}{missing}"
            )
        console.print()

    console.print("[bold]Derived[/] [dim](never authored)[/]")
    console.print(f"  phases            {course.phase_count}")
    console.print(f"  lessons           {course.lesson_count}")
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
