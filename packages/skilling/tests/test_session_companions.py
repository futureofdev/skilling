"""Paired producer/CLI companion writes and refusal probes; all learner work is synthetic."""

from __future__ import annotations

import dataclasses
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Capability, Course, Record
from skilling.delivery import ObjectiveRefusal, ObjectiveSettlementError, settle_objective
from skilling.session import FileSession, SessionRefusal, load_course
from skilling.store import Conflict, FileProgressStore, InvalidSubmissionToken, SubmissionToken
from skilling.workspace import WorkspaceManifest, save_manifest

from .conftest import REPO_ROOT
from .test_state_paths import directory_alias

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)
runner = CliRunner()


def data(view: object) -> dict:
    assert dataclasses.is_dataclass(view) and not isinstance(view, type)
    return json.loads(
        json.dumps(
            dataclasses.asdict(view),
            default=lambda value: (
                value.isoformat().replace("+00:00", "Z")
                if isinstance(value, (date, datetime))
                else str(value)
            ),
        )
    )


def state_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and p.name != ".skilling.lock"
    }


def finish(service: FileSession) -> None:
    for _ in range(20):
        view = service.snapshot()
        if view.beat.name == "complete":
            return
        given = {
            "gate-concept": "proceed",
            "gate-exercise": "attempted",
            "quiz": "answer-correct",
        }.get(view.beat.name, "next")
        service.advance(given)
    raise AssertionError("fixture lesson did not reach completion")


def test_paired_completion_queue_ceremony_submission_progress_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("skilling.course._clock.utc_now", lambda: NOW)
    monkeypatch.setenv("SKILLING_NOW", NOW.isoformat())
    api_root, cli_root = tmp_path / "api", tmp_path / "cli"
    for root in (api_root, cli_root):
        save_manifest(root, WorkspaceManifest())
        shutil.copytree(REPO_ROOT / "examples/workbench", root / "course")
    api_state, cli_state = api_root / ".skilling/state", cli_root / ".skilling/state"
    service = FileSession.open(
        load_course(api_root / "course"),
        state_root=api_state,
        learner_id="local",
        workspace_root=api_root,
        now=NOW,
    )

    def cli(*args: str) -> dict:
        monkeypatch.chdir(cli_root)
        result = runner.invoke(
            app,
            [*args, "--course", str(cli_root / "course"), "--state", str(cli_state)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    def same() -> None:
        assert state_bytes(api_state) == state_bytes(cli_state)

    cli("next")
    same()
    for number in range(4):
        while service.snapshot().beat.name != "complete":
            view = service.snapshot()
            given = {
                "gate-concept": "proceed",
                "gate-exercise": "attempted",
                "quiz": "answer-correct",
            }.get(view.beat.name, "next")
            service.advance(given)
            cli("advance", "--input", given)
        result = service.complete(service.snapshot().revision)
        out = cli("complete")
        for key in (
            "already_completed",
            "badges_awarded",
            "phase_completed",
            "homework_placed",
            "homework_queued",
        ):
            assert out[key] == data(result)[key]
        same()
        before = state_bytes(api_state)
        assert service.complete(service.snapshot().revision).already_completed
        assert cli("complete")["already_completed"]
        assert state_bytes(api_state) == before
        same()
        if number in (1, 3):
            ceremony = service.ceremony()
            actual = cli("ceremony")["beat"]["content"]
            expected = data(ceremony)
            expected.pop("snapshot")
            assert actual == expected
            for root in (api_root, cli_root):
                (root / "note.md").write_text("Synthetic learner artifact\n")
            artifact = service.artifact_add(
                Path("note.md"),
                "Note",
                workspace_root=api_root,
                path_base=api_root,
                expected_revision=service.snapshot().revision,
            )
            out = cli("artifact", "add", "note.md", "--title", "Note")
            assert out["artifact"] == data(artifact.artifact)
            same()
    progress = data(service.progress())
    progress["course"].pop("title")
    assert cli("progress") == {"ok": True, "verb": "progress", **progress}
    assert cli("artifact", "list")["artifacts"] == [data(a) for a in service.artifacts()]
    assert (
        yaml.safe_load((api_state / "workbench/record.yaml").read_bytes())["objectives_met"] == []
    )
    assert service.snapshot().completed_count == 4  # no objective or artifact gate
    before = state_bytes(api_state)
    checked = service.homework_check()
    out = cli("homework", "check")
    assert checked.active is not None and len(checked.active.queued) == 1
    assert out["submission_token"] == checked.submission_token
    assert out["revision"] == checked.revision
    active = data(checked.active)
    for queued in active["queued"]:
        queued.pop("queued")
    assert out["active"] == active
    assert state_bytes(api_state) == before
    same()
    token = checked.submission_token
    assert token is not None
    archived = service.homework_submit(token)
    expected = data(archived)
    expected.pop("course")
    assert cli("homework", "submit", "--token", token)["archived"] == expected
    same()
    next_assignment = service.homework_check()
    assert next_assignment.active is not None and next_assignment.active.coordinate == "2.2"
    before = state_bytes(api_state)
    assert service.homework_submit(token) == archived
    assert cli("homework", "submit", "--token", token)["archived"] == expected
    assert state_bytes(api_state) == before  # replay never consumes the successor
    same()
    monkeypatch.setattr("skilling.delivery._runtime.new_anonymous_id", lambda: "paired-id")
    for value, action in ((None, "ask"), (True, "on"), (False, "off"), (True, "on")):
        telemetry = service.telemetry(value)
        out = cli("telemetry", action)
        assert out["opt_in"] == telemetry.opt_in and out["revision"] == telemetry.revision
        if value is not None:
            assert out["anonymous_id"] == telemetry.anonymous_id == "paired-id"
        same()


def test_noninitializing_homework_check_and_token_refusal(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "absent"
    service = FileSession.open(
        load_course(clean_dir), state_root=state, learner_id="local", initialize=False
    )
    assert service.homework_check().submission_token is None
    assert not state.exists()
    with pytest.raises(InvalidSubmissionToken):
        service.homework_submit("malformed")
    assert not state.exists()

    from skilling.course import HomeworkSlot, Requirement

    other = SubmissionToken.for_slot(
        "other",
        service.course.id,
        service.course.version,
        HomeworkSlot(
            coordinate="1.1",
            title="Other",
            objective="Other",
            requirements=[Requirement(text="Other")],
            submission="Submit",
            unlocked_at=NOW,
        ),
        "revision",
    ).encode()
    with pytest.raises(InvalidSubmissionToken):
        service.homework_submit(other)
    assert not state.exists()


def test_objective_refusals_evidence_and_stale_cas_match_cli(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from .test_cli_objectives import PRACTICE_OBJECTIVE_WITH_CHECK, _install

    _install(clean_dir, PRACTICE_OBJECTIVE_WITH_CHECK)
    course_path = clean_dir
    course = load_course(course_path)
    api_state, cli_state = tmp_path / "api", tmp_path / "cli"
    monkeypatch.setattr("skilling.course._clock.utc_now", lambda: NOW)
    monkeypatch.setenv("SKILLING_NOW", NOW.isoformat())
    service = FileSession.open(course, state_root=api_state, learner_id="local", now=NOW)
    runner.invoke(
        app,
        ["next", "--course", str(course_path), "--state", str(cli_state)],
        catch_exceptions=False,
    )
    objective = service.objectives((Capability.OBSERVE,))[0]
    for oid, caps, checked, host, code in (
        ("unknown", (Capability.OBSERVE,), None, None, "objective-unknown"),
        (objective.id, (Capability.CONVERSE,), "actual", "host", "capability-missing"),
        (objective.id, (Capability.OBSERVE,), None, None, "missing-provenance"),
    ):
        before = state_bytes(api_state)
        with pytest.raises(SessionRefusal) as refusal:
            service.settle_objective(oid, caps, checked=checked, attested_by=host)
        assert refusal.value.code == code
        assert state_bytes(api_state) == before
        args = [
            "objective",
            "settle",
            oid,
            "--evidence",
            "observed",
            "--course",
            str(course_path),
            "--state",
            str(cli_state),
        ]
        for cap in caps:
            args.extend(["--capability", str(cap)])
        if checked:
            args.extend(["--checked", checked, "--attested-by", host or ""])
        result = runner.invoke(app, args, catch_exceptions=False)
        assert json.loads(result.stdout)["error"]["code"] == code
        assert state_bytes(api_state) == state_bytes(cli_state)
    captured = service.snapshot().revision
    result = service.settle_objective(
        objective.id,
        (Capability.OBSERVE,),
        checked="actual file inspected",
        attested_by="fixture",
        expected_revision=captured,
    )
    args = [
        "objective",
        "settle",
        objective.id,
        "--evidence",
        "observed",
        "--capability",
        "observe",
        "--checked",
        "actual file inspected",
        "--attested-by",
        "fixture",
        "--course",
        str(course_path),
        "--state",
        str(cli_state),
    ]
    out = json.loads(runner.invoke(app, args, catch_exceptions=False).stdout)
    assert out["objective"]["provenance"] == data(result.provenance)
    assert state_bytes(api_state) == state_bytes(cli_state)
    before = state_bytes(api_state)
    assert not service.settle_objective(
        objective.id, (Capability.OBSERVE,), checked="same", attested_by="fixture"
    ).newly_met
    assert state_bytes(api_state) == before
    with pytest.raises(Conflict):
        service.settle_objective(
            objective.id,
            (Capability.OBSERVE,),
            checked="same",
            attested_by="fixture",
            expected_revision=captured,
        )
    assert state_bytes(api_state) == before


def test_typed_delivery_error_preserves_value_error(clean_dir: Path, tmp_path: Path) -> None:
    course = Course.load(clean_dir)
    store = FileProgressStore(tmp_path / "state")
    record = Record.new(course, "local")
    revision = store.put_record(record, None)
    with pytest.raises(ObjectiveSettlementError) as error:
        settle_objective(store, record, revision, course.first_lesson, "unknown", ())
    assert isinstance(error.value, ValueError)
    assert error.value.reason is ObjectiveRefusal.UNKNOWN


def test_artifact_refusals_chronology_stale_and_relocation(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copytree(clean_dir, workspace / "course")
    state = workspace / "state"
    service = FileSession.open(
        load_course(workspace / "course"), state_root=state, learner_id="local", now=NOW
    )
    finish(service)
    service.complete(service.snapshot().revision)
    target = workspace / "note.md"
    target.write_text("fixture\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("outside\n")
    directory_alias(workspace / "alias", outside)
    for path, code in (
        (Path("missing"), "artifact-missing"),
        (outside / "note.md", "artifact-outside-workspace"),
        (Path("alias/note.md"), "artifact-outside-workspace"),
    ):
        before = state_bytes(state)
        with pytest.raises(SessionRefusal) as error:
            service.artifact_add(path, "Note", workspace_root=workspace, path_base=workspace)
        assert error.value.code == code
        assert state_bytes(state) == before
    with pytest.raises(SessionRefusal) as error:
        service.artifact_add(
            target, "Note", workspace_root=workspace, path_base=workspace, coordinate="1.1"
        )
    assert error.value.code == "chronology-invalid"
    captured = service.snapshot().revision
    service.artifact_add(target, "Note", workspace_root=workspace, path_base=workspace)
    before = state_bytes(state)
    with pytest.raises(Conflict):
        service.artifact_add(
            target,
            "Updated",
            workspace_root=workspace,
            path_base=workspace,
            expected_revision=captured,
        )
    assert state_bytes(state) == before
    # Move a stopped writer; pointers and progress use the explicit new roots without cwd discovery.
    moved = tmp_path / "moved"
    workspace.rename(moved)
    monkeypatch.chdir(tmp_path)
    reopened = FileSession.open(
        load_course(moved / "course"), state_root=moved / "state", learner_id="local"
    )
    assert reopened.artifacts()[0].path == "note.md"
    assert reopened.progress().completed == ("0.1",)
    assert (
        reopened.artifact_add(
            Path("note.md"), "Moved", workspace_root=moved, path_base=moved
        ).artifact.path
        == "note.md"
    )


def test_practice_without_verify_refuses_without_mutation(clean_dir: Path, tmp_path: Path) -> None:
    from .test_cli_objectives import PRACTICE_OBJECTIVE_WITHOUT_VERIFY, _install

    _install(clean_dir, PRACTICE_OBJECTIVE_WITHOUT_VERIFY)
    state = tmp_path / "state"
    service = FileSession.open(load_course(clean_dir), state_root=state, learner_id="local")
    before = state_bytes(state)
    with pytest.raises(SessionRefusal) as error:
        service.settle_objective(
            "obj-id", (Capability.OBSERVE,), checked="actual observation", attested_by="fixture"
        )
    assert error.value.code == "no-verify"
    assert state_bytes(state) == before
    result = runner.invoke(
        app,
        [
            "objective",
            "settle",
            "obj-id",
            "--evidence",
            "observed",
            "--capability",
            "observe",
            "--checked",
            "actual observation",
            "--attested-by",
            "fixture",
            "--course",
            str(clean_dir),
            "--state",
            str(state),
        ],
        catch_exceptions=False,
    )
    assert json.loads(result.stdout)["error"]["code"] == "no-verify"
    assert state_bytes(state) == before


def test_noninitializing_companion_writes_refuse_before_creation(tmp_path: Path) -> None:
    course = load_course(REPO_ROOT / "examples/welcome-skilling")
    state = tmp_path / "absent"
    service = FileSession.open(course, state_root=state, learner_id="local", initialize=False)
    objective = next(o for o in service.objectives((Capability.CONVERSE,)) if o.settleable_now)
    assert service.telemetry().opt_in is None
    assert service.progress().revision is None
    assert not state.exists()
    for choice in (True, False):
        with pytest.raises(SessionRefusal) as error:
            service.telemetry(choice)
        assert error.value.code == "record-missing"
        assert not state.exists()
    with pytest.raises(SessionRefusal) as error:
        service.settle_objective(objective.id, (Capability.CONVERSE,))
    assert error.value.code == "record-missing"
    assert not state.exists()
