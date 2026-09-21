"""Keep every reviewed, version-pinned reference in sync with one source of truth.

The learner-facing install command is deliberately unpinned (``uv tool install skilling``), so
it is not registered here. Everything below is pinned on purpose instead — the reviewed
example course tag, the release workflow's own identifiers, and a handful of maintainer docs —
and used to mean hand-editing a dozen files per release and hoping none were missed.
``packages/skilling/pyproject.toml`` is the one place a release owner edits ``version``; this
module rewrites (or, with ``--check``, verifies) every derived copy listed in ``SITES``.

Test-file references are handled separately, by importing ``skilling.__version__`` or
``tools/release_candidate.py``'s ``VERSION``/``CANDIDATE_ARTIFACT`` directly, so they never go
stale and are deliberately not registered here.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

PYPROJECT_PATH = "packages/skilling/pyproject.toml"

_VERSION_RE = r"\d+\.\d+\.\d+"


@dataclass(frozen=True)
class Site:
    """One place ``version`` must appear, identified by its exact surrounding text.

    ``count`` pins how many times ``before``...``after`` should bracket a version number in
    the file. A mismatch means the file changed in a way this registry no longer describes
    (a site was added, removed or reworded) rather than a real version drift, so it is
    reported as an error in both sync and check modes rather than silently skipped.
    """

    path: str
    before: str
    after: str
    count: int


SITES: tuple[Site, ...] = (
    # -- release workflow and its helper -------------------------------------------------
    Site(".github/workflows/release.yml", "  group: release-", "", 1),
    Site(".github/workflows/release.yml", "skilling-", "-candidate", 5),
    Site(".github/workflows/release.yml", "--require-tag ", "", 1),
    Site("tools/release_candidate.py", 'VERSION = "', '"', 1),
    Site("tools/release_candidate.py", 'CANDIDATE_ARTIFACT = "skilling-', '-candidate"', 1),
    # -- package version constant --------------------------------------------------------
    Site("packages/skilling/src/skilling/__init__.py", '__version__ = "', '"', 1),
    # -- release runbook (the maintainer-facing install pin stays exact on purpose) -----
    Site("docs/releasing.md", "skilling-", "-candidate", 2),
    Site("docs/releasing.md", "package version `", "`", 1),
    Site("docs/releasing.md", "dist/skilling-", "-py3-none-any.whl", 1),
    Site("docs/releasing.md", "dist/skilling-", ".tar.gz", 1),
    Site("docs/releasing.md", "`v", "`", 2),
    Site("docs/releasing.md", "[the ", " notes]", 1),
    Site("docs/releasing.md", "releases/", ".md)", 1),
    Site("docs/releasing.md", "`skilling==", "`", 1),
    Site("docs/releasing.md", "rebuilding `", "`", 1),
    # -- learner docs and READMEs: install is unpinned, the example tag stays pinned ----
    Site("README.md", "@v", "#examples/welcome-skilling", 2),
    Site("README.md", "`v", "` tag is published", 1),
    Site("packages/skilling/README.md", "skilling/v", "/brand/assets/github/", 3),
    Site("packages/skilling/README.md", "@v", "#examples/welcome-skilling", 1),
    Site("packages/skilling/README.md", "`v", "` is", 1),
    Site("packages/skilling/README.md", "skilling/blob/v", "/docs/", 4),
    Site("packages/skilling/README.md", "skilling/tree/v", "/spec", 1),
    Site("packages/skilling/README.md", "Package version: **", "**", 1),
    Site("packages/skilling/README.md", "skilling/blob/v", "/LICENSE", 1),
    Site("docs/learning-a-course.md", "@v", "#examples/welcome-skilling", 1),
    Site("examples/README.md", "@v", "#examples/welcome-skilling", 1),
    Site("brand/github/org-profile-README.md", "@v", "#examples/welcome-skilling", 1),
    Site("brand/assets/github/README-snippet.md", "`v", "`, because", 1),
    Site("brand/github-launch.md", "@v", "#examples/welcome-skilling", 1),
)


def current_version(source: Path) -> str:
    project = tomllib.loads((source / PYPROJECT_PATH).read_text(encoding="utf-8"))
    version = project["project"]["version"]
    assert isinstance(version, str)
    return version


def _pattern(site: Site) -> re.Pattern[str]:
    return re.compile(re.escape(site.before) + _VERSION_RE + re.escape(site.after))


def sync(source: Path, version: str, *, check: bool) -> list[str]:
    """Rewrite (or, with ``check``, verify) every site against ``version``.

    Returns problem descriptions: a non-empty list means sync/check failed. A count mismatch
    is always a problem, in either mode, since it means ``SITES`` no longer matches the file.
    """
    problems: list[str] = []
    for site in SITES:
        path = source / site.path
        text = path.read_text(encoding="utf-8")
        occurrences = list(_pattern(site).finditer(text))
        if len(occurrences) != site.count:
            where = f"{site.before!r} ... {site.after!r}"
            problems.append(
                f"{site.path}: expected {site.count} occurrence(s) of {where}, "
                f"found {len(occurrences)}"
            )
            continue

        replacement = site.before + version + site.after
        new_text = _pattern(site).sub(replacement, text)
        if new_text == text:
            continue
        if check:
            problems.append(f"{site.path} is stale for {site.before!r} ... {site.after!r}")
        else:
            path.write_text(new_text, encoding="utf-8")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    check = "--check" in args
    args = [a for a in args if a != "--check"]
    source = Path(args[0]) if args else Path(".")

    version = current_version(source)
    problems = sync(source, version, check=check)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        if check:
            print("version references are stale. Run: task version:sync", file=sys.stderr)
        return 1

    print(f"version references are current at {version}." if check else f"synced to {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
