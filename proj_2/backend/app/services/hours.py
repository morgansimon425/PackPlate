"""Opening hours: turn stored hours rows into times, and answer "open at T?".

Pure functions, no database. Ingestion stores one row per location and date
(db.models.HoursDay): status "open" / "closed" / "unknown", and windows as
[open_minute, close_minute] after that date's midnight. A close at or past
1440 runs into the next day, so "open at 12:30am" must also check the
previous day's row.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CAMPUS_TZ = ZoneInfo("America/New_York")
MINUTES_PER_DAY = 24 * 60


def campus_time(at: datetime | None = None) -> datetime:
    """`at` in campus time. None means now; a naive datetime is taken as campus time."""
    if at is None:
        return datetime.now(CAMPUS_TZ)
    if at.tzinfo is None:
        return at.replace(tzinfo=CAMPUS_TZ)
    return at.astimezone(CAMPUS_TZ)


def _at_minute(day: date, minute: int) -> datetime:
    day += timedelta(days=minute // MINUTES_PER_DAY)
    minute %= MINUTES_PER_DAY
    return datetime.combine(day, time(minute // 60, minute % 60), CAMPUS_TZ)


def periods(day: date, windows: list) -> list[tuple[datetime, datetime]]:
    """[[420, 1260]] on 2026-10-06 -> [(Oct 6 7:00am, Oct 6 9:00pm)], in campus time."""
    return [(_at_minute(day, start), _at_minute(day, end)) for start, end in windows]


@dataclass
class OpenState:
    is_open: bool | None          # None = we don't know today's hours
    closes_at: datetime | None    # when the current period ends, if open
    opens_next_at: datetime | None  # next opening later today, if closed


def open_state(at: datetime, today, yesterday) -> OpenState:
    """Whether a location is open at `at`.

    today / yesterday are HoursDay rows (anything with .date, .status,
    .windows) for at's date and the day before, or None if not stored.
    """
    if yesterday is not None and yesterday.status == "open":
        for opens, closes in periods(yesterday.date, yesterday.windows):
            if opens <= at < closes:
                return OpenState(True, closes, None)

    if today is None or today.status == "unknown":
        return OpenState(None, None, None)

    todays = periods(today.date, today.windows) if today.status == "open" else []
    for opens, closes in todays:
        if opens <= at < closes:
            return OpenState(True, closes, None)
    later = [opens for opens, _ in todays if opens > at]
    return OpenState(False, None, min(later) if later else None)
