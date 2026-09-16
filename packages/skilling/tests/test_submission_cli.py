"""Token/confirmation boundary tests; scripted input is synthetic, never host evidence."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from skilling.cli import app
from skilling.cli.learning._walk import LearnerLeft, Walker
from skilling.course import Course
from skilling.delivery import complete_lesson, submit_homework
from skilling.store import (
    Conflict,
    FileProgressStore,
    InvalidSubmissionToken,
    NotSupported,
    RecoveryRequired,
    SubmissionToken,
)

from .test_submission_recovery import NOW, commit_for, invoke, seed, submit, token_for, worker
from .test_submission_recovery import workbench as workbench
from .test_transition_recovery import bytes_at

runner = CliRunner()


def run(course: Course, root: Path, *args: str):
    return runner.invoke(
        app,
        ["homework", *args, "--course", str(course.root), "--state", str(root)],
        catch_exceptions=False,
    )


@pytest.mark.parametrize("token", (None, "", "bad", "s2.abc", "s1.e30"))
def test_missing_or_malformed_token_never_initializes_state(
    tmp_path: Path, workbench: Course, token: str | None
) -> None:
    root = tmp_path / "absent"
    args = ["submit"] + (["--token", token] if token is not None else [])
    got = run(workbench, root, *args)
    assert got.exit_code == 2, got.output
    assert json.loads(got.stdout)["error"]["code"] == "invalid-submission-token"
    assert not root.exists()


def test_check_is_read_only_and_empty_token_is_null(tmp_path: Path, workbench: Course) -> None:
    root = tmp_path / "absent"
    got = run(workbench, root, "check")
    assert got.exit_code == 0, got.output
    out = json.loads(got.stdout)
    assert out["active"] is out["revision"] is out["submission_token"] is None
    assert not root.exists()
    seed(root, workbench)
    before = bytes_at(root)
    a = run(workbench, root, "check")
    b = run(workbench, root, "check")
    assert a.stdout == b.stdout and a.exit_code == b.exit_code == 0
    token = SubmissionToken.parse(json.loads(a.stdout)["submission_token"])
    assert token.slot_revision == json.loads(a.stdout)["revision"]
    assert bytes_at(root) == before


@pytest.mark.parametrize("field", ("learner_id", "course_id", "course_version"))
def test_wrong_stream_token_cannot_recover_pending_state(
    tmp_path: Path, workbench: Course, field: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    original = token_for(store, workbench)
    assert (
        invoke(
            worker(
                workbench,
                store.state_root,
                token=original,
                now=NOW.isoformat(),
                fault="exit",
                boundary="prepared",
            )
        ).returncode
        == 73
    )
    token = replace(
        SubmissionToken.parse(original),
        **{field: "9.0.0" if field == "course_version" else "different"},
    ).encode()
    before = bytes_at(store.state_root)
    got = run(workbench, store.state_root, "submit", "--token", token)
    assert got.exit_code == 2, got.output
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize(
    "damage",
    ("padding", "version", "boolean-version", "missing-version", "extra", "instance", "coordinate"),
)
def test_token_requires_canonical_versioned_payload(
    tmp_path: Path, workbench: Course, damage: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    data = json.loads(base64.urlsafe_b64decode(token[3:] + "=" * (-len(token[3:]) % 4)))
    if damage == "padding":
        broken = token + "="
    else:
        if damage == "version":
            data["version"] = 2
        elif damage == "boolean-version":
            data["version"] = True
        elif damage == "missing-version":
            del data["version"]
        elif damage == "extra":
            data["extra"] = "ignored?"
        elif damage == "instance":
            data["instance_id"] = "short"
        else:
            data["coordinate"] = "../escape"
        broken = "s1." + base64.urlsafe_b64encode(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
    before = bytes_at(store.state_root)
    with pytest.raises(InvalidSubmissionToken):
        SubmissionToken.parse(broken)
    got = run(workbench, store.state_root, "submit", "--token", broken)
    assert got.exit_code == 2
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize("answers", ((False,), (True, False), (True, True), (True, None)))
def test_walker_waits_for_distinct_confirmation(
    tmp_path: Path,
    workbench: Course,
    monkeypatch: pytest.MonkeyPatch,
    answers: tuple[bool | None, ...],
) -> None:
    store = seed(tmp_path / "state", workbench)
    walk = Walker(workbench, store, learner_id="local", console=Console(file=io.StringIO()))
    found = store.get_record("local", workbench.id)
    assert found is not None
    walk.record, walk.revision = found
    before = bytes_at(store.state_root)
    supplied = iter(answers)
    questions: list[str] = []

    def confirm(question: str, *, default: bool = False) -> bool:
        questions.append(question)
        answer = next(supplied)
        if answer is None:
            raise LearnerLeft
        return answer

    monkeypatch.setattr(walk, "_confirm", confirm)
    if answers[-1] is None:
        with pytest.raises(LearnerLeft):
            walk._homework(now=NOW)
    else:
        walk._homework(now=NOW)
    assert len(questions) == len(answers)
    if answers == (True, True):
        assert len(store.get_homework_archive("local", workbench.id)) == 1
        assert store.get_homework("local", workbench.id) == (None, None)
    else:
        assert bytes_at(store.state_root) == before


def test_walker_uses_pre_confirmation_token_and_requires_new_check_on_conflict(
    tmp_path: Path, workbench: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = seed(tmp_path / "state", workbench)
    console = io.StringIO()
    walk = Walker(workbench, store, learner_id="local", console=Console(file=console))
    found = store.get_record("local", workbench.id)
    assert found is not None
    walk.record, walk.revision = found
    confirmations = 0
    changed: dict[str, bytes] = {}

    def confirm(question: str, *, default: bool = False) -> bool:
        nonlocal confirmations
        confirmations += 1
        if confirmations == 2:
            slot, revision = store.get_homework("local", workbench.id)
            assert slot
            slot.requirements[0].reason = "Changed during confirmation"
            store.put_homework("local", workbench.id, slot, revision)
            changed.update(bytes_at(store.state_root))
        return True

    monkeypatch.setattr(walk, "_confirm", confirm)
    walk._homework(now=NOW)
    assert confirmations == 2
    assert bytes_at(store.state_root) == changed
    assert "Check it again" in console.getvalue()


class CompletionOnlyBackend:
    """An older adapter with the old required methods and no new submission seam."""

    def __init__(self, store: FileProgressStore) -> None:
        self.store = store

    def __getattr__(self, name: str):
        if name in {"get_submission_receipt", "commit_submission"}:
            raise AttributeError(name)
        return getattr(self.store, name)


def test_older_backend_refuses_before_effects_and_names_missing_submission_methods(
    tmp_path: Path, workbench: Course
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    backend = CompletionOnlyBackend(store)
    before = bytes_at(store.state_root)
    with pytest.raises(NotSupported, match="get_submission_receipt, commit_submission"):
        submit_homework(backend, "local", workbench.id, "1.2", token=token)  # type: ignore[arg-type]
    found = store.get_record("local", workbench.id)
    assert found is not None
    record, revision = found
    lesson = workbench.lesson_at("1.1")
    assert lesson
    with pytest.raises(NotSupported, match="get_submission_receipt, commit_submission"):
        complete_lesson(backend, workbench, record, revision, lesson, now=NOW)  # type: ignore[arg-type]
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize("field", ("token", "coordinate", "instance_id", "archive"))
def test_runtime_rejects_incoherent_backend_replay(
    tmp_path: Path, workbench: Course, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    token = token_for(store, workbench)
    submit(store, workbench, token)
    receipt = store.get_submission_receipt("local", workbench.id, token)
    assert receipt
    value = (
        receipt.archive.model_copy(update={"coordinate": "2.2"}) if field == "archive" else "other"
    )
    malformed = replace(receipt, **{field: value})
    monkeypatch.setattr(store, "get_submission_receipt", lambda *args: malformed)
    before = bytes_at(store.state_root)
    with pytest.raises(RecoveryRequired):
        submit(store, workbench, token)
    assert bytes_at(store.state_root) == before


@pytest.mark.parametrize("route", ("runtime", "receipt", "commit"))
@pytest.mark.parametrize("field", ("learner_id", "course_id", "course_version"))
def test_public_api_wrong_stream_refuses_before_pending_recovery(
    tmp_path: Path, workbench: Course, route: str, field: str
) -> None:
    store = seed(tmp_path / "state", workbench)
    original = token_for(store, workbench)
    commit = commit_for(store, workbench, original)
    assert (
        invoke(
            worker(
                workbench,
                store.state_root,
                token=original,
                now=NOW.isoformat(),
                fault="exit",
                boundary="prepared",
            )
        ).returncode
        == 73
    )
    changed = "9.0.0" if field == "course_version" else "different"
    token = replace(SubmissionToken.parse(original), **{field: changed}).encode()
    before = bytes_at(store.state_root)
    with pytest.raises((InvalidSubmissionToken, Conflict)):
        if route == "runtime":
            submit(store, workbench, token)
        elif route == "receipt":
            store.get_submission_receipt("local", workbench.id, token)
        else:
            altered = replace(commit.receipt, token=token, **{field: changed})
            store.commit_submission(replace(commit, receipt=altered))
    assert bytes_at(store.state_root) == before


def test_direct_commit_with_absent_stream_does_not_create_state(
    tmp_path: Path, workbench: Course
) -> None:
    source = seed(tmp_path / "source", workbench)
    commit = commit_for(source, workbench, token_for(source, workbench))
    root = tmp_path / "absent"
    store = FileProgressStore(root)
    with pytest.raises(Conflict):
        store.commit_submission(commit)
    assert not root.exists()
