"""Course validation: every check the format makes, reported as coded findings.

The entry point only. The checks themselves live in ``_manifest`` (the document itself,
ceremony copy, numbering, and its agreement with disk) and ``_lesson`` (frontmatter, the
section registry, and the grammars inside each section), sharing the finding model in
``_findings`` and the authored-count rule in ``_counts``.
"""

from __future__ import annotations

from pathlib import Path

from ..course import MANIFEST_NAME, CourseLoadError, load_manifest, parse_lesson, resolve
from ._counts import _BODY_COUNTS, _scan_counts
from ._findings import Finding, Report, _Collector
from ._lesson import _check_lesson
from ._manifest import _check_ceremony, _check_disk, _check_manifest, _check_numbering

__all__ = ["Finding", "Report", "validate_course"]


def validate_course(root: Path | str) -> Report:
    root = Path(root)
    out = _Collector(root)

    try:
        manifest = load_manifest(root)
    except CourseLoadError as exc:
        out.add(exc.code, exc.message, path=exc.path or MANIFEST_NAME)
        return Report(out.findings)

    raw = (root / MANIFEST_NAME).read_text(encoding="utf-8")
    _check_manifest(out, manifest, raw)
    _check_ceremony(out, manifest, raw)
    _check_numbering(out, manifest, raw)

    course = resolve(root, manifest)
    _check_disk(out, course)

    for resolved in course.lessons():
        if not resolved.path.is_file():
            continue
        parsed = parse_lesson(resolved.path)
        _check_lesson(out, course, resolved, parsed)

    for phase in course.phases:
        overview = phase.overview_path
        if overview:
            _scan_counts(
                out,
                overview.read_text(encoding="utf-8"),
                _BODY_COUNTS,
                path=overview,
                where=f"Phase {phase.number}'s overview",
            )

    return Report(out.findings)
