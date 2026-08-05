"""Time helpers shared by ``course`` and ``delivery``.

Lives here rather than in ``delivery`` so that ``_models.Record.new`` can compute "today"
without ``course`` reaching into ``delivery`` — ``delivery`` already depends on ``course``,
and the reverse edge would cycle. This module depends on nothing in the package.
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
