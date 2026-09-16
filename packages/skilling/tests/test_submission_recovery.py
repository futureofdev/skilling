"""Synthetic workbench transactions; real storage/processes, no learner-proof claim."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from skilling.course import Assignment, Course, HomeworkArchiveEntry, HomeworkSlot, Record
from skilling.delivery import (
    Dispatcher,
    RecordingSink,
    assignment_from_lesson,
    complete_lesson,
    submit_homework,
)
from skilling.store import (
    Conflict,
    FileProgressStore,
    RecoveryRequired,
    SubmissionCommit,
    SubmissionReceipt,
    SubmissionToken,
)
from skilling.store._journal import _submission, _transition

from .conftest import REPO_ROOT
from .test_transition_recovery import bytes_at, environment

NOW = datetime(2026, 8, 3, 23, 59, 59, tzinfo=UTC)
BOUNDARIES = ("prepared", "archive", "slot", "receipt", "committed")


@pytest.fixture
def workbench() -> Course:
    return Course.load(REPO_ROOT / "examples/workbench")


def seed(root: Path, course: Course, queued: bool = False) -> FileProgressStore:
    store = FileProgressStore(root)
    store.put_record(Record.new(course, "local", now=NOW), None)
    first, second = course.lesson_at("1.2"), course.lesson_at("2.2")
    assert first and second
    assigned = assignment_from_lesson(first, now=NOW)
    following = assignment_from_lesson(second, now=NOW)
    assert assigned and following
    slot = HomeworkSlot(**assigned.model_dump(), queued=[following] if queued else [])
    slot.requirements[0].verdict = "met"
    slot.requirements[0].reason = "Synthetic inspected example"
    store.put_homework("local", course.id, slot, None)
    return store


def token_for(store: FileProgressStore, course: Course) -> str:
    slot, revision = store.get_homework("local", course.id)
    assert slot is not None and revision is not None
    return SubmissionToken.for_slot("local", course.id, course.version, slot, revision).encode()


def commit_for(store: FileProgressStore, course: Course, token: str) -> SubmissionCommit:
    slot, revision = store.get_homework("local", course.id)
    assert slot and revision
    archive = HomeworkArchiveEntry(
        coordinate=slot.coordinate,
        title=slot.title,
        requirements=slot.requirements,
        stretch_goals=slot.stretch_goals,
        submitted_at=NOW,
    )
    identity = SubmissionToken.parse(token)
    receipt = SubmissionReceipt(
        token, "local", course.id, course.version, slot.coordinate, identity.instance_id, archive
    )
    after = (
        HomeworkSlot(**slot.queued[0].model_dump(), queued=slot.queued[1:]) if slot.queued else None
    )
    return SubmissionCommit(receipt, revision, after)


def submit(store: FileProgressStore, course: Course, token: str, **kwargs) -> HomeworkArchiveEntry:
    return submit_homework(
        store,
        "local",
        course.id,
        SubmissionToken.parse(token).coordinate,
        token=token,
        now=kwargs.pop("now", NOW),
        **kwargs,
    )


def worker(course: Course, root: Path, verb: str = "submit", **options: str) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "packages.skilling.tests.submission_worker",
        verb,
        "--course",
        str(course.root),
        "--state",
        str(root),
    ]
    for key, value in options.items():
        args += ["--" + key.replace("_", "-"), value]
    return args


def invoke(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=environment(),
        text=True,
        capture_output=True,
        timeout=40,
        check=False,
    )


def wait_for(path: Path, proc: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    while not path.exists():
        assert proc.poll() is None, proc.communicate()
        assert time.monotonic() < deadline, "worker did not reach boundary"
        time.sleep(0.02)


def assert_one(store: FileProgressStore, course: Course, token: str, queued: bool) -> None:
    archives = store.get_homework_archive("local", course.id)
    assert len(archives) == 1 and archives[0].coordinate == "1.2"
    assert archives[0].submitted_at == NOW
    assert archives[0].requirements[0].verdict == "met"
    assert archives[0].requirements[0].reason == "Synthetic inspected example"
    slot, _ = store.get_homework("local", course.id)
    assert (slot.coordinate if slot else None) == ("2.2" if queued else None)
    assert slot is None or slot.queued == []
    receipt = store.get_submission_receipt("local", course.id, token)
    assert receipt is not None and receipt.archive == archives[0]


@pytest.mark.parametrize("queued", (False, True))
@pytest.mark.parametrize("fault", ("error", "exit", "hold"))
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_actual_boundary_interruption_and_next_day_replay(
    tmp_path: Path, workbench: Course, queued: bool, fault: str, boundary: str
) -> None:
    store = seed(tmp_path / "state", workbench, queued)
    token = token_for(store, workbench)
    record_before = (store.state_root / workbench.id / "record.yaml").read_bytes()
    args = worker(
        workbench,
        store.state_root,
        token=token,
        now=NOW.isoformat(),
        fault=fault,
        boundary=boundary,
        marker=str(tmp_path / "marker"),
    )
    if fault == "hold":
        with subprocess.Popen(
            args,
            cwd=REPO_ROOT,
            env=environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as proc:
            try:
                wait_for(tmp_path / "marker", proc)
                proc.kill()
                proc.communicate(timeout=10)
                assert proc.returncode != 0
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
    else:
        failed = invoke(args)
        assert failed.returncode == (73 if fault == "exit" else 1), failed.stderr
    # A different process opens and recovers, before any retry.
    read = invoke(worker(workbench, store.state_root, "inspect"))
    assert read.returncode == 0, read.stderr
    assert_one(store, workbench, token, queued)
    settled = bytes_at(store.state_root)
    retry = invoke(
        worker(workbench, store.state_root, token=token, now=(NOW + timedelta(days=1)).isoformat())
    )
    assert retry.returncode == 0, retry.stderr
    assert json.loads(retry.stdout)["archived"]["submitted_at"] == NOW.isoformat().replace(
        "+00:00", "Z"
    )
    assert bytes_at(store.state_root) == settled
    assert (store.state_root / workbench.id / "record.yaml").read_bytes() == record_before


def test_before_intent_failure_has_no_effect_or_accepted_token(
    tmp_path: Path, workbench: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = seed(tmp_path / "state", workbench, True)
    token = token_for(store, workbench)
    before = bytes_at(store.state_root)

    def fail(path: Path, data: bytes) -> None:
        raise OSError("before prepared publication")

    monkeypatch.setattr(_submission, "_write_bytes_atomic", fail)
    with pytest.raises(OSError):
        submit(store, workbench, token)
    assert bytes_at(store.state_root) == before
    assert store.get_submission_receipt("local", workbench.id, token) is None


@pytest.mark.parametrize("queued", (False, True))
def test_pending_state_relocates_without_absolute_paths(
    tmp_path: Path, workbench: Course, queued: bool
) -> None:
    original = tmp_path / "workspace"
    copied = original / "course"
    shutil.copytree(workbench.root, copied)
    course = Course.load(copied)
    store = seed(original / "state", course, queued)
    token = token_for(store, course)
    assert (
        invoke(
            worker(course, store.state_root, token=token, now=NOW.isoformat(), fault="exit")
        ).returncode
        == 73
    )
    moved = tmp_path / "moved"
    shutil.move(str(original), moved)
    course = Course.load(moved / "course")
    retry = invoke(
        worker(course, moved / "state", token=token, now=(NOW + timedelta(days=1)).isoformat())
    )
    assert retry.returncode == 0, retry.stderr
    assert_one(FileProgressStore(moved / "state"), course, token, queued)
    assert all(str(original).encode() not in data for data in bytes_at(moved / "state").values())


@pytest.mark.parametrize("change", ("verdict", "reason", "queue", "unlock"))
def test_changed_slot_conflicts_without_effects(
    tmp_path: Path, workbench: Course, change: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    slot, revision = store.get_homework("local", workbench.id)
    assert slot
    if change == "verdict":
        slot.requirements[0].verdict = "partial"
    elif change == "reason":
        slot.requirements[0].reason = "New inspected evidence"
    elif change == "queue":
        slot.queued = [Assignment.model_validate(slot.model_dump(exclude={"queued"}))]
    else:
        slot.unlocked_at += timedelta(days=1)
    store.put_homework("local", workbench.id, slot, revision)
    next_token = token_for(store, workbench)
    assert next_token != token
    assert (
        SubmissionToken.parse(next_token).instance_id == SubmissionToken.parse(token).instance_id
    ) == (change != "unlock")
    before = bytes_at(store.state_root)
    with pytest.raises(Conflict):
        submit(store, workbench, token)
    assert bytes_at(store.state_root) == before


def test_repeated_coordinate_is_a_distinct_instance_and_legacy_archives_remain(
    tmp_path: Path, workbench: Course
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    original, _ = store.get_homework("local", workbench.id)
    assert original
    legacy = commit_for(store, workbench, token).receipt.archive
    store.append_homework_archive("local", workbench.id, legacy)
    store.append_homework_archive("local", workbench.id, legacy)
    historical = bytes_at(store.state_root / workbench.id / "homework/archive")
    first = submit(store, workbench, token)
    later = original.model_copy(update={"unlocked_at": NOW + timedelta(days=1)})
    store.put_homework("local", workbench.id, later, None)
    second_token = token_for(store, workbench)
    assert second_token != token
    before = bytes_at(store.state_root)
    assert submit(store, workbench, token, now=NOW + timedelta(days=2)) == first
    assert bytes_at(store.state_root) == before
    submit(store, workbench, second_token, now=NOW + timedelta(days=1))
    archives = bytes_at(store.state_root / workbench.id / "homework/archive")
    assert len(archives) == 4
    assert historical.items() <= archives.items()


@pytest.mark.parametrize("peer", ("same-token", "changed-token", "completion"))
def test_concurrent_checked_writers_preserve_peer_work(
    tmp_path: Path, workbench: Course, peer: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    ready, release = tmp_path / "ready", tmp_path / "release"
    args = worker(
        workbench,
        store.state_root,
        token=token,
        now=NOW.isoformat(),
        ready=str(ready),
        release=str(release),
    )
    with subprocess.Popen(
        args,
        cwd=REPO_ROOT,
        env=environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as proc:
        try:
            wait_for(ready, proc)
            if peer == "same-token":
                got = invoke(worker(workbench, store.state_root, token=token, now=NOW.isoformat()))
                assert got.returncode == 0, got.stderr
            elif peer == "changed-token":
                slot, revision = store.get_homework("local", workbench.id)
                assert slot
                slot.requirements[0].reason = "Peer inspection"
                store.put_homework("local", workbench.id, slot, revision)
                got = invoke(
                    worker(
                        workbench,
                        store.state_root,
                        token=token_for(store, workbench),
                        now=NOW.isoformat(),
                    )
                )
                assert got.returncode == 0, got.stderr
            else:
                found = store.get_record("local", workbench.id)
                assert found is not None
                record, revision = found
                lesson = workbench.lesson_at("2.2")
                assert lesson
                complete_lesson(store, workbench, record, revision, lesson, now=NOW)
            before = bytes_at(store.state_root)
            release.write_text("go")
            stdout, stderr = proc.communicate(timeout=30)
            assert proc.returncode == (0 if peer == "same-token" else 3), (stdout, stderr)
            assert bytes_at(store.state_root) == before
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
    slot, _ = store.get_homework("local", workbench.id)
    if peer == "completion":
        assert slot and [q.coordinate for q in slot.queued] == ["2.2"]
        assert store.get_homework_archive("local", workbench.id) == []
    else:
        assert slot is None and len(store.get_homework_archive("local", workbench.id)) == 1


def test_hooks_only_follow_new_durable_commit(tmp_path: Path, workbench: Course) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    sink = RecordingSink()
    hooks = Dispatcher(first_party=[sink])
    found = store.get_record("local", workbench.id)
    assert found is not None
    record = found[0]
    submit(store, workbench, token, hooks=hooks, record=record)
    submit(store, workbench, token, hooks=hooks, record=record, now=NOW + timedelta(days=1))
    assert len(sink.events) == 1
    assert sink.events[0].event == "homework_submitted"


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_recovery_and_replay_do_not_dispatch_hooks(
    tmp_path: Path, workbench: Course, boundary: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    assert (
        invoke(
            worker(
                workbench,
                store.state_root,
                token=token,
                now=NOW.isoformat(),
                fault="exit",
                boundary=boundary,
            )
        ).returncode
        == 73
    )
    sink = RecordingSink()
    found = store.get_record("local", workbench.id)
    assert found is not None
    record = found[0]
    submit(store, workbench, token, hooks=Dispatcher(first_party=[sink]), record=record)
    assert sink.events == []


@pytest.mark.parametrize("change", ("revision", "coordinate", "archive", "next-slot"))
def test_direct_commit_validates_before_replay(
    tmp_path: Path, workbench: Course, change: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    commit = commit_for(store, workbench, token)
    submit(store, workbench, token)
    if change == "revision":
        commit = replace(commit, expected_slot_revision="wrong")
    elif change == "coordinate":
        commit = replace(commit, receipt=replace(commit.receipt, coordinate="2.2"))
    elif change == "archive":
        commit = replace(
            commit,
            receipt=replace(
                commit.receipt,
                archive=commit.receipt.archive.model_copy(
                    update={"submitted_at": NOW.replace(tzinfo=None)}
                ),
            ),
        )
    else:
        commit = replace(commit, slot=HomeworkSlot.model_construct(coordinate="../../escape"))
    before = bytes_at(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.commit_submission(commit)
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize(
    "damage",
    (
        "version",
        "boolean-version",
        "missing-version",
        "missing-kind",
        "stream",
        "coordinate",
        "instance",
        "archive-path",
        "archive-bytes",
        "slot-after",
        "slot-before",
        "receipt-version",
        "unexpected-slot",
        "unexpected-archive",
        "unexpected-receipt",
    ),
)
def test_corrupt_pending_metadata_refuses_without_effects(
    tmp_path: Path, workbench: Course, damage: str
) -> None:
    store = seed(tmp_path / "state", workbench, True)
    token = token_for(store, workbench)
    assert (
        invoke(
            worker(
                workbench,
                store.state_root,
                token=token,
                now=NOW.isoformat(),
                fault="exit",
                boundary="prepared",
            )
        ).returncode
        == 73
    )
    course_root = store.state_root / workbench.id
    path = course_root / "submission.yaml"
    data = yaml.safe_load(path.read_bytes())
    if damage == "version":
        data["version"] = 9
    elif damage == "boolean-version":
        data["version"] = True
    elif damage == "missing-version":
        del data["version"]
    elif damage == "missing-kind":
        del data["kind"]
    elif damage in ("stream", "coordinate", "instance"):
        field = {"stream": "learner_id", "coordinate": "coordinate", "instance": "instance_id"}[
            damage
        ]
        data["receipt"]["value"][field] = "other"
    elif damage == "archive-path":
        data["receipt"]["archive_path"] = "../escape.yaml"
    elif damage == "archive-bytes":
        data["archive_after"] = b"unexpected"
    elif damage == "slot-after":
        data["slot_after"] = None
    elif damage == "slot-before":
        data["slot_before"] = data["slot_after"]
    elif damage == "receipt-version":
        del data["receipt"]["version"]
    elif damage == "unexpected-slot":
        (course_root / "homework/active.yaml").write_bytes(b"unexpected")
    elif damage == "unexpected-archive":
        target = course_root / data["receipt"]["archive_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"unexpected")
    else:
        target = course_root / "submission-receipts" / _submission.receipt_name(token)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"unexpected")
    path.write_bytes(_submission.dump(data))
    before = bytes_at(store.state_root)
    with pytest.raises(RecoveryRequired):
        FileProgressStore(store.state_root).get_record("local", workbench.id)
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize("damage", ("missing-version", "stream", "archive", "receipt", "no-record"))
def test_committed_metadata_refuses_corruption_but_allows_later_progress(
    tmp_path: Path, workbench: Course, damage: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    submit(store, workbench, token)
    found = store.get_record("local", workbench.id)
    assert found is not None
    record, revision = found
    store.put_record(record.model_copy(update={"streak_days": 99}), revision)
    assert store.get_submission_receipt("local", workbench.id, token) is not None
    root = store.state_root / workbench.id
    path = root / "submission.yaml"
    data = yaml.safe_load(path.read_bytes())
    if damage == "missing-version":
        del data["version"]
        path.write_bytes(_submission.dump(data))
    elif damage in ("stream", "no-record"):
        record_path = root / "record.yaml"
        if damage == "stream":
            raw = yaml.safe_load(record_path.read_bytes())
            raw["course_version"] = "9.0.0"
            record_path.write_bytes(_submission.dump(raw))
        else:
            record_path.unlink()
    elif damage == "archive":
        (root / data["receipt"]["archive_path"]).write_bytes(b"unexpected")
    else:
        (root / "submission-receipts" / _submission.receipt_name(token)).unlink()
    before = bytes_at(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.get_record("local", workbench.id)
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize("other", ("completion", "transition"))
def test_two_individually_valid_prepared_journals_refuse_together(
    tmp_path: Path, workbench: Course, monkeypatch: pytest.MonkeyPatch, other: str
) -> None:
    from skilling.store import _journal

    from .test_transition_recovery import next_commit

    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    root = store.state_root / workbench.id
    transition = next_commit(workbench.root, store.state_root, "coexisting")

    def stop(*args: object) -> None:
        raise OSError("stop before effects")

    with monkeypatch.context() as patch:
        patch.setattr(_submission.SubmissionJournal, "apply", stop)
        with pytest.raises(OSError):
            submit(store, workbench, token)
    raw = (root / "submission.yaml").read_bytes()
    (root / "submission.yaml").unlink()
    with monkeypatch.context() as patch:
        if other == "completion":
            patch.setattr(_journal.Journal, "_apply", stop)
            found = store.get_record("local", workbench.id)
            assert found is not None
            record, revision = found
            lesson = workbench.lesson_at("2.2")
            assert lesson
            with pytest.raises(OSError):
                complete_lesson(store, workbench, record, revision, lesson, now=NOW)
        else:
            patch.setattr(_journal.TransitionJournal, "apply", stop)
            with pytest.raises(OSError):
                store.commit_transition(transition)
    (root / "submission.yaml").write_bytes(raw)
    assert isinstance(
        _submission.SubmissionJournal(store.state_root, workbench.id).inspect(),
        _submission.Prepared,
    )
    if other == "completion":
        journal = _journal.Journal(store.state_root, workbench.id)
        prepared = journal._load()
        assert isinstance(prepared, _journal.Prepared)
        journal._preflight(prepared)
    else:
        assert isinstance(
            _journal.TransitionJournal(store.state_root, workbench.id).inspect(),
            _transition.Prepared,
        )
    before = bytes_at(store.state_root)
    with pytest.raises(RecoveryRequired, match="multiple prepared"):
        store.get_record("local", workbench.id)
    assert bytes_at(store.state_root) == before
    # Malformed companion also refuses before applying otherwise-valid accepted work.
    (root / (other + ".yaml")).write_bytes(b"version: 999\nkind: prepared\n")
    before = bytes_at(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.get_record("local", workbench.id)
    assert bytes_at(store.state_root) == before
