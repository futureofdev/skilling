"""Deterministic native-process publication, failure and kernel-lock recovery."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from skilling.sources import CacheBusy, CacheConflict, resolve
from skilling.sources._identity import Index, ref_digest
from skilling.sources._locking import locked_cache

from .test_cache_identity import legacy_cache, read_index, repository, snapshot

WORKER = Path(__file__).with_name("cache_worker.py")
BOUNDARIES = (
    "staged",
    "reservation-before",
    "reservation",
    "directory-before",
    "directory",
    "index-before",
    "index",
)


def worker(ref: str, cache: Path, marker: Path, *, fault: str = "none", boundary: str = "index"):
    return subprocess.Popen(
        [
            sys.executable,
            str(WORKER),
            "resolve",
            "--ref",
            ref,
            "--cache",
            str(cache),
            "--marker",
            str(marker),
            "--fault",
            fault,
            "--boundary",
            boundary,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def ready(process: subprocess.Popen[str], marker: Path) -> None:
    deadline = time.monotonic() + 45
    while not marker.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(f"worker exited {process.returncode}: {stdout}\n{stderr}")
        if time.monotonic() > deadline:
            pytest.fail("worker did not reach the publication barrier")
        time.sleep(0.01)


def finish(process: subprocess.Popen[str], expected: int = 0) -> dict[str, str]:
    stdout, stderr = process.communicate(timeout=60)
    assert process.returncode == expected, (stdout, stderr)
    return json.loads(stdout) if stdout else {}


@pytest.mark.parametrize("mode", ["error", "exit"])
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_each_interruption_recovers_without_losing_other_bindings(
    tmp_path: Path, clean_dir: Path, boundary: str, mode: str
) -> None:
    seed = repository(clean_dir, tmp_path / "seed", course_id="unrelated-course")
    target = repository(clean_dir, tmp_path / "target")
    cache = tmp_path / "cache"
    unrelated = resolve(seed.as_uri(), cache=cache)
    seed_bytes = snapshot(unrelated.path)
    source_digest = ref_digest(target.as_uri())
    process = worker(target.as_uri(), cache, tmp_path / "fault", fault=mode, boundary=boundary)
    try:
        finish(process, 2 if mode == "error" else 73)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert (tmp_path / "fault").read_text() == boundary
    index = read_index(cache)
    assert ref_digest(seed.as_uri()) in index.entries
    assert snapshot(unrelated.path) == seed_bytes
    assert (source_digest in index.entries) == (boundary == "index")
    published = (cache / "clean-course@1.0.0").exists()
    assert published == (boundary in {"directory", "index-before", "index"})
    if boundary == "index":
        target.rename(tmp_path / "unavailable")
    replay = worker(target.as_uri(), cache, tmp_path / "retry")
    assert finish(replay)["id"] == "clean-course"
    recovered = read_index(cache)
    assert len(recovered.entries) == 2
    assert recovered.entries[source_digest].key == "clean-course@1.0.0"
    assert snapshot(unrelated.path) == seed_bytes
    assert resolve(seed.as_uri(), cache=cache) == unrelated
    assert not (cache / "clean-course@1.0.0/course").exists()


@pytest.mark.parametrize("relation", ["same-ref", "equivalent", "conflict", "distinct-course"])
def test_concurrent_fetched_sources_serialize_index_and_directory_publication(
    tmp_path: Path, clean_dir: Path, relation: str
) -> None:
    first = repository(clean_dir, tmp_path / "first", title="First")
    if relation == "same-ref":
        second = first
    else:
        second = repository(
            clean_dir,
            tmp_path / "second",
            title="Different" if relation == "conflict" else "First",
            course_id="other-course" if relation == "distinct-course" else None,
        )
    cache = tmp_path / "cache"
    markers = [tmp_path / "one.marker", tmp_path / "two.marker"]
    processes = [
        worker(ref.as_uri(), cache, marker, fault="hold", boundary="staged")
        for ref, marker in zip((first, second), markers, strict=True)
    ]
    try:
        for process, marker in zip(processes, markers, strict=True):
            ready(process, marker)
        for marker in markers:
            marker.with_suffix(".release").write_text("go")
        deadline = time.monotonic() + 60
        while any(process.poll() is None for process in processes):
            index_path = cache / ".index.json"
            if index_path.exists():
                with locked_cache(cache):
                    Index.model_validate_json(index_path.read_bytes())
            assert time.monotonic() < deadline
            time.sleep(0.01)
        outputs = [process.communicate(timeout=5) for process in processes]
        codes = sorted(process.returncode for process in processes)
        assert codes == ([0, 2] if relation == "conflict" else [0, 0]), outputs
        index = read_index(cache)
        assert len(index.entries) == (1 if relation in {"same-ref", "conflict"} else 2)
        assert len(index.contents) == (2 if relation == "distinct-course" else 1)
        for process, ref in zip(processes, (first, second), strict=True):
            if process.returncode == 0:
                hit = resolve(ref.as_uri(), cache=cache)
                assert hit.course.root == hit.path
                assert all(lesson.path.is_file() for lesson in hit.course.lessons())
            else:
                with pytest.raises(CacheConflict):
                    resolve(ref.as_uri(), cache=cache)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_killed_lock_owner_releases_native_lock_without_replacing_lock_file(
    tmp_path: Path, clean_dir: Path
) -> None:
    remote = repository(clean_dir, tmp_path / "remote")
    cache = tmp_path / "cache"
    marker = tmp_path / "held.marker"
    process = worker(remote.as_uri(), cache, marker, fault="hold", boundary="directory")
    try:
        ready(process, marker)
        inode = (cache / ".cache.lock").stat().st_ino
        with pytest.raises(CacheBusy), locked_cache(cache, timeout=0.05):
            pytest.fail("live worker owns the kernel lock")
        process.kill()
        process.wait(timeout=10)
        recovered = worker(remote.as_uri(), cache, tmp_path / "retry")
        assert finish(recovered)["id"] == "clean-course"
        assert (cache / ".cache.lock").stat().st_ino == inode
        with locked_cache(cache), locked_cache(cache, timeout=0):
            assert read_index(cache).entries
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


@pytest.mark.parametrize("mode", ["error", "exit"])
@pytest.mark.parametrize(
    "boundary",
    ["reservation-before", "reservation", "sanitized-before", "sanitized", "index-before", "index"],
)
def test_legacy_adoption_recovers_around_durable_modes_and_git_cleanup(
    tmp_path: Path, clean_dir: Path, mode: str, boundary: str
) -> None:
    (clean_dir / "run.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
    remote = repository(clean_dir, tmp_path / "remote")
    subprocess.run(["git", "update-index", "--chmod=+x", "run.sh"], cwd=remote, check=True)
    subprocess.run(["git", "commit", "-qm", "executable"], cwd=remote, check=True)
    # Make a real checkout, so the legacy tree's bytes/modes match the stored Git intent.
    from skilling.sources import _git

    checkout = tmp_path / "old-checkout"
    _git.clone(remote.as_uri(), checkout, pin=None)
    cache = tmp_path / "cache"
    destination = legacy_cache(cache, remote.as_uri(), checkout)
    before = {
        name: data for name, data in snapshot(destination).items() if not name.startswith(".git/")
    }
    marker = tmp_path / "fault"
    process = worker(remote.as_uri(), cache, marker, fault=mode, boundary=boundary)
    try:
        finish(process, 2 if mode == "error" else 73)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    assert marker.read_text() == boundary
    assert {
        name: data for name, data in snapshot(destination).items() if not name.startswith(".git/")
    } == before
    assert (destination / ".git").exists() == (
        boundary in {"reservation-before", "reservation", "sanitized-before"}
    )
    if boundary != "reservation-before":
        index = read_index(cache)
        assert index.contents[destination.name].executables == ("run.sh",)
        assert bool(index.entries) == (boundary == "index")
    if boundary == "index":
        remote.rename(tmp_path / "unavailable")
    assert finish(worker(remote.as_uri(), cache, tmp_path / "retry"))["id"] == "clean-course"
    assert not (destination / ".git").exists()
    assert read_index(cache).entries[ref_digest(remote.as_uri())].key == destination.name
    assert snapshot(destination) == before
