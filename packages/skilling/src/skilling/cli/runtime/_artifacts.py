"""``skilling artifact add`` / ``artifact list`` — pointers to work the learner built, recorded
only through the CLI at exactly the moments the loop already owns: phase ceremony and confirmed
homework submission (spec/workspace.md#artifacts). This module writes neither: it is the
storage primitive the driving skill calls *at* those moments, not a third moment of its own.

Artifacts never gate the flow — this module imports neither ``complete_lesson`` nor
``submit_homework``, so it could not accidentally make either wait on a write it does. ``add``
is the one verb here with anything to decide: resolving ``<path>`` against the workspace root,
defaulting the coordinate the same way ``ceremony`` already does, and upserting by path through
the store's own CAS. ``list`` enumerates ``record.artifacts`` using shared session loading,
which initializes a record on first use, like ``homework check``.

"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from ...session import SessionRefusal
from ...store import LOCAL_LEARNER, Conflict
from ...workspace import find_workspace, load_manifest, resolve_course_location
from ._common import (
    ExitCode,
    emit,
    fail,
    now_override,
    open_file_chronology_session,
    open_file_session,
    refuse_session,
    view_data,
)

COURSE_REF_HELP = (
    "Course id (resolved through the workspace manifest) or a path. Defaults to the "
    "workspace's sole course when it holds exactly one."
)
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseRefOption = typer.Option(None, "--course", help=COURSE_REF_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

artifact = typer.Typer(no_args_is_help=True, help="Record and list pointers to workspace work.")


def _course_ref(course: str | None, workspace: Path | None) -> str:
    """Select a sole-course default; shared session plumbing resolves every id and path."""
    if course is not None:
        return course
    if workspace is None:
        fail(ExitCode.INVALID, "course-required", "pass --course or run inside a workspace")
    try:
        manifest = load_manifest(workspace)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        fail(ExitCode.INVALID, "course-not-found", f"cannot read the workspace manifest: {exc}")
    if len(manifest.courses) == 1:
        course_id = manifest.courses[0].id
        location = resolve_course_location(course_id)
        if location is None:
            fail(ExitCode.INVALID, "course-not-found", f"no usable workspace course {course_id!r}")
        return str(location.resolve())
    fail(
        ExitCode.INVALID,
        "course-required",
        "no --course given and the workspace holds "
        f"{len(manifest.courses)} courses — say which one, by id or path",
    )


# ------------------------------------------------------------------------------------- add


@artifact.command("add")
def add(
    path: str = typer.Argument(..., help="Path to the artifact, resolved against the cwd."),
    title: str = typer.Option(..., "--title", help="A short title for the artifact."),
    course: str | None = _CourseRefOption,
    coordinate: str | None = typer.Option(
        None,
        "--coordinate",
        help="Completed coordinate. Defaults to the final entry in the completion log.",
    ),
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Record a pointer to work the learner built. Upserts by path: adding the same path
    again replaces that entry (new title, new coordinate) rather than duplicating it — agent
    retries are common, and the record is not the append-only log.

    Requires a workspace: a course on its own has no folder to relativize ``<path>`` against,
    and nowhere durable for the pointer to outlive one runtime process.
    """
    workspace = find_workspace()
    if workspace is None:
        fail(
            ExitCode.INVALID,
            "no-workspace",
            "artifact add needs a workspace — no .skilling/workspace.yaml was found in this "
            "directory or any parent",
        )

    ref = _course_ref(course, workspace)
    service = open_file_chronology_session(ref, state, learner)
    try:
        result = service.artifact_add(
            Path(path),
            title,
            workspace_root=workspace,
            path_base=Path.cwd(),
            coordinate=coordinate,
            now=now_override(),
        )
    except SessionRefusal as exc:
        refuse_session(exc, ref)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))
    emit(
        {
            "ok": True,
            "verb": "artifact-add",
            "course": {"id": result.course.id, "version": result.course.version},
            "artifact": view_data(result.artifact),
            "revision": result.revision,
        }
    )


@artifact.command("list")
def list_artifacts(
    course: str | None = _CourseRefOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """List pointers; first use initializes progress like the existing CLI."""
    ref = _course_ref(course, find_workspace())
    service = open_file_session(ref, state, learner)
    try:
        artifacts = service.artifacts()
    except SessionRefusal as exc:
        refuse_session(exc, ref)
    emit(
        {
            "ok": True,
            "verb": "artifact-list",
            "course": {"id": service.course.id, "version": service.course.version},
            "artifacts": [view_data(a) for a in artifacts],
        }
    )
