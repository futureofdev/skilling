"""Structural counts written into prose instead of derived — the ``AUTHORED_COUNT`` rule.

Shared by every check family: a count can appear in the manifest's own fields, in ceremony
copy, or in a lesson body, and the rule that catches it is the same wherever it shows up.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..course import strip_code
from ._errors import Code
from ._findings import _Collector

# Counts written into manifest prose. Any number attached to "lesson" or "phase" here is
# a count the manifest already knows.
_MANIFEST_COUNTS = (
    re.compile(r"\b\d+\s*[-–—]?\s*lessons?\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*[-–—]?\s*phases?\b", re.IGNORECASE),
)

# Counts written into teaching prose. Deliberately narrower: a lesson may legitimately
# discuss numbers, so only self-referential phrasings — the ones that describe *this*
# course or the learner's position in it — are findings.
_BODY_COUNTS = (
    re.compile(r"\blesson\s+\d+\s+of\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bphase\s+\d+\s+of\s+\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*%\s*(?:complete|through|done|finished)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+of\s+\d+\s+lessons?\b", re.IGNORECASE),
    re.compile(r"\bthis\s+course\s+(?:has|contains|is)\s+\d+", re.IGNORECASE),
    re.compile(r"\b\d+\s+lessons?\s+(?:in|of)\s+this\s+(?:course|phase)\b", re.IGNORECASE),
)


def _scan_counts(
    out: _Collector,
    text: str,
    patterns: tuple[re.Pattern[str], ...],
    *,
    path: Path | str,
    offset: int = 1,
    where: str,
) -> None:
    for i, line in enumerate(strip_code(text).splitlines()):
        for pattern in patterns:
            m = pattern.search(line)
            if m:
                out.add(
                    Code.AUTHORED_COUNT,
                    f"{where} states {m.group(0).strip()!r}. Structural counts are derived "
                    "from the manifest; writing one down creates a second source of truth.",
                    path=path,
                    line=i + offset,
                )
                break
