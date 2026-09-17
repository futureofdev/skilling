"""Separate-process import interruption harness; no production fault option."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from skilling.cli.packaging._start import start
from skilling.workspace import _recovery, _setup, find_workspace, load_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "inspect"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--boundary", default="backup")
    parser.add_argument("--when", choices=["before", "after"], default="after")
    parser.add_argument("--fault", choices=["none", "error", "exit", "hold"], default="none")
    parser.add_argument("--marker", type=Path)
    args = parser.parse_args()
    fired = False

    def fault(boundary: str, when: str) -> None:
        nonlocal fired
        if fired or (boundary, when) != (args.boundary, args.when) or args.fault == "none":
            return
        fired = True
        if args.marker is not None:
            args.marker.write_text(boundary, encoding="utf-8")
        if args.fault == "error":
            raise OSError("injected import interruption")
        if args.fault == "exit":
            os._exit(81)
        while True:
            time.sleep(0.05)

    real_validate = _setup._validated_course
    real_write = _recovery._atomic_write
    real_rename = Path.rename
    real_cleanup = _recovery._cleanup

    def validate(path: Path):
        staged = path.name == "course" and path.parent.name.startswith(".skilling-import-")
        if staged:
            fault("staged", "before")
        course = real_validate(path)
        if staged:
            fault("staged", "after")
        return course

    def write(path: Path, content: bytes) -> None:
        boundary = "manifest" if path.name == "workspace.yaml" else ""
        if path.name == "import.yaml":
            boundary = json.loads(content)["phase"]
        fault(boundary, "before")
        real_write(path, content)
        fault(boundary, "after")

    def rename(path: Path, target: Path) -> Path:
        boundary = "backup" if target.name == "previous" else "candidate"
        fault(boundary, "before")
        result = real_rename(path, target)
        fault(boundary, "after")
        return result

    def cleanup(root: Path, intent: _recovery.Intent) -> None:
        fault("cleanup", "before")
        real_cleanup(root, intent)
        fault("cleanup", "after")

    _setup._validated_course = validate
    _recovery._atomic_write = write
    _recovery._cleanup = cleanup
    patch.object(Path, "rename", rename).start()
    if args.action == "inspect":
        assert find_workspace(args.workspace) == args.workspace
        manifest = load_manifest(args.workspace)
        for entry in manifest.courses:
            assert (args.workspace / ".skilling" / entry.path / "course.yaml").is_file()
        print(manifest.model_dump_json())
    else:
        assert args.source is not None
        start(str(args.source), args.workspace, True)


if __name__ == "__main__":
    main()
