"""File-only concurrency regressions using real revision comparisons and writes."""

from __future__ import annotations

import multiprocessing as mp
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skilling.course import HomeworkArchiveEntry, Requirement
from skilling.store import Conflict, FileProgressStore, _file

from .test_store import COURSE, LEARNER, a_record, a_slot, an_entry


def archive_entry(label: str) -> HomeworkArchiveEntry:
    return HomeworkArchiveEntry(
        coordinate="0.2",
        title=label,
        requirements=[Requirement(text="Do it")],
        submitted_at=datetime(2026, 8, 3, 10, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "kind,existing",
    [
        (kind, existing)
        for existing in (False, True)
        for kind in ("record", "homework", "delete", "log", "archive")
        if existing or kind != "delete"
    ],
)
def test_controlled_writers_preserve_acknowledgements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    existing: bool,
) -> None:
    store = FileProgressStore(tmp_path / "state")
    revision = None
    if existing:
        if kind == "record":
            revision = store.put_record(a_record(), None)
        elif kind in {"homework", "delete"}:
            revision = store.put_homework(LEARNER, COURSE, a_slot(), None)
        elif kind == "log":
            store.append_completion(LEARNER, COURSE, an_entry("0.0"))
        else:
            store.append_homework_archive(LEARNER, COURSE, archive_entry("original"))
    entered, release, contender_entered = threading.Event(), threading.Event(), threading.Event()
    original_write = _file._write_atomic
    original_unlink = Path.unlink

    def pause() -> None:
        if threading.current_thread().name.endswith("_0"):
            entered.set()
            assert release.wait(10), "parent did not release first writer"
        else:
            contender_entered.set()

    def write(path: Path, text: str) -> None:
        pause()
        original_write(path, text)

    def unlink(path: Path, missing_ok: bool = False) -> None:
        if path.name == "active.yaml":
            pause()
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(_file, "_write_atomic", write)
    monkeypatch.setattr(Path, "unlink", unlink)

    def mutate(label: str) -> str:
        peer = FileProgressStore(store.state_root)
        try:
            if kind == "record":
                peer.put_record(a_record(skills_unlocked=[label]), revision)
            elif kind in {"homework", "delete"}:
                slot = None if kind == "delete" and label == "alpha" else a_slot(label)
                peer.put_homework(LEARNER, COURSE, slot, revision)
            elif kind == "log":
                peer.append_completion(LEARNER, COURSE, an_entry(label))
            else:
                peer.append_homework_archive(LEARNER, COURSE, archive_entry(label))
        except Conflict:
            return "conflict"
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(mutate, "alpha")
        try:
            assert entered.wait(10)
            second = pool.submit(mutate, "beta")
            # Old code reaches its write here; fixed code waits before its revision read.
            contender_entered.wait(0.2)
        finally:
            release.set()
        outcomes = [first.result(timeout=10), second.result(timeout=10)]
    if kind in {"record", "homework", "delete"}:
        assert outcomes == ["ok", "conflict"]
        if kind == "record":
            found = store.get_record(LEARNER, COURSE)
            assert found is not None and found[0].skills_unlocked == ["alpha"]
        else:
            slot, _ = store.get_homework(LEARNER, COURSE)
            assert (
                slot is None
                if kind == "delete"
                else slot is not None and slot.coordinate == "alpha"
            )
    elif kind == "log":
        assert outcomes == ["ok", "ok"]
        assert [e.coordinate for e in store.get_log(LEARNER, COURSE)] == (
            (["0.0"] if existing else []) + ["alpha", "beta"]
        )
    else:
        assert outcomes == ["ok", "ok"]
        assert {e.title for e in store.get_homework_archive(LEARNER, COURSE)} == (
            ({"original"} if existing else set()) | {"alpha", "beta"}
        )


def _writer(root, kind, revision, label, ready, go, results) -> None:
    store = FileProgressStore(Path(root))
    ready.put(label)
    if not go.wait(15):
        raise RuntimeError("parent did not release writer")
    try:
        if kind == "record":
            store.put_record(a_record(skills_unlocked=[label]), revision)
        elif kind in {"homework", "delete"}:
            slot = None if kind == "delete" and label == "alpha" else a_slot(label)
            store.put_homework(LEARNER, COURSE, slot, revision)
        elif kind == "log":
            store.append_completion(LEARNER, COURSE, an_entry(label))
        else:
            store.append_homework_archive(LEARNER, COURSE, archive_entry(label))
    except Conflict:
        results.put(("conflict", label))
    else:
        results.put(("ok", label))


@pytest.mark.parametrize(
    "kind,existing",
    [
        (kind, existing)
        for existing in (False, True)
        for kind in ("record", "homework", "delete", "log", "archive")
        if existing or kind != "delete"
    ],
)
def test_spawn_writers_preserve_acknowledgements(tmp_path: Path, kind: str, existing: bool) -> None:
    ctx = mp.get_context("spawn")
    root = tmp_path / "state"
    store = FileProgressStore(root)
    revision = None
    if existing:
        if kind == "record":
            revision = store.put_record(a_record(), None)
        elif kind in {"homework", "delete"}:
            revision = store.put_homework(LEARNER, COURSE, a_slot(), None)
        elif kind == "log":
            store.append_completion(LEARNER, COURSE, an_entry("0.0"))
        else:
            store.append_homework_archive(LEARNER, COURSE, archive_entry("original"))
    before = {p: p.read_bytes() for p in root.rglob("archive/*.yaml")}
    ready, results, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    workers = [
        ctx.Process(target=_writer, args=(str(root), kind, revision, label, ready, go, results))
        for label in ("alpha", "beta")
    ]
    try:
        for worker in workers:
            worker.start()
        assert {ready.get(timeout=15), ready.get(timeout=15)} == {"alpha", "beta"}
        go.set()
        outcomes = [results.get(timeout=15), results.get(timeout=15)]
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
        if kind in {"record", "homework", "delete"}:
            assert sorted(status for status, _ in outcomes) == ["conflict", "ok"]
            winner = next(label for status, label in outcomes if status == "ok")
            if kind == "record":
                found = store.get_record(LEARNER, COURSE)
                assert found is not None and found[0].skills_unlocked == [winner]
                loser = next(label for status, label in outcomes if status == "conflict")
                # Retry only the refused writer's intent on the newly read state.
                updated = found[0].model_copy(update={"skills_unlocked": [winner, loser]})
                store.put_record(updated, found[1])
                final = store.get_record(LEARNER, COURSE)
                assert final is not None and set(final[0].skills_unlocked) == {"alpha", "beta"}
            else:
                slot, _ = store.get_homework(LEARNER, COURSE)
                if kind == "delete" and winner == "alpha":
                    assert slot is None
                else:
                    assert slot is not None and slot.coordinate == winner
        elif kind == "log":
            assert all(status == "ok" for status, _ in outcomes)
            entries = store.get_log(LEARNER, COURSE)
            assert sorted(e.coordinate for e in entries) == sorted(
                (["0.0"] if existing else []) + ["alpha", "beta"]
            )
            if existing:
                assert entries[0] == an_entry("0.0")
        else:
            assert all(status == "ok" for status, _ in outcomes)
            assert {e.title for e in store.get_homework_archive(LEARNER, COURSE)} == (
                ({"original"} if existing else set()) | {"alpha", "beta"}
            )
            assert all(path.read_bytes() == raw for path, raw in before.items())
    finally:
        go.set()
        for worker in workers:
            if worker.is_alive():
                worker.kill()
            if worker.pid is not None:
                worker.join(15)
        ready.close()
        results.close()
