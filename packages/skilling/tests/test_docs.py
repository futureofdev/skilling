"""Documentation integrity.

Three things rot silently in a repository like this: a generated catalogue drifting from the
code that generates it, a link pointing at a file that moved, and an anchor pointing at a
heading that was reworded. All three are cheap to check and expensive to notice by hand,
especially the anchors — every validator finding carries one, so a stale anchor is a broken
promise made forty times over.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from skilling.codegen import docs
from skilling.conformance import CATALOGUE, Code

from .conftest import REPO_ROOT

MARKDOWN_GLOBS = (
    "*.md",
    "spec/*.md",
    "docs/**/*.md",
    "examples/**/*.md",
    "packages/*/README.md",
)

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*([^)\s]+?)\s*\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)


def _markdown_files() -> list[Path]:
    found: set[Path] = set()
    for pattern in MARKDOWN_GLOBS:
        found.update(p for p in REPO_ROOT.glob(pattern) if p.is_file())
    return sorted(found)


FILES = _markdown_files()


def anchor_slug(heading: str) -> str:
    """GitHub's heading-to-anchor rule, near enough for our own headings."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\*\*?([^*]*)\*\*?", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text)


def anchors_in(path: Path) -> set[str]:
    if path.suffix != ".md" or not path.is_file():
        return set()
    out: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if match := _HEADING.match(line):
            out.add(anchor_slug(match.group(2)))
    return out


def links_in(path: Path) -> list[str]:
    out: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.extend(_LINK.findall(line))
    return out


# ------------------------------------------------------------------------- generated docs


def test_error_codes_document_is_current() -> None:
    path = REPO_ROOT / docs.ERROR_CODES_PATH
    assert path.is_file(), "docs/error-codes.md is missing — run `task docs`"
    assert path.read_text(encoding="utf-8") == docs.render_error_codes(), (
        "docs/error-codes.md is stale — run `task docs`"
    )


def test_every_code_appears_in_the_document() -> None:
    text = (REPO_ROOT / docs.ERROR_CODES_PATH).read_text(encoding="utf-8")
    for code in CATALOGUE:
        assert f"`{code}`" in text, code


# ------------------------------------------------------------------------- catalogue anchors


@pytest.mark.parametrize("code", sorted(CATALOGUE, key=str))
def test_every_catalogue_anchor_resolves(code: Code) -> None:
    anchor = CATALOGUE[code].anchor
    relative, fragment = anchor.split("#", 1)
    target = REPO_ROOT / relative
    assert target.is_file(), f"{code}: {relative} does not exist"
    assert fragment in anchors_in(target), f"{code}: no heading in {relative} produces #{fragment}"


# ------------------------------------------------------------------------------ every link


def test_there_is_something_to_check() -> None:
    assert len(FILES) >= 12


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(REPO_ROOT)) for p in FILES])
def test_internal_links_resolve(path: Path) -> None:
    broken: list[str] = []

    for target in links_in(path):
        if _EXTERNAL.match(target):
            continue

        if target.startswith("#"):
            if target[1:] not in anchors_in(path):
                broken.append(f"{target} (same-page anchor)")
            continue

        relative, _, fragment = target.partition("#")
        resolved = (path.parent / relative).resolve()

        if not resolved.exists():
            broken.append(f"{target} → missing {relative}")
            continue
        if fragment and fragment not in anchors_in(resolved):
            broken.append(f"{target} → no heading produces #{fragment}")

    assert not broken, f"{path.relative_to(REPO_ROOT)}:\n  " + "\n  ".join(broken)


def test_the_spec_only_links_within_the_repository() -> None:
    """Normative text must not depend on a URL someone else controls staying up."""
    for path in sorted((REPO_ROOT / "spec").glob("*.md")):
        for target in links_in(path):
            if not _EXTERNAL.match(target):
                continue
            assert target.startswith("https://"), f"{path.name}: {target}"


def test_llms_txt_lists_every_page_it_should() -> None:
    text = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")
    for expected in [
        "spec/README.md",
        "spec/course-format.md",
        "spec/runtime.md",
        "spec/CHANGELOG.md",
        "docs/authoring-a-course.md",
        "docs/implementing-a-runtime.md",
        "docs/error-codes.md",
        "docs/implementations.md",
        "examples/hello-skilling/",
    ]:
        assert expected in text, f"llms.txt does not index {expected}"


def test_llms_txt_links_all_resolve() -> None:
    text = (REPO_ROOT / "llms.txt").read_text(encoding="utf-8")
    for target in _LINK.findall(text):
        if _EXTERNAL.match(target):
            continue
        relative, _, fragment = target.partition("#")
        resolved = (REPO_ROOT / relative).resolve()
        assert resolved.exists(), f"llms.txt: {target} does not exist"
        if fragment:
            assert fragment in anchors_in(resolved), f"llms.txt: {target}"


# ------------------------------------------------------------------- the one version claim


def _declared_spec_version() -> str:
    text = (REPO_ROOT / "spec" / "README.md").read_text(encoding="utf-8")
    match = re.search(r"\*\*Version ([0-9][\w.\-]*)\*\*", text)
    assert match, "spec/README.md no longer declares a version"
    return match.group(1)


def test_every_version_claim_matches_the_spec() -> None:
    """The version is declared in spec/README.md; every other statement of it is a repetition,
    and this repository has already watched two of them drift. This is the fixture for the
    rule that they move together."""
    version = _declared_spec_version()
    claims = {
        "README.md": f"Specification **{version}**",
        "llms.txt": f"Specification version {version}",
    }
    for name, needle in claims.items():
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert needle in text, f"{name} does not state spec version {version}"


def test_changelog_leads_with_the_declared_version() -> None:
    text = (REPO_ROOT / "spec" / "CHANGELOG.md").read_text(encoding="utf-8")
    first = next(line for line in text.splitlines() if line.startswith("## "))
    assert first.startswith(f"## {_declared_spec_version()} "), first


def test_every_concept_page_names_its_normative_home() -> None:
    for path in sorted((REPO_ROOT / "docs" / "concepts").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "spec/" in text, f"{path.name} does not point at the specification"


def test_every_concept_page_states_its_limits() -> None:
    """Honesty discipline: a page that explains why something is good must say where it
    is not."""
    for path in sorted((REPO_ROOT / "docs" / "concepts").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert "## Limits" in text or "## What this costs" in text, path.name
