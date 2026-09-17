"""Workspace directory/manifest publication, exercised across process death."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

import pytest

from skilling.cli.packaging._start import start
from skilling.sources import _cache, resolve
from skilling.workspace import ImportRecoveryError, load_manifest, recover_workspace

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/hello-skilling"
WORKER = Path(__file__).with_name("import_worker.py")
BOUNDARIES = ["staged", "prepared", "backup", "candidate", "manifest", "committed", "cleanup"]


def worker(workspace: Path, source: Path | None = None, *args: str) -> list[str]:
    command = [
        sys.executable,
        str(WORKER),
        "start" if source else "inspect",
        "--workspace",
        str(workspace),
    ]
    if source is not None:
        command += ["--source", str(source)]
    return [*command, *args]


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=30, **kwargs)


class Fixture(NamedTuple):
    source: Path
    workspace: Path


def setup(tmp_path: Path, *, initial: bool = False) -> Fixture:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    shutil.copytree(EXAMPLE, source)
    if not initial:
        result = run(worker(workspace, source))
        assert result.returncode == 0, result.stderr
    (source / "new.txt").write_text("new payload", encoding="utf-8")
    return Fixture(source, workspace)


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_death_after_backup_recovers_content_and_manifest(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    stopped = run(worker(workspace, source, "--boundary", "backup", "--fault", "exit"))
    assert stopped.returncode == 81, stopped.stderr
    assert not (workspace / ".skilling/courses/hello-skilling@1.0.0").exists()
    inspected = run(worker(workspace))
    assert inspected.returncode == 0, inspected.stderr
    entry = load_manifest(workspace).course("hello-skilling")
    assert entry is not None
    content = workspace / ".skilling" / entry.path
    assert (content / "new.txt").read_text() == "new payload"


@pytest.mark.parametrize("boundary", BOUNDARIES)
@pytest.mark.parametrize("when", ["before", "after"])
@pytest.mark.parametrize("fault", ["error", "exit", "hold"])
def test_replacement_boundaries(tmp_path: Path, boundary: str, when: str, fault: str) -> None:
    source, workspace = setup(tmp_path)
    before = load_manifest(workspace)
    protected = tree(workspace / ".skilling/state")
    marker = tmp_path / "stopped"
    command = worker(
        workspace,
        source,
        "--boundary",
        boundary,
        "--when",
        when,
        "--fault",
        fault,
        "--marker",
        str(marker),
    )
    if fault == "hold":
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            deadline = time.monotonic() + 20
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            try:
                assert marker.exists(), process.communicate(timeout=1)
            finally:
                process.kill()
                process.communicate(timeout=10)
    else:
        stopped = run(command)
        assert stopped.returncode != 0, stopped.stdout
        assert marker.exists(), stopped.stderr
    inspected = run(worker(workspace))
    assert inspected.returncode == 0, inspected.stderr
    assert tree(workspace / ".skilling/state") == protected
    entry = load_manifest(workspace).course("hello-skilling")
    original = before.course("hello-skilling")
    assert entry is not None and original is not None and entry.added_at == original.added_at
    assert not (workspace / ".skilling/import.yaml").exists()
    retry = run(worker(workspace, source))
    assert retry.returncode == 0, retry.stderr
    assert (workspace / ".skilling" / entry.path / "new.txt").is_file()


@pytest.mark.parametrize("boundary", [b for b in BOUNDARIES if b != "backup"])
@pytest.mark.parametrize("initial", [True, False])
def test_first_import_and_new_version_recover(tmp_path: Path, boundary: str, initial: bool) -> None:
    source, workspace = setup(tmp_path, initial=initial)
    if not initial:
        manifest = source / "course.yaml"
        manifest.write_text(manifest.read_text().replace('version: "1.0.0"', 'version: "1.1.0"'))
    stopped = run(worker(workspace, source, "--boundary", boundary, "--fault", "exit"))
    assert stopped.returncode == 81, stopped.stderr
    if boundary == "staged":
        # Before an intent, a first import has no discoverable workspace or published content.
        if initial:
            assert not (workspace / ".skilling/workspace.yaml").exists()
    else:
        inspected = run(worker(workspace))
        assert inspected.returncode == 0, inspected.stderr
    retry = run(worker(workspace, source))
    assert retry.returncode == 0, retry.stderr
    entry = load_manifest(workspace).course("hello-skilling")
    assert entry is not None and entry.version == ("1.0.0" if initial else "1.1.0")


@pytest.mark.parametrize(
    "damage",
    [
        "unknown",
        "version",
        "bool-version",
        "missing-version",
        "missing-phase",
        "missing-old-digest",
        "escape",
        "backup",
        "manifest",
        "payload",
        "base64",
        "after",
        "old-type",
        "extra-stage",
        "rolled-back",
        "committed",
    ],
)
def test_malformed_intent_refuses_before_any_effect(tmp_path: Path, damage: str) -> None:
    source, workspace = setup(tmp_path)
    assert (
        run(worker(workspace, source, "--boundary", "backup", "--fault", "exit")).returncode == 81
    )
    path = workspace / ".skilling/import.yaml"
    intent = json.loads(path.read_bytes())
    if damage == "unknown":
        intent["unknown"] = True
    elif damage == "version":
        intent["version"] = 2
    elif damage == "bool-version":
        intent["version"] = True
    elif damage.startswith("missing-"):
        del intent[damage.removeprefix("missing-").replace("-", "_")]
    elif damage == "escape":
        intent["staging"] = "../outside"
    elif damage == "backup":
        intent["previous"] = "courses/other"
    elif damage == "manifest":
        (workspace / ".skilling/workspace.yaml").write_bytes(b"courses: []\n")
    elif damage == "payload":
        (workspace / ".skilling" / intent["candidate"] / "new.txt").write_text("tampered")
    elif damage == "base64":
        intent["new_manifest"] = "not base64!"
    elif damage == "after":
        intent["new_manifest"] = base64.b64encode(b"courses: []\n").decode()
    elif damage == "old-type":
        intent["old_manifest"] = base64.b64encode(b"false\n").decode()
    elif damage in {"rolled-back", "committed"}:
        intent["phase"] = damage
    elif damage == "extra-stage":
        (workspace / ".skilling" / intent["staging"] / "foreign.txt").write_text("owned by user")
    path.write_text(json.dumps(intent))
    snapshot = tree(workspace)
    with pytest.raises(ImportRecoveryError):
        recover_workspace(workspace)
    assert tree(workspace) == snapshot
    inspected = run(worker(workspace))
    assert inspected.returncode != 0
    assert tree(workspace) == snapshot


def test_missing_candidate_restores_exact_prior_manifest(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    manifest = workspace / ".skilling/workspace.yaml"
    original = b"# keep exact legacy bytes\r\n" + manifest.read_bytes()
    manifest.write_bytes(original)
    assert (
        run(worker(workspace, source, "--boundary", "backup", "--fault", "exit")).returncode == 81
    )
    intent = json.loads((workspace / ".skilling/import.yaml").read_bytes())
    shutil.rmtree(workspace / ".skilling" / intent["candidate"])
    assert run(worker(workspace)).returncode == 0
    assert manifest.read_bytes() == original
    assert not (workspace / ".skilling/courses/hello-skilling@1.0.0/new.txt").exists()


def test_pending_relocation_and_runtime_direct_path(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    assert (
        run(worker(workspace, source, "--boundary", "backup", "--fault", "exit")).returncode == 81
    )
    relocated = tmp_path / "relocated"
    workspace.rename(relocated)
    cli = Path(sys.executable).parent / ("skilling.exe" if os.name == "nt" else "skilling")
    content = relocated / ".skilling/courses/hello-skilling@1.0.0"
    for arguments in (
        ["next", "--course", str(content)],
        ["progress", "--course", "hello-skilling"],
        ["artifact", "list", "--course", "hello-skilling"],
    ):
        result = run([str(cli), *arguments], cwd=relocated)
        assert result.returncode == 0, result.stderr
    assert (content / "new.txt").is_file()


def test_concurrent_starts_preserve_both_courses(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path, initial=True)
    other = EXAMPLE.parent / "workbench"
    commands = [worker(workspace, source), worker(workspace, other)]
    processes = [
        subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for c in commands
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)
    assert {c.id for c in load_manifest(workspace).courses} == {"hello-skilling", "workbench"}


def test_remote_binding_invalidated_by_local_replacement(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path, initial=True)
    from .test_cache_identity import repository

    remote = repository(EXAMPLE, tmp_path / "remote")
    ref = remote.as_uri()
    start(ref, workspace, True)
    cache = workspace / ".skilling/courses"
    assert _cache.lookup(cache, ref).course is not None
    start(str(source), workspace, True)
    assert _cache.lookup(cache, ref).course is None
    before = tree(workspace)
    from skilling.sources import ResolveError

    with pytest.raises(ResolveError):
        resolve(ref, cache=cache)
    assert tree(workspace) == before


@pytest.mark.parametrize(
    "ref",
    [
        "https://name:SYNTHETIC_PASSWORD@example.invalid/c.git?token=SYNTHETIC_QUERY#secret",
        "git+ssh://user:SYNTHETIC_PASSWORD@example.invalid/c.git?token=SYNTHETIC_QUERY",
    ],
)
def test_new_provenance_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    from skilling.cli.packaging import _start
    from skilling.course import Course
    from skilling.sources import ResolvedSource
    from skilling.workspace import import_local_course

    source, workspace = setup(tmp_path)
    imported = import_local_course(workspace, source, ref=ref)
    monkeypatch.setattr(
        _start,
        "resolve_remote",
        lambda *a, **k: ResolvedSource(Course.load(imported.path), imported.path, ref, None),
    )
    start(ref, workspace, True)
    for content in tree(workspace).values():
        assert b"SYNTHETIC_PASSWORD" not in content and b"SYNTHETIC_QUERY" not in content
    if ref.startswith("git+ssh"):
        assert "user@" in load_manifest(workspace).courses[0].ref


def test_impossible_prepared_state_preserves_every_byte(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    # Both payloads are intentionally identical: digest equality must not hide missing history.
    (source / "new.txt").unlink()
    assert (
        run(worker(workspace, source, "--boundary", "prepared", "--fault", "exit")).returncode == 81
    )
    journal = workspace / ".skilling/import.yaml"
    intent = json.loads(journal.read_bytes())
    intent["old_digest"] = None
    journal.write_text(json.dumps(intent))
    before = tree(workspace)
    with pytest.raises(ImportRecoveryError, match="impossible"):
        recover_workspace(workspace)
    assert tree(workspace) == before


def test_self_import_recovers_missing_destination_before_validation(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    assert (
        run(worker(workspace, source, "--boundary", "backup", "--fault", "exit")).returncode == 81
    )
    content = workspace / ".skilling/courses/hello-skilling@1.0.0"
    assert not content.exists()
    result = run(worker(workspace, content))
    assert result.returncode == 0, result.stderr
    assert (content / "new.txt").is_file()


def test_foreign_staging_without_ownership_marker_is_preserved(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    assert (
        run(worker(workspace, source, "--boundary", "backup", "--fault", "exit")).returncode == 81
    )
    journal = workspace / ".skilling/import.yaml"
    intent = json.loads(journal.read_bytes())
    (workspace / ".skilling" / intent["staging"] / ".owner").unlink()
    snapshot = tree(workspace)
    with pytest.raises(ImportRecoveryError, match="ownership"):
        recover_workspace(workspace)
    assert tree(workspace) == snapshot


def test_cleanup_of_readonly_local_git_files(tmp_path: Path) -> None:
    from .test_cache_identity import repository

    source = repository(EXAMPLE, tmp_path / "source")
    workspace = tmp_path / "workspace"
    assert run(worker(workspace, source)).returncode == 0
    content = workspace / ".skilling/courses/hello-skilling@1.0.0"
    readonly = content / ".git/readonly"
    readonly.write_text("old metadata", encoding="utf-8")
    readonly.chmod(0o444)
    (source / "new.txt").write_text("replacement", encoding="utf-8")
    assert (
        run(worker(workspace, source, "--boundary", "committed", "--fault", "exit")).returncode
        == 81
    )
    assert run(worker(workspace)).returncode == 0
    assert not readonly.exists()
    assert not list((workspace / ".skilling/courses").glob(".skilling-import-*"))


def test_partial_cleanup_retains_ownership_until_backup_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skilling.workspace import _recovery

    source, workspace = setup(tmp_path)
    assert (
        run(worker(workspace, source, "--boundary", "committed", "--fault", "exit")).returncode
        == 81
    )
    original = _recovery.remove_owned_tree

    def interrupted(path: Path) -> None:
        next(p for p in path.rglob("*") if p.is_file()).unlink()
        raise OSError("interrupted cleanup")

    monkeypatch.setattr(_recovery, "remove_owned_tree", interrupted)
    with pytest.raises(ImportRecoveryError):
        recover_workspace(workspace)
    monkeypatch.setattr(_recovery, "remove_owned_tree", original)
    assert run(worker(workspace)).returncode == 0


def test_mixed_case_tree_order_uses_portable_posix_strings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skilling.workspace import _recovery

    source = tmp_path / "mixed"
    source.mkdir()
    for name in ("a.txt", "Z.txt", "B.txt"):
        (source / name).write_text(name, encoding="utf-8")
    expected = _recovery._digest(source)
    monkeypatch.setattr(Path, "__lt__", lambda left, right: str(left).lower() < str(right).lower())
    assert _recovery._digest(source) == expected


def test_legacy_secret_before_image_is_preserved_not_migrated(tmp_path: Path) -> None:
    from skilling.workspace import _recovery, import_local_course

    source, workspace = setup(tmp_path)
    manifest = workspace / ".skilling/workspace.yaml"
    old = manifest.read_bytes().replace(
        str(source).encode(), b"https://name:LEGACY_SECRET@example.invalid/course"
    )
    manifest.write_bytes(old)
    # Preparation persists exact old bytes, while the replacement provenance is sanitized.
    with pytest.MonkeyPatch.context() as patch:
        original = _recovery._write_intent

        def stop(root: Path, intent: _recovery.Intent) -> None:
            original(root, intent)
            raise OSError("prepared")

        patch.setattr(_recovery, "_write_intent", stop)
        with pytest.raises(OSError):
            import_local_course(
                workspace, source, ref="https://name:NEW_SECRET@example.invalid/course"
            )
    intent = json.loads((workspace / ".skilling/import.yaml").read_bytes())
    assert base64.b64decode(intent["old_manifest"]) == old
    assert b"NEW_SECRET" not in base64.b64decode(intent["new_manifest"])
    assert b"NEW_SECRET" not in (workspace / ".skilling/import.yaml").read_bytes()
    recover_workspace(workspace)


@pytest.mark.parametrize("remote", [False, True])
def test_concurrent_replacements_and_local_remote_starts(tmp_path: Path, remote: bool) -> None:
    from .test_cache_identity import repository

    source, workspace = setup(tmp_path)
    other = repository(EXAMPLE.parent / "workbench", tmp_path / "other") if remote else source
    cli = Path(sys.executable).parent / ("skilling.exe" if os.name == "nt" else "skilling")
    commands = [
        worker(workspace, source),
        [str(cli), "start", other.as_uri() if remote else str(other), str(workspace), "--json"],
    ]
    processes = [
        subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for c in commands
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, (stdout, stderr)
    manifest = load_manifest(workspace)
    assert {c.id for c in manifest.courses} == (
        {"hello-skilling", "workbench"} if remote else {"hello-skilling"}
    )


def test_reader_waits_for_killed_writer_in_configured_workspace(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    marker = tmp_path / "marker"
    command = worker(
        workspace, source, "--boundary", "backup", "--fault", "hold", "--marker", str(marker)
    )
    cli = Path(sys.executable).parent / ("skilling.exe" if os.name == "nt" else "skilling")
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as writer:
        deadline = time.monotonic() + 20
        while not marker.exists() and writer.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        try:
            assert marker.exists()
            environment = {**os.environ, "SKILLING_WORKSPACE": str(workspace)}
            environment.pop("SKILLING_STATE_ROOT", None)
            with subprocess.Popen(
                [str(cli), "next", "--course", "hello-skilling"],
                cwd=tmp_path,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as reader:
                time.sleep(0.2)
                assert reader.poll() is None
                writer.kill()
                writer.communicate(timeout=10)
                stdout, stderr = reader.communicate(timeout=20)
                assert reader.returncode == 0, (stdout, stderr)
                assert json.loads(stdout)["beat"]["name"] == "welcome"
        finally:
            if writer.poll() is None:
                writer.kill()
                writer.communicate(timeout=10)


@pytest.mark.parametrize("name", ["import.yaml", "workspace.yaml"])
def test_dangling_metadata_refuses_discovery(tmp_path: Path, name: str) -> None:
    from skilling.workspace import find_workspace

    root = tmp_path / ".skilling"
    root.mkdir()
    try:
        (root / name).symlink_to(root / "missing")
    except OSError:
        pytest.skip("file symlinks unavailable")
    with pytest.raises(ImportRecoveryError, match="symlinks"):
        find_workspace(tmp_path)


def test_post_commit_finishing_failure_can_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from skilling.cli import app
    from skilling.cli.packaging import _start

    source, workspace = setup(tmp_path, initial=True)
    from skilling.workspace import refresh_entry_files

    original = refresh_entry_files

    def fail(workspace: Path) -> list[Path]:
        raise OSError("failed finishing")

    monkeypatch.setattr(_start, "refresh_entry_files", fail)
    result = CliRunner().invoke(app, ["start", str(source), str(workspace)])
    assert result.exit_code == 1 and "failed finishing" in result.output
    assert load_manifest(workspace).course("hello-skilling") is not None
    assert (workspace / ".skilling/courses/hello-skilling@1.0.0/new.txt").is_file()
    monkeypatch.setattr(_start, "refresh_entry_files", original)
    result = CliRunner().invoke(app, ["start", str(source), str(workspace)])
    assert result.exit_code == 0, result.output


def test_new_credentials_absent_from_prepared_intent_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from skilling.cli import app
    from skilling.cli.packaging import _start
    from skilling.sources import CourseInvalid
    from skilling.workspace import _recovery, import_local_course

    source, workspace = setup(tmp_path)
    ref = "https://user:NEW_PASSWORD@example.invalid/course?token=NEW_QUERY"
    original = _recovery._write_intent

    def stopped(root: Path, intent: _recovery.Intent) -> None:
        original(root, intent)
        raise OSError("prepared")

    with monkeypatch.context() as patch:
        patch.setattr(_recovery, "_write_intent", stopped)
        with pytest.raises(OSError):
            import_local_course(workspace, source, ref=ref)
    raw = (workspace / ".skilling/import.yaml").read_bytes()
    intent = json.loads(raw)
    for content in (
        raw,
        base64.b64decode(intent["new_manifest"]),
        base64.b64decode(intent["old_manifest"]),
    ):
        assert b"NEW_PASSWORD" not in content and b"NEW_QUERY" not in content
    recover_workspace(workspace)

    def invalid(*args, **kwargs):
        raise CourseInvalid("invalid remote", findings=[])

    monkeypatch.setattr(_start, "resolve_remote", invalid)
    result = CliRunner().invoke(app, ["start", ref, str(workspace)])
    assert result.exit_code == 1
    assert "NEW_PASSWORD" not in result.output and "NEW_QUERY" not in result.output


def test_invalid_cache_during_recovery_is_json_refusal_without_effects(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    assert (
        run(worker(workspace, source, "--boundary", "backup", "--fault", "exit")).returncode == 81
    )
    (workspace / ".skilling/courses/.index.json").write_bytes(b"{invalid cache")
    before = tree(workspace)
    cli = Path(sys.executable).parent / ("skilling.exe" if os.name == "nt" else "skilling")
    result = run([str(cli), "next", "--course", "hello-skilling"], cwd=workspace)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "workspace-recovery-required"
    assert "Traceback" not in result.stderr
    assert tree(workspace) == before


def test_workspace_lock_acquisition_failure_is_json_refusal(tmp_path: Path) -> None:
    source, workspace = setup(tmp_path)
    before = tree(workspace)
    injected = """
from contextlib import contextmanager
from skilling.workspace import _recovery
from skilling.cli import main
@contextmanager
def fail(*args, **kwargs):
    raise OSError('injected workspace lock failure')
    yield
_recovery.locked_directory = fail
main()
"""
    result = run(
        [sys.executable, "-c", injected, "next", "--course", "hello-skilling"], cwd=workspace
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "workspace-recovery-required"
    assert "Traceback" not in result.stderr
    assert tree(workspace) == before


def test_workspace_guard_does_not_translate_command_body_errors(tmp_path: Path) -> None:
    from skilling.workspace import workspace_lock

    with pytest.raises(OSError, match="body failure"), workspace_lock(tmp_path):
        raise OSError("body failure")


@pytest.mark.parametrize("error", [OSError, RuntimeError])
def test_workspace_read_path_resolution_is_explicit_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    from skilling.workspace import workspace_read

    def fail(path: Path) -> Path:
        raise error("resolution failed")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", fail)
        with pytest.raises(ImportRecoveryError, match="cannot resolve"), workspace_read(tmp_path):
            raise AssertionError("unreachable")
