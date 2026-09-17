"""Remote cache identity: no source may silently borrow another course's payload."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import traceback
from pathlib import Path

import pytest

from skilling.course import Course
from skilling.sources import (
    CacheConflict,
    CacheInvalid,
    GitFailed,
    ResolveError,
    _cache,
    _git,
    invalidate_cached_course,
    resolve,
    safe_source_ref,
)
from skilling.sources._identity import Index, inspect_payload, ref_digest

from .test_state_paths import directory_alias, file_alias


def repository(
    source: Path, destination: Path, *, title: str | None = None, course_id: str | None = None
) -> Path:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
    if title is not None:
        manifest = destination / "course.yaml"
        manifest.write_text(re.sub(r"(?m)^title:.*$", f"title: {title}", manifest.read_text()))
    if course_id is not None:
        manifest = destination / "course.yaml"
        manifest.write_text(re.sub(r"(?m)^id:.*$", f"id: {course_id}", manifest.read_text()))
    for args in (
        ["init", "-q", "-b", "main"],
        # Legacy fixtures copy .git; automatic maintenance must not outlive a commit.
        ["config", "maintenance.auto", "false"],
        ["config", "core.autocrlf", "false"],
        ["config", "user.name", "Cache fixture"],
        ["config", "user.email", "cache@example.invalid"],
        ["add", "-A"],
        ["commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=destination, check=True, capture_output=True)
    return destination


def test_distinct_sources_with_same_id_and_version_never_substitute_content(
    tmp_path: Path, clean_dir: Path
) -> None:
    first = repository(clean_dir, tmp_path / "first", title="First source")
    second = repository(clean_dir, tmp_path / "second", title="Second source")
    cache = tmp_path / "cache"
    original = resolve(first.as_uri(), cache=cache)
    before = (cache / ".index.json").read_bytes()

    with pytest.raises(ResolveError, match="cache conflict"):
        resolve(second.as_uri(), cache=cache)

    assert (cache / ".index.json").read_bytes() == before
    again = resolve(first.as_uri(), cache=cache)
    assert again == original
    assert again.course.manifest.title == "First source"


def test_equivalent_sources_share_payload_but_keep_distinct_verified_commits(
    tmp_path: Path, clean_dir: Path
) -> None:
    first = repository(clean_dir, tmp_path / "first")
    second = repository(clean_dir, tmp_path / "second")
    subprocess.run(
        ["git", "commit", "--allow-empty", "-qm", "different history"], cwd=second, check=True
    )
    cache = tmp_path / "cache"
    a = resolve(first.as_uri(), cache=cache)
    b = resolve(second.as_uri(), cache=cache)
    assert a.course == b.course and a.path == b.path
    index = read_index(cache)
    assert len(index.entries) == 2 and len(index.contents) == 1
    assert len({entry.source.commit for entry in index.entries.values()}) == 2
    assert set(index.entries) == {ref_digest(first.as_uri()), ref_digest(second.as_uri())}
    assert not list(cache.rglob(".git"))


def read_index(cache: Path) -> Index:
    return Index.model_validate_json((cache / ".index.json").read_bytes())


@pytest.mark.parametrize("changed", ["lesson", "resource", "executable"])
def test_changed_payload_cannot_borrow_an_existing_identity(
    tmp_path: Path, clean_dir: Path, changed: str
) -> None:
    (clean_dir / "assets").mkdir(exist_ok=True)
    (clean_dir / "assets/data.txt").write_bytes(b"resource\n")
    first = repository(clean_dir, tmp_path / "first")
    second = repository(clean_dir, tmp_path / "second")
    if changed == "lesson":
        path = next(second.glob("phases/*/lesson-*.md"))
        path.write_text(path.read_text() + "\nUpdated explanation.\n")
    elif changed == "resource":
        (second / "assets/data.txt").write_bytes(b"different resource\n")
    else:
        subprocess.run(
            ["git", "update-index", "--chmod=+x", "assets/data.txt"], cwd=second, check=True
        )
    if changed != "executable":
        subprocess.run(["git", "add", "-A"], cwd=second, check=True)
    subprocess.run(["git", "commit", "-qm", "changed"], cwd=second, check=True)
    cache = tmp_path / "cache"
    first_result = resolve(first.as_uri(), cache=cache)
    before = snapshot(cache)
    with pytest.raises(CacheConflict):
        resolve(second.as_uri(), cache=cache)
    assert snapshot(cache) == before
    assert resolve(first.as_uri(), cache=cache) == first_result


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_moving_branch_stays_cached_and_a_new_pin_detects_changed_payload(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    real_clone = _git.clone
    monkeypatch.setattr(
        _git, "clone", lambda url, dst, *, pin: real_clone(remote.as_uri(), dst, pin=pin)
    )
    cache = tmp_path / "cache"
    initial = resolve("gh:owner/course@main", cache=cache)
    old_commit = next(iter(read_index(cache).entries.values())).source.commit
    (remote / "extra.txt").write_text("New revision\n")
    subprocess.run(["git", "add", "-A"], cwd=remote, check=True)
    subprocess.run(["git", "commit", "-qm", "updated"], cwd=remote, check=True)
    new_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=remote, text=True
    ).strip()
    assert new_commit != old_commit
    assert resolve("gh:owner/course@main", cache=cache) == initial
    with pytest.raises(CacheConflict):
        resolve(f"gh:owner/course@{new_commit}", cache=cache)
    assert resolve(f"gh:owner/course@{old_commit}", cache=cache).course == initial.course


def test_verified_hit_is_offline_and_portable(tmp_path: Path, clean_dir: Path) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    first = resolve(remote.as_uri(), cache=cache)
    remote.rename(tmp_path / "unavailable")
    moved = tmp_path / "moved"
    cache.rename(moved)
    hit = resolve(first.ref, cache=moved)
    assert hit.course.manifest == first.course.manifest
    assert hit.path == moved / first.path.name
    assert hit.course.root == hit.path
    assert all(lesson.path.is_file() for lesson in hit.course.lessons())


def legacy_cache(cache: Path, ref: str, source: Path) -> Path:
    destination = cache / "clean-course@1.0.0"
    shutil.copytree(source, destination)
    (cache / ".index.json").write_text(json.dumps({ref: destination.name}))
    return destination


def test_legacy_adoption_verifies_requested_source_and_removes_git_metadata(
    tmp_path: Path, clean_dir: Path
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    destination = legacy_cache(cache, remote.as_uri(), remote)
    result = resolve(remote.as_uri(), cache=cache)
    assert result.path == destination
    assert not (destination / ".git").exists()
    assert ref_digest(remote.as_uri()) in read_index(cache).entries
    remote.rename(tmp_path / "unavailable")
    assert resolve(result.ref, cache=cache) == result


def test_legacy_unavailable_refuses_without_trusting_or_changing_content(
    tmp_path: Path, clean_dir: Path
) -> None:
    ref = (tmp_path / "unavailable").as_uri()
    cache = tmp_path / "cache"
    destination = legacy_cache(cache, ref, clean_dir)
    before = snapshot(cache)
    with pytest.raises(GitFailed, match="retry online.*workspace course ID"):
        resolve(ref, cache=cache)
    after = snapshot(cache)
    after.pop(".cache.lock", None)
    assert after == before
    assert Course.load(destination).id == "clean-course"


def test_legacy_different_source_never_adopts_wrong_content(
    tmp_path: Path, clean_dir: Path
) -> None:
    original = repository(clean_dir, tmp_path / "original")
    remote = repository(clean_dir, tmp_path / "remote", title="Different")
    cache = tmp_path / "cache"
    legacy_cache(cache, remote.as_uri(), original)
    before = (cache / ".index.json").read_bytes()
    with pytest.raises(CacheConflict):
        resolve(remote.as_uri(), cache=cache)
    assert (cache / ".index.json").read_bytes() == before


@pytest.mark.parametrize(
    "data",
    [
        "broken json",
        "[]",
        '{"version": 99}',
        '{"version": true}',
        '{"version": 1, "extra": 1}',
        '{"file:///remote": "../../outside"}',
        '{"file:///remote": 42}',
        '{"version": 1, "pending": {"bad": "clean-course@1.0.0"}}',
        '{"version": 1, "contents": {"/outside": {"digest": "' + "a" * 64 + '"}}}',
    ],
)
def test_corrupt_index_refuses_before_fetch_or_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data: str
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    path = cache / ".index.json"
    path.write_text(data)
    monkeypatch.setattr(_git, "clone", lambda *args, **kwargs: pytest.fail("must not fetch"))
    with pytest.raises(CacheInvalid):
        resolve("file:///remote", cache=cache)
    assert path.read_text() == data


@pytest.mark.parametrize(
    "damage", ["modified", "missing", "source", "identity", "pin", "transport", "subdirectory"]
)
def test_verified_mapping_is_validated_before_hit(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    result = resolve(remote.as_uri(), cache=cache)
    if damage == "modified":
        (result.path / "new.txt").write_text("changed")
    elif damage == "missing":
        shutil.rmtree(result.path)
    else:
        data = json.loads((cache / ".index.json").read_text())
        entry = data["entries"][ref_digest(remote.as_uri())]
        if damage == "source":
            entry["source"]["source"] = "file:///other-source"
        elif damage == "identity":
            entry["key"] = "different@1.0.0"
        else:
            entry["source"][damage] = "unexpected"
        (cache / ".index.json").write_text(json.dumps(data))
    before = snapshot(cache)
    monkeypatch.setattr(_git, "clone", lambda *args, **kwargs: pytest.fail("must not fetch"))
    with pytest.raises(CacheInvalid):
        resolve(remote.as_uri(), cache=cache)
    assert snapshot(cache) == before


@pytest.mark.parametrize("target", [".index.json", ".cache.lock", "clean-course@1.0.0"])
def test_cache_aliases_refuse_without_touching_external_targets(
    tmp_path: Path, clean_dir: Path, target: str
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    result = resolve(remote.as_uri(), cache=cache)
    outside = tmp_path / "outside"
    if target == result.path.name:
        result.path.rename(outside)
        directory_alias(result.path, outside)
        before = snapshot(outside)
    else:
        (cache / target).rename(outside)
        file_alias(cache / target, outside)
        before = {"file": outside.read_bytes()}
    with pytest.raises(CacheInvalid):
        resolve(remote.as_uri(), cache=cache)
    assert (snapshot(outside) if outside.is_dir() else {"file": outside.read_bytes()}) == before


def test_symlink_and_junction_payload_refuses_without_reading_target(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"untouched")
    directory_alias(payload / "escape", outside)
    with pytest.raises(CacheInvalid):
        inspect_payload(payload, ())
    assert (outside / "sentinel").read_bytes() == b"untouched"


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO has no Windows counterpart")
def test_special_payload_is_refused_without_opening_it(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(CacheInvalid):
        inspect_payload(tmp_path, ())


def test_empty_file_and_directory_contribute_to_content_identity(tmp_path: Path) -> None:
    empty = inspect_payload(tmp_path, ())
    (tmp_path / "empty").mkdir()
    directory = inspect_payload(tmp_path, ())
    (tmp_path / "empty/file").write_bytes(b"")
    file = inspect_payload(tmp_path, ())
    assert len({empty.digest, directory.digest, file.digest}) == 3


@pytest.mark.parametrize(
    "subdirectory", ["../outside", "/outside", "C:/outside", "safe/../../outside"]
)
def test_escaping_subdirectory_is_refused_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, subdirectory: str
) -> None:
    monkeypatch.setattr(_git, "clone", lambda *args, **kwargs: pytest.fail("must not fetch"))
    with pytest.raises(ResolveError):
        resolve(f"gh:owner/repo#{subdirectory}", cache=tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


@pytest.mark.parametrize("ref", ["gh:owner/repo?token=SECRET", "gh:owner/repo@pin?token=SECRET"])
def test_query_bearing_shorthand_is_safely_refused_before_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    monkeypatch.setattr(_git, "clone", lambda *args, **kwargs: pytest.fail("must not fetch"))
    with pytest.raises(ResolveError) as caught:
        resolve(ref, cache=tmp_path / "cache")
    assert "SECRET" not in str(caught.value)
    assert "SECRET" not in safe_source_ref(ref)
    assert not (tmp_path / "cache").exists()


def test_credentials_are_never_persisted_in_cache_metadata_or_payload(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    ref = "https://SECRET_USER:SECRET_PASSWORD@example.invalid/course?token=SECRET_QUERY"
    real_clone = _git.clone

    def authenticated(url: str, dst: Path, *, pin: str | None) -> None:
        real_clone(remote.as_uri(), dst, pin=pin)
        subprocess.run(["git", "remote", "set-url", "origin", url], cwd=dst, check=True)

    monkeypatch.setattr(_git, "clone", authenticated)
    cache = tmp_path / "cache"
    result = resolve(ref, cache=cache)
    assert result.ref == ref
    data = b"\n".join(snapshot(cache).values())
    assert b"SECRET" not in data
    assert not list(cache.rglob(".git"))
    entry = read_index(cache).entries[ref_digest(ref)]
    assert entry.source.source == "https://example.invalid/course?redacted"
    assert safe_source_ref("ssh://git:SECRET@example.invalid/course?token=SECRET") == (
        "ssh://git@example.invalid/course?redacted"
    )


def test_transport_failure_never_formats_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = "https://SECRET:SECRET@example.invalid/course?token=SECRET"

    def failure(url: str, dst: Path, *, pin: str | None) -> None:
        raise subprocess.CalledProcessError(1, ["git", url], output=ref, stderr=ref)

    monkeypatch.setattr(_git, "clone", failure)
    with pytest.raises(GitFailed) as caught:
        resolve(ref, cache=tmp_path / "cache")
    assert "SECRET" not in "".join(traceback.format_exception(caught.value))
    assert not (tmp_path / "cache").exists()


def test_invalidation_forgets_all_bindings_and_reservations_under_the_lock(
    tmp_path: Path, clean_dir: Path
) -> None:
    first = repository(clean_dir, tmp_path / "first")
    second = repository(clean_dir, tmp_path / "second")
    cache = tmp_path / "cache"
    a = resolve(first.as_uri(), cache=cache)
    resolve(second.as_uri(), cache=cache)
    index = read_index(cache)
    pending = {ref_digest("file:///legacy"): a.path.name}
    (cache / ".index.json").write_text(
        index.model_copy(update={"pending": pending}).model_dump_json()
    )
    with invalidate_cached_course(cache, a.course.id, a.course.version):
        invalidated = read_index(cache)
        assert not invalidated.entries and not invalidated.pending and not invalidated.contents
        assert a.path.is_dir()
    first.rename(tmp_path / "unavailable")
    with pytest.raises(GitFailed):
        resolve(a.ref, cache=cache)
    if os.name == "nt":
        with pytest.raises(CacheInvalid, match="legacy executable intent"):
            resolve(second.as_uri(), cache=cache)
        assert Course.load(a.path) == a.course
    else:
        assert resolve(second.as_uri(), cache=cache).course == a.course


def test_final_hit_rechecks_provenance_after_network_fetch(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = repository(clean_dir, tmp_path / "first", title="First")
    other = repository(clean_dir, tmp_path / "other", title="Other")
    cache = tmp_path / "cache"
    existing = resolve(other.as_uri(), cache=cache)
    stage = _cache.stage

    def damage_during_fetch(fetched: Path, destination: Path) -> None:
        stage(fetched, destination)
        with _cache._locked(cache):
            index = read_index(cache)
            wrong = index.entries[ref_digest(other.as_uri())]
            damaged = index.model_copy(
                update={"entries": {**index.entries, ref_digest(first.as_uri()): wrong}}
            )
            _cache._write_index(cache, damaged)

    monkeypatch.setattr(_cache, "stage", damage_during_fetch)
    with pytest.raises(CacheInvalid, match="provenance"):
        resolve(first.as_uri(), cache=cache)
    assert Course.load(existing.path) == existing.course


@pytest.mark.parametrize("retained_git", [True, False])
def test_legacy_mode_only_conflict_never_borrows_fetched_executable_intent(
    tmp_path: Path, clean_dir: Path, retained_git: bool
) -> None:
    (clean_dir / "run.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    destination = legacy_cache(cache, remote.as_uri(), remote)
    subprocess.run(["git", "update-index", "--chmod=+x", "run.sh"], cwd=destination, check=True)
    if os.name == "posix":
        (destination / "run.sh").chmod(0o755)
    if not retained_git:
        from skilling.sources._paths import remove_tree

        remove_tree(destination / ".git")
    before = snapshot(cache)
    expected = CacheInvalid if os.name == "nt" and not retained_git else CacheConflict
    with pytest.raises(expected):
        resolve(remote.as_uri(), cache=cache)
    after = snapshot(cache)
    after.pop(".cache.lock", None)
    assert after == before


def test_unpublished_reservation_can_be_won_by_different_content(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = repository(clean_dir, tmp_path / "first", title="Unpublished")
    second = repository(clean_dir, tmp_path / "second", title="Published")
    cache = tmp_path / "cache"
    write = _cache._write_index

    def reserve_then_fail(root: Path, index: Index) -> None:
        write(root, index)
        raise OSError("interrupted immediately after the durable reservation")

    with monkeypatch.context() as patch:
        patch.setattr(_cache, "_write_index", reserve_then_fail)
        with pytest.raises(CacheInvalid):
            resolve(first.as_uri(), cache=cache)
    reserved = read_index(cache)
    assert reserved.contents and not reserved.entries
    assert not (cache / "clean-course@1.0.0").exists()
    winner = resolve(second.as_uri(), cache=cache)
    before = snapshot(cache)
    with pytest.raises(CacheConflict):
        resolve(first.as_uri(), cache=cache)
    assert snapshot(cache) == before
    assert winner.course.manifest.title == "Published"


def test_failed_atomic_index_replace_preserves_other_sources_and_retries(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = repository(clean_dir, tmp_path / "first", course_id="first-course")
    second = repository(clean_dir, tmp_path / "second")
    cache = tmp_path / "cache"
    initial = resolve(first.as_uri(), cache=cache)
    before = snapshot(cache)
    replace = os.replace

    def fail_index(source: str | Path, destination: str | Path) -> None:
        if Path(destination).name == ".index.json":
            raise OSError("index replacement failed")
        replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail_index)
        with pytest.raises(CacheInvalid):
            resolve(second.as_uri(), cache=cache)
    assert snapshot(cache) == before
    assert resolve(first.as_uri(), cache=cache) == initial
    assert resolve(second.as_uri(), cache=cache).course.id == "clean-course"
    assert len(read_index(cache).entries) == 2


def test_git_symlink_intent_refuses_even_when_checkout_uses_plain_files(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    blob = (
        subprocess.check_output(
            ["git", "hash-object", "-w", "--stdin"], cwd=remote, input=b"course.yaml\n"
        )
        .decode()
        .strip()
    )
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"120000,{blob},alias"],
        cwd=remote,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "symlink intent"], cwd=remote, check=True)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.symlinks")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
    with pytest.raises(CacheInvalid, match="symlink"):
        resolve(remote.as_uri(), cache=tmp_path / "cache")
    assert not (tmp_path / "cache").exists()


def test_git_executable_intent_survives_offline_relocation_on_each_platform(
    tmp_path: Path, clean_dir: Path
) -> None:
    (clean_dir / "run.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    remote = repository(clean_dir, tmp_path / "remote")
    subprocess.run(["git", "update-index", "--chmod=+x", "run.sh"], cwd=remote, check=True)
    subprocess.run(["git", "commit", "-qm", "executable intent"], cwd=remote, check=True)
    ref = remote.as_uri()
    cache = tmp_path / "cache"
    result = resolve(ref, cache=cache)
    identity = read_index(cache).contents[result.path.name]
    assert identity.executables == ("run.sh",)
    remote.rename(tmp_path / "unavailable")
    cache.rename(tmp_path / "relocated")
    hit = resolve(ref, cache=tmp_path / "relocated")
    assert (hit.path / "run.sh").read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert read_index(tmp_path / "relocated").contents[hit.path.name] == identity
    if os.name == "posix":
        (hit.path / "run.sh").chmod(0o644)
        with pytest.raises(CacheInvalid, match="executable intent"):
            resolve(ref, cache=tmp_path / "relocated")


@pytest.mark.skipif(os.name != "nt", reason="Windows legacy adoption needs independent Git modes")
@pytest.mark.parametrize("damage", ["missing-index", "untracked-file"])
def test_windows_legacy_cannot_infer_absent_executable_intent(
    tmp_path: Path, clean_dir: Path, damage: str
) -> None:
    (clean_dir / "run.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    destination = legacy_cache(cache, remote.as_uri(), remote)
    if damage == "missing-index":
        (destination / ".git/index").unlink()
    else:
        subprocess.run(
            ["git", "update-index", "--force-remove", "run.sh"], cwd=destination, check=True
        )
    before = snapshot(cache)
    with pytest.raises(CacheInvalid):
        resolve(remote.as_uri(), cache=cache)
    after = snapshot(cache)
    after.pop(".cache.lock", None)
    assert after == before


def test_staging_flushes_through_a_writable_handle_before_restoring_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "run.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    (source / "empty").write_bytes(b"")
    (source / "run.sh").chmod(0o555)
    expected = snapshot(source)
    real_fsync = os.fsync
    flushed: list[int] = []

    def require_write_access(fd: int) -> None:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            os.write(fd, b"")
            flushed.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", require_write_access)
    _cache.stage(source, tmp_path / "staged")
    assert len(flushed) == 2
    assert snapshot(source) == snapshot(tmp_path / "staged") == expected
    assert (tmp_path / "staged/run.sh").stat().st_mode == (source / "run.sh").stat().st_mode


def test_repository_fixture_does_not_start_maintenance_before_legacy_copy(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force inherited maintenance on; foreground mode bounds the failing pre-fix experiment.
    config = tmp_path / "inherited.gitconfig"
    config.write_text("[maintenance]\n\tauto = true\n\tautoDetach = false\n", encoding="utf-8")
    trace = tmp_path / "git-trace.jsonl"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))
    remote = repository(clean_dir, tmp_path / "remote")
    subprocess.run(
        ["git", "commit", "--allow-empty", "-qm", "later fixture commit"],
        cwd=remote,
        check=True,
        capture_output=True,
    )
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    children = [event["argv"] for event in events if event.get("event") == "child_start"]
    assert not any("maintenance" in argv or "gc" in argv for argv in children), children
    before = snapshot(remote / ".git")
    copied = legacy_cache(tmp_path / "cache", remote.as_uri(), remote)
    assert snapshot(copied / ".git") == before
    assert "index" in before and "HEAD" in before
    assert any(name.startswith("objects/") for name in before)
