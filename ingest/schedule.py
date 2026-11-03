"""The capture schedule (HANDOFF 8.1), defined once and read by workflows tests and alerts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

# DOH's update lands about 13:00 to 14:20 ET (17:00 to 19:20 UTC across the daylight saving
# change), and a day is covered by a capture from 18:00 UTC that day to 06:00 UTC the next
# (ADR 0010, widened in ADR 0027: DOH does not update before the next afternoon). Scheduled
# runs have started 1 to 6 hours late and the earliest slot never ran, so the slots sit earlier
# and off the hour and half hour, where most still land inside the window when late (ADR 0025).
DASHBOARD_CRONS = (
    "13 19 * * 1,3,5",
    "7 20 * * 1,3,5",
    "53 20 * * 1,3,5",
    "47 21 * * 1,3,5",
    "17 13 * * 2,4,6",
)
LIGHT_CRONS = ("30 14 * * *",)
RELEASE_CRONS = ("23 13 * * 1",)  # off the half hour (ADR 0026)
CAPTURE_DAYS = (0, 2, 4)  # Monday, Wednesday, Friday (Python weekday numbers)
COVER_START_HOUR_UTC = 18
COVER_END_HOUR_UTC_NEXT = 6  # covering window closes 06:00 UTC the next day (ADR 0027)
COVER_WIDE_FROM = date(2026, 11, 2)  # the wider window applies from this day, not before
SCHEDULE_START = date(2026, 10, 7)  # first scheduled dashboard window (docs/PROGRESS.md)


def cover_window(day: date) -> tuple[datetime, datetime]:
    """The UTC window in which a good dashboard capture covers capture day ``day``: from 18:00
    that day up to (not including) 06:00 the next day (HANDOFF 8.1, ADR 0027). Days before
    ``COVER_WIDE_FROM`` keep the earlier rule, ending at midnight: the owner chose not to apply
    the wider window to past weeks, so G2 is earned under the rule as it now stands."""
    start = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=COVER_START_HOUR_UTC)
    extra = COVER_END_HOUR_UTC_NEXT if day >= COVER_WIDE_FROM else 0
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC) + timedelta(
        hours=extra
    )
    return start, end


def _field(spec: str, lo: int, hi: int) -> set[int]:
    if spec == "*":
        return set(range(lo, hi + 1))
    return {int(x) for x in spec.split(",")}


def next_run(crons: tuple[str, ...], after: datetime) -> datetime:
    """Next firing time for simple cron lines (lists or ``*`` only, no ranges or steps)."""
    best: datetime | None = None
    for line in crons:
        minute, hour, dom, mon, dow = line.split()
        assert dom == "*" and mon == "*", "only day-of-week schedules are supported"
        mins, hours = _field(minute, 0, 59), _field(hour, 0, 23)
        dows = _field(dow, 0, 6)  # cron: 0 = Sunday
        t = after.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(8 * 24 * 60):
            if t.minute in mins and t.hour in hours and (t.isoweekday() % 7) in dows:
                break
            t += timedelta(minutes=1)
        if best is None or t < best:
            best = t
    assert best is not None
    return best
