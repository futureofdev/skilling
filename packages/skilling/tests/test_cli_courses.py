"""Tests for ``skilling courses``: cross-course enumeration for the skill triad's "which course
did you mean" default (docs/superpowers/specs/2026-08-06-generic-delivery-skills-design.md).

Records are written straight through ``FileProgressStore`` rather than driven through
``next``/``advance`` — those JSON transition verbs live on their own in-flight branches and are
not part of this command's dependency surface. ``courses`` only ever reads what a store already
holds.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from skilling.course import Position, Record
from skilling.store import FileProgressStore

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE

runner = CliRunner()


def run(args: list[str], tmp: Path, cache: Path | None = None):
    full = [*args, "--state", str(tmp)]
    if cache is not None:
        full = [*full, "--cache", str(cache)]
    from skilling.cli import app

    return runner.invoke(app, full, catch_exceptions=False)


def _write_record(
    state_root: Path,
    course_id: str,
    *,
    version: str = "1.0.0",
    last_activity: date,
) -> None:
    store = FileProgressStore(state_root)
    record = Record(
        learner_id=store.learner_id,
        course_id=course_id,
        course_version=version,
        spec_version="1.0",
        position=Position(phase=0, lesson=1),
        started_at=last_activity,
        last_activity=last_activity,
    )
    store.put_record(record, expected_revision=None)


def test_no_state_root_is_an_empty_list(tmp_path: Path) -> None:
    never_created = tmp_path / "state"
    out = json.loads(run(["courses"], never_created).stdout)
    assert out == {"ok": True, "verb": "courses", "courses": []}


def test_state_root_exists_but_holds_no_records(tmp_path: Path) -> None:
    (tmp_path / "some-other-file.txt").write_text("not a course\n", encoding="utf-8")
    out = json.loads(run(["courses"], tmp_path).stdout)
    assert out["courses"] == []


def test_one_course_with_no_cache_entry_falls_back_to_id_as_title(tmp_path: Path) -> None:
    _write_record(tmp_path, "solo-course", last_activity=date(2026, 8, 1))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert out["ok"] is True
    assert out["courses"] == [
        {"id": "solo-course", "title": "solo-course", "last_activity": "2026-08-01"}
    ]


def test_title_resolves_from_the_fetch_cache_when_present(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    fx.build(cache / "clean-course@1.0.0")  # id: clean-course, title: Clean Course, v1.0.0
    _write_record(tmp_path, "clean-course", version="1.0.0", last_activity=date(2026, 8, 2))

    out = json.loads(run(["courses"], tmp_path, cache=cache).stdout)

    assert out["courses"] == [
        {"id": "clean-course", "title": "Clean Course", "last_activity": "2026-08-02"}
    ]


def test_several_courses_order_most_recent_first(tmp_path: Path) -> None:
    _write_record(tmp_path, "oldest", last_activity=date(2026, 1, 1))
    _write_record(tmp_path, "newest", last_activity=date(2026, 8, 5))
    _write_record(tmp_path, "middle", last_activity=date(2026, 3, 15))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert [c["id"] for c in out["courses"]] == ["newest", "middle", "oldest"]
    assert [c["last_activity"] for c in out["courses"]] == [
        "2026-08-05",
        "2026-03-15",
        "2026-01-01",
    ]


def test_tied_last_activity_breaks_by_id_for_determinism(tmp_path: Path) -> None:
    same_day = date(2026, 8, 5)
    _write_record(tmp_path, "zeta", last_activity=same_day)
    _write_record(tmp_path, "alpha", last_activity=same_day)

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert [c["id"] for c in out["courses"]] == ["alpha", "zeta"]


def test_a_course_with_an_unresolvable_content_directory_does_not_crash(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    # A cache entry exists for the id@version but is not a loadable course (no manifest) —
    # e.g. a half-finished or corrupted cache directory.
    (cache / "broken-course@2.0.0").mkdir(parents=True)
    _write_record(tmp_path, "broken-course", version="2.0.0", last_activity=date(2026, 8, 3))

    out = json.loads(run(["courses"], tmp_path, cache=cache).stdout)

    assert out["ok"] is True
    assert out["courses"] == [
        {"id": "broken-course", "title": "broken-course", "last_activity": "2026-08-03"}
    ]


def test_json_envelope_is_stable(tmp_path: Path) -> None:
    _write_record(tmp_path, "solo-course", last_activity=date(2026, 8, 1))
    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)
    assert set(out) == {"ok", "verb", "courses"}
    assert set(out["courses"][0]) == {"id", "title", "last_activity"}


def test_example_course_directly_referenced_has_no_cache_entry_either(tmp_path: Path) -> None:
    """Mirrors how the rest of this test suite points ``--course`` straight at
    examples/hello-skilling: a bare local path is never fetched into the cache, so its title
    is unresolvable from the state root alone, exactly like any other never-fetched course."""
    from skilling.course import Course

    course = Course.load(EXAMPLE_COURSE)
    _write_record(tmp_path, course.id, version=course.version, last_activity=date(2026, 8, 4))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert out["courses"] == [{"id": course.id, "title": course.id, "last_activity": "2026-08-04"}]
