"""Tests for the JSON transition verbs: ``next``, ``advance``, ``complete``, ``ceremony``.

One process per transition, so every assertion is about what got *persisted* — the record and
the scratch file beside it — not about what stayed in memory. That split is the entire reason
``cli/runtime/_common.py`` exists: a wrong answer or a resumed gate has to survive a process
exit, which the interactive walker never had to think about.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.store import Conflict, FileProgressStore
from skilling.workspace import WorkspaceCourse, WorkspaceManifest
from skilling.workspace import courses_dir as workspace_courses_dir
from skilling.workspace import save_manifest as save_workspace_manifest
from skilling.workspace import state_root as workspace_state_root

from . import fixtures as fx

runner = CliRunner()


def run(args: list[str], tmp: Path):
    return runner.invoke(app, [*args, "--state", str(tmp)], catch_exceptions=False)


def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """State-root and course-id resolution both walk up from the cwd and consult the
    environment — clearing both is what keeps a precedence test honest about which source
    it is actually exercising, rather than inheriting whatever the test runner's own
    environment happens to hold."""
    monkeypatch.delenv("SKILLING_STATE_ROOT", raising=False)
    monkeypatch.delenv("SKILLING_WORKSPACE", raising=False)


def _add_to_workspace(workspace: Path, course_dir: Path, course_id: str, version: str = "1.0.0"):
    """Add ``course_dir``'s content to ``workspace`` under the manifest's own
    ``<id>@<version>`` naming, and return the destination directory."""
    dest = workspace_courses_dir(workspace) / f"{course_id}@{version}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(course_dir, dest)
    save_workspace_manifest(
        workspace,
        WorkspaceManifest(
            courses=[
                WorkspaceCourse(
                    id=course_id,
                    version=version,
                    ref="local",
                    path=f"courses/{course_id}@{version}",
                    showcase=f"showcase/{course_id}",
                    added_at=datetime.now(UTC),
                )
            ]
        ),
    )
    return dest


def _advance(course: Path, tmp: Path, given: str, *, key: str | None = None):
    args = ["advance", "--course", str(course), "--input", given]
    if key is not None:
        args = [*args, "--key", key]
    return run(args, tmp)


def _record(tmp: Path, course_id: str = "clean-course") -> dict:
    return yaml.safe_load((tmp / course_id / "record.yaml").read_text(encoding="utf-8"))


# The clean-course fixture (tests/fixtures.py): lesson 0.1 has an exercise, lesson 0.2 has an
# exercise and unlocks 'alpha', lesson 1.1 (last in the course) declares its exercise absent.
LESSON_WITH_EXERCISE = [
    "next",
    "next",
    "next",
    "proceed",
    "next",
    "attempted",
    "answer-correct",
    "answer-correct",
    "answer-correct",
]
LESSON_WITHOUT_EXERCISE = [
    "next",
    "next",
    "next",
    "proceed",
    "answer-correct",
    "answer-correct",
    "answer-correct",
]


def _walk_to_complete(course: Path, tmp: Path, inputs: list[str]) -> dict:
    """Drive ``advance`` through a whole lesson, from wherever it currently stands to the
    completion beat, and return the last emitted envelope."""
    out: dict = {}
    for given in inputs:
        result = _advance(course, tmp, given)
        assert result.exit_code == 0, result.output
        out = json.loads(result.stdout)
    return out


# --------------------------------------------------------------------------------------- next


def test_beats_deliver_in_order(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["next", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["beat"]["name"] == "welcome"
    assert out["legal_inputs"] == ["next"]

    for expected in ["objectives", "concept", "gate-concept"]:
        result = _advance(clean_dir, tmp_path, "next")
        assert result.exit_code == 0, result.output
        out = json.loads(result.stdout)
        assert out["beat"]["name"] == expected

    # The concept gate's legal inputs are what actually drive the walk from here: 'proceed'
    # moves on, 'go-deeper' loops back to the concept without moving position.
    assert set(out["legal_inputs"]) == {"go-deeper", "proceed"}

    looped = json.loads(_advance(clean_dir, tmp_path, "go-deeper").stdout)
    assert looped["beat"]["name"] == "concept"
    # Curiosity is not progress: the coordinate and question index hold even though the beat
    # itself legitimately moves back from the gate to the concept.
    assert looped["position"]["phase"] == out["position"]["phase"]
    assert looped["position"]["lesson"] == out["position"]["lesson"]
    assert looped["position"]["question_index"] == out["position"]["question_index"]


def test_json_envelope_is_stable(clean_dir: Path, tmp_path: Path) -> None:
    out = json.loads(run(["next", "--course", str(clean_dir)], tmp_path).stdout)
    assert set(out) == {
        "ok",
        "verb",
        "course",
        "tutor",
        "position",
        "beat",
        "legal_inputs",
        "revision",
        "completed_count",
        "lesson_count",
    }
    assert out["ok"] is True
    assert out["verb"] == "next"
    assert out["course"] == {"id": "clean-course", "version": "1.0.0", "title": "Clean Course"}
    assert out["position"] == {"phase": 0, "lesson": 1, "beat": None, "question_index": None}
    assert out["completed_count"] == 0
    assert out["lesson_count"] == 3


def test_envelope_carries_the_manifests_declared_persona(clean_dir: Path, tmp_path: Path) -> None:
    # The clean-course fixture declares a tutor block (tests/fixtures.py) — next's envelope
    # must surface it verbatim rather than a course.title-only summary.
    out = json.loads(run(["next", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["tutor"] == {"persona": "A calm instructor.", "tone": ["Direct"]}


def test_tutor_is_omitted_when_the_manifest_declares_none(tmp_path: Path) -> None:
    root = fx.build(tmp_path / "no-tutor-course")
    fx.edit(
        root,
        fx.MANIFEST_PATH,
        "tutor:\n  persona: A calm instructor.\n  tone:\n    - Direct\n",
        "",
    )
    out = json.loads(run(["next", "--course", str(root)], tmp_path).stdout)
    assert out["course"]["title"] == "Clean Course"
    assert "tutor" not in out


def test_next_is_read_only(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)
    run(["next", "--course", str(clean_dir)], tmp_path)
    # load_or_create writes the record once, on first use; a second read must not touch it.
    assert _record(tmp_path)["position"] == {
        "phase": 0,
        "lesson": 1,
        "beat": None,
        "question_index": None,
    }


# ------------------------------------------------------------------------------------ advance


def test_illegal_input_is_a_typed_refusal_not_a_noop(clean_dir: Path, tmp_path: Path) -> None:
    result = _advance(clean_dir, tmp_path, "attempted")
    assert result.exit_code == 4
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "illegal-transition"


def test_unknown_input_is_invalid_not_illegal(clean_dir: Path, tmp_path: Path) -> None:
    result = _advance(clean_dir, tmp_path, "teleport")
    assert result.exit_code == 2
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "unknown-input"


def test_a_gate_input_illegal_at_another_gate_is_refused(clean_dir: Path, tmp_path: Path) -> None:
    for given in ["next", "next", "next", "proceed", "next"]:  # welcome -> gate-exercise
        result = _advance(clean_dir, tmp_path, given)
        assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["beat"]["name"] == "gate-exercise"

    # 'proceed' is legal at gate-concept, never at gate-exercise.
    result = _advance(clean_dir, tmp_path, "proceed")
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "illegal-transition"


def test_replayed_advance_is_idempotent(clean_dir: Path, tmp_path: Path) -> None:
    a = _advance(clean_dir, tmp_path, "next", key="k1")
    b = _advance(clean_dir, tmp_path, "next", key="k1")
    assert a.exit_code == 0
    first, replay = json.loads(a.stdout), json.loads(b.stdout)
    assert first.pop("replayed") is False
    assert replay.pop("replayed") is True
    assert first == replay  # current envelope; applied once

    assert _record(tmp_path)["position"]["beat"] == "objectives"


def test_a_fresh_key_applies_again(clean_dir: Path, tmp_path: Path) -> None:
    a = _advance(clean_dir, tmp_path, "next", key="k1")
    b = _advance(clean_dir, tmp_path, "next", key="k2")
    assert json.loads(a.stdout)["beat"]["name"] == "objectives"
    assert json.loads(b.stdout)["beat"]["name"] == "concept"


def test_conflict_surfaces_as_exit_3(clean_dir: Path, tmp_path: Path, monkeypatch) -> None:
    # Prime the record first, unpatched, so open_session's own record-creation write is
    # unaffected — only this call's own advance write should ever hit the patched method.
    run(["next", "--course", str(clean_dir)], tmp_path)

    def _boom(self, commit):
        raise Conflict("record.yaml", commit.expected_record_revision, "elsewhere")

    monkeypatch.setattr(FileProgressStore, "commit_transition", _boom)

    result = _advance(clean_dir, tmp_path, "next")
    assert result.exit_code == 3
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "conflict"


def test_advance_refuses_at_the_completion_beat(clean_dir: Path, tmp_path: Path) -> None:
    out = _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    assert out["beat"]["name"] == "complete"

    result = _advance(clean_dir, tmp_path, "next")
    assert result.exit_code == 4
    body = json.loads(result.stdout)
    assert body["error"]["code"] == "illegal-transition"
    assert "complete" in body["error"]["message"]


def test_advance_refuses_once_the_course_is_complete(clean_dir: Path, tmp_path: Path) -> None:
    for inputs in [LESSON_WITH_EXERCISE, LESSON_WITH_EXERCISE, LESSON_WITHOUT_EXERCISE]:
        _walk_to_complete(clean_dir, tmp_path, inputs)
        run(["complete", "--course", str(clean_dir)], tmp_path)

    result = _advance(clean_dir, tmp_path, "next")
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "course-complete"


# ----------------------------------------------------------------------------------- complete


def test_complete_refuses_before_the_quiz_is_finished(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)
    result = run(["complete", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "illegal-transition"


def test_completion_writes_the_record_and_is_idempotent(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)

    first = json.loads(run(["complete", "--course", str(clean_dir)], tmp_path).stdout)
    assert first["ok"] is True
    assert first["already_completed"] is False
    assert first["badges_awarded"] == []
    assert first["position"] == {"phase": 0, "lesson": 2, "beat": None, "question_index": None}

    before = _record(tmp_path)
    again = json.loads(run(["complete", "--course", str(clean_dir)], tmp_path).stdout)
    assert again["already_completed"] is True
    assert _record(tmp_path) == before, "a replayed complete must change nothing"
    assert _record(tmp_path)["completed"] == ["0.1"]


def test_completing_a_lesson_that_unlocks_a_skill_awards_the_badge_and_places_homework(
    clean_dir: Path, tmp_path: Path
) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # 0.1, no badge

    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    outcome = json.loads(run(["complete", "--course", str(clean_dir)], tmp_path).stdout)

    assert outcome["badges_awarded"] == ["alpha"]
    assert outcome["phase_completed"] == 0
    assert outcome["homework_placed"] is True

    record = _record(tmp_path)
    assert record["completed"] == ["0.1", "0.2"]
    assert record["skills_unlocked"] == ["alpha"]
    assert (tmp_path / "clean-course" / "homework" / "active.yaml").is_file()


# ----------------------------------------------------------------------------------- ceremony


def test_ceremony_refuses_when_not_at_a_phase_boundary(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # completes 0.1: not phase-final

    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "not-a-phase-boundary"


def test_ceremony_refuses_before_anything_has_completed(clean_dir: Path, tmp_path: Path) -> None:
    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "not-a-phase-boundary"


def test_ceremony_reports_the_finished_phase(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # 0.1
    _walk_to_complete(clean_dir, tmp_path, LESSON_WITH_EXERCISE)
    run(["complete", "--course", str(clean_dir)], tmp_path)  # 0.2, phase-final

    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["beat"]["name"] == "ceremony"
    assert body["beat"]["content"]["phase_number"] == 0
    assert body["beat"]["content"]["coordinate"] == "0.2"
    assert body["beat"]["content"]["course_complete"] is False
    # The clean-course manifest declares no ceremony/brand block, so there is no copy to
    # invent — the verb must say so honestly rather than manufacture something.
    assert body["beat"]["content"]["share_text"] is None


def test_ceremony_knows_when_the_whole_course_is_done(clean_dir: Path, tmp_path: Path) -> None:
    for inputs in [LESSON_WITH_EXERCISE, LESSON_WITH_EXERCISE, LESSON_WITHOUT_EXERCISE]:
        _walk_to_complete(clean_dir, tmp_path, inputs)
        run(["complete", "--course", str(clean_dir)], tmp_path)

    result = run(["ceremony", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["beat"]["content"]["course_complete"] is True


# ------------------------------------------------------------------------------- version guard


def test_a_course_version_mismatch_is_refused(clean_dir: Path, tmp_path: Path) -> None:
    run(["next", "--course", str(clean_dir)], tmp_path)  # creates the record at 1.0.0

    manifest = clean_dir / "course.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace('version: "1.0.0"', 'version: "2.0.0"'),
        encoding="utf-8",
    )

    result = run(["next", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 5
    assert json.loads(result.stdout)["error"]["code"] == "version-mismatch"


# ------------------------------------------------------------------- state-root resolution
#
# The defect this closes: every verb here used a bare cwd-relative ".skilling" default while
# ``courses`` (_courses.py) resolved to ~/.skilling/state — two conventions for the same
# thing. ``resolve_state_root`` (workspace/_resolve.py) is the one precedence every verb now
# shares: explicit --state, then $SKILLING_STATE_ROOT, then the enclosing workspace's own
# state, then the learner's home default.


def test_explicit_state_beats_env_and_workspace(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    save_workspace_manifest(workspace, WorkspaceManifest())
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("SKILLING_STATE_ROOT", str(tmp_path / "env-state"))
    explicit = tmp_path / "explicit-state"

    result = runner.invoke(
        app, ["next", "--course", str(clean_dir), "--state", str(explicit)], catch_exceptions=False
    )

    assert result.exit_code == 0
    assert (explicit / "clean-course" / "record.yaml").is_file()
    assert not (tmp_path / "env-state").exists()
    assert not workspace_state_root(workspace).exists()


def test_env_beats_the_enclosing_workspace(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    save_workspace_manifest(workspace, WorkspaceManifest())
    monkeypatch.chdir(workspace)
    env_state = tmp_path / "env-state"
    monkeypatch.setenv("SKILLING_STATE_ROOT", str(env_state))

    result = runner.invoke(app, ["next", "--course", str(clean_dir)], catch_exceptions=False)

    assert result.exit_code == 0
    assert (env_state / "clean-course" / "record.yaml").is_file()
    assert not workspace_state_root(workspace).exists()


def test_the_enclosing_workspace_beats_home(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    save_workspace_manifest(workspace, WorkspaceManifest())
    nested = workspace / "showcase" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)  # discovery walks up, so a verb run from anywhere inside works
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    result = runner.invoke(app, ["next", "--course", str(clean_dir)], catch_exceptions=False)

    assert result.exit_code == 0
    assert (workspace_state_root(workspace) / "clean-course" / "record.yaml").is_file()
    assert not (fake_home / ".skilling").exists()


def test_home_is_the_last_resort_outside_any_workspace(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression this issue closes: with nothing else set and no enclosing workspace, a
    verb must land on exactly ~/.skilling/state — the same default ``courses`` already used,
    now shared instead of split-brained."""
    _isolate(monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    result = runner.invoke(app, ["next", "--course", str(clean_dir)], catch_exceptions=False)

    assert result.exit_code == 0
    assert (fake_home / ".skilling" / "state" / "clean-course" / "record.yaml").is_file()


# --------------------------------------------------------------- --course by id, in a workspace


def test_course_ref_accepts_a_workspace_course_id(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    _add_to_workspace(workspace, clean_dir, "clean-course")
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["next", "--course", "clean-course"], catch_exceptions=False)

    assert result.exit_code == 0
    out = json.loads(result.stdout)
    assert out["course"] == {"id": "clean-course", "version": "1.0.0", "title": "Clean Course"}
    # No --state either: this also proves the workspace's own state was used.
    assert (workspace_state_root(workspace) / "clean-course" / "record.yaml").is_file()


def test_course_ref_an_id_the_workspace_never_added_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    save_workspace_manifest(workspace, WorkspaceManifest())  # a workspace, but empty
    monkeypatch.chdir(workspace)

    result = run(["next", "--course", "never-added"], tmp_path / "state")

    assert result.exit_code == 2
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "course-not-found"


def test_course_ref_an_id_outside_any_workspace_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate(monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    result = run(["next", "--course", "no-such-course"], tmp_path / "state")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "course-not-found"


def test_course_ref_an_existing_directory_is_still_tried_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ref that is *both* a real directory relative to cwd *and* a course id the enclosing
    workspace's manifest happens to know must resolve as the directory, exactly as it always
    has — id resolution is only the fallback for a ref that is not a directory."""
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    fx.build(workspace / "clean-course")  # a real course directory, named like an id
    save_workspace_manifest(
        workspace,
        WorkspaceManifest(
            courses=[
                WorkspaceCourse(
                    id="clean-course",
                    version="9.9.9",
                    ref="local",
                    path="courses/does-not-exist@9.9.9",  # would fail to load if consulted
                    showcase="showcase/clean-course",
                    added_at=datetime.now(UTC),
                )
            ]
        ),
    )
    monkeypatch.chdir(workspace)

    result = runner.invoke(
        app,
        ["next", "--course", "clean-course", "--state", str(tmp_path / "state")],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["course"]["id"] == "clean-course"


@pytest.mark.parametrize("damage", ["missing", "corrupt", "wrong-id", "wrong-version"])
def test_unusable_workspace_course_is_not_found_and_never_uses_cache(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    content = _add_to_workspace(workspace, clean_dir, "clean-course")
    if damage == "missing":
        shutil.rmtree(content)
    elif damage == "corrupt":
        (content / "course.yaml").write_text("[broken", encoding="utf-8")
    elif damage == "wrong-id":
        fx.edit(content, fx.MANIFEST_PATH, "id: clean-course", "id: other-course")
    else:
        fx.edit(content, fx.MANIFEST_PATH, 'version: "1.0.0"', 'version: "2.0.0"')
    cache = tmp_path / "cache"
    fx.build(cache / "clean-course@1.0.0")
    monkeypatch.setenv("SKILLING_CACHE_DIR", str(cache))
    monkeypatch.chdir(workspace)

    result = runner.invoke(app, ["next", "--course", "clean-course"], catch_exceptions=False)

    assert result.exit_code == 2
    body = json.loads(result.stdout)
    assert body["error"]["code"] == "course-not-found"
    assert "usable" in body["error"]["message"]
    assert not workspace_state_root(workspace).exists()


@pytest.mark.parametrize("recovery", ["flag", "environment"])
def test_legacy_state_requires_explicit_recovery_and_is_not_migrated(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recovery: str
) -> None:
    _isolate(monkeypatch)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    legacy = tmp_path / ".skilling"
    result = run(["next", "--course", str(clean_dir)], legacy)
    assert result.exit_code == 0
    record_path = legacy / "clean-course" / "record.yaml"
    before = record_path.read_bytes()

    default = runner.invoke(app, ["courses"], catch_exceptions=False)
    assert json.loads(default.stdout)["courses"] == []
    if recovery == "flag":
        args = ["courses", "--state", str(legacy)]
    else:
        monkeypatch.setenv("SKILLING_STATE_ROOT", str(legacy))
        args = ["courses"]
    restored = runner.invoke(app, args, catch_exceptions=False)
    assert [row["id"] for row in json.loads(restored.stdout)["courses"]] == ["clean-course"]
    assert record_path.read_bytes() == before
    assert not fake_home.exists()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("corruption", ["traversal", "lesson", "yaml", "unicode"])
def test_invalid_course_cannot_create_state(
    clean_dir: Path, tmp_path: Path, corruption: str, existing: bool
) -> None:
    from skilling.conformance import Code

    from .corruptions import CORRUPTIONS

    manifest_path = clean_dir / "course.yaml"
    if corruption == "traversal":
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["id"] = "../escaped"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    elif corruption == "lesson":
        CORRUPTIONS[Code.QUIZ_WRONG_QUESTION_COUNT](clean_dir)
    elif corruption == "yaml":
        manifest_path.write_text("id: [unfinished", encoding="utf-8")
    else:
        manifest_path.write_bytes(b"\xff")
    from .test_state_paths import snapshot
    from .test_store import a_record

    state = tmp_path / "state"
    if existing:
        FileProgressStore(state).put_record(a_record(), None)
    (tmp_path / "sentinel").write_bytes(b"preserve outside state")
    before = snapshot(tmp_path)
    result = runner.invoke(app, ["next", "--course", str(clean_dir), "--state", str(state)])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "course-invalid"
    assert snapshot(tmp_path) == before
    assert state.exists() == existing
    assert not (tmp_path / "escaped").exists()


def test_warning_only_course_can_open_a_session(clean_dir: Path, tmp_path: Path) -> None:
    from skilling.conformance import Code

    from .corruptions import CORRUPTIONS

    CORRUPTIONS[Code.NEXT_UP_TOO_LONG](clean_dir)
    result = run(["next", "--course", str(clean_dir)], tmp_path / "state")
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("leaf", ["record.yaml", "scratch.yaml", "homework"])
def test_session_preflight_prevents_first_use_writes(
    clean_dir: Path,
    tmp_path: Path,
    leaf: str,
) -> None:
    from .test_state_paths import directory_alias, file_alias, snapshot

    state = tmp_path / "state"
    course_state = state / "clean-course"
    course_state.mkdir(parents=True)
    target = tmp_path / "target"
    if leaf == "homework":
        target.mkdir()
        directory_alias(course_state / leaf, target)
    else:
        target.write_bytes(b"outside sentinel")
        file_alias(course_state / leaf, target)
    before = snapshot(tmp_path)
    result = runner.invoke(app, ["next", "--course", str(clean_dir), "--state", str(state)])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "state-invalid"
    assert snapshot(tmp_path) == before


def test_console_entrypoint_controls_late_state_errors(clean_dir: Path, tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    injection = tmp_path / "injection"
    injection.mkdir()
    (injection / "sitecustomize.py").write_text(
        "from skilling.cli.runtime import _session\n"
        "from skilling.store import StatePathError\n"
        "def refuse(*args, **kwargs):\n"
        "    raise StatePathError('test late scratch refusal')\n"
        "_session.commit_runtime = refuse\n",
        encoding="utf-8",
    )
    executable = Path(sys.executable).parent / ("skilling.exe" if os.name == "nt" else "skilling")
    result = subprocess.run(
        [
            str(executable),
            "advance",
            "--course",
            str(clean_dir),
            "--state",
            str(tmp_path / "state"),
            "--input",
            "next",
        ],
        env={**os.environ, "PYTHONPATH": str(injection)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["error"]["code"] == "state-invalid"
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("stage", ["validate", "load"])
def test_session_source_io_failures_are_controlled(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    from skilling.cli.runtime import _common
    from skilling.course import Course

    def unreadable(*args):
        raise PermissionError("source unreadable")

    if stage == "validate":
        monkeypatch.setattr(_common, "validate_course", unreadable)
    else:
        monkeypatch.setattr(Course, "load", unreadable)
    result = runner.invoke(
        app, ["next", "--course", str(clean_dir), "--state", str(tmp_path / "state")]
    )
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "course-invalid"
    assert not (tmp_path / "state").exists()


def test_scratch_save_rechecks_its_path(clean_dir: Path, tmp_path: Path) -> None:
    from skilling.cli.runtime._common import Scratch, open_session, save_scratch
    from skilling.store import StatePathError

    from .test_state_paths import file_alias, snapshot

    state = tmp_path / "state"
    session = open_session(str(clean_dir), state, "local")
    target = tmp_path / "outside"
    target.write_bytes(b"untouched")
    file_alias(state / "clean-course" / "scratch.yaml", target)
    before = snapshot(tmp_path)
    with pytest.raises(StatePathError):
        save_scratch(session, Scratch(wrong_count=1), session.revision or "")
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("command", ["next", "courses"])
def test_state_root_construction_refusal_is_controlled(
    clean_dir: Path,
    tmp_path: Path,
    command: str,
) -> None:
    from .test_state_paths import file_alias

    root = tmp_path / "root"
    file_alias(root, root)
    args = [command, "--state", str(root)]
    if command == "next":
        args += ["--course", str(clean_dir)]
    result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "state-invalid"
