from __future__ import annotations

from datetime import UTC, datetime

from ingest import schedule


def test_next_dashboard_run() -> None:
    wed_noon = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # a Wednesday
    assert schedule.next_run(schedule.DASHBOARD_CRONS, wed_noon) == datetime(
        2026, 10, 7, 18, 0, tzinfo=UTC
    )
    wed_late = datetime(2026, 10, 7, 22, 0, tzinfo=UTC)
    assert schedule.next_run(schedule.DASHBOARD_CRONS, wed_late) == datetime(
        2026, 10, 8, 13, 0, tzinfo=UTC
    )
    sat_late = datetime(2026, 10, 10, 14, 0, tzinfo=UTC)
    assert schedule.next_run(schedule.DASHBOARD_CRONS, sat_late) == datetime(
        2026, 10, 12, 18, 0, tzinfo=UTC
    )


def test_next_release_run() -> None:
    assert schedule.next_run(schedule.RELEASE_CRONS, datetime(2026, 10, 7, tzinfo=UTC)) == datetime(
        2026, 10, 12, 13, 30, tzinfo=UTC
    )
