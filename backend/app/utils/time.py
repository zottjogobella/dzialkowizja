"""Europe/Warsaw time helpers.

All org access-policy checks happen in Warsaw local time so that admin
schedules configured as "09:00-18:00" always mean what Polish users
expect, with DST handled by the zoneinfo database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")


def now_warsaw() -> datetime:
    """Return current time as a timezone-aware datetime in Europe/Warsaw."""
    return datetime.now(WARSAW)


def warsaw_midnight_utc() -> datetime:
    """Start of 'today' in Warsaw, expressed as a UTC-aware datetime.

    Useful for comparing against ``created_at`` columns (stored in UTC with
    tz). DST-aware: during spring-forward the local day still starts at
    00:00, which maps to a single unambiguous UTC instant.
    """
    warsaw_midnight = now_warsaw().replace(hour=0, minute=0, second=0, microsecond=0)
    return warsaw_midnight.astimezone(timezone.utc)
