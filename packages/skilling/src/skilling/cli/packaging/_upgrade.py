"""``skilling upgrade`` — the one sanctioned way a learner moves to a newer course version.

``--check`` (the default) looks and reports; it never switches the workspace and never writes
the record. Ordinary resolution keeps a cached ref as a snapshot (spec/workspace.md
#fetched-content), so the check fetches the source *fresh* (``sources.fetch_fresh``):
following semver tags with the record's major version, falling back to the default branch
when a repository has none, and reporting a sha-pinned ref as pinned. Fetched content may land
under its own ``<id>@<version>`` directory, but no ref binding, manifest entry or record moves.

``--yes`` applies the same plan as one recoverable sequence under the workspace lock: bind the
ref to the verified content, switch the manifest entry, then roll the record forward through
the store's journaled upgrade (``delivery.roll_forward``). Each step is atomic on its own. A
crash between the manifest switch and the record commit leaves a course whose record is behind
its workspace entry; every command then refuses with a pointer back here, and re-running
``skilling upgrade --yes`` finishes it. A plan that cannot carry progress over refuses before
anything changes (exit 5, ``version-mismatch``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import typer

from ...conformance import validate_course
from ...course import Course, CourseLoadError, compare, declared_level, is_course_id
from ...delivery import UpgradePlan, preview_upgrade, roll_forward
from ...sources import (
    CacheConflict,
    CourseInvalid,
    GhResolver,
    ResolvedSource,
    ResolveError,
    UpdateKind,
    UpdateSource,
    UrlResolver,
    bind_fresh,
    fetch_fresh,
    find_update,
)
from ...store import LOCAL_LEARNER, Conflict, FileProgressStore, RuntimeSnapshot
from ...workspace import (
    SKILLING_DIR,
    WorkspaceCourse,
    add_course,
    courses_dir,
    find_workspace,
    import_local_course,
    load_manifest,
    resolve_state_root,
    workspace_lock,
)
from .. import _render as render
from ..runtime import ExitCode, emit

NEWER = ("patch", "minor", "major")


@dataclass(frozen=True)
class Located:
    """The course being upgraded, as this workspace (or an explicit directory) holds it."""

    course_id: str
    installed: Course
    store: FileProgressStore
    workspace: Path | None = None
    entry: WorkspaceCourse | None = None


@dataclass(frozen=True)
class Check:
    located: Located
    status: str
    """``up-to-date``, ``available``, ``pending`` (record behind its installed content),
    ``pinned`` or ``no-same-major``."""

    record_version: str | None
    source: UpdateSource | None = None
    available: Course | None = None
    fetched: ResolvedSource | None = None
    local_source: Path | None = None
    plan: UpgradePlan | None = None

    @property
    def target(self) -> Course | None:
        """What applying would move to: newer available content, else installed content the
        record is behind on, else nothing."""
        if self.status == "available":
            return self.available
        if self.status == "pending":
            return self.located.installed
        return None


def upgrade(
    course: str = typer.Option(..., "--course", help="Course id in this workspace, or a path."),
    check: bool = typer.Option(False, "--check", help="Report only (the default)."),
    yes: bool = typer.Option(False, "--yes", help="Apply the upgrade the check reports."),
    state: Path | None = typer.Option(
        None, "--state", envvar="SKILLING_STATE_ROOT", help="Where the progress record lives."
    ),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check for a newer version of a course and, with --yes, move to it keeping progress."""
    if check and yes:
        _refuse(ExitCode.INVALID, "invalid-arguments", "choose --check or --yes, not both", as_json)
    try:
        located = _locate(course, state, as_json)
        found = _check(located, as_json)
        if not yes:
            _report(found, "check", as_json)
            return
        _apply(found, as_json)
    except CourseInvalid as exc:
        _refuse(ExitCode.INVALID, "course-invalid", str(exc), as_json)
    except CacheConflict as exc:
        _refuse(ExitCode.CONFLICT, "cache-conflict", str(exc), as_json)
    except ResolveError as exc:
        _refuse(ExitCode.ERROR, "source-unavailable", str(exc), as_json)
    except Conflict as exc:
        _refuse(ExitCode.CONFLICT, "conflict", str(exc), as_json)


# ------------------------------------------------------------------------------- locating


def _locate(course: str, state: Path | None, as_json: bool) -> Located:
    store = FileProgressStore(resolve_state_root(state))
    path = Path(course)
    if path.is_dir():
        installed = _validated(path)
        return Located(installed.id, installed, store)
    workspace = find_workspace()
    entry = load_manifest(workspace).course(course) if workspace and is_course_id(course) else None
    if workspace is None or entry is None:
        _refuse(
            ExitCode.INVALID,
            "course-not-found",
            f"{course!r} is not a course directory or a course in this workspace",
            as_json,
        )
    installed = _validated(workspace / SKILLING_DIR / entry.path)
    return Located(entry.id, installed, store, workspace, entry)


def _validated(path: Path) -> Course:
    report = validate_course(path)
    if not report.clean:
        raise CourseInvalid(f"{path} does not conform to the format", findings=report.findings)
    try:
        return Course.load(path)
    except CourseLoadError as exc:
        raise CourseInvalid(f"{exc.code}: {exc.message}", findings=[]) from exc


def _is_remote(ref: str) -> bool:
    return GhResolver.claims(ref) or UrlResolver.claims(ref)


def _local_source(located: Located) -> Path | None:
    if located.entry is None or _is_remote(located.entry.ref):
        return None
    candidate = Path(located.entry.ref)
    for option in (candidate, (located.workspace or Path.cwd()) / candidate):
        if option.is_dir():
            return option.resolve()
    raise ResolveError(
        f"the local course source {located.entry.ref!r} is no longer there; restore it or "
        "start the course from its new location"
    )


# -------------------------------------------------------------------------------- checking


def _record(located: Located) -> RuntimeSnapshot | None:
    return located.store.read_runtime_snapshot(LOCAL_LEARNER, located.course_id)


def _check(located: Located, as_json: bool) -> Check:
    snapshot = _record(located)
    record_version = snapshot.record.course_version if snapshot else None
    current = record_version or located.installed.version
    source: UpdateSource | None = None
    fetched: ResolvedSource | None = None
    local: Path | None = None
    available: Course | None = None
    if located.entry is None:
        available = located.installed
    elif _is_remote(located.entry.ref):
        assert located.workspace is not None
        source = find_update(located.entry.ref, current)
        if source.fetch:
            fetched = fetch_fresh(source.ref, cache=courses_dir(located.workspace), pin=source.pin)
            available = fetched.course
    else:
        local = _local_source(located)
        assert local is not None
        available = _validated(local)

    newer = (
        available is not None
        and declared_level(located.installed.version, available.version) in NEWER
    )
    if newer:
        status = "available"
    elif record_version is not None and record_version != located.installed.version:
        status = "pending"
    elif source is not None and source.kind is UpdateKind.PINNED:
        status = "pinned"
    elif source is not None and source.tag is None and source.newer_major is not None:
        status = "no-same-major"
    else:
        status = "up-to-date"
    found = Check(located, status, record_version, source, available, fetched, local)
    target = found.target
    plan = (
        preview_upgrade(located.store, target, LOCAL_LEARNER).plan if target is not None else None
    )
    return Check(located, status, record_version, source, available, fetched, local, plan)


# -------------------------------------------------------------------------------- applying


def _apply(found: Check, as_json: bool) -> None:
    target = found.target
    if target is None:
        _report(found, "apply", as_json)
        return
    if found.plan is not None and not found.plan.ok:
        _refuse(
            ExitCode.VERSION_MISMATCH,
            "version-mismatch",
            found.plan.refusal_message(),
            as_json,
            upgrade=_payload(found, "apply"),
        )
    located = found.located
    if located.workspace is not None and found.status == "available":
        with workspace_lock(located.workspace):
            switch_workspace(found)
    rolled = roll_forward(located.store, target, LOCAL_LEARNER)
    if rolled.plan is not None and not rolled.plan.ok:
        _refuse(
            ExitCode.VERSION_MISMATCH,
            "version-mismatch",
            rolled.plan.refusal_message() + " Run `skilling upgrade --check` again.",
            as_json,
        )
    _report(found, "apply", as_json, applied=True)


def switch_workspace(found: Check) -> None:
    """Point the workspace entry at the target content: bind a fetched ref, or re-import a
    local source, each through its existing atomic path."""
    located = found.located
    assert located.workspace is not None and located.entry is not None
    if found.fetched is not None and found.source is not None:
        bound = bind_fresh(found.source.ref, found.fetched, cache=courses_dir(located.workspace))
        add_course(located.workspace, bound.course, found.source.ref, bound.path)
    elif found.local_source is not None:
        imported = import_local_course(located.workspace, found.local_source, ref=located.entry.ref)
        if found.available is None or imported.course.version != found.available.version:
            raise Conflict("course source", found.available and found.available.version, None)


# ------------------------------------------------------------------------------- reporting


def progress_payload(plan: UpgradePlan | None, *, applied: bool = False) -> dict[str, object]:
    if plan is None:
        return {"status": "none", "message": "No progress to carry over."}
    status = ("rolled-forward" if applied else "carries-over") if plan.ok else "not-resumable"
    return {
        "status": status,
        "from": plan.from_version,
        "to": plan.to_version,
        "level": plan.level,
        "reason": plan.refusal.value if plan.refusal is not None else None,
        "dropped_objectives": list(plan.dropped_objectives),
        "lesson_restarted": plan.lesson_restarted,
        "message": plan.summary(),
    }


def _bump(found: Check) -> dict[str, object] | None:
    target = found.target
    if target is None:
        return None
    old = found.located.installed
    if found.status == "pending" or target is old:
        assert found.record_version is not None
        return {"declared": declared_level(found.record_version, target.version)}
    diff = compare(old, target)
    return {
        "declared": diff.declared,
        "required": diff.required,
        "satisfied": diff.satisfied,
        "reasons": diff.reasons(),
    }


def _payload(found: Check, mode: str, *, applied: bool = False) -> dict[str, object]:
    source = found.source
    target = found.target
    return {
        "course": {
            "id": found.located.course_id,
            "installed": found.located.installed.version,
            "record": found.record_version,
        },
        "status": "applied" if applied else found.status,
        "mode": mode,
        "available": target.version if target is not None else None,
        "source": {
            "kind": source.kind.value,
            "ref": source.ref,
            "tag": source.tag,
            "newer_major": source.newer_major,
        }
        if source is not None
        else {"kind": "local" if found.located.entry else "directory"},
        "bump": _bump(found),
        "progress": progress_payload(found.plan, applied=applied),
    }


def _report(found: Check, mode: str, as_json: bool, *, applied: bool = False) -> None:
    payload = _payload(found, mode, applied=applied)
    if as_json:
        emit({"ok": True, "verb": "upgrade", **payload})
        return
    console = render.console
    located = found.located
    console.print(f"[bold]{located.course_id}[/] {located.installed.version}", soft_wrap=True)
    target = found.target
    if applied and target is not None:
        console.print(f"  [green]Upgraded to {target.version}.[/]", soft_wrap=True)
    elif found.status == "available" and target is not None:
        bump = _bump(found) or {}
        console.print(f"  {target.version} is available ({bump.get('declared')}).", soft_wrap=True)
    elif found.status == "pending" and target is not None:
        console.print(
            f"  Progress is still on {found.record_version}; {target.version} is installed.",
            soft_wrap=True,
        )
    elif found.status == "pinned":
        console.print("  Pinned to a commit: no automatic upgrades.", soft_wrap=True)
    else:
        console.print("  Up to date.", soft_wrap=True)
    if found.source is not None and found.source.newer_major is not None:
        console.print(
            f"  A new major release ({found.source.newer_major}) exists; progress would not "
            "carry over to it automatically.",
            soft_wrap=True,
        )
    if found.plan is not None:
        console.print(f"  {found.plan.summary()}", soft_wrap=True)
    if not applied and target is not None and (found.plan is None or found.plan.ok):
        console.print(f"Run: skilling upgrade --course {located.course_id} --yes", soft_wrap=True)


def _refuse(
    code: ExitCode,
    error: str,
    message: str,
    as_json: bool,
    *,
    upgrade: dict[str, object] | None = None,
) -> NoReturn:
    if as_json:
        body: dict[str, object] = {"code": error, "message": message}
        if upgrade is not None:
            body["upgrade"] = upgrade
        emit({"ok": False, "error": body})
    else:
        render.err_console.print(f"[red]{error}[/] {message}")
    raise typer.Exit(code)
