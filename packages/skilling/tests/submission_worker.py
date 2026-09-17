"""Synthetic subprocess submission faults at actual durable file boundaries."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

from skilling.cli import main
from skilling.store import FileProgressStore, SubmissionCommit, SubmissionCommitResult
from skilling.store._journal import _submission


def boundary_for(path: Path, data: bytes) -> str:
    if path.name == "submission.yaml":
        return yaml.safe_load(data)["kind"]
    if path.parent.name == "submission-receipts":
        return "receipt"
    if path.parent.name == "archive":
        return "archive"
    return "slot" if path.name == "active.yaml" else "other"


def main_worker() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("verb", choices=("submit", "inspect"))
    parser.add_argument("--course", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--token")
    parser.add_argument("--now")
    parser.add_argument("--fault", choices=("none", "error", "exit", "hold"), default="none")
    parser.add_argument("--boundary", default="archive")
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--release", type=Path)
    args = parser.parse_args()
    real_write, real_fsync = _submission._write_bytes_atomic, _submission._fsync_dir

    def interrupt(boundary: str) -> None:
        if args.fault == "none" or boundary != args.boundary:
            return
        if args.fault == "error":
            raise OSError("injected after durable " + boundary)
        if args.fault == "exit":
            os._exit(73)
        assert args.marker is not None
        args.marker.write_text("ready", encoding="utf-8")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(0.02)
        raise TimeoutError("parent did not terminate held worker")

    def write(path: Path, data: bytes) -> None:
        real_write(path, data)
        interrupt(boundary_for(path, data))

    def fsync(path: Path) -> None:
        real_fsync(path)
        interrupt("slot")  # deletion has no atomic-write boundary

    _submission._write_bytes_atomic, _submission._fsync_dir = write, fsync
    if args.ready is not None:
        real_commit = FileProgressStore.commit_submission

        def commit_at_barrier(
            self: FileProgressStore, commit: SubmissionCommit
        ) -> SubmissionCommitResult:
            args.ready.write_text(json.dumps({"token": commit.receipt.token}), encoding="utf-8")
            deadline = time.monotonic() + 30
            while not args.release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("parent did not release checked worker")
                time.sleep(0.02)
            return real_commit(self, commit)

        FileProgressStore.commit_submission = commit_at_barrier
    if args.now:
        os.environ["SKILLING_NOW"] = args.now
    command = [
        "homework",
        "submit" if args.verb == "submit" else "check",
        "--course",
        args.course,
        "--state",
        args.state,
    ]
    if args.verb == "submit" and args.token is not None:
        command += ["--token", args.token]
    sys.argv = ["skilling", *command]
    main()


if __name__ == "__main__":
    main_worker()
