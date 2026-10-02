"""Explicit workspace artifact pointers and ceremony copy, with existing chronology rules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from ..course import Artifact, utc_now
from ..delivery import share_text
from ..workspace import showcase_dir
from ._companion import check_revision, course_view, select_coordinate
from ._errors import RefusalKind, SessionRefusal
from ._loading import RuntimeSession
from ._teaching import _course_complete, snapshot_view
from ._types import ArtifactResult, ArtifactView, CeremonyView


def artifact_view(artifact: Artifact) -> ArtifactView:
    return ArtifactView(artifact.path, artifact.title, artifact.coordinate, artifact.added_at)


def ceremony(
    session: RuntimeSession, coordinate: str | None, workspace_root: Path | None
) -> CeremonyView:
    selected = select_coordinate(session, coordinate)
    finished = session.course.lesson_at(selected)
    if finished is None or not session.course.is_last_in_phase(selected):
        raise SessionRefusal(
            RefusalKind.ILLEGAL,
            "not-a-phase-boundary",
            f"{selected} is not the last lesson of its phase",
        )
    phase = session.course.phase_of(selected)
    done = _course_complete(session.course, session.record)
    showcase = None
    if workspace_root is not None:
        if not workspace_root.is_absolute():
            raise SessionRefusal(
                RefusalKind.INVALID, "no-workspace", "workspace root must be absolute"
            )
        showcase = (
            showcase_dir(workspace_root, session.course.id).relative_to(workspace_root).as_posix()
        )
    return CeremonyView(
        snapshot_view(session.course, session.record, session.revision, session.scratch),
        selected,
        phase.number if phase else None,
        phase.name if phase else None,
        phase.highlight if phase else None,
        share_text(session.course, session.record, phase, course_complete=done),
        done,
        showcase,
    )


def artifact_add(
    session: RuntimeSession,
    path: Path,
    title: str,
    workspace_root: Path,
    path_base: Path,
    coordinate: str | None,
    expected_revision: str | None,
    now: datetime | None,
) -> ArtifactResult:
    if not workspace_root.is_absolute() or not path_base.is_absolute():
        raise SessionRefusal(
            RefusalKind.INVALID, "no-workspace", "workspace and path base must be absolute"
        )
    if expected_revision is not None:
        check_revision(session, expected_revision)
    absolute = (path if path.is_absolute() else path_base / path).resolve()
    if not absolute.exists():
        raise SessionRefusal(
            RefusalKind.INVALID, "artifact-missing", f"{str(path)!r} does not exist"
        )
    workspace = workspace_root.resolve()
    if not absolute.is_relative_to(workspace):
        raise SessionRefusal(
            RefusalKind.INVALID,
            "artifact-outside-workspace",
            f"{str(path)!r} resolves to {absolute}, outside the workspace root {workspace}",
        )
    selected = select_coordinate(session, coordinate)
    try:
        artifact = Artifact(
            path=absolute.relative_to(workspace).as_posix(),
            title=title,
            coordinate=selected,
            added_at=now or utc_now(),
        )
    except ValidationError as exc:
        raise SessionRefusal(RefusalKind.INVALID, "artifact-invalid", str(exc)) from exc
    kept = [a for a in session.record.artifacts if a.path != artifact.path]
    record = session.record.model_copy(update={"artifacts": [*kept, artifact]})
    revision = session.store.put_record(record, session.revision)
    return ArtifactResult(course_view(session.course), artifact_view(artifact), revision)
