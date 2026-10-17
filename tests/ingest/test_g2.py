"""G2 tracker and the good-capture rule (ADR 0009), offline."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from ingest import access, capture_log
from ingest.capture.browser import VIEWS
from ingest.capture_log import CaptureLog, CaptureRecord

# The error a capture of the deleted report logged on 2026-10-14 (shortened call logs).
DEAD_ERROR = "; ".join(
    f"{v}: TimeoutError: Locator.click: Timeout 15000ms exceeded.\nCall log:\n  - waiting"
    for v in capture_log.DASHBOARD_CLICK_VIEWS
)


def _rec(cid: str, finished: str, *, trigger: str | None, outcome: str = "changed", error=None):  # type: ignore[no-untyped-def]
    return CaptureRecord(
        capture_id=cid,
        source_id="doh_dashboard",
        url="u",
        started_utc=finished,
        finished_utc=finished,
        http_status=200,
        outcome=outcome,
        raw_path=None,
        sha256=None,
        content_hash=None,
        bytes=None,
        runner="local",
        error=error,
        trigger=trigger,
    )


def test_click_views_match_the_capture() -> None:
    assert tuple(v.key for v in VIEWS[1:]) == capture_log.DASHBOARD_CLICK_VIEWS


def test_is_good_rejects_captures_of_a_dead_report() -> None:
    base = {"source_id": "doh_dashboard", "outcome": "unchanged", "error": None}
    assert capture_log.is_good(base)
    assert not capture_log.is_good({**base, "error": DEAD_ERROR})  # logged before the fix
    assert not capture_log.is_good({**base, "error": "report unavailable: data API HTTP 401 X"})
    assert not capture_log.is_good({**base, "outcome": "failed"})
    # One view failing is a partial capture, still good; other sources ignore view errors.
    assert capture_log.is_good({**base, "error": "county: TimeoutError: x"})
    assert capture_log.is_good({**base, "source_id": "doh_measles_page", "error": DEAD_ERROR})


def test_trigger_is_recorded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
    assert _rec("a", "2026-10-19T18:01:00Z", trigger=None).trigger == "schedule"
    monkeypatch.delenv("GITHUB_EVENT_NAME")
    assert _rec("a", "2026-10-19T18:01:00Z", trigger=None).trigger == "local"


def test_capture_days_show_what_covered_them_and_skip_dead_captures(root: Path) -> None:
    log = CaptureLog("r1", root)
    # A record written before triggers were logged has no trigger key at all.
    old = asdict(_rec("r1:01:doh_dashboard", "2026-10-12T18:43:00Z", trigger="x"))
    del old["trigger"]
    log.path.parent.mkdir(parents=True, exist_ok=True)
    log.path.write_text(json.dumps(old) + "\n")
    log.append(
        _rec(
            "r1:02:doh_dashboard",
            "2026-10-14T18:43:00Z",
            trigger="workflow_dispatch",
            outcome="unchanged",
            error=DEAD_ERROR,
        )
    )
    log.append(_rec("r1:03:doh_dashboard", "2026-10-16T19:00:00Z", trigger="schedule"))
    log.append(_rec("r1:04:doh_dashboard", "2026-10-16T19:30:00Z", trigger="workflow_dispatch"))
    days = access.capture_days(datetime(2026, 10, 17, 12, tzinfo=UTC), root)
    got = {r["day"]: (r["status"], r["by"], r["unattended"]) for r in days.to_dicts()}
    assert got[date(2026, 10, 12)] == ("covered", "unknown", False)
    assert got[date(2026, 10, 14)] == ("missed", "", False)  # the dead report never covers
    assert got[date(2026, 10, 16)] == ("covered", "schedule, workflow_dispatch", True)


def test_g2_needs_two_full_weeks_of_scheduled_cover(root: Path) -> None:
    log = CaptureLog("r1", root)
    days = ["2026-10-19", "2026-10-21", "2026-10-23", "2026-10-26", "2026-10-28", "2026-10-30"]
    for i, d in enumerate(days):
        log.append(_rec(f"r1:{i:02d}:doh_dashboard", f"{d}T18:30:00Z", trigger="schedule"))
    # Partial first week (from Wed Oct 7), a dispatch-only week, then two scheduled weeks.
    log.append(_rec("r1:90:doh_dashboard", "2026-10-12T18:43:00Z", trigger="workflow_dispatch"))
    g = access.g2_status(datetime(2026, 10, 27, 12, tzinfo=UTC), root)
    assert (g["status"], g["streak"]) == ("not yet", 1)  # week of Oct 26 not complete yet
    g = access.g2_status(datetime(2026, 10, 31, 12, tzinfo=UTC), root)
    assert (g["status"], g["streak"]) == ("pass", 2)
    first = g["weeks"][0]
    assert first["week_of"] == date(2026, 10, 5) and not first["complete"]
    # A missed day breaks the streak.
    log.append(_rec("r1:91:doh_dashboard", "2026-11-04T18:30:00Z", trigger="schedule"))
    g = access.g2_status(datetime(2026, 11, 7, 12, tzinfo=UTC), root)
    assert (g["status"], g["streak"]) == ("not yet", 0)


def test_dead_report_rule_holds_for_records_from_before_a_view_was_added() -> None:
    # Records before 2026-10-17 never tried epi_curve: a dead one names the other eight views.
    old = "; ".join(
        f"{v}: TimeoutError" for v in capture_log.DASHBOARD_CLICK_VIEWS if v != "epi_curve"
    )
    assert not capture_log.is_good(
        {"source_id": "doh_dashboard", "outcome": "changed", "error": old}
    )
    # One view failing is a partial capture, not a dead report.
    one = {"source_id": "doh_dashboard", "outcome": "changed", "error": "epi_curve: TimeoutError"}
    assert capture_log.is_good(one)
