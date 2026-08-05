"""Tests for ``skilling.pack``: generation, the choreography invariants, and the audit.

The five invariants from the wave-1 plan (no structure facts, verbs not files, gates are open
waits, the quiz loop never reads the lesson, and a derived trigger description) are checked
both at generation time (the templates cannot produce a violation) and by ``audit()`` (which
catches a violation introduced by hand-editing a written pack).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Course
from skilling.pack import Pack, PackFinding, PackRefused, audit, write_pack

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE

runner = CliRunner()


def _frontmatter(content: str) -> dict[str, object]:
    match = re.match(r"\A---\n(.*?)\n---\n", content, re.DOTALL)
    assert match, "no frontmatter block found"
    loaded = yaml.safe_load(match.group(1))
    assert isinstance(loaded, dict)
    return loaded


def _dir_bytes(root: Path) -> bytes:
    parts: list[bytes] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            parts.append(str(path.relative_to(root)).encode())
            parts.append(path.read_bytes())
    return b"\n".join(parts)


# --------------------------------------------------------------------------------- generate


def test_refuses_a_course_with_findings(corrupt) -> None:
    """The manifest itself parses, and ``Course.load`` succeeds — it is ``validate_course``
    finding the missing lesson file that must refuse generation, not the loader."""
    root = corrupt(lambda r: (r / fx.LESSON_THREE_PATH).unlink())
    course = Course.load(root)
    with pytest.raises(PackRefused) as excinfo:
        Pack.generate(course)
    assert excinfo.value.findings


def test_frontmatter_is_exactly_name_and_description(clean) -> None:
    pack = Pack.generate(clean)
    fm = _frontmatter(pack.files[0].content)
    assert set(fm) == {"name", "description"}
    name, description = fm["name"], fm["description"]
    assert isinstance(name, str) and isinstance(description, str)
    assert name == pack.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name)
    assert len(name) <= 64
    assert 0 < len(description) <= 1024


def test_name_defaults_to_the_course_id(clean) -> None:
    pack = Pack.generate(clean)
    assert pack.name == clean.id == "clean-course"


def test_name_override(clean) -> None:
    pack = Pack.generate(clean, name="my-front-door")
    assert pack.name == "my-front-door"
    fm = _frontmatter(pack.files[0].content)
    assert fm["name"] == "my-front-door"


def test_name_override_must_still_be_a_valid_skill_name(clean) -> None:
    with pytest.raises(ValueError):
        Pack.generate(clean, name="Not Valid")


def test_first_file_is_skill_md_with_references_beside_it(clean) -> None:
    pack = Pack.generate(clean)
    relatives = [f.relative for f in pack.files]
    assert relatives[0] == Path("SKILL.md")
    assert Path("references/delivery-loop.md") in relatives
    assert Path("references/objectives.md") in relatives
    assert Path("references/troubleshooting.md") in relatives


def test_skill_md_body_is_under_500_lines(clean) -> None:
    pack = Pack.generate(clean)
    assert len(pack.files[0].content.splitlines()) < 500


def test_no_structure_facts_leak_for_the_clean_course(clean) -> None:
    pack = Pack.generate(clean)
    text = "\n".join(f.content for f in pack.files)
    assert f"{clean.lesson_count} lesson" not in text
    for phase in clean.manifest.phases:
        assert phase.name not in text
        for lesson in phase.lessons:
            assert lesson.title not in text


def test_no_structure_facts_leak_for_the_golden_example() -> None:
    course = Course.load(EXAMPLE_COURSE)
    pack = Pack.generate(course)
    text = "\n".join(f.content for f in pack.files)
    assert f"{course.lesson_count} lesson" not in text
    for phase in course.manifest.phases:
        assert phase.name not in text
        for lesson in phase.lessons:
            assert lesson.title not in text


def test_generation_is_idempotent(clean, tmp_path: Path) -> None:
    a = write_pack(Pack.generate(clean), tmp_path / "a")
    b = write_pack(Pack.generate(clean), tmp_path / "b")
    assert _dir_bytes(a) == _dir_bytes(b)


def test_description_is_derived_from_title_and_id(clean) -> None:
    pack = Pack.generate(clean)
    fm = _frontmatter(pack.files[0].content)
    assert clean.manifest.title in fm["description"]
    assert clean.id in fm["description"]


def test_tutor_persona_and_tone_are_included_when_present(clean) -> None:
    pack = Pack.generate(clean)
    assert clean.manifest.tutor is not None
    body = pack.files[0].content
    assert clean.manifest.tutor.persona in body
    for line in clean.manifest.tutor.tone:
        assert line in body


def test_no_tutor_section_when_the_course_declares_none(clean_dir: Path) -> None:
    fx.edit(
        clean_dir,
        fx.MANIFEST_PATH,
        "tutor:\n  persona: A calm instructor.\n  tone:\n    - Direct\n",
        "",
    )
    course = Course.load(clean_dir)
    assert course.manifest.tutor is None
    pack = Pack.generate(course)
    assert "Tutor voice" not in pack.files[0].content


# ------------------------------------------------------------------------------------ write


def test_write_pack_returns_the_out_slash_name_directory(clean, tmp_path: Path) -> None:
    out = tmp_path / "out"
    written = write_pack(Pack.generate(clean), out)
    assert written == out / clean.id
    assert (written / "SKILL.md").is_file()
    assert (written / "references" / "delivery-loop.md").is_file()
    assert (written / "references" / "objectives.md").is_file()
    assert (written / "references" / "troubleshooting.md").is_file()


# ------------------------------------------------------------------------------------ audit


def test_a_freshly_written_pack_audits_clean(clean, tmp_path: Path) -> None:
    out = write_pack(Pack.generate(clean), tmp_path / "out")
    assert audit(out, clean) == []


def test_check_detects_staleness_injected_fact_and_trigger_drift(clean, tmp_path: Path) -> None:
    out = write_pack(Pack.generate(clean), tmp_path / "out")
    skill_md = out / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    anchor = "Ask `skilling progress"
    assert text.count(anchor) == 1, "the corruption anchor must be unique in SKILL.md"
    skill_md.write_text(
        text.replace(anchor, f"This course has {clean.lesson_count} lessons. {anchor}"),
        encoding="utf-8",
    )

    findings = audit(out, clean)
    rules = {f.rule for f in findings}
    assert "structure-fact" in rules
    assert "stale" in rules
    assert all(isinstance(f, PackFinding) for f in findings)


def test_trigger_drift_detected_on_a_hand_edited_description(clean, tmp_path: Path) -> None:
    out = write_pack(Pack.generate(clean), tmp_path / "out")
    skill_md = out / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    edited = text.replace(clean.manifest.title, "Something Else Entirely", 1)
    skill_md.write_text(edited, encoding="utf-8")

    rules = {f.rule for f in audit(out, clean)}
    assert "trigger-drift" in rules or "stale" in rules


def test_audit_flags_a_broken_frontmatter(clean, tmp_path: Path) -> None:
    out = write_pack(Pack.generate(clean), tmp_path / "out")
    (out / "SKILL.md").write_text("no frontmatter here at all\n", encoding="utf-8")

    rules = {f.rule for f in audit(out, clean)}
    assert "frontmatter" in rules


# -------------------------------------------------------------------------------------- CLI


def test_cli_pack_writes_a_pack(clean_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["pack", str(clean_dir), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "clean-course" / "SKILL.md").is_file()


def test_cli_pack_respects_name_override(clean_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["pack", str(clean_dir), "--out", str(out), "--name", "front-door"])
    assert result.exit_code == 0, result.output
    assert (out / "front-door" / "SKILL.md").is_file()


def test_cli_pack_exits_nonzero_on_a_course_that_does_not_load(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "course.yaml").write_text("not: [valid", encoding="utf-8")
    result = runner.invoke(app, ["pack", str(broken)])
    assert result.exit_code == 1


def test_cli_pack_exits_nonzero_when_validation_finds_errors(corrupt, tmp_path: Path) -> None:
    root = corrupt(lambda r: (r / fx.LESSON_THREE_PATH).unlink())
    result = runner.invoke(app, ["pack", str(root), "--out", str(tmp_path / "out")])
    assert result.exit_code == 1


def test_cli_pack_check_passes_on_a_current_pack(clean_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert runner.invoke(app, ["pack", str(clean_dir), "--out", str(out)]).exit_code == 0
    result = runner.invoke(app, ["pack", str(clean_dir), "--out", str(out), "--check"])
    assert result.exit_code == 0, result.output


def test_cli_pack_check_fails_when_no_pack_exists_yet(clean_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(app, ["pack", str(clean_dir), "--out", str(out), "--check"])
    assert result.exit_code == 1


def test_cli_pack_check_fails_on_a_stale_pack(clean_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert runner.invoke(app, ["pack", str(clean_dir), "--out", str(out)]).exit_code == 0
    (out / "clean-course" / "SKILL.md").write_text("stale by hand\n", encoding="utf-8")
    result = runner.invoke(app, ["pack", str(clean_dir), "--out", str(out), "--check"])
    assert result.exit_code == 1
