"""``skilling artifact add`` / ``artifact list`` — pointers to work the learner built, recorded
only through the CLI at exactly the moments the loop already owns: phase ceremony and confirmed
homework submission (spec/workspace.md#artifacts). This module writes neither: it is the
storage primitive the driving skill calls *at* those moments, not a third moment of its own.

Artifacts never gate the flow — this module imports neither ``complete_lesson`` nor
``submit_homework``, so it could not accidentally make either wait on a write it does. ``add``
is the one verb here with anything to decide: resolving ``<path>`` against the workspace root,
defaulting the coordinate the same way ``ceremony`` already does, and upserting by path through
the store's own CAS. ``list`` is a plain read of ``record.artifacts``, no different from
``homework check``.

Interim note: ``open_session`` (``_common.py``) does not yet resolve a workspace course id or
default its state root to the workspace's own ``<state-root>`` — that is tracked separately
(state-root resolution). ``_resolve_course_ref`` and the explicit ``state_root(workspace)``
fallback below are this module's own, local stand-in, so ``add`` does not have to wait on it;
reconcile the two when that lands.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Artifact, is_course_id, utc_now
from ...store import LOCAL_LEARNER, Conflict
from ...workspace import SKILLING_DIR, find_workspace, load_manifest, state_root
from ._common import ExitCode, emit, fail, now_override, open_session

COURSE_HELP = "Path to the course directory."
COURSE_REF_HELP = (
    "Course id (resolved through the workspace manifest) or a path. Defaults to the "
    "workspace's sole course when it holds exactly one."
)
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_CourseRefOption = typer.Option(None, "--course", help=COURSE_REF_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

artifact = typer.Typer(no_args_is_help=True, help="Record and list pointers to workspace work.")


def _resolve_course_ref(course: str | None, workspace: Path) -> str:
    """A workspace course id resolves through the manifest to its real content directory
    (``<workspace>/.skilling/<entry.path>``); anything else — including an unrecognised id —
    is treated as a literal path, exactly like every other verb's ``--course``.

    Omitted entirely, the workspace's sole course stands in, since naming one is pointless
    when there is only one to mean.
    """
    manifest = load_manifest(workspace)
    if course is not None:
        if is_course_id(course):
            entry = manifest.course(course)
            if entry is not None:
                return str(workspace / SKILLING_DIR / entry.path)
        return course
    if len(manifest.courses) == 1:
        return str(workspace / SKILLING_DIR / manifest.courses[0].path)
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
        help="Coordinate to record against. Defaults to the last completed lesson.",
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

    course_ref = _resolve_course_ref(course, workspace)
    resolved_state = state if state is not None else state_root(workspace)
    session = open_session(course_ref, resolved_state, learner)

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

    if coordinate is not None:
        resolved_coordinate = coordinate
    elif session.record.completed:
        # The same keying `ceremony` already uses (`_session.py`): by the time there is
        # anything worth pointing at, `complete` has moved `position` past the finished
        # lesson, so "the current position" is not what a default coordinate should mean.
        resolved_coordinate = session.record.completed[-1]
    else:
        fail(
            ExitCode.INVALID,
            "coordinate-unknown",
            "no --coordinate given and no lesson has been completed yet",
        )

    if session.course.lesson_at(resolved_coordinate) is None:
        fail(
            ExitCode.INVALID,
            "coordinate-unknown",
            f"{resolved_coordinate!r} is not a lesson in {session.course.id}",
        )

    new_artifact = Artifact(
        path=relative,
        title=title,
        coordinate=resolved_coordinate,
        added_at=now_override() or utc_now(),
    )
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
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Every artifact on the record, read-only — same session-loading as every other read
    verb, no workspace requirement beyond what ``open_session`` already needs (though an
    artifact is only ever meaningful once one exists)."""
    session = open_session(course, state, learner)
    emit(
        {
            "ok": True,
            "verb": "artifact-list",
            "course": {"id": session.course.id, "version": session.course.version},
            "artifacts": [a.model_dump(mode="json") for a in session.record.artifacts],
        }
    )
