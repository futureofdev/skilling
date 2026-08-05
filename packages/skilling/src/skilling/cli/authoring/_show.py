"""``skilling show`` — the resolved structure, and every count derived rather than authored."""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Course, CourseLoadError, parse_lesson, parse_quiz
from ...store import LOCAL_LEARNER, FileProgressStore
from .. import _render as render


def show(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    state: Path = typer.Option(
        None, "--state", help="Progress state root, to show a learner's position too."
    ),
    objectives: bool = typer.Option(
        False,
        "--objectives",
        help="Show each objective beside the quiz question(s) its 'about' references, "
        "plus the loose ends: objectives with no about, and questions no objective "
        "points at.",
    ),
) -> None:
    """Print the resolved structure and every derived count."""
    try:
        resolved = Course.load(course)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc

    if objectives:
        _objective_mapping(resolved)
        return

    completed: list[str] = []
    if state:
        store = FileProgressStore(state)
        found = store.get_record(LOCAL_LEARNER, resolved.id)
        if found:
            completed = found[0].completed
    render.course_summary(resolved, completed=completed)


def _objective_mapping(course: Course) -> None:
    """Per lesson with structured objectives: each objective beside the full text of the
    question(s) its `about` references. Then the two ways that mapping goes stale, across
    the whole course — an objective pointing at nothing, and a question nothing points at.

    Authoring-facing only: this reads what a tutor would use for remediation, but a quiz
    settles nothing, so nothing here feeds back into a learner's record.
    """
    console = render.console
    no_about: list[tuple[str, str, str]] = []  # coordinate, objective id, objective text
    no_objective: list[tuple[str, int, str]] = []  # coordinate, question number, question text
    any_structured = False

    for lesson in course.lessons():
        parsed = parse_lesson(lesson.path)
        fm = parsed.frontmatter
        if fm is None or not fm.objectives:
            continue
        any_structured = True

        quiz_section = parsed.section("quiz")
        questions = parse_quiz(quiz_section.body, quiz_section.body_line) if quiz_section else []
        by_number = {q.number: q for q in questions}
        addressed: set[int] = set()

        console.print(f"[bold cyan]{lesson.coordinate}[/]  {lesson.title}")
        for objective in fm.objectives:
            if not objective.about:
                no_about.append((lesson.coordinate, objective.id, objective.text))
                continue
            console.print(f"  [bold]{objective.id}[/] [dim]({objective.kind})[/] {objective.text}")
            for number in objective.about:
                addressed.add(number)
                question = by_number.get(number)
                text = question.text if question else "(no such question)"
                console.print(f"      → Q{number}: {text}")
        console.print()

        for question in questions:
            if question.number not in addressed:
                no_objective.append((lesson.coordinate, question.number, question.text))

    if not any_structured:
        console.print("[dim]No lesson declares structured objectives.[/]")
        console.print()

    console.print("[bold]Objectives with no about[/] [dim](nothing to steer remediation at)[/]")
    if no_about:
        for coordinate, objective_id, text in no_about:
            console.print(f"  [cyan]{coordinate}[/]  {objective_id}  {text}")
    else:
        console.print("  none")
    console.print()

    console.print("[bold]Questions no objective points at[/]")
    if no_objective:
        for coordinate, number, text in no_objective:
            console.print(f"  [cyan]{coordinate}[/]  Q{number}: {text}")
    else:
        console.print("  none")
