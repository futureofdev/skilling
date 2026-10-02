"""Actual process death and competing native writers for file-only public actions."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from skilling.course import parse_lesson, parse_quiz
from skilling.session import (
    ActionOperation,
    FileSession,
    QuizAnswerOutcome,
    TrustedAction,
    load_course,
)

from .conftest import REPO_ROOT
from .test_session_actions import answer_action, at_quiz, service
from .test_transition_recovery import BOUNDARIES, bytes_at, environment, invoke, worker


def action_file(root: Path, action: TrustedAction, name: str = "action.json") -> Path:
    path = root / name
    path.write_text(json.dumps(asdict(action)))
    return path


def fault_process(command: list[str], marker: Path, fault: str) -> None:
    if fault != "hold":
        result = invoke(command)
        assert result.returncode != 0, result.stdout
        return
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
    finally:
        process.kill()
        process.communicate(timeout=10)


@pytest.mark.parametrize("boundary", BOUNDARIES)
@pytest.mark.parametrize("fault", ["exit", "hold"])
@pytest.mark.parametrize("final,correct", [(False, True), (False, False), (True, True)])
def test_answer_process_death_keeps_original_feedback(
    clean_dir: Path,
    tmp_path: Path,
    boundary: str,
    fault: str,
    final: bool,
    correct: bool,
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    if final:
        quiz = parse_lesson(load_course(clean_dir).first_lesson.path).section("quiz")
        assert quiz is not None
        final_number = parse_quiz(quiz.body, quiz.body_line)[-1].number
        while session.question().number < final_number:
            session.answer(answer_action(session, clean_dir, "unused").payload)
    captured = answer_action(session, clean_dir, "process-once", correct=correct)
    marker = tmp_path / "marker"
    fault_process(
        worker(
            clean_dir,
            state,
            "trusted",
            action_file=str(action_file(tmp_path, captured)),
            fault=fault,
            boundary=boundary,
            marker=str(marker),
        ),
        marker,
        fault,
    )
    del session
    pending = FileSession.pending_feedback_at(
        state_root=state, learner_id="local", course_id="clean-course"
    )
    assert pending is not None and pending.outcome.correct is correct
    session = service(clean_dir, state)
    before = bytes_at(state)
    replay = session.act(captured)
    assert replay.replayed and replay.original_outcome == pending.outcome
    assert isinstance(replay.original_outcome, QuizAnswerOutcome)
    assert replay.snapshot.pending_feedback == pending.outcome
    assert bytes_at(state) == before
    assert len(list((state / "clean-course/transition-receipts").glob("*.yaml"))) == 1
    session.acknowledge_feedback(pending.feedback_id, pending.revision)
    if final:
        result = session.complete(session.snapshot().revision)
        assert session.complete(result.snapshot.revision).already_completed
        assert result.snapshot.completed_count == 1
        before = bytes_at(state)
        replay = session.act(captured)
        assert replay.replayed and replay.original_outcome == pending.outcome
        assert replay.snapshot.completed_count == 1 and replay.snapshot.pending_feedback is None
        assert bytes_at(state) == before


@pytest.mark.parametrize("boundary", ["prepared", "scratch", "committed"])
@pytest.mark.parametrize("fault", ["exit", "hold"])
def test_ack_process_death_changes_no_learner_record_or_log(
    clean_dir: Path,
    tmp_path: Path,
    boundary: str,
    fault: str,
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    session.act(answer_action(session, clean_dir, "answer"))
    pending = session.pending_feedback()
    assert pending is not None
    before = bytes_at(state)
    marker = tmp_path / "marker"
    fault_process(
        worker(clean_dir, state, "ack", fault=fault, boundary=boundary, marker=str(marker)),
        marker,
        fault,
    )
    assert (
        FileSession.pending_feedback_at(
            state_root=state, learner_id="local", course_id="clean-course"
        )
        is None
    )
    after = bytes_at(state)
    for name in before:
        if name not in ("clean-course/scratch.yaml", "clean-course/transition.yaml"):
            assert after[name] == before[name]
    assert session.question().number == 2


@pytest.mark.parametrize("same_identity", [False, True])
def test_two_writers_one_revision_one_answer(
    clean_dir: Path,
    tmp_path: Path,
    same_identity: bool,
) -> None:
    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    first = answer_action(session, clean_dir, "first")
    second = first if same_identity else replace(first, event_id="second")
    release = tmp_path / "release"
    processes = []
    ready_paths = []
    try:
        for number, action in enumerate((first, second)):
            ready = tmp_path / f"ready-{number}"
            ready_paths.append(ready)
            processes.append(
                subprocess.Popen(
                    worker(
                        clean_dir,
                        state,
                        "trusted",
                        action_file=str(action_file(tmp_path, action, f"{number}.json")),
                        ready=str(ready),
                        release=str(release),
                    ),
                    cwd=REPO_ROOT,
                    env=environment(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        deadline = time.monotonic() + 15
        while not all(p.exists() for p in ready_paths) and time.monotonic() < deadline:
            assert all(p.poll() is None for p in processes)
            time.sleep(0.02)
        assert all(p.exists() for p in ready_paths)
        release.write_text("go")
        outputs = [p.communicate(timeout=20) for p in processes]
        assert sum(p.returncode == 0 for p in processes) == (2 if same_identity else 1), outputs
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    pending = session.pending_feedback()
    assert pending is not None
    assert session.snapshot().position.question_index == 1
    assert len(list((state / "clean-course/transition-receipts").glob("*.yaml"))) == 1


@pytest.mark.parametrize("damage", ["version", "outcome", "pointer", "revision", "path"])
def test_corrupt_v2_prepared_metadata_refuses_before_recovery_writes(
    clean_dir: Path,
    tmp_path: Path,
    damage: str,
) -> None:
    import yaml

    from skilling.store import RecoveryRequired

    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    captured = answer_action(session, clean_dir, "prepared")
    result = invoke(
        worker(
            clean_dir,
            state,
            "trusted",
            action_file=str(action_file(tmp_path, captured)),
            fault="exit",
            boundary="prepared",
        )
    )
    assert result.returncode == 73
    path = state / "clean-course/transition.yaml"
    data = yaml.safe_load(path.read_bytes())
    if damage == "version":
        data["version"] = 99
    if damage == "outcome":
        del data["receipt"]["outcome"]
    if damage == "revision":
        data["identity"]["expected_revision"] = "0" * 16
    if damage == "path":
        data["receipt_path"] = "../../outside.yaml"
    if damage == "pointer":
        scratch = yaml.safe_load(data["scratch_after"])
        scratch["pending_feedback"]["answer_key"] = "0" * 64
        data["scratch_after"] = yaml.safe_dump(scratch).encode()
    path.write_text(yaml.safe_dump(data))
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired):
        FileSession.pending_feedback_at(
            state_root=state, learner_id="local", course_id="clean-course"
        )
    assert bytes_at(state) == before


@pytest.mark.parametrize("operation", ["advance", "answer", "acknowledge"])
def test_prepared_v2_same_model_changed_receipt_bytes_refuse_before_effects(
    clean_dir: Path, tmp_path: Path, operation: str
) -> None:
    import yaml

    from skilling.store import RecoveryRequired
    from skilling.store._journal import _transition

    state = tmp_path / "state"
    session = service(clean_dir, state)
    if operation == "advance":
        captured = TrustedAction.create(
            session.snapshot(),
            event_id="prepared",
            operation=ActionOperation.ADVANCE,
            payload="next",
        )
    else:
        at_quiz(session)
        captured = answer_action(session, clean_dir, "prepared")
    if operation == "acknowledge":
        session.act(captured)
        command = worker(clean_dir, state, "ack", fault="exit", boundary="prepared")
    else:
        command = worker(
            clean_dir,
            state,
            "trusted",
            action_file=str(action_file(tmp_path, captured)),
            fault="exit",
            boundary="prepared",
        )
    result = invoke(command)
    assert result.returncode == 73
    intent = yaml.safe_load((state / "clean-course/transition.yaml").read_bytes())
    assert intent["kind"] == "prepared"
    if operation == "acknowledge":
        receipt = next((state / "clean-course/transition-receipts").glob("*.yaml"))
        canonical = receipt.read_bytes()
    else:
        receipt = state / "clean-course" / intent["receipt_path"]
        receipt.parent.mkdir(exist_ok=True)
        canonical = _transition.dump(intent["receipt"])
    altered = canonical + b"\n"
    assert yaml.safe_load(altered) == yaml.safe_load(canonical)
    receipt.write_bytes(altered)
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired):
        FileSession.pending_feedback_at(
            state_root=state, learner_id="local", course_id="clean-course"
        )
    assert bytes_at(state) == before
    assert (
        yaml.safe_load((state / "clean-course/transition.yaml").read_bytes())["kind"] == "prepared"
    )


@pytest.mark.parametrize(
    "case",
    [
        "legacy-advance",
        "trusted-advance",
        "next-answer",
        "ack-pending",
        "ack-presented",
        "legacy-after-presented",
        "trusted-after-presented",
    ],
)
def test_prepared_all_feedback_references_refuse_corruption_before_effects(
    clean_dir: Path, tmp_path: Path, case: str
) -> None:
    import yaml

    from skilling.store import RecoveryRequired

    state = tmp_path / "state"
    session = service(clean_dir, state)
    at_quiz(session)
    after_advance = "advance" in case or "after-presented" in case
    session.act(answer_action(session, clean_dir, "first", correct=not after_advance))
    first = session.pending_feedback()
    assert first is not None
    session.acknowledge_feedback(first.feedback_id, first.revision)
    if case.startswith("ack-"):
        session.act(answer_action(session, clean_dir, "second"))
        command = worker(clean_dir, state, "ack", fault="exit", boundary="prepared")
    elif case.startswith("legacy-"):
        command = worker(
            clean_dir,
            state,
            "advance",
            input="continue",
            key="after-ack",
            fault="exit",
            boundary="prepared",
        )
    else:
        captured = (
            answer_action(session, clean_dir, "second")
            if case == "next-answer"
            else TrustedAction.create(
                session.snapshot(),
                event_id="after-ack",
                operation=ActionOperation.ADVANCE,
                payload="continue",
            )
        )
        command = worker(
            clean_dir,
            state,
            "trusted",
            action_file=str(action_file(tmp_path, captured)),
            fault="exit",
            boundary="prepared",
        )
    result = invoke(command)
    assert result.returncode == 73
    path = state / "clean-course/transition.yaml"
    intent = yaml.safe_load(path.read_bytes())
    before_scratch = yaml.safe_load(intent["scratch_before"])
    if "after-presented" in case:
        after_scratch = yaml.safe_load(intent["scratch_after"])
        after_scratch["presented_feedback"] = dict(before_scratch["presented_feedback"])
        after_scratch["presented_feedback"]["receipt_digest"] = "0" * 64
        intent["scratch_after"] = yaml.safe_dump(after_scratch).encode()
        path.write_text(yaml.safe_dump(intent))
    else:
        pointer = before_scratch[
            "pending_feedback" if case == "ack-pending" else "presented_feedback"
        ]
        receipt = next(
            p
            for p in (state / "clean-course/transition-receipts").glob("*.yaml")
            if yaml.safe_load(p.read_bytes())["identity"]["key"] == pointer["answer_key"]
        )
        canonical = receipt.read_bytes()
        assert yaml.safe_load(canonical + b"\n") == yaml.safe_load(canonical)
        receipt.write_bytes(canonical + b"\n")
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired):
        FileSession.pending_feedback_at(
            state_root=state, learner_id="local", course_id="clean-course"
        )
    assert bytes_at(state) == before
    assert yaml.safe_load(path.read_bytes())["kind"] == "prepared"
