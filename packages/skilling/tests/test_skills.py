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


def _bundled_text(name: str) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in skill_files(name))


def _compact(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("name", SKILL_NAMES)
def test_skill_triad_uses_workspace_discovery_and_one_record_stream(name: str) -> None:
    body = _compact(_bundled_text(name))
    assert "workspace" in body
    assert "skilling courses" in body
    assert "course id" in body
    assert "`path`" in body
    assert "--state" in body
    assert "--learner" in body
    assert "ordinary workspace use" in body
    assert "omit `--state`" in body or "omitting `--state`" in body
    assert "search the filesystem" in body


def test_course_resolution_prefers_workspace_ids_before_path_or_fetch_fallbacks() -> None:
    for name in ("learn", "homework"):
        body = _compact(_bundled_text(name))
        assert "tie on `last_activity`" in body or "tie on the same day" in body
        assert "empty" in body
        assert "use the selected" in body and "id" in body
        assert "even when the row" in body and "`path`" in body
        assert "`course-not-found`" in body
        assert "Only then" in body
        assert "skilling fetch <ref> --json" in body
        assert "ask" in body and "path" in body and "ref" in body

    progress = _compact(_bundled_text("progress"))
    assert "first use its id directly" in progress
    assert "do not replace the id with that internal path" in progress
    assert "Only when the workspace id/content is unusable" in progress
    assert "title-and-recency only" in progress


def test_ordinary_workspace_examples_use_ids_and_implicit_state() -> None:
    learn = _compact(_bundled_text("learn"))
    homework = _compact(_bundled_text("homework"))
    progress = _compact(_bundled_text("progress"))

    assert "skilling next --course example" in learn
    assert "skilling homework check --course example" in homework
    assert "`skilling progress --course <course-id>`" in progress
    for body in (learn, homework, progress):
        assert "skilling courses --state <path>" not in body


def test_learn_keeps_transition_gate_quiz_and_state_custody() -> None:
    body = _compact(_bundled_text("learn"))
    required = (
        "fresh `--key <token>`",
        "same key and input",
        "`replayed: true`",
        "`idempotency-key-conflict`",
        "wait for their actual reply",
        "Never read a lesson's quiz section",
        "`skilling quiz next",
        "`skilling answer",
        "Only these CLI verbs may mutate learner state",
        "do not open the lesson Markdown",
        "`store-busy`",
    )
    for phrase in required:
        assert phrase in body


def test_learn_declares_the_bare_cli_and_folder_scoped_start_contract() -> None:
    body = _compact(_bundled_text("learn"))
    required = (
        "already installed bare `skilling` executable",
        "`skilling start <ref> <workspace> --json`",
        "`.claude/skills/`",
        "`.agents/skills/`",
        "returned workspace",
    )
    for phrase in required:
        assert phrase in body


def test_artifact_handoffs_use_runtime_paths_and_completed_coordinates() -> None:
    learn = _compact(_bundled_text("learn"))
    homework = _compact(_bundled_text("homework"))

    assert "ceremony.beat.content.coordinate" in learn
    assert "response's `showcase`" in learn
    assert "work the learner already created" in learn
    assert "optional and never delays completion" in learn

    assert "`archived.coordinate`" in homework
    assert "submit response deliberately has no `showcase`" in homework
    assert "workspace and `showcase` fact retained earlier" in homework
    assert "optional and never gates submission" in homework


def test_homework_presents_the_returned_archive_before_offering_an_artifact() -> None:
    workflows = _compact(
        (skill_dir("homework") / "references" / "workflows.md").read_text(encoding="utf-8")
    )
    presentation = "Present the real returned `archived` object before doing anything else"
    artifact_offer = "Only after presenting `archived` may you offer"
    assert presentation in workflows
    assert "assignment title and coordinate" in workflows
    assert "actual `submitted_at`" in workflows
    assert workflows.index(presentation) < workflows.index(artifact_offer)


def test_homework_retains_confirmation_and_submission_token_custody() -> None:
    body = _compact(_bundled_text("homework"))
    required = (
        "exact `submission_token`",
        "own, distinct",
        "same retained token",
        "new, distinct confirmation",
        "`invalid-submission-token`",
        "`store-busy`",
    )
    for phrase in required:
        assert phrase in body


def test_bundled_skills_do_not_expand_the_supported_host_or_install_surface() -> None:
    body = "\n".join(_bundled_text(name) for name in SKILL_NAMES)
    for unsupported in ("uvx", "ChatGPT", "Cowork", "--project"):
        assert unsupported not in body


def test_learn_handles_current_artifact_refusals_without_hidden_state_edits() -> None:
    body = _compact(_bundled_text("learn"))
    for error_code in (
        "`no-workspace`",
        "`course-not-found`",
        "`artifact-missing`",
        "`artifact-outside-workspace`",
        "`coordinate-required`",
    ):
        assert error_code in body
    assert "Do not manufacture a workspace" in body
    assert "Do not repair the workspace manifest by hand" in body
    assert "never create placeholder work" in body
    assert "never substitute the current lesson position" in body
    assert "`coordinate-unknown`" not in body


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
