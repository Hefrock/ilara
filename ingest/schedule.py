"""The capture schedule (HANDOFF 8.1), defined once and read by workflows tests and alerts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

# DOH's update lands about 13:00 to 14:20 ET (17:00 to 19:20 UTC across the daylight saving
# change), and a day is covered by a capture between 18:00 and 23:59 UTC (ADR 0010). Scheduled
# runs have started 1 to 3 hours late and the earliest slot never ran, so the slots sit earlier
# and off the hour and half hour, where most still land inside the window when late (ADR 0025).
DASHBOARD_CRONS = (
    "13 19 * * 1,3,5",
    "7 20 * * 1,3,5",
    "53 20 * * 1,3,5",
    "47 21 * * 1,3,5",
    "17 13 * * 2,4,6",
)
LIGHT_CRONS = ("30 14 * * *",)
RELEASE_CRONS = ("30 13 * * 1",)
CAPTURE_DAYS = (0, 2, 4)  # Monday, Wednesday, Friday (Python weekday numbers)
COVER_START_HOUR_UTC = 18
SCHEDULE_START = date(2026, 10, 7)  # first scheduled dashboard window (docs/PROGRESS.md)


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
