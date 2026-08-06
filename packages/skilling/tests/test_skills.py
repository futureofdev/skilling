"""Structural sanity for the bundled ``learn``/``progress``/``homework`` Agent Skills.

There is no generation step left to check freshness against (docs/superpowers/specs/
2026-08-06-generic-delivery-skills-design.md) — these are hand-maintained files, not a
byte-equivalence target. What *is* code, and so gets normal unit test coverage, is the
frontmatter-validation helper and the small file manifest each skill is built from. The
real verification for whether the choreography in ``SKILL.md``/``references/*.md`` actually
works against a stock host is the live two-host proof, deliberately out of scope here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skilling.skills import (
    SKILL_NAMES,
    FrontmatterError,
    parse_frontmatter,
    skill_dir,
    skill_files,
    skill_md_path,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------- the bundled content


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_bundled_skill_frontmatter_is_valid(name: str) -> None:
    frontmatter = parse_frontmatter(skill_md_path(name))
    assert frontmatter.name == name
    assert 0 < len(frontmatter.description) <= 1024


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_bundled_skill_files_all_exist(name: str) -> None:
    files = skill_files(name)
    assert files, f"{name} has no files at all"
    for path in files:
        assert path.is_file(), f"{path} is listed for {name} but does not exist"


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_bundled_skill_references_are_all_linked(name: str) -> None:
    """Every ``references/*.md`` file sits beside a ``SKILL.md`` that actually names it —
    catches a reference written and never linked, or a link left dangling after a rename."""
    skill_md, *references = skill_files(name)
    body = skill_md.read_text(encoding="utf-8")
    for reference in references:
        link = f"references/{reference.name}"
        assert link in body, f"{skill_md} never mentions {link}"


def test_skill_dir_rejects_an_unknown_name() -> None:
    with pytest.raises(ValueError, match="not one of"):
        skill_dir("not-a-real-skill")


# --------------------------------------------------------------------- parse_frontmatter itself


def test_parses_a_minimal_valid_block(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\nname: learn\ndescription: Do the thing.\n---\nBody.\n")
    frontmatter = parse_frontmatter(path)
    assert frontmatter.name == "learn"
    assert frontmatter.description == "Do the thing."


def test_missing_file_is_a_frontmatter_error(tmp_path: Path) -> None:
    with pytest.raises(FrontmatterError, match="does not exist"):
        parse_frontmatter(tmp_path / "SKILL.md")


def test_no_frontmatter_block_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "# Just a heading\n")
    with pytest.raises(FrontmatterError, match="no frontmatter block"):
        parse_frontmatter(path)


def test_unclosed_frontmatter_block_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\nname: learn\ndescription: Do the thing.\n")
    with pytest.raises(FrontmatterError, match="no frontmatter block"):
        parse_frontmatter(path)


def test_an_extra_key_is_an_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "---\nname: learn\ndescription: Do the thing.\nversion: 1.0.0\n---\nBody.\n"
    )
    with pytest.raises(FrontmatterError, match="exactly name, description"):
        parse_frontmatter(path)


def test_a_missing_key_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\nname: learn\n---\nBody.\n")
    with pytest.raises(FrontmatterError, match="exactly name, description"):
        parse_frontmatter(path)


@pytest.mark.parametrize("bad_name", ["Learn", "learn_skill", "-learn", "learn-", "", "a" * 65])
def test_an_invalid_name_is_an_error(tmp_path: Path, bad_name: str) -> None:
    path = _write(tmp_path, f"---\nname: {bad_name!r}\ndescription: Do the thing.\n---\nBody.\n")
    with pytest.raises(FrontmatterError, match="name"):
        parse_frontmatter(path)


def test_an_empty_description_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\nname: learn\ndescription: ''\n---\nBody.\n")
    with pytest.raises(FrontmatterError, match="description"):
        parse_frontmatter(path)


def test_an_overlong_description_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, f"---\nname: learn\ndescription: {'x' * 1025}\n---\nBody.\n")
    with pytest.raises(FrontmatterError, match="description"):
        parse_frontmatter(path)


def test_a_non_mapping_frontmatter_is_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\n- just\n- a\n- list\n---\nBody.\n")
    with pytest.raises(FrontmatterError, match="not a mapping"):
        parse_frontmatter(path)
