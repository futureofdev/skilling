"""Real named-zone dates and a UTC fallback independent of timezone databases."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest

from skilling.course import _clock


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 8, 3, 23, 59, 59, tzinfo=UTC), date(2026, 8, 3)),
        (datetime(2026, 8, 4, 0, 0, 1, tzinfo=UTC), date(2026, 8, 4)),
    ],
)
@pytest.mark.parametrize("error", [ZoneInfoNotFoundError, ValueError])
def test_utc_fallback_never_needs_a_timezone_database(
    monkeypatch: pytest.MonkeyPatch,
    moment: datetime,
    expected: date,
    error: type[Exception],
) -> None:
    calls: list[str] = []

    def unavailable(zone: str) -> None:
        calls.append(zone)
        raise error(zone)

    monkeypatch.setattr(_clock, "ZoneInfo", unavailable)
    assert _clock.today_in("Unavailable/Zone", moment) == expected
    assert calls == ["Unavailable/Zone"]


def test_named_zones_work_without_the_system_database() -> None:
    """A new interpreter avoids ZoneInfo's process cache and consumes the tzdata dependency."""
    program = """
from datetime import UTC, date, datetime
from zoneinfo import TZPATH
from skilling.course import today_in
assert TZPATH == ()
assert today_in('Pacific/Auckland', datetime(2026, 8, 3, 23, 30, tzinfo=UTC)) == date(2026, 8, 4)
assert today_in('America/New_York', datetime(2026, 1, 15, 4, 30, tzinfo=UTC)) == date(2026, 1, 14)
assert today_in('America/New_York', datetime(2026, 7, 15, 4, 30, tzinfo=UTC)) == date(2026, 7, 15)
assert today_in('Mars/Olympus', datetime(2026, 8, 3, 23, 30, tzinfo=UTC)) == date(2026, 8, 3)
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        env={**os.environ, "PYTHONTZPATH": ""},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
