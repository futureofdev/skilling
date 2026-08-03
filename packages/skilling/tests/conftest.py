from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from skilling.loader import Course, load_course

from . import fixtures as fx

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
    return load_course(clean_dir)


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
    return load_course(EXAMPLE_COURSE)
