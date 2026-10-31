from __future__ import annotations

from datetime import UTC, datetime

from ingest import schedule


def test_next_dashboard_run() -> None:
    wed_noon = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # a Wednesday
    assert schedule.next_run(schedule.DASHBOARD_CRONS, wed_noon) == datetime(
        2026, 10, 7, 19, 13, tzinfo=UTC
    )
    wed_evening = datetime(2026, 10, 7, 20, 30, tzinfo=UTC)
    assert schedule.next_run(schedule.DASHBOARD_CRONS, wed_evening) == datetime(
        2026, 10, 7, 20, 53, tzinfo=UTC
    )
    wed_late = datetime(2026, 10, 7, 21, 50, tzinfo=UTC)
    assert schedule.next_run(schedule.DASHBOARD_CRONS, wed_late) == datetime(
        2026, 10, 8, 13, 17, tzinfo=UTC
    )
    sat_late = datetime(2026, 10, 10, 14, 0, tzinfo=UTC)
    assert schedule.next_run(schedule.DASHBOARD_CRONS, sat_late) == datetime(
        2026, 10, 12, 19, 13, tzinfo=UTC
    )


def test_next_release_run() -> None:
    assert schedule.next_run(schedule.RELEASE_CRONS, datetime(2026, 10, 7, tzinfo=UTC)) == datetime(
        2026, 10, 12, 13, 30, tzinfo=UTC
    )
