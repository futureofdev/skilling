"""Ownership lifecycle, read barriers and failure paths for local course locks."""

from __future__ import annotations

import errno
import multiprocessing as mp
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from skilling.store import FileProgressStore, StatePathError, StoreBusy, _file, _locking
from skilling.store._locking import locked_course

from .test_store import COURSE, LEARNER, OTHER_COURSE, a_record, a_slot, an_entry
from .test_store_concurrency import archive_entry


def _hold(root, ready, release) -> None:
    store = FileProgressStore(root)
    with store._locked_course(COURSE):
        ready.set()
        if not release.wait(20):
            raise RuntimeError("holder was not released")


def _try_lock(root, results, mutate=False) -> None:
    store = FileProgressStore(root)
    try:
        with locked_course(store.course_dir(COURSE), timeout=0.1):
            if mutate:
                found = store.get_record(LEARNER, COURSE)
                assert found is not None
                store.put_record(a_record(skills_unlocked=["fresh"]), found[1])
    except StoreBusy:
        results.put("busy")
    else:
        results.put("ok")


def _run_contender(ctx, root: Path, expected: str, *, mutate: bool = False) -> None:
    results = ctx.Queue()
    worker = ctx.Process(target=_try_lock, args=(str(root), results, mutate))
    try:
        worker.start()
        assert results.get(timeout=15) == expected
        worker.join(15)
        assert worker.exitcode == 0
    finally:
        if worker.is_alive():
            worker.kill()
        if worker.pid is not None:
            worker.join(15)
        results.close()


def test_killed_owner_releases_kernel_lock_without_removing_file(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    store.append_completion(LEARNER, COURSE, an_entry("0.1"))
    store.put_homework(LEARNER, COURSE, a_slot(), None)
    before = {p: p.read_bytes() for p in store.state_root.rglob("*") if p.is_file()}
    lock = store.checked_path(COURSE, ".skilling.lock")
    identity = lock.stat()
    ctx = mp.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    holder = ctx.Process(target=_hold, args=(str(store.state_root), ready, release))
    try:
        holder.start()
        assert ready.wait(15)
        _run_contender(ctx, store.state_root, "busy")
        assert all(path.read_bytes() == raw for path, raw in before.items())
        holder.kill()
        holder.join(15)
        assert holder.exitcode is not None and holder.exitcode != 0
        _run_contender(ctx, store.state_root, "ok", mutate=True)
        assert (lock.stat().st_dev, lock.stat().st_ino) == (identity.st_dev, identity.st_ino)
        found = store.get_record(LEARNER, COURSE)
        assert found is not None and found[0].skills_unlocked == ["fresh"]
    finally:
        # Never touch a multiprocessing Event after killing its waiter: its mutex may die held.
        if holder.is_alive():
            holder.kill()
        holder.join(15)


@pytest.mark.parametrize("alias_kind", ["symlink", "case"])
def test_root_aliases_share_process_lock(tmp_path: Path, alias_kind: str) -> None:
    root = tmp_path / "State"
    store = FileProgressStore(root)
    store.put_record(a_record(), None)
    alias = tmp_path / ("alias" if alias_kind == "symlink" else "state")
    if alias_kind == "case":
        if not alias.exists():
            pytest.skip("case-sensitive filesystem has no case alias")
    elif os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(root)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    else:
        alias.symlink_to(root, target_is_directory=True)
    with store._locked_course(COURSE):
        _run_contender(mp.get_context("spawn"), alias, "busy")
    _run_contender(mp.get_context("spawn"), alias, "ok", mutate=True)


def test_reentrancy_across_instances_and_thread_exclusion(tmp_path: Path) -> None:
    first = FileProgressStore(tmp_path / "state")
    second = FileProgressStore(first.state_root)
    started = threading.Event()

    def contender() -> None:
        started.set()
        with locked_course(first.course_dir(COURSE), timeout=0.1):
            pytest.fail("another thread inherited reentrancy")

    with (
        ThreadPoolExecutor(max_workers=1) as pool,
        first._locked_course(COURSE),
        second._locked_course(COURSE),
    ):
        revision = second.put_record(a_record(), None)
        assert first.get_record(LEARNER, COURSE) == (a_record(), revision)
        second.append_completion(LEARNER, COURSE, an_entry("0.1"))
        future = pool.submit(contender)
        assert started.wait(5)
        with pytest.raises(StoreBusy):
            future.result(timeout=5)
        # A separate course is independently writable while this lock is held.
        pool.submit(second.put_record, a_record(OTHER_COURSE), None).result(timeout=5)
    with locked_course(first.course_dir(COURSE), timeout=0):
        pass


@pytest.mark.parametrize(
    "method", ["get_record", "get_log", "get_homework", "get_homework_archive", "list_records"]
)
def test_getters_create_nothing_for_absent_course(tmp_path: Path, method: str) -> None:
    store = FileProgressStore(tmp_path / "absent")
    methods = {
        "get_record": lambda: store.get_record(LEARNER, COURSE),
        "get_log": lambda: store.get_log(LEARNER, COURSE),
        "get_homework": lambda: store.get_homework(LEARNER, COURSE),
        "get_homework_archive": lambda: store.get_homework_archive(LEARNER, COURSE),
        "list_records": lambda: store.list_records(COURSE),
    }
    methods[method]()
    assert not store.state_root.exists()


@pytest.mark.parametrize("method", ["record", "log", "homework", "archive", "list"])
def test_getters_wait_even_when_target_file_is_absent(tmp_path: Path, method: str) -> None:
    store = FileProgressStore(tmp_path / "state")
    started, finished = threading.Event(), threading.Event()

    def read():
        started.set()
        operations = {
            "record": lambda: store.get_record(LEARNER, COURSE),
            "log": lambda: store.get_log(LEARNER, COURSE),
            "homework": lambda: store.get_homework(LEARNER, COURSE),
            "archive": lambda: store.get_homework_archive(LEARNER, COURSE),
            "list": lambda: store.list_records(COURSE),
        }
        result = operations[method]()
        finished.set()
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        with store._locked_course(COURSE):
            future = pool.submit(read)
            assert started.wait(5)
            assert not finished.wait(0.1)
            store.put_record(a_record(), None)
            store.append_completion(LEARNER, COURSE, an_entry("0.1"))
            store.put_homework(LEARNER, COURSE, a_slot(), None)
            store.append_homework_archive(LEARNER, COURSE, archive_entry("first"))
        result = future.result(timeout=5)
        assert result is not None and result != [] and result != (None, None)


def test_lock_inode_stays_stable_and_descendant_alias_refuses_without_effect(
    tmp_path: Path,
) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    lock = store.checked_path(COURSE, ".skilling.lock")
    first = lock.stat()
    for index in range(3):
        store.append_completion(LEARNER, COURSE, an_entry(f"0.{index}"))
        revision = store.put_homework(LEARNER, COURSE, a_slot(), None)
        store.put_homework(LEARNER, COURSE, None, revision)
        store.append_homework_archive(LEARNER, COURSE, archive_entry(str(index)))
        assert (lock.stat().st_dev, lock.stat().st_ino) == (first.st_dev, first.st_ino)
        assert lock.read_bytes() == b""
    # Use a directory junction on Windows, which does not need symlink privileges.
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    bad = FileProgressStore(tmp_path / "bad")
    bad.course_dir(COURSE).mkdir(parents=True)
    link = bad.course_dir(COURSE) / ".skilling.lock"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(unsafe)], capture_output=True
        )
        assert result.returncode == 0
    else:
        link.symlink_to(unsafe, target_is_directory=True)
    with pytest.raises(StatePathError):
        bad.put_record(a_record(), None)
    assert list(unsafe.iterdir()) == []
    assert list(bad.course_dir(COURSE).iterdir()) == [link]


@pytest.mark.parametrize("timeout", [-1, float("inf"), float("nan")])
def test_invalid_timeout_has_no_effect(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(ValueError), locked_course(tmp_path, timeout=timeout):
        pass
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("stage", ["open", "seek", "lock", "unlock"])
@pytest.mark.parametrize("code", [errno.EACCES, errno.EIO])
def test_io_errors_propagate_and_cleanup_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    code: int,
) -> None:
    error = OSError(code, "injected I/O failure")
    calls = 0
    before = _locking._OPEN_FDS.copy()

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise error

    with monkeypatch.context() as patch:
        if stage in {"open", "seek"}:
            patch.setattr(os, "open" if stage == "open" else "lseek", fail)
        else:
            patch.setattr(_locking, "_kernel_lock" if stage == "lock" else "_kernel_unlock", fail)
        expected = StoreBusy if stage == "lock" and code == errno.EACCES else OSError
        with pytest.raises(expected) as caught, locked_course(tmp_path, timeout=0.03):
            pass
        if expected is OSError:
            assert caught.value is error
            assert calls == 1
    assert before == _locking._OPEN_FDS
    assert not _locking._OWNERSHIP.descriptors
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: _acquire(tmp_path)).result(timeout=5)


def _acquire(path: Path) -> None:
    with locked_course(path, timeout=0.1):
        pass


def test_body_exception_releases_ownership(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="body"), locked_course(tmp_path):
        raise RuntimeError("body")
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_acquire, tmp_path).result(timeout=5)


@pytest.mark.parametrize("code", [errno.EAGAIN, errno.EACCES, errno.EINTR])
def test_kernel_retries_use_original_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    calls = 0

    def busy(fd: int) -> None:
        nonlocal calls
        calls += 1
        raise OSError(code, "busy")

    monkeypatch.setattr(_locking, "_kernel_lock", busy)
    start = time.monotonic()
    with pytest.raises(StoreBusy), locked_course(tmp_path, timeout=0.06):
        pass
    assert 0.04 <= time.monotonic() - start < 1
    assert calls >= 2


@pytest.mark.parametrize("operation", ["record", "delete", "archive"])
def test_locked_operations_propagate_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    store = FileProgressStore(tmp_path)
    revision = store.put_homework(LEARNER, COURSE, a_slot(), None)
    error = OSError(errno.EIO, "flush failed")

    def fail(directory: Path) -> None:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(_file, "_fsync_dir", fail)
        with pytest.raises(OSError) as caught:
            if operation == "record":
                store.put_record(a_record(), None)
            elif operation == "delete":
                store.put_homework(LEARNER, COURSE, None, revision)
            else:
                store.append_homework_archive(LEARNER, COURSE, archive_entry("first"))
        assert caught.value is error
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(_acquire, store.course_dir(COURSE)).result(timeout=5)


@pytest.mark.skipif(os.name != "posix", reason="POSIX fork ownership; Windows uses spawn")
@pytest.mark.parametrize("other_thread", [False, True])
def test_fork_child_cannot_inherit_parent_ownership(tmp_path: Path, other_thread: bool) -> None:
    store = FileProgressStore(tmp_path)
    store.put_record(a_record(), None)
    held, release = threading.Event(), threading.Event()

    def hold_thread() -> None:
        with store._locked_course(COURSE):
            held.set()
            assert release.wait(15)

    if other_thread:
        thread = threading.Thread(target=hold_thread)
        thread.start()
        try:
            assert held.wait(5)
            _run_contender(mp.get_context("fork"), tmp_path, "busy")
        finally:
            release.set()
            thread.join(5)
    else:
        with store._locked_course(COURSE):
            _run_contender(mp.get_context("fork"), tmp_path, "busy")
    _run_contender(mp.get_context("spawn"), tmp_path, "ok", mutate=True)


@pytest.mark.parametrize("operation", ["read", "update", "delete"])
def test_homework_disappearance_during_path_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    store = FileProgressStore(tmp_path)
    revision = store.put_homework(LEARNER, COURSE, a_slot(), None)
    inspected, release = threading.Event(), threading.Event()
    resolve = Path.resolve
    reader_id: int | None = None

    def paused_resolve(path: Path, strict: bool = False) -> Path:
        if path.name == "active.yaml" and strict and threading.get_ident() == reader_id:
            inspected.set()
            assert release.wait(5)
        return resolve(path, strict=strict)

    def contender():
        nonlocal reader_id
        reader_id = threading.get_ident()
        if operation == "read":
            return store.get_homework(LEARNER, COURSE)
        return store.put_homework(
            LEARNER, COURSE, a_slot("0.3") if operation == "update" else None, revision
        )

    monkeypatch.setattr(Path, "resolve", paused_resolve)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(contender)
        try:
            assert inspected.wait(5)
            store.put_homework(LEARNER, COURSE, None, revision)
        finally:
            release.set()
        if operation == "read":
            assert future.result(timeout=5) == (None, None)
        else:
            from skilling.store import Conflict

            with pytest.raises(Conflict):
                future.result(timeout=5)
    assert store.get_homework(LEARNER, COURSE) == (None, None)


def _fork_keepalive(ready, release) -> None:
    assert not _locking._OPEN_FDS
    assert not _locking._OWNERSHIP.descriptors
    ready.set()
    assert release.wait(15)


@pytest.mark.skipif(os.name != "posix", reason="POSIX fork descriptors; Windows uses spawn")
def test_fork_child_does_not_retain_parent_kernel_lock(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path)
    store.put_record(a_record(), None)
    ctx = mp.get_context("fork")
    ready, release = ctx.Event(), ctx.Event()
    child = ctx.Process(target=_fork_keepalive, args=(ready, release))
    try:
        with store._locked_course(COURSE):
            child.start()
            assert ready.wait(5)
        # The child remains alive; retaining any inherited open description would block this.
        _run_contender(mp.get_context("spawn"), tmp_path, "ok", mutate=True)
    finally:
        release.set()
        child.join(10)
        if child.is_alive():
            child.kill()
            child.join(5)
        assert child.exitcode == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX fork context unwinding; Windows uses spawn")
def test_fork_child_can_unwind_inherited_context_without_closing_reused_fd(tmp_path: Path) -> None:
    import sys

    launcher = """
import os
import sys
from pathlib import Path
from skilling.store._locking import locked_course, _OWNERSHIP
root = Path(sys.argv[1])
child = -1
with locked_course(root):
    inherited_fd = next(iter(_OWNERSHIP.descriptors.values()))
    child = os.fork()
    if child == 0:
        reused = os.open(root / "child-owned", os.O_RDWR | os.O_CREAT, 0o600)
        if reused != inherited_fd:
            os.dup2(reused, inherited_fd)
            os.close(reused)
        reused = inherited_fd
if child == 0:
    try:
        os.write(reused, b"still open")
        os.close(reused)
    except BaseException:
        os._exit(1)
    os._exit(0)
_, status = os.waitpid(child, 0)
assert os.waitstatus_to_exitcode(status) == 0
assert (root / "child-owned").read_bytes() == b"still open"
"""
    result = subprocess.run(
        [sys.executable, "-c", launcher, str(tmp_path)], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name != "posix", reason="POSIX fork waiting descriptors; Windows uses spawn")
def test_fork_resets_descriptor_waiting_on_kernel_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened, release = threading.Event(), threading.Event()
    original = _locking._kernel_lock

    def paused(fd: int) -> None:
        opened.set()
        assert release.wait(10)
        original(fd)

    monkeypatch.setattr(_locking, "_kernel_lock", paused)
    ctx = mp.get_context("fork")
    ready, child_release = ctx.Event(), ctx.Event()
    child = ctx.Process(target=_fork_keepalive, args=(ready, child_release))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_acquire, tmp_path)
        try:
            assert opened.wait(5)
            assert _locking._OPEN_FDS
            child.start()
            assert ready.wait(5)
        finally:
            release.set()
            child_release.set()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
        future.result(timeout=5)
    assert child.exitcode == 0


def test_local_and_kernel_waits_share_one_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    elapsed = 0.0
    sleeps: list[float] = []

    class DelayedLocalLock:
        def acquire(self, *, timeout: float) -> bool:
            nonlocal elapsed
            assert timeout == 0.2
            elapsed += 0.12
            return True

        def release(self) -> None:
            pass

    def sleep(seconds: float) -> None:
        nonlocal elapsed
        sleeps.append(seconds)
        elapsed += seconds

    def busy(fd: int) -> None:
        raise OSError(errno.EAGAIN, "kernel busy")

    stat = tmp_path.stat()
    identity = _locking._Identity(stat.st_dev, stat.st_ino)
    monkeypatch.setattr(_locking, "_LOCKS", {identity: DelayedLocalLock()})
    monkeypatch.setattr(_locking, "time", SimpleNamespace(monotonic=lambda: elapsed, sleep=sleep))
    monkeypatch.setattr(_locking, "_kernel_lock", busy)
    with pytest.raises(StoreBusy), locked_course(tmp_path, timeout=0.2):
        pass
    assert elapsed == pytest.approx(0.2)
    assert sleeps == pytest.approx([0.05, 0.03])
