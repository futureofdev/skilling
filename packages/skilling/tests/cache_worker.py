"""Real cache subprocess with test-only interruption at actual publication boundaries."""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from skilling.sources import ResolveError, _cache, resolve
from skilling.sources._identity import Index, ref_digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["resolve"])
    parser.add_argument("--ref", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--fault", choices=["none", "error", "exit", "hold"], default="none")
    parser.add_argument(
        "--boundary",
        choices=[
            "staged",
            "reservation-before",
            "reservation",
            "directory-before",
            "directory",
            "index-before",
            "index",
            "sanitized-before",
            "sanitized",
        ],
        default="index",
    )
    parser.add_argument("--marker", type=Path, required=True)
    args = parser.parse_args()
    source_digest = ref_digest(args.ref)

    def fault(boundary: str) -> None:
        if args.fault == "none" or args.boundary != boundary:
            return
        args.marker.write_text(boundary)
        if args.fault == "exit":
            os._exit(73)
        if args.fault == "error":
            raise OSError("injected cache publication interruption")
        deadline = time.monotonic() + 90
        while not args.marker.with_suffix(".release").exists():
            if time.monotonic() > deadline:
                raise TimeoutError("parent did not release cache worker")
            time.sleep(0.01)

    real_stage = _cache.stage
    real_write = _cache._write_index
    real_rename = Path.rename
    real_strip = _cache._strip_git_metadata

    def stage(fetched: Path, destination: Path) -> None:
        real_stage(fetched, destination)
        fault("staged")

    def write_index(cache: Path, index: Index) -> None:
        boundary = "index" if source_digest in index.entries else "reservation"
        fault(boundary + "-before")
        real_write(cache, index)
        fault(boundary)

    def rename(path: Path, target: str | Path) -> Path:
        publishing = path.name == "course" and Path(target).parent == args.cache.resolve()
        if publishing:
            fault("directory-before")
        result = real_rename(path, target)
        if publishing:
            fault("directory")
        return result

    def strip(directory: Path) -> None:
        fault("sanitized-before")
        real_strip(directory)
        fault("sanitized")

    with ExitStack() as stack:
        stack.enter_context(patch.object(_cache, "stage", stage))
        stack.enter_context(patch.object(_cache, "_write_index", write_index))
        stack.enter_context(patch.object(Path, "rename", rename))
        stack.enter_context(patch.object(_cache, "_strip_git_metadata", strip))
        try:
            result = resolve(args.ref, cache=args.cache)
        except ResolveError as exc:
            print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
            raise SystemExit(2) from None
        print(
            json.dumps(
                {
                    "id": result.course.id,
                    "title": result.course.manifest.title,
                    "path": str(result.path),
                }
            )
        )


if __name__ == "__main__":
    main()
