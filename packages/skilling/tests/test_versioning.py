"""The package release and normative format have independent identities."""

from __future__ import annotations

import re
import tomllib
from importlib import metadata

import skilling

from .conftest import REPO_ROOT


def test_package_versions_agree() -> None:
    project = tomllib.loads(
        (REPO_ROOT / "packages/skilling/pyproject.toml").read_text(encoding="utf-8")
    )
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(package for package in lock["package"] if package["name"] == "skilling")

    assert project["project"]["version"] == "0.6.0"
    assert skilling.__version__ == metadata.version("skilling") == "0.6.0"
    assert locked["version"] == "0.6.0"


def test_specification_version_remains_independent() -> None:
    text = (REPO_ROOT / "spec/README.md").read_text(encoding="utf-8")
    declared = re.search(r"\*\*Version ([0-9][\w.\-]*)\*\*", text)

    assert declared is not None
    assert declared.group(1) == "1.4.0-draft"
    assert skilling.SPEC_VERSION == "1.4"
    assert skilling.__version__ != skilling.SPEC_VERSION
