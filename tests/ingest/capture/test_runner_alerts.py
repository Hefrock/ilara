from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import httpx

from ingest import alerts, registry
from ingest.capture import runner
from ingest.capture.http import PoliteClient, RateLimiter
from ingest.capture_log import CaptureLog


def _client(handler) -> PoliteClient:
    lim = RateLimiter(min_interval=0.0, sleep=lambda s: None)
    return PoliteClient(transport=httpx.MockTransport(handler), limiter=lim, sleep=lambda s: None)


def _handler(req: httpx.Request) -> httpx.Response:
    if req.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")
    if "cdc.gov" in req.url.host:
        return httpx.Response(403, text="forbidden")
    if "census.gov" in req.url.host:
        raise RuntimeError("unexpected crash in fetcher")
    return httpx.Response(
        200, text=f"<html>{req.url.path}</html>", headers={"content-type": "text/html"}
    )


def test_one_failure_does_not_stop_others(root: Path) -> None:  # T2.7
    reg = registry.load(root)
    srcs = [
        reg[s]
        for s in (
            "cdc_measles_national",
            "census_popest_totals",
            "doh_measles_page",
            "doh_newsroom",
        )
    ]
    log = CaptureLog("run-a", root)
    recs = runner.run(srcs, log, root, client=_client(_handler))
    by = {r.source_id: r.outcome for r in recs}
    assert by == {
        "cdc_measles_national": "blocked",
        "census_popest_totals": "failed",
        "doh_measles_page": "changed",
        "doh_newsroom": "changed",
    }
    lines = log.path.read_text().splitlines()
    assert len(lines) == 4
    # T2.6: blocked yields an issue payload and no curated rows
    al = alerts.build_alerts([json.loads(x) for x in lines], [])
    assert {a.source_id for a in al} == {"cdc_measles_national", "census_popest_totals"}
    assert all("Capture id" in a.body and "Next scheduled attempt" in a.body for a in al)
    assert not (root / "data" / "curated").exists()


def test_unchanged_logs_one_line_no_file(root: Path) -> None:  # T2.2 (log side)
    reg = registry.load(root)
    src = reg["doh_newsroom"]
    runner.run([src], CaptureLog("run-1", root), root, client=_client(_handler))
    log2 = CaptureLog("run-2", root)
    recs = runner.run([src], log2, root, client=_client(_handler))
    assert [r.outcome for r in recs] == ["unchanged"]
    assert len(log2.path.read_text().splitlines()) == 1
    assert len([p for p in (root / "data/raw").rglob("*.html")]) == 1


def test_two_runs_write_different_log_files(root: Path) -> None:  # T2.9 (log part)
    a, b = CaptureLog("gh-1-1", root), CaptureLog("gh-2-1", root)
    assert a.path != b.path


def test_issue_lifecycle() -> None:  # WP2e
    calls: list[tuple[str, str, dict]] = []
    open_issues = [
        {"number": 7, "title": "[capture-failure] doh_newsroom: failed"},
        {"number": 8, "title": "[capture-failure] cdc_measles_national: blocked"},
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else {}
        calls.append((req.method, req.url.path, body))
        if req.method == "GET":
            label = req.url.params.get("labels")
            return httpx.Response(200, json=open_issues if label == "capture-failure" else [])
        if req.url.path.endswith("/issues") and req.method == "POST":
            return httpx.Response(201, json={"number": 9})
        return httpx.Response(200, json={})

    gh = alerts.GitHubIssues("o/r", "t", transport=httpx.MockTransport(handler))
    rec = {
        "capture_id": "c1",
        "source_id": "cdc_measles_national",
        "url": "u",
        "outcome": "blocked",
        "finished_utc": "2026-10-07T18:00:00Z",
        "http_status": 403,
        "sha256": None,
        "error": "HTTP 403",
    }
    new = dict(rec, source_id="doh_measles_page", outcome="failed")
    al = alerts.build_alerts([rec, new], [])
    actions = gh.apply(al, recovered={"doh_newsroom"})
    assert "commented #8" in actions  # duplicate comments on the open issue
    assert "opened #9" in actions
    assert "closed #7" in actions  # closes only after a successful capture
    closes = [c for c in calls if c[0] == "PATCH"]
    assert closes == [
        ("PATCH", "/repos/o/r/issues/7", {"state": "closed", "state_reason": "completed"})
    ]


def test_capture_record_round_trip(root: Path) -> None:
    log = CaptureLog("x", root)
    reg = registry.load(root)
    recs = runner.run([reg["doh_newsroom"]], log, root, client=_client(_handler))
    stored = json.loads(log.path.read_text().splitlines()[0])
    assert stored == asdict(recs[0])


def test_partial_capture_is_an_anomaly() -> None:
    rec = {
        "capture_id": "c2",
        "source_id": "doh_dashboard",
        "url": "u",
        "outcome": "changed",
        "finished_utc": "2026-10-07T18:00:00Z",
        "http_status": 200,
        "sha256": "ab",
        "error": "county: TimeoutError",
    }
    al = alerts.build_alerts([rec], [])
    assert len(al) == 1 and al[0].label == "data-anomaly"
    assert alerts.recovered_sources([rec]) == set()


def test_flags_raised_in_a_run_open_an_issue_and_close_only_when_cleared() -> None:  # ADR 16, 19
    rec = {"source_id": "doh_dashboard", "started_utc": "2026-10-19T19:42:00Z"}
    source_of = {"aaa": "doh_dashboard", "bbb": "doh_dashboard"}
    flags = [
        {  # raised by this run's parse
            "code": "COUNTY_COUNT_DROP",
            "ref_raw_sha256": "aaa",
            "description": "66 county rows on 2026-10-19, 67 on 2026-10-16",
            "fetched_at_utc": "2026-10-19T19:42:32Z",
        },
        {  # an older flag: already alerted when it was raised
            "code": "PARSE_SCHEMA_CHANGE",
            "ref_raw_sha256": "bbb",
            "description": "old",
            "fetched_at_utc": "2026-10-14T19:00:00Z",
        },
        {  # not an alerting code
            "code": "CUM_DECREASE",
            "ref_raw_sha256": "aaa",
            "description": "x",
            "fetched_at_utc": "2026-10-19T19:42:32Z",
        },
    ]
    al = alerts.flag_alerts([rec], flags, source_of)
    assert [a.title for a in al] == [
        "[data-anomaly] doh_dashboard/COUNTY_COUNT_DROP: data-quality flag"
    ]
    assert "66 county rows" in al[0].body
    cleared = alerts.cleared_flag_keys({"doh_dashboard"}, flags, source_of, {"aaa"})
    assert "doh_dashboard/COUNTY_COUNT_DROP" not in cleared  # on the newest capture: stays open
    # ADR 0019: an older flag that stays open by design does not hold an issue open once the
    # newest capture parses without it.
    assert "doh_dashboard/PARSE_SCHEMA_CHANGE" in cleared
    assert "doh_dashboard/COUNTY_SUM_MISMATCH" in cleared
    # The next capture parses cleanly: the issue closes.
    cleared = alerts.cleared_flag_keys({"doh_dashboard"}, flags, source_of, {"ccc"})
    assert "doh_dashboard/COUNTY_COUNT_DROP" in cleared
    # A successful capture alone never closes a flag issue: its key is not a source id.
    assert "doh_dashboard/COUNTY_COUNT_DROP" not in alerts.recovered_sources(
        [{"source_id": "doh_dashboard", "outcome": "changed", "error": None}]
    )


def test_newest_capture_holds_every_file_of_the_newest_capture() -> None:  # ADR 0019
    m = [
        {"source_id": "doh_dashboard", "sha256": "old", "fetched_at_utc": "2026-10-23T19:42:07Z"},
        {"source_id": "doh_dashboard", "sha256": "txt", "fetched_at_utc": "2026-10-26T19:41:54Z"},
        {"source_id": "doh_dashboard", "sha256": "json", "fetched_at_utc": "2026-10-26T19:41:54Z"},
        {"source_id": "cdc_measles_cases_map", "sha256": "c", "fetched_at_utc": "2026-10-23T18:38"},
    ]
    assert alerts.newest_capture(m) == {"txt", "json", "c"}
