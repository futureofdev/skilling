"""``skilling courses`` — enumerate every course a learner has local progress state for.

The mechanism the generic ``learn``/``progress``/``homework`` skill triad needs for cross-course
discovery (docs/superpowers/specs/2026-08-06-generic-delivery-skills-design.md): nothing prior
to this ever enumerated "what courses does this learner even have, and which one were they most
recently working on" — every other verb is *handed* a course. Read-only: enumeration only, no
session, no write.

Title resolution. A state root (``store/_file.py``) only ever records a course *id* plus the
record it wrote for that id — never where that course's content lives. When the current
directory is inside a workspace (spec/workspace.md) and that workspace's manifest has added
the course, its content sits at ``.skilling/<path>`` and both the title and a ``path`` field
are resolved from there first. Otherwise, if the course was ever resolved through
``skilling fetch``, its manifest sits in the fetch cache at
``<cache>/<id>@<record.course_version>/`` (``sources/_cache.py``'s own layout), and the title is
read from there instead — with no ``path`` in the row, since a fetch-cache hit says nothing
about where a workspace keeps that course. A course the learner pointed ``--course`` at
directly — a bare local path, never fetched, added to a workspace, or cached, exactly how this
repo's own tests run against ``examples/hello-skilling`` — has neither; falling back to the id
itself as the display title, and omitting ``path`` entirely, is the documented, honest choice
for that case, rather than guessing or crashing the whole listing over one unresolvable course.

Last-activity granularity. ``Record.last_activity`` is a ``date``, not a ``datetime`` — the
runtime (``delivery/_runtime.py``) deliberately maintains it on every write, so it is the
honest signal for "which day this course was last touched," not an incidental one like a
state-root file's mtime (which a backup, sync, or checkout can bump with no learning activity
behind it at all). Its cost is granularity: two courses touched on the same calendar day tie.
That tie is surfaced as-is rather than papered over with invented sub-day precision — the
calling skill is already specified to ask the learner when ``last_activity`` genuinely ties.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

import typer

from ...course import CourseLoadError, is_course_id, is_semver, load_manifest
from ...sources import CACHE_ENV
from ...store import FileProgressStore, open_store
from ...workspace import SKILLING_DIR, find_workspace, resolve_state_root
from ...workspace import courses_dir as workspace_courses_dir
from ...workspace import load_manifest as load_workspace_manifest
from ._common import ExitCode, emit, fail


class _CourseSummary(NamedTuple):
    """One row of the enumeration: exactly what ``courses`` promises, typed rather than a
    raw dict, so sorting has an actual comparable key instead of ``object``.

    ``path`` is ``None`` whenever no discovered workspace has this course — the row-building
    function below turns that into the key's *absence*, not a JSON ``null``, matching
    ``cli/runtime/_session.py``'s ``_tutor`` idiom for the same kind of optional field.
    """

    id: str
    title: str
    last_activity: str
    path: str | None = None


def _row(summary: _CourseSummary) -> dict[str, str]:
    row = {"id": summary.id, "title": summary.title, "last_activity": summary.last_activity}
    if summary.path is not None:
        row["path"] = summary.path
    return row


STATE_HELP = "Where the learner's progress records live."
CACHE_HELP = "Where fetched courses are cached, consulted only to resolve a display title."
JSON_HELP = (
    "Present for compatibility with the documented invocation; output is always this one "
    "JSON line — there is no other rendering to opt out of."
)

_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_CacheOption = typer.Option(None, "--cache", envvar=CACHE_ENV, help=CACHE_HELP)
_JsonOption = typer.Option(True, "--json", help=JSON_HELP)


def _default_cache_root() -> Path:
    """Mirrors ``sources._resolve._default_cache`` — private there and not exported, so this
    is a deliberate two-line duplicate rather than reaching into that module's internals."""
    configured = os.environ.get(CACHE_ENV)
    return Path(configured) if configured else Path.home() / ".skilling" / "courses"


def _title(cache_root: Path, course_id: str, course_version: str) -> str:
    """The manifest title for a course this learner has state for, or the id itself when
    that course's content cannot be found or loaded. See the module docstring."""
    if not (is_course_id(course_id) and is_semver(course_version)):
        return course_id
    candidate = cache_root / f"{course_id}@{course_version}"
    if not candidate.is_dir():
        return course_id
    try:
        return load_manifest(candidate).title
    except CourseLoadError:
        return course_id


def courses(
    state: Path | None = _StateOption,
    cache: Path | None = _CacheOption,
    as_json: bool = _JsonOption,
) -> None:
    """Every course this learner has local progress for, most-recently-active first.

    Backs the skill triad's "which course did you mean" default: pick the course with the
    latest ``last_activity``, and only ask the learner when two or more genuinely tie.
    """
    del as_json  # No alternate rendering exists yet; see JSON_HELP.
    store = open_store(str(resolve_state_root(state)))
    if not isinstance(store, FileProgressStore):
        fail(
            ExitCode.ERROR,
            "enumeration-not-supported",
            "skilling courses can only enumerate the file store backend today",
        )

    cache_root = cache if cache is not None else _default_cache_root()
    workspace = find_workspace()
    manifest = None
    if workspace is not None:
        try:
            manifest = load_workspace_manifest(workspace)
        except FileNotFoundError:
            manifest = None

    found: list[_CourseSummary] = []
    root = store.state_root
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            got = store.get_record(store.learner_id, entry.name)
            if got is None:
                continue
            record, _revision = got

            title = _title(cache_root, record.course_id, record.course_version)
            path: str | None = None
            if workspace is not None and manifest is not None:
                added = manifest.course(record.course_id)
                if added is not None:
                    title = _title(workspace_courses_dir(workspace), added.id, added.version)
                    path = str(workspace / SKILLING_DIR / added.path)

            found.append(
                _CourseSummary(
                    id=record.course_id,
                    title=title,
                    last_activity=record.last_activity.isoformat(),
                    path=path,
                )
            )

    # Stable two-pass sort: id ascending first, then last_activity descending — ties (same
    # last_activity) come out in id order without needing a tuple key with mixed directions.
    found.sort(key=lambda c: c.id)
    found.sort(key=lambda c: c.last_activity, reverse=True)

    emit({"ok": True, "verb": "courses", "courses": [_row(c) for c in found]})
