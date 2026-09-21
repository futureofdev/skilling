"""Every pinned reference to the release version must match pyproject.toml.

Complements `task version:sync:check`: this runs on every `task test` / CI matrix cell rather
than only in the dedicated freshness job, the same way `test_error_codes_document_is_current`
backs up `task docs:check`.
"""

from __future__ import annotations

from skilling.codegen import version_refs

from .conftest import REPO_ROOT


def test_version_references_are_current() -> None:
    version = version_refs.current_version(REPO_ROOT)
    problems = version_refs.sync(REPO_ROOT, version, check=True)
    assert not problems, "\n".join([*problems, "Run: task version:sync"])
