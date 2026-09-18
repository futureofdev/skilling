"""Documentation integrity.

Three things rot silently in a repository like this: a generated catalogue drifting from the
code that generates it, a link pointing at a file that moved, and an anchor pointing at a
heading that was reworded. All three are cheap to check and expensive to notice by hand,
especially the anchors — every validator finding carries one, so a stale anchor is a broken
promise made forty times over.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
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
        "docs/learning-a-course.md",
        "docs/course-sources.md",
        "docs/troubleshooting.md",
        "docs/authoring-a-course.md",
        "docs/implementing-a-runtime.md",
        "docs/error-codes.md",
        "docs/implementations.md",
        "examples/hello-skilling/",
        "examples/welcome-skilling/",
        "examples/workbench/",
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


# -------------------------------------------------------------------- learner front door


def test_readme_banners_are_theme_aware_and_resolve() -> None:
    root = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    package = (REPO_ROOT / "packages" / "skilling" / "README.md").read_text(encoding="utf-8")
    for name in ("readme-banner-light.png", "readme-banner-dark.png"):
        path = REPO_ROOT / "brand" / "assets" / "github" / name
        assert path.is_file() and path.stat().st_size > 0
        assert f"brand/assets/github/{name}" in root
        assert (
            f"https://raw.githubusercontent.com/futureofdev/skilling/v0.5.0/"
            f"brand/assets/github/{name}"
        ) in package
    for text in (root, package):
        assert "<picture>" in text
        assert "prefers-color-scheme: dark" in text
        assert "prefers-color-scheme: light" in text
        assert 'alt="Skilling — learn one-to-one with Claude Code or Codex"' in text

    package_picture = re.search(r"<picture>(.*?)</picture>", package, re.DOTALL)
    assert package_picture is not None
    fallback = re.search(r'<img [^>]*src="(https://[^"]+)"', package_picture.group(1))
    assert fallback is not None
    assert fallback.group(1).endswith("/v0.5.0/brand/assets/github/readme-banner-light.png")
    # PyPI may remove picture/source; the ordinary absolute img remains a useful fallback.
    without_picture_sources = re.sub(r"</?picture>|<source[^>]*>", "", package_picture.group(0))
    assert "<img " in without_picture_sources
    assert fallback.group(1) in without_picture_sources


def test_recorded_public_brand_hashes_match_committed_assets() -> None:
    record = json.loads((REPO_ROOT / "brand" / "generated-sha256.json").read_text(encoding="utf-8"))
    assert "brand/build.py --with-browser --zip" in record["generator"]
    for relative, expected in record["sources"].items():
        content = (REPO_ROOT / "brand" / relative).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected, relative
    for relative, expected in record["assets"].items():
        content = (REPO_ROOT / "brand" / relative).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected, relative


def test_brand_tree_has_no_retired_launch_copy_or_generated_nesting() -> None:
    brand = REPO_ROOT / "brand"
    assert not list(brand.rglob(".DS_Store"))
    assert not (brand / "dist").exists()
    retired = (
        "uvx skilling",
        "skilling deliver",
        "spec-v10.svg",
        "implementations-1.svg",
        "stability-pre-10.svg",
        "licence-cc-by-sa-40.svg",
    )
    for path in brand.rglob("*"):
        relative = path.relative_to(brand).as_posix()
        for needle in retired:
            assert needle not in relative, f"retired path {relative!r}"
        if path.is_file() and path.suffix.lower() in {
            ".md",
            ".py",
            ".html",
            ".css",
            ".scss",
            ".json",
            ".svg",
        }:
            text = path.read_text(encoding="utf-8")
            for needle in retired:
                assert needle not in text, f"{path.relative_to(REPO_ROOT)} contains {needle!r}"


def test_generated_brand_zip_excludes_retired_copy_and_nested_dist(tmp_path: Path) -> None:
    copied = tmp_path / "brand"
    shutil.copytree(REPO_ROOT / "brand", copied)
    result = subprocess.run(
        [sys.executable, str(copied / "build.py"), "--only-report"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [sys.executable, "-c", "import build; build.build_zip()"],
        cwd=copied,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    archive = copied / "dist" / "skilling-brand-assets-v2.0.zip"
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert names
        assert not any("/dist/" in name or name.endswith("/.DS_Store") for name in names)
        for name in names:
            for needle in (
                "spec-v10.svg",
                "implementations-1.svg",
                "stability-pre-10.svg",
                "licence-cc-by-sa-40.svg",
            ):
                assert needle not in name
        text = "\n".join(
            bundle.read(name).decode("utf-8")
            for name in names
            if Path(name).suffix.lower()
            in {".md", ".py", ".html", ".css", ".scss", ".json", ".svg"}
        )
    assert "uvx skilling" not in text
    assert "skilling deliver" not in text
