"""Local import intents: a recoverable tree/manifest pair under a workspace lock.

Only cooperating local-filesystem processes are covered. Stop writers before relocation;
this is neither hostile-path protection nor a physical power-loss guarantee.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..conformance import validate_course
from ..course import Course
from ..sources import (
    GhResolver,
    ResolveError,
    UrlResolver,
    invalidate_cached_course,
    locked_directory,
    safe_source_ref,
)
from ._manifest import WorkspaceManifest


class ImportRecoveryError(ResolveError):
    """A workspace needs investigation; preserve its import intent and course copies."""


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: Literal[1]
    phase: Literal["prepared", "committed", "rolled-back"]
    staging: str = Field(pattern=r"^courses/\.skilling-import-[a-z0-9_\-]+$")
    destination: str
    previous: str
    candidate: str
    old_manifest: str | None
    new_manifest: str
    old_digest: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    new_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    course_id: str
    course_version: str

    @field_validator("version", mode="before")
    @classmethod
    def known_version(cls, value: object) -> object:
        if type(value) is not int or value != 1:
            raise ValueError("unsupported import metadata version")
        return value


def _ref(ref: str) -> str:
    return safe_source_ref(ref) if GhResolver.claims(ref) or UrlResolver.claims(ref) else ref


def _plain(path: Path, *, directory: bool) -> None:
    if not path.exists() and not path.is_symlink():
        return
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or (info.st_file_attributes & 0x400 if os.name == "nt" else False)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        raise ImportRecoveryError("workspace paths must be plain files/directories, not symlinks")


def _root(workspace: Path) -> Path:
    root = workspace / ".skilling"
    _plain(root, directory=True)
    _plain(root / "courses", directory=True)
    for name in ("workspace.yaml", "import.yaml", ".workspace.lock"):
        _plain(root / name, directory=False)
    return root


def _digest(path: Path) -> str:
    """Exact local tree bytes/kinds, including Git files; no remote mode trust is inferred."""
    _plain(path, directory=True)
    if not path.is_dir():
        raise ImportRecoveryError("import tree is missing")
    result = hashlib.sha256(b"skilling-import-tree-v1\0")
    for child in sorted(path.rglob("*"), key=lambda p: p.relative_to(path).as_posix()):
        directory = child.is_dir()
        _plain(child, directory=directory)
        name = child.relative_to(path).as_posix().encode()
        result.update(len(name).to_bytes(8, "big") + name)
        result.update(b"directory\0" if directory else b"file\0")
        if not directory:
            result.update(hashlib.sha256(child.read_bytes()).digest())
    return result.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    _plain(path, directory=False)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def manifest_bytes(manifest: WorkspaceManifest) -> bytes:
    return yaml.safe_dump(
        manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
    ).encode("utf-8")


def _decode(encoded: str | None) -> bytes | None:
    return base64.b64decode(encoded, validate=True) if encoded is not None else None


def _manifest(raw: bytes | None) -> WorkspaceManifest:
    decoded = yaml.safe_load(raw) if raw is not None else None
    if decoded is not None and not isinstance(decoded, dict):
        raise ImportRecoveryError("import manifest must be a mapping")
    return WorkspaceManifest.model_validate(decoded if decoded is not None else {})


def _write_intent(root: Path, intent: Intent) -> None:
    _atomic_write(root / "import.yaml", intent.model_dump_json(indent=2).encode())


def _checked_tree(path: Path, digest: str, intent: Intent) -> None:
    if _digest(path) != digest:
        raise ImportRecoveryError("import tree changed; preserve all copies and investigate")
    report = validate_course(path)
    if not report.clean:
        raise ImportRecoveryError("import tree no longer validates; preserve all copies")
    course = Course.load(path)
    if (course.id, course.version) != (intent.course_id, intent.course_version):
        raise ImportRecoveryError("import tree identity disagrees with intent")


def _preflight(root: Path, intent: Intent) -> None:
    """Validate the entire descriptor and all observable targets before any effect."""
    old, new = _decode(intent.old_manifest), _decode(intent.new_manifest)
    before, after = _manifest(old), _manifest(new)
    entry = after.course(intent.course_id)
    if (
        entry is None
        or entry.version != intent.course_version
        or entry.path != f"courses/{entry.id}@{entry.version}"
        or entry.showcase != f"showcase/{entry.id}"
        or intent.destination != entry.path
        or intent.candidate != f"{intent.staging}/course"
        or intent.previous != f"{intent.staging}/previous"
        or entry.ref != _ref(entry.ref)
        or len([c for c in after.courses if c.id == entry.id]) != 1
        or [c for c in before.courses if c.id != entry.id]
        != [c for c in after.courses if c.id != entry.id]
    ):
        raise ImportRecoveryError("import descriptor disagrees with manifest")
    existing = before.course(entry.id)
    if existing is not None and entry.added_at != existing.added_at:
        raise ImportRecoveryError("import changed the original added-at time")
    for name in (intent.staging, intent.candidate, intent.previous, intent.destination):
        _plain(root / name, directory=True)
    stage = root / intent.staging
    if stage.exists() and any(
        p.name not in {"course", "previous", ".owner"} for p in stage.iterdir()
    ):
        raise ImportRecoveryError("import staging contains unrecognized files; preserve it")
    owner = stage / ".owner"
    _plain(owner, directory=False)
    if (
        stage.exists()
        and not (intent.phase != "prepared" and not any(stage.iterdir()))
        and (not owner.exists() or owner.read_bytes() != stage.name.encode())
    ):
        raise ImportRecoveryError("import staging ownership cannot be established")
    manifest = root / "workspace.yaml"
    current = manifest.read_bytes() if manifest.exists() else None
    if current not in (old, new):
        raise ImportRecoveryError("workspace manifest changed outside the import; preserve it")
    destination, candidate, previous = (
        root / intent.destination,
        root / intent.candidate,
        root / intent.previous,
    )
    if intent.phase == "committed":
        if (
            current != new
            or candidate.exists()
            or (previous.exists() and intent.old_digest is None)
        ):
            raise ImportRecoveryError("committed import disagrees with its manifest or staging")
        _checked_tree(destination, intent.new_digest, intent)
        # Cleanup may have removed part of the owned backup; check safety, not its old hash.
        if previous.exists():
            _digest(previous)
        return
    if intent.phase == "rolled-back":
        if current != old or previous.exists() or candidate.exists() or intent.old_digest is None:
            raise ImportRecoveryError("rolled-back import disagrees with its manifest or backup")
        if intent.old_digest is not None:
            _checked_tree(destination, intent.old_digest, intent)
        elif destination.exists():
            raise ImportRecoveryError("unexpected destination after rollback")
        return
    if (
        candidate.exists()
        and destination.exists()
        and (
            intent.old_digest is None
            or previous.exists()
            or _digest(destination) != intent.old_digest
        )
    ):
        raise ImportRecoveryError("impossible prepared import directory combination")
    if candidate.exists():
        _checked_tree(candidate, intent.new_digest, intent)
    if previous.exists():
        if intent.old_digest is None:
            raise ImportRecoveryError("unexpected import backup")
        _checked_tree(previous, intent.old_digest, intent)
    if destination.exists():
        digest = _digest(destination)
        if digest not in (intent.new_digest, intent.old_digest):
            raise ImportRecoveryError("import destination changed; preserve all copies")
        _checked_tree(destination, digest, intent)
        if previous.exists() and digest != intent.new_digest:
            raise ImportRecoveryError("ambiguous import backup and destination")
    if not (candidate.exists() or destination.exists() or previous.exists()):
        raise ImportRecoveryError("no validated import copy survives")


def remove_owned_tree(path: Path) -> None:
    """Delete only a preflighted task-owned tree, including Windows read-only Git files."""

    def writable(operation: Callable[..., object], name: str, error: object) -> None:
        item = Path(name)
        _plain(item, directory=False)
        item.chmod(item.stat().st_mode | stat.S_IWRITE)
        operation(name)

    shutil.rmtree(path, onerror=writable)


def claim_staging(stage: Path) -> None:
    _atomic_write(stage / ".owner", stage.name.encode())


def _cleanup(root: Path, intent: Intent) -> None:
    stage = root / intent.staging
    if stage.exists():
        for name in ("previous", "course"):
            path = stage / name
            if path.exists():
                remove_owned_tree(path)
        (stage / ".owner").unlink(missing_ok=True)
        stage.rmdir()
    (root / "import.yaml").unlink()


def _apply(root: Path, intent: Intent) -> None:
    _preflight(root, intent)
    if intent.phase != "prepared":
        _cleanup(root, intent)
        return
    destination, candidate, previous = (
        root / intent.destination,
        root / intent.candidate,
        root / intent.previous,
    )
    new_available = candidate.exists() or (
        destination.exists() and _digest(destination) == intent.new_digest
    )
    with invalidate_cached_course(root / "courses", intent.course_id, intent.course_version):
        if new_available:
            if candidate.exists():
                if destination.exists():
                    destination.rename(previous)
                try:
                    candidate.rename(destination)
                except OSError:
                    if previous.exists() and not destination.exists():
                        previous.rename(destination)
                    raise
            _atomic_write(root / "workspace.yaml", _decode(intent.new_manifest) or b"")
            finalized = intent.model_copy(update={"phase": "committed"})
        else:
            if previous.exists():
                previous.rename(destination)
            old = _decode(intent.old_manifest)
            if old is None:
                (root / "workspace.yaml").unlink(missing_ok=True)
            else:
                _atomic_write(root / "workspace.yaml", old)
            finalized = intent.model_copy(update={"phase": "rolled-back"})
        _write_intent(root, finalized)
        _cleanup(root, finalized)


def _recover(root: Path) -> None:
    path = root / "import.yaml"
    if not path.exists():
        return
    try:
        intent = Intent.model_validate_json(path.read_bytes())
        _apply(root, intent)
    except ImportRecoveryError:
        raise
    except (ResolveError, ValueError, OSError, yaml.YAMLError) as exc:
        raise ImportRecoveryError(
            "workspace import recovery refused; preserve .skilling/import.yaml and course copies"
        ) from exc


@contextmanager
def workspace_lock(workspace: Path) -> Iterator[None]:
    """Serialize starts and coherent reads, recovering before exposing manifest/content."""
    with ExitStack() as stack:
        try:
            root = _root(workspace)
            root.mkdir(parents=True, exist_ok=True)
            stack.enter_context(locked_directory(root, filename=".workspace.lock"))
            _root(workspace)
            _recover(root)
        except ImportRecoveryError:
            raise
        except (OSError, ResolveError) as exc:
            raise ImportRecoveryError(
                "cannot access or recover workspace; preserve its files and retry"
            ) from exc
        yield


def recover_workspace(workspace: Path) -> None:
    with workspace_lock(workspace):
        pass


def publish_import(
    workspace: Path, candidate: Path, destination: Path, manifest: WorkspaceManifest
) -> None:
    """Caller holds workspace lock; prepare the complete intent before cache/tree effects."""
    root = _root(workspace)
    path = root / "workspace.yaml"
    old = path.read_bytes() if path.exists() else None
    course = Course.load(candidate)
    intent = Intent(
        version=1,
        phase="prepared",
        staging=candidate.parent.relative_to(root).as_posix(),
        candidate=candidate.relative_to(root).as_posix(),
        previous=(candidate.parent / "previous").relative_to(root).as_posix(),
        destination=destination.relative_to(root).as_posix(),
        old_manifest=base64.b64encode(old).decode() if old is not None else None,
        new_manifest=base64.b64encode(manifest_bytes(manifest)).decode(),
        old_digest=_digest(destination) if destination.exists() else None,
        new_digest=_digest(candidate),
        course_id=course.id,
        course_version=course.version,
    )
    _preflight(root, intent)
    _write_intent(root, intent)
    _apply(root, intent)


@contextmanager
def workspace_read(path: Path) -> Iterator[None]:
    """Hold recovery/read isolation for a workspace path, even outside the caller's cwd."""
    try:
        current = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise ImportRecoveryError("cannot resolve workspace content path") from exc
    for candidate in (current, *current.parents):
        root = candidate / ".skilling"
        if any(
            p.exists() or p.is_symlink() for p in (root / "workspace.yaml", root / "import.yaml")
        ):
            with workspace_lock(candidate):
                yield
            return
    yield
