from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from skilling.course import Course

from . import fixtures as fx


def pytest_configure() -> None:
    """CLI tests assert on captured output as plain text, so the ambient colour environment
    must not reach rich — a developer's or CI's FORCE_COLOR would thread ANSI codes through
    every assertion. Scrubbed here because it runs before any test module imports the CLI,
    whose module-level Consoles read the environment once at import."""
    for var in ("FORCE_COLOR", "NO_COLOR", "CLICOLOR", "CLICOLOR_FORCE"):
        os.environ.pop(var, None)


REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_COURSE = REPO_ROOT / "examples" / "hello-skilling"
SPEC_DIR = REPO_ROOT / "spec"
SCHEMAS_DIR = REPO_ROOT / "schemas"


@pytest.fixture
def clean_dir(tmp_path: Path) -> Path:
    """A freshly written clean course directory."""
    return fx.build(tmp_path / "clean-course")


@pytest.fixture
def clean(clean_dir: Path) -> Course:
    return Course.load(clean_dir)


@pytest.fixture
def corrupt(tmp_path: Path) -> Callable[[Callable[[Path], None]], Path]:
    """Build a clean course, apply one corruption, return the directory."""
    counter = {"n": 0}

    def make(mutate: Callable[[Path], None]) -> Path:
        counter["n"] += 1
        root = fx.build(tmp_path / f"case-{counter['n']}")
        mutate(root)
        return root

    return make


@pytest.fixture
def example() -> Course:
    return Course.load(EXAMPLE_COURSE)
