"""Course-version roll-forward (spec/runtime.md#course-version-changes, issue #99).

A patch or minor bump whose coordinates are all still present moves the record forward in
place; a downgrade, a major bump, or a missing coordinate refuses with ``version-mismatch``
and leaves the record byte-for-byte unchanged. The upgrade is one recoverable store write.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Course, ObjectiveMet
from skilling.delivery import (
    CoordinateMap,
    UpgradeRefusal,
    UpgradeTarget,
    plan_upgrade,
    roll_forward,
)
from skilling.store import (
    Conflict,
    FileProgressStore,
    RecoveryRequired,
    UpgradeCommit,
    UpgradeIdentity,
)
from skilling.store._journal import _upgrade

from . import fixtures as fx
from .conftest import REPO_ROOT
from .test_cli_runtime import LESSON_WITH_EXERCISE, _walk_to_complete

runner = CliRunner()


@pytest.fixture
def state(tmp_path: Path) -> Path:
    """Kept apart from the course directory so byte comparisons see only learner state."""
    return tmp_path / "state"


LESSON_FOUR = fx.LESSON_THREE.replace("lesson: 1\n", "lesson: 2\n", 1).replace(
    'title: "Three"', 'title: "Four"', 1
)


def run(args: list[str], state: Path):
    return runner.invoke(app, [*args, "--state", str(state)], catch_exceptions=False)


def ok(args: list[str], state: Path) -> dict:
    result = run(args, state)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def set_version(course: Path, version: str) -> None:
    manifest = course / fx.MANIFEST_PATH
    text = manifest.read_text(encoding="utf-8")
    current = yaml.safe_load(text)["version"]
    manifest.write_text(
        text.replace(f'version: "{current}"', f'version: "{version}"'), encoding="utf-8"
    )


def patch_bump(course: Path, version: str = "1.0.1") -> None:
    set_version(course, version)
    lesson = course / fx.LESSON_ONE_PATH
    lesson.write_text(
        lesson.read_text(encoding="utf-8").replace("worth knowing", "well worth knowing"),
        encoding="utf-8",
    )


def append_lesson(course: Path, version: str = "1.1.0") -> None:
    set_version(course, version)
    manifest = course / fx.MANIFEST_PATH
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "      - { number: 1, slug: three, title: Three }\n",
            "      - { number: 1, slug: three, title: Three }\n"
            "      - { number: 2, slug: four, title: Four }\n",
        ),
        encoding="utf-8",
    )
    fx.write(course, f"{fx.PHASE_ONE}/lesson-02-four.md", LESSON_FOUR)


def remove_last_lesson(course: Path) -> None:
    manifest = course / fx.MANIFEST_PATH
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "      - { number: 2, slug: two, title: Two, homework: true }\n", ""
        ),
        encoding="utf-8",
    )
    (course / fx.LESSON_TWO_PATH).unlink()
    three = course / fx.LESSON_THREE_PATH
    three.write_text(
        three.read_text(encoding="utf-8").replace('["0.2"]', '["0.1"]'), encoding="utf-8"
    )


def record(state: Path) -> dict:
    return yaml.safe_load((state / "clean-course" / "record.yaml").read_text(encoding="utf-8"))


def state_bytes(state: Path) -> dict[str, bytes]:
    return {
        p.relative_to(state).as_posix(): p.read_bytes()
        for p in state.rglob("*")
        if p.is_file() and p.name != ".skilling.lock"
    }


def finish_first_lesson(course: Path, state: Path) -> None:
    ok(["next", "--course", str(course)], state)
    _walk_to_complete(course, state, LESSON_WITH_EXERCISE)
    ok(["complete", "--course", str(course)], state)


def to_concept_gate(course: Path, state: Path) -> None:
    for _ in range(3):
        ok(["advance", "--course", str(course), "--input", "next"], state)


# ------------------------------------------------------------------------- rolling forward


def test_a_patch_bump_resumes_at_the_same_position(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    to_concept_gate(clean_dir, state)
    before = record(state)
    assert before["position"] == {"phase": 0, "lesson": 2, "beat": "gate-concept"} | {
        "question_index": None
    }

    patch_bump(clean_dir)
    out = ok(["next", "--course", str(clean_dir)], state)

    assert out["beat"]["name"] == "gate-concept"
    after = record(state)
    assert after["course_version"] == "1.0.1"
    assert after == before | {"course_version": "1.0.1"}
    log = yaml.safe_load((state / "clean-course" / "completed.yaml").read_text())
    assert [e["course_version"] for e in log] == ["1.0.0"]  # history is never rewritten
    committed = yaml.safe_load((state / "clean-course" / "upgrade.yaml").read_bytes())
    assert committed["kind"] == "committed"
    assert (committed["identity"]["from_version"], committed["identity"]["to_version"]) == (
        "1.0.0",
        "1.0.1",
    )
    # The upgraded stream keeps working: transitions and progress against the new version.
    ok(["advance", "--course", str(clean_dir), "--input", "proceed"], state)
    assert ok(["progress", "--course", str(clean_dir)], state)["ok"] is True


def test_a_minor_bump_with_appended_lessons_resumes(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE)
    ok(["complete", "--course", str(clean_dir)], state)  # 0.2 ends phase 0: homework
    slot_before = (state / "clean-course" / "homework" / "active.yaml").read_bytes()

    append_lesson(clean_dir)
    out = ok(["next", "--course", str(clean_dir)], state)

    assert (out["position"]["phase"], out["position"]["lesson"]) == (1, 1)
    after = record(state)
    assert after["course_version"] == "1.1.0"
    assert sorted(after["completed"]) == ["0.1", "0.2"]
    assert (state / "clean-course" / "homework" / "active.yaml").read_bytes() == slot_before
    checked = ok(["homework", "check", "--course", str(clean_dir)], state)
    assert checked["active"]["coordinate"] == "0.2"
    assert checked["course"]["version"] == "1.1.0"


def test_rolling_forward_is_idempotent(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    patch_bump(clean_dir)
    ok(["next", "--course", str(clean_dir)], state)
    settled = state_bytes(state)
    ok(["next", "--course", str(clean_dir)], state)
    assert state_bytes(state) == settled


def test_a_beat_the_new_lesson_lacks_restarts_that_lesson(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    for given in ("next", "next", "next", "proceed"):  # 0.2 has no welcome: lands on exercise
        ok(["advance", "--course", str(clean_dir), "--input", given], state)
    assert record(state)["position"]["beat"] == "exercise"

    patch_bump(clean_dir)
    lesson = clean_dir / fx.LESSON_TWO_PATH
    lesson.write_text(
        lesson.read_text(encoding="utf-8")
        .replace(
            "  exercise: present\n",
            '  exercise:\n    status: none\n    intent: "Folded into the concept."\n',
        )
        .replace("## Hands-On Exercise\nTry the second thing yourself.\n\n", ""),
        encoding="utf-8",
    )
    out = ok(["next", "--course", str(clean_dir)], state)

    after = record(state)
    assert after["course_version"] == "1.0.1"
    assert (after["position"]["phase"], after["position"]["lesson"]) == (0, 2)
    assert after["position"]["beat"] is None
    assert after["completed"] == ["0.1"]
    assert out["position"]["lesson"] == 2
    assert (state / "clean-course" / "scratch.yaml").read_bytes() == b""


# ------------------------------------------------------------------------------- refusals


def test_a_major_bump_refuses_and_keeps_the_record(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    before = state_bytes(state)

    set_version(clean_dir, "2.0.0")
    result = run(["next", "--course", str(clean_dir)], state)

    assert result.exit_code == 5
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "version-mismatch"
    assert "1.0.0" in error["message"] and "2.0.0" in error["message"]
    assert "major version change" in error["message"]
    assert "cannot carry over automatically" in error["message"]
    assert "record is unchanged" in error["message"]
    assert state_bytes(state) == before


def test_a_downgrade_refuses(clean_dir: Path, state: Path) -> None:
    set_version(clean_dir, "1.2.0")
    finish_first_lesson(clean_dir, state)
    before = state_bytes(state)

    set_version(clean_dir, "1.1.9")
    result = run(["next", "--course", str(clean_dir)], state)

    assert result.exit_code == 5
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "version-mismatch"
    assert "older than the 1.2.0" in error["message"]
    assert state_bytes(state) == before


def test_a_missing_coordinate_refuses_and_names_it(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)  # position is now 0.2
    before = state_bytes(state)

    set_version(clean_dir, "1.0.1")  # dishonest: a patch that removes a lesson
    remove_last_lesson(clean_dir)
    result = run(["next", "--course", str(clean_dir)], state)

    assert result.exit_code == 5
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "version-mismatch"
    assert "no longer has position 0.2" in error["message"]
    assert state_bytes(state) == before


# ------------------------------------------------------------------------- the pure plan


def newer(clean: Course, version: str = "1.1.0") -> UpgradeTarget:
    return replace(UpgradeTarget.of(clean), version=version)


def test_plan_checks_every_recorded_reference(clean: Course) -> None:
    from skilling.course import Record

    record = Record.new(clean, "local")
    record = record.model_copy(update={"completed": ["0.1"]})
    target = newer(clean)
    assert plan_upgrade(record, [], None, target).ok

    met = ObjectiveMet(id="vanished", at=record.started_at, evidence="explained")
    stale = record.model_copy(update={"objectives_met": [met], "completed": ["0.1", "9.9"]})
    plan = plan_upgrade(stale, [], None, target)
    assert plan.refusal is UpgradeRefusal.MISSING
    assert plan.missing == ("completed 9.9", "objective vanished")


def test_an_invalid_in_lesson_beat_restarts_only_that_lesson(clean: Course) -> None:
    from skilling.course import Record

    record = Record.new(clean, "local")
    position = record.position.model_copy(
        update={"phase": 1, "lesson": 1, "beat": "exercise"}
    )  # 1.1 declares no exercise
    record = record.model_copy(update={"position": position})
    plan = plan_upgrade(record, [], None, newer(clean))
    assert plan.ok and plan.lesson_restarted and plan.record is not None
    assert plan.record.position.coordinate == "1.1"
    assert plan.record.position.beat is None


def test_a_major_bump_is_the_coordinate_map_seam(clean: Course) -> None:
    from skilling.course import Record

    record = Record.new(clean, "local")
    record = record.model_copy(update={"completed": ["7.1"]})
    target = newer(clean, "2.0.0")
    assert plan_upgrade(record, [], None, target).refusal is UpgradeRefusal.MAJOR
    plan = plan_upgrade(record, [], None, target, CoordinateMap((("7.1", "0.1"),)))
    assert plan.ok and plan.record is not None
    assert plan.record.completed == ["0.1"]


# ---------------------------------------------------------- journals bound to the old version


def test_keys_bound_before_an_upgrade_stay_bound(clean_dir: Path, state: Path) -> None:
    base = ["advance", "--course", str(clean_dir), "--input", "next", "--key", "k1"]
    ok(base, state)
    position = record(state)["position"]

    patch_bump(clean_dir)
    retried = run(base, state)

    assert retried.exit_code == 3
    assert json.loads(retried.stdout)["error"]["code"] == "idempotency-key-conflict"
    assert record(state)["position"] == position  # never a second transition
    fresh = ok([*base[:-1], "k2"], state)
    assert fresh["replayed"] is False


def test_committed_markers_are_retired_not_left_invalid(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)  # leaves committed completion + transition markers
    course_dir = state / "clean-course"
    old = {n: (course_dir / n).read_bytes() for n in ("completion.yaml", "transition.yaml")}

    patch_bump(clean_dir)
    ok(["next", "--course", str(clean_dir)], state)

    assert not (course_dir / "completion.yaml").exists()
    assert not (course_dir / "transition.yaml").exists()
    committed = yaml.safe_load((course_dir / "upgrade.yaml").read_bytes())
    assert committed["retired"] == old
    # A retried completion of the finished lesson after the upgrade is still a no-op.
    out = ok(["complete", "--course", str(clean_dir)], state)
    assert out["ok"] is True
    assert record(state)["completed"] == ["0.1"]


def test_an_old_version_homework_token_refuses(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE)
    ok(["complete", "--course", str(clean_dir)], state)
    token = ok(["homework", "check", "--course", str(clean_dir)], state)["submission_token"]

    patch_bump(clean_dir)
    result = run(["homework", "submit", "--course", str(clean_dir), "--token", token], state)

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "invalid-submission-token"
    fresh = ok(["homework", "check", "--course", str(clean_dir)], state)
    assert fresh["submission_token"] != token


# ---------------------------------------------------------- interruption and concurrency

BOUNDARIES = ("prepared", "reservation", "marker", "record", "committed")


def boundary_of(path: Path, data: bytes) -> str:
    if path.name == "upgrade.yaml":
        return yaml.safe_load(data)["kind"]
    if path.parent.name == "transition-receipts":
        return "reservation"
    return {"scratch.yaml": "scratch", "record.yaml": "record"}.get(path.name, "other")


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_an_interrupted_upgrade_recovers_on_next_access(
    clean_dir: Path, state: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    finish_first_lesson(clean_dir, state)
    ok(["advance", "--course", str(clean_dir), "--input", "next", "--key", "k1"], state)
    patch_bump(clean_dir)
    real_write, real_unlink = _upgrade._write_bytes_atomic, Path.unlink

    def write(path: Path, data: bytes) -> None:
        real_write(path, data)
        if boundary_of(path, data) == boundary:
            raise OSError("injected after durable " + boundary)

    def unlink(self: Path, missing_ok: bool = False) -> None:
        real_unlink(self, missing_ok=missing_ok)
        if boundary == "marker" and self.name.endswith(".yaml") and self.parent == stream:
            raise OSError("injected after retiring a marker")

    stream = state / "clean-course"
    monkeypatch.setattr(_upgrade, "_write_bytes_atomic", write)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(OSError, match="injected"):
        runner.invoke(
            app,
            ["next", "--course", str(clean_dir), "--state", str(state)],
            catch_exceptions=False,
        )
    monkeypatch.undo()

    out = ok(["next", "--course", str(clean_dir)], state)
    assert out["ok"] is True
    after = record(state)
    assert after["course_version"] == "1.0.1"
    assert after["completed"] == ["0.1"]
    assert yaml.safe_load((stream / "upgrade.yaml").read_bytes())["kind"] == "committed"
    retried = run(["advance", "--course", str(clean_dir), "--input", "next", "--key", "k1"], state)
    assert json.loads(retried.stdout)["error"]["code"] == "idempotency-key-conflict"


def test_recovery_refuses_bytes_it_did_not_write(
    clean_dir: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finish_first_lesson(clean_dir, state)
    patch_bump(clean_dir)
    real_write = _upgrade._write_bytes_atomic

    def write(path: Path, data: bytes) -> None:
        real_write(path, data)
        if boundary_of(path, data) == "prepared":
            raise OSError("injected after durable prepared")

    monkeypatch.setattr(_upgrade, "_write_bytes_atomic", write)
    with pytest.raises(OSError, match="injected"):
        runner.invoke(
            app,
            ["next", "--course", str(clean_dir), "--state", str(state)],
            catch_exceptions=False,
        )
    monkeypatch.undo()
    stream = state / "clean-course"
    (stream / "record.yaml").write_text(
        (stream / "record.yaml").read_text().replace("streak_days: 1", "streak_days: 9")
    )

    store = FileProgressStore(state)
    with pytest.raises(RecoveryRequired, match="upgrade target record.yaml"):
        store.read_runtime_snapshot("local", "clean-course")


def test_a_stale_or_repeated_upgrade_commit_is_safe(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    patch_bump(clean_dir)
    store = FileProgressStore(state)
    snapshot = store.read_runtime_snapshot("local", "clean-course")
    assert snapshot is not None
    upgraded = snapshot.record.model_copy(update={"course_version": "1.0.1"})
    identity = UpgradeIdentity("local", "clean-course", "1.0.0", "1.0.1")
    commit = UpgradeCommit(
        identity, snapshot.revision, snapshot.scratch, upgraded, snapshot.scratch
    )

    first = store.commit_upgrade(commit)
    again = store.commit_upgrade(commit)  # an interrupted caller retrying the same upgrade
    assert (first.replayed, again.replayed) == (False, True)
    assert again.snapshot == first.snapshot

    stale = UpgradeCommit(
        UpgradeIdentity("local", "clean-course", "1.0.0", "1.0.2"),
        snapshot.revision,
        snapshot.scratch,
        snapshot.record.model_copy(update={"course_version": "1.0.2"}),
        snapshot.scratch,
    )
    with pytest.raises(Conflict):
        store.commit_upgrade(stale)
    assert record(state)["course_version"] == "1.0.1"


def test_a_concurrent_winner_counts_as_rolled_forward(
    clean_dir: Path, state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finish_first_lesson(clean_dir, state)
    patch_bump(clean_dir)
    store = FileProgressStore(state)
    course = Course.load(clean_dir)
    real = FileProgressStore.commit_upgrade

    def race(self: FileProgressStore, commit: UpgradeCommit):
        monkeypatch.setattr(FileProgressStore, "commit_upgrade", real)
        roll_forward(FileProgressStore(state), course, "local")  # the other process wins
        return real(self, commit)

    monkeypatch.setattr(FileProgressStore, "commit_upgrade", race)
    rolled = roll_forward(store, course, "local")
    assert rolled.snapshot is not None
    assert rolled.snapshot.record.course_version == "1.0.1"


def test_concurrent_processes_upgrade_exactly_once(clean_dir: Path, state: Path) -> None:
    finish_first_lesson(clean_dir, state)
    patch_bump(clean_dir)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("SKILLING_STATE_ROOT", "SKILLING_WORKSPACE", "SKILLING_NOW")
    }
    code = "from skilling.cli import main; main()"
    args = [sys.executable, "-c", code, "next", "--course", str(clean_dir), "--state", str(state)]
    procs = [
        subprocess.Popen(args, cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, text=True)
        for _ in range(4)
    ]
    outputs = [p.communicate(timeout=60)[0] for p in procs]

    assert [p.returncode for p in procs] == [0, 0, 0, 0], outputs
    assert all(json.loads(o)["beat"]["name"] == "welcome" for o in outputs)
    after = record(state)
    assert after["course_version"] == "1.0.1"
    assert after["completed"] == ["0.1"]


# ----------------------------------------------------------------------------- start


def test_start_reports_what_happens_to_progress(tmp_path: Path) -> None:
    source = fx.build(tmp_path / "src" / "clean-course")
    workspace = tmp_path / "ws"
    first = runner.invoke(app, ["start", str(source), str(workspace), "--json"])
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout)["progress"] is None

    patch_bump(source)
    second = runner.invoke(app, ["start", str(source), str(workspace), "--json"])
    assert second.exit_code == 0, second.output
    progress = json.loads(second.stdout)["progress"]
    assert progress["status"] == "rolled-forward"
    assert (progress["from"], progress["to"]) == ("1.0.0", "1.0.1")
    state = workspace / ".skilling" / "state"
    assert record(state)["course_version"] == "1.0.1"

    set_version(source, "2.0.0")
    third = runner.invoke(app, ["start", str(source), str(workspace)])
    assert third.exit_code == 0, third.output
    assert "not resumable" in third.output
    assert "major version change" in third.output
    assert record(state)["course_version"] == "1.0.1"
