"""``skilling start`` — one command from a course ref to an openable learner workspace: the
onboarding acid test's engine (spec/workspace.md). Fully non-interactive — the ref and an
optional target directory are the whole input — so the friendly route of pasting one prompt
into any of the four hosts can have the agent run this command itself, no prompts to answer.

``skilling init`` stays authoring-only; this never scaffolds a new course, only ever starts a
learner into an existing one.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ...conformance import Report
from ...delivery import load_or_create
from ...skills import SKILL_NAMES, HostTarget, Platform
from ...skills import install as install_triad
from ...sources import CourseInvalid, GhResolver, ResolveError, UrlResolver
from ...sources import resolve as resolve_remote
from ...store import LOCAL_LEARNER, FileProgressStore
from ...workspace import (
    SKILLING_DIR,
    add_course,
    courses_dir,
    ensure_workspace,
    import_local_course,
    refresh_entry_files,
    state_root,
)
from .. import _render as render

ALL_PLATFORMS = tuple(Platform)


def start(
    ref: str = typer.Argument(
        ..., help="Course ref: a path, gh:owner/repo[@ref], git+ssh:, or https:."
    ),
    dir: Path = typer.Argument(
        None, help="Workspace directory to create or grow. Defaults to the current directory."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Machine-readable output for CI and driving agents."
    ),
) -> None:
    """Resolve a course, grow a learner workspace around it, install the skill triad
    folder-scoped into it, refresh the entry files, and initialise the progress record —
    one command from a ref to an openable workspace. Idempotent: re-running upserts the
    manifest and refreshes skills and entry files, never duplicating either."""
    workspace = (dir if dir is not None else Path.cwd()).resolve()

    try:
        if GhResolver.claims(ref) or UrlResolver.claims(ref):
            resolved = resolve_remote(ref, cache=courses_dir(workspace))
            course, content_path = resolved.course, resolved.path
        else:
            imported = import_local_course(workspace, Path(ref))
            course, content_path = imported.course, imported.path
    except CourseInvalid as exc:
        report = Report(exc.findings)
        if as_json:
            render.findings_json(report)
        else:
            render.findings(report, root=ref)
        raise typer.Exit(1) from exc
    except ResolveError as exc:
        render.err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    # Nothing above ever touches `workspace` on disk unless resolution succeeded (a remote
    # cache write only happens after validation passes; a local import validates before
    # copying) — a refusal above leaves no half-created workspace behind.
    ensure_workspace(workspace)
    entry = add_course(workspace, course, ref, content_path)

    skill_dirs: list[Path] = []
    for platform in ALL_PLATFORMS:
        target = HostTarget(platform)
        # `home` is dead here — `skills_dir` ignores it whenever `project` is given — but it
        # is a required argument, and passing `workspace` rather than the real `Path.home()`
        # means a future refactor that starts honouring it can never reach outside the
        # workspace this command owns.
        result = install_triad(target, project=workspace, home=workspace)
        skill_dirs.extend(result.skill_dirs)

    entry_files = refresh_entry_files(workspace)

    store = FileProgressStore(state_root(workspace))
    load_or_create(store, course, LOCAL_LEARNER)

    course_display = f"{SKILLING_DIR}/{entry.path}"
    skills_relative = [p.relative_to(workspace).as_posix() for p in skill_dirs]
    entry_files_relative = [p.relative_to(workspace).as_posix() for p in entry_files]

    if as_json:
        render.console.print_json(
            json.dumps(
                {
                    "ok": True,
                    "verb": "start",
                    "workspace": str(workspace),
                    "course": {
                        "id": course.id,
                        "version": course.version,
                        "title": course.manifest.title,
                    },
                    "showcase": entry.showcase,
                    "skills": skills_relative,
                    "entry_files": entry_files_relative,
                    "state_initialised": True,
                }
            )
        )
        return

    console = render.console
    console.print(f"[bold]{course.id} {course.version}[/] — {course.manifest.title}")
    # soft_wrap: these lines carry filesystem paths meant to be read (or copied) whole — a
    # narrow terminal or a piped capture must never fold one across two lines.
    console.print(f"  {'workspace':<9}  {workspace}", soft_wrap=True)
    console.print(f"  {'course':<9}  {course_display}", soft_wrap=True)
    console.print(f"  {'showcase':<9}  {entry.showcase}/", soft_wrap=True)
    console.print(
        f"  {'skills':<9}  .claude/skills/ + .agents/skills/ ({', '.join(SKILL_NAMES)})",
        soft_wrap=True,
    )
    console.print()
    console.print(
        f"Next: open {workspace} in Claude Code, Codex, Claude Cowork, or ChatGPT Work "
        'and say "learn".',
        soft_wrap=True,
    )
