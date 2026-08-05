"""Time helpers shared by ``models`` and ``runtime``.

Kept separate from both so that ``models.Record.new`` can compute "today" without ``models``
importing ``runtime`` — ``runtime`` already imports ``models``, and a mutual import is a cycle
either module would have to work around. This module depends on neither.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def today_in(zone: str, now: datetime | None = None) -> date:
    """Today's date in the record's timezone — the streak is defined in local days."""
    moment = now or utc_now()
    try:
        return moment.astimezone(ZoneInfo(zone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return moment.astimezone(ZoneInfo("UTC")).date()


def next_streak(last_activity: date | None, today: date, current: int) -> int:
    """Yesterday → increment. Today → unchanged. Older or unset → 1."""
    if last_activity is None:
        return 1
    if last_activity == today:
        return max(current, 1)
    if last_activity == today - timedelta(days=1):
        return current + 1
    return 1
