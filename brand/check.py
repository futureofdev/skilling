#!/usr/bin/env python3
"""Regenerate the public brand assets in scratch space and verify committed output."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
RETIRED = (
    "uvx " + "skilling",
    "skilling " + "deliver",
    "spec-v10" + ".svg",
    "implementations-1" + ".svg",
    "stability-pre-10" + ".svg",
    "licence-cc-by-sa-40" + ".svg",
)
TEXT_SUFFIXES = {".css", ".html", ".json", ".md", ".py", ".scss", ".svg"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_current(root: Path) -> None:
    record = json.loads((ROOT / "generated-sha256.json").read_text(encoding="utf-8"))
    failures = [
        relative
        for relative, expected in {**record["sources"], **record["assets"]}.items()
        if digest(root / relative) != expected
    ]
    if failures:
        raise SystemExit("generated asset drift: " + ", ".join(failures))


def assert_clean_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.name == ".DS_Store" or "/dist/" in f"/{relative}/":
            raise SystemExit(f"unwanted generated path: {relative}")
        for retired in RETIRED:
            if retired in relative:
                raise SystemExit(f"retired path: {relative}")
        if path != root / "check.py" and path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            for retired in RETIRED:
                if retired in text:
                    raise SystemExit(f"retired copy in {relative}: {retired}")


def assert_clean_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as bundle:
        for name in bundle.namelist():
            if "/dist/" in name or name.endswith("/.DS_Store"):
                raise SystemExit(f"unwanted archive path: {name}")
            for retired in RETIRED:
                if retired in name:
                    raise SystemExit(f"retired archive path: {name}")
            if not name.endswith("/check.py") and Path(name).suffix.lower() in TEXT_SUFFIXES:
                text = bundle.read(name).decode("utf-8")
                for retired in RETIRED:
                    if retired in text:
                        raise SystemExit(f"retired archive copy in {name}: {retired}")


def main() -> None:
    assert_clean_tree(ROOT)
    with tempfile.TemporaryDirectory(prefix="skilling-brand-check-") as directory:
        copy = Path(directory) / "brand"
        shutil.copytree(
            ROOT,
            copy,
            ignore=shutil.ignore_patterns("dist", "__pycache__", "*.pyc"),
        )
        subprocess.run(
            [sys.executable, str(copy / "build.py"), "--with-browser", "--zip"],
            check=True,
        )
        assert_current(copy)
        assert_clean_zip(copy / "dist" / "skilling-brand-assets-v2.0.zip")
    print("Brand sources, regenerated public assets and release ZIP are current.")


if __name__ == "__main__":
    main()
