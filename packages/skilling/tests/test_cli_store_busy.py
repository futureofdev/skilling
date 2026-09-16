"""Actual console entrypoint errors; CliRunner(app) bypasses this boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skilling.store import FileProgressStore, _file

from .test_store import COURSE, a_record


def _environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in {"SKILLING_WORKSPACE", "SKILLING_STATE_ROOT"}
    }


@pytest.mark.parametrize("verb", ["next", "progress"])
def test_main_reports_real_lock_timeout(clean_dir: Path, tmp_path: Path, verb: str) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    before = {p: p.read_bytes() for p in store.state_root.rglob("*") if p.is_file()}
    assert _file.DEFAULT_LOCK_TIMEOUT == 30.0
    launcher = (
        "from skilling.store import _file; _file.DEFAULT_LOCK_TIMEOUT = 0.1; "
        "from skilling.cli import main; main()"
    )
    with store._locked_course(COURSE):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                launcher,
                verb,
                "--course",
                str(clean_dir),
                "--state",
                str(store.state_root),
            ],
            cwd=tmp_path,
            env=_environment(),
            capture_output=True,
            text=True,
            timeout=15,
        )
    assert result.returncode == 1, result.stderr
    assert len(result.stdout.splitlines()) == 1
    body = json.loads(result.stdout)
    assert body["ok"] is False and body["error"]["code"] == "store-busy"
    assert str(store.course_dir(COURSE)) in body["error"]["message"]
    assert "Traceback" not in result.stderr
    assert {p: p.read_bytes() for p in store.state_root.rglob("*") if p.is_file()} == before


def test_main_preserves_real_stale_revision_conflict(clean_dir: Path, tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    launcher = """
from skilling.store import FileProgressStore
from skilling.cli import main
original = FileProgressStore.commit_transition
def competing_write(self, commit):
    peer = commit.record.model_copy(update={"skills_unlocked": ["peer"]})
    self.put_record(peer, commit.expected_record_revision)
    return original(self, commit)
FileProgressStore.commit_transition = competing_write
main()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            launcher,
            "advance",
            "--input",
            "next",
            "--course",
            str(clean_dir),
            "--state",
            str(store.state_root),
        ],
        cwd=tmp_path,
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 3, result.stderr
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["error"]["code"] == "conflict"
    assert "Traceback" not in result.stderr
    found = store.get_record("local", COURSE)
    assert found is not None and found[0].skills_unlocked == ["peer"]
