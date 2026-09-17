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
from pydantic import ValidationError

from ...course import Artifact, utc_now
from ...store import LOCAL_LEARNER, Conflict
from ...workspace import find_workspace, load_manifest, resolve_course_location
from ._common import (
    ExitCode,
    emit,
    fail,
    now_override,
    open_chronology_session,
    open_session,
    select_completed_coordinate,
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

    session = open_chronology_session(_course_ref(course, workspace), state, learner)

    given = Path(path)
    absolute = (given if given.is_absolute() else Path.cwd() / given).resolve()
    if not absolute.exists():
        fail(ExitCode.INVALID, "artifact-missing", f"{path!r} does not exist")

    workspace_resolved = workspace.resolve()
    if not absolute.is_relative_to(workspace_resolved):
        fail(
            ExitCode.INVALID,
            "artifact-outside-workspace",
            f"{path!r} resolves to {absolute}, outside the workspace root {workspace_resolved}",
        )
    relative = absolute.relative_to(workspace_resolved).as_posix()

    resolved_coordinate = select_completed_coordinate(session, learner, coordinate)

    try:
        new_artifact = Artifact(
            path=relative,
            title=title,
            coordinate=resolved_coordinate,
            added_at=now_override() or utc_now(),
        )
    except ValidationError as exc:
        fail(ExitCode.INVALID, "artifact-invalid", str(exc))

    kept = [a for a in session.record.artifacts if a.path != new_artifact.path]
    updated_record = session.record.model_copy(update={"artifacts": [*kept, new_artifact]})

    try:
        new_revision = session.store.put_record(updated_record, session.revision)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))

    emit(
        {
            "ok": True,
            "verb": "artifact-add",
            "course": {"id": session.course.id, "version": session.course.version},
            "artifact": new_artifact.model_dump(mode="json"),
            "revision": new_revision,
        }
    )


# ------------------------------------------------------------------------------------ list


@artifact.command("list")
def list_artifacts(
    course: str | None = _CourseRefOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """List artifacts using the same course and state selection as ``add``.

    Like other session verbs, initializes a progress record on first use. Explicit course
    references work outside a workspace; omission selects the workspace's sole course.
    """
    session = open_session(_course_ref(course, find_workspace()), state, learner)
    emit(
        {
            "ok": True,
            "verb": "artifact-list",
            "course": {"id": session.course.id, "version": session.course.version},
            "artifacts": [a.model_dump(mode="json") for a in session.record.artifacts],
        }
    )
