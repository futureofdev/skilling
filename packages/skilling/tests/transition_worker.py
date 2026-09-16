"""Real CLI worker; faults wrap durable writes, never production fault flags."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

from skilling.cli import main
from skilling.store import FileProgressStore, TransitionCommit, TransitionResult
from skilling.store._journal import _transition


def boundary_for(path: Path, data: bytes) -> str:
    if path.name == "transition.yaml":
        return yaml.safe_load(data)["kind"]
    if path.parent.name == "transition-receipts":
        return "receipt"
    return {"record.yaml": "record", "scratch.yaml": "scratch"}.get(path.name, "other")


def main_worker() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("verb", choices=("advance", "answer", "inspect"))
    parser.add_argument("--course", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--input", default="next")
    parser.add_argument("--key")
    parser.add_argument("--fault", choices=("none", "error", "exit", "hold"), default="none")
    parser.add_argument("--boundary", default="record")
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--release", type=Path)
    args = parser.parse_args()
    real_write = _transition._write_bytes_atomic

    def write(path: Path, data: bytes) -> None:
        real_write(path, data)
        if args.fault == "none" or boundary_for(path, data) != args.boundary:
            return
        if args.fault == "error":
            raise OSError("injected after durable " + args.boundary)
        if args.fault == "exit":
            os._exit(73)
        assert args.marker is not None
        args.marker.write_text("ready", encoding="utf-8")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            time.sleep(0.02)
        raise TimeoutError("parent did not terminate held worker")

    _transition._write_bytes_atomic = write
    if args.ready is not None:
        real_commit = FileProgressStore.commit_transition

        def commit_at_barrier(
            self: FileProgressStore, commit: TransitionCommit
        ) -> TransitionResult:
            args.ready.write_text("ready", encoding="utf-8")
            deadline = time.monotonic() + 30
            while not args.release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("parent did not release prepared worker")
                time.sleep(0.02)
            return real_commit(self, commit)

        FileProgressStore.commit_transition = commit_at_barrier
    base = ["--course", args.course, "--state", args.state]
    if args.verb == "advance":
        command = ["advance", "--input", args.input, *base]
        if args.key is not None:
            command += ["--key", args.key]
    elif args.verb == "answer":
        command = ["answer", args.input, *base]
    else:
        command = ["next", *base]
    sys.argv = ["skilling", *command]
    main()


if __name__ == "__main__":
    main_worker()
