"""Golden-file tests for the dashboard parser (T3.1, T3.11, T3.15)."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from ingest import access, rawstore
from ingest.parse import doh_dashboard, runner

from conftest import REPO

FIXTURE = REPO / "tests/fixtures/doh_dashboard/2026-10-05_responses.json.gz"
COMMUNITY = {
    "Centre",
    "Chester",
    "Clarion",
    "Clearfield",
    "Indiana",
    "Jefferson",
    "Lancaster",
    "Mifflin",
    "Snyder",
    "Somerset",
    "Union",
    "York",
}  # docs/sources.md S1, Oct 5


def bundle() -> dict[str, Any]:
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def test_golden_statewide() -> None:  # T3.1
    out = doh_dashboard.parse(bundle())
    assert out["as_of_date"] == date(2026, 10, 5)
    by_def = {r["count_definition"]: r for r in out["state"]}
    ytd, apr = by_def["calendar_year"], by_def["since_april"]
    assert (
        ytd["cum_cases"],
        ytd["counties_with_cases"],
        ytd["hospitalizations"],
        ytd["deaths"],
        ytd["new_7day"],
    ) == (1004, 39, 198, 5, 106)
    assert (apr["cum_cases"], apr["hospitalizations"], apr["deaths"]) == (992, 197, 5)
    assert apr.get("counties_with_cases") is None
    assert "under 18 31.8%" in ytd["notes"] and "fully vaccinated <1%" in ytd["notes"]
    assert out["flags"] == []


def test_golden_county() -> None:  # T3.1, T3.11
    out = doh_dashboard.parse(bundle())
    c = {r["county_fips"]: r for r in out["county"]}
    assert len(c) == 67
    assert sum(r["cum_cases"] for r in c.values()) == 1004
    assert sum(1 for r in c.values() if r["cum_cases"] > 0) == 39
    # Oct 5 sanity values (HANDOFF T3.11); repeat-coded rows decoded (Bedford = Armstrong = 2)
    assert (c["42071"]["cum_cases"], c["42087"]["cum_cases"], c["42029"]["cum_cases"]) == (
        391,
        118,
        84,
    )
    assert c["42009"]["cum_cases"] == 2 and c["42005"]["cum_cases"] == 2
    assert c["42003"]["cum_cases"] == 0  # Allegheny: a reported zero, not absent
    assert {r["count_definition"] for r in c.values()} == {"calendar_year"}
    from ingest.reference import pa_counties

    flagged = {pa_counties.COUNTIES[f] for f, r in c.items() if r["community_transmission"]}
    assert flagged == COMMUNITY


def test_golden_vaccine_doses() -> None:  # T3.1
    out = doh_dashboard.parse(bundle())
    doses = out["doses"]
    assert [r["period_start"].month for r in doses] == list(range(1, 11))
    assert doses[0]["doses"] == 117 and doses[7]["doses"] == 3664
    # The report's own total card on the same page reads 8,843 for this capture.
    assert sum(r["doses"] for r in doses) == 8843
    assert [r["period_complete"] for r in doses] == [True] * 9 + [False]  # October is partial
    assert {(r["administered_by"], r["geography"]) for r in doses} == {("doh_staff", "state")}


def test_missing_past_month_dose_is_an_error() -> None:
    b = bundle()
    for r in b["responses"]:
        if r["view"] == "vaccine" and "Hierarchy.Month" in json.dumps(r["body"]):
            ph = r["body"]["results"][0]["result"]["data"]["dsr"]["DS"][0]["PH"][0]["DM0"]
            ph[0]["C"] = [0]  # January with its count marked null
            ph[0]["Ø"] = 2
    with pytest.raises(doh_dashboard.DashboardParseError):
        doh_dashboard.parse(b)


def test_county_definition_unknown_when_totals_differ() -> None:
    b = bundle()
    for r in b["responses"]:
        if "querydata" not in r["url"] or "'Year to date'" not in (r["post_data"] or ""):
            continue
        data = r["body"]["results"][0]["result"]["data"]
        names = [s["Name"] for s in data["descriptor"]["Select"]]
        if names == ["Sum(PAmeasles2026_Public.count)"]:
            data["dsr"]["DS"][0]["PH"][0]["DM0"][0]["M0"] += 1  # YTD total now 1,005
    out = doh_dashboard.parse(b)
    assert {r["count_definition"] for r in out["county"]} == {"unknown"}
    assert [c for c, _ in out["flags"]] == ["DEFINITION_UNKNOWN"]


def test_no_queries_is_an_error() -> None:
    with pytest.raises(doh_dashboard.DashboardParseError):
        doh_dashboard.parse({"responses": []})


def _save(root: Path, b: dict[str, Any], ts: datetime) -> None:
    rawstore.save(
        source_id="doh_dashboard",
        url="https://report.test",
        fetched_at=ts,
        data=json.dumps(b, sort_keys=True).encode(),
        ext="json",
        capture_key="responses",
        root=root,
    )


def _later(b: dict[str, Any], drop_last_county: bool) -> dict[str, Any]:
    b = json.loads(json.dumps(b))
    for r in b["responses"]:
        if "querydata" not in r["url"]:
            continue
        data = r["body"]["results"][0]["result"]["data"]
        names = [s["Name"] for s in data["descriptor"]["Select"]]
        ph = data["dsr"]["DS"][0]["PH"]
        if names == [doh_dashboard.LAST_UPDATED]:
            ph[0]["DM0"][0]["M0"] += 2 * 86_400_000  # two days later
        if drop_last_county and names == [doh_dashboard.COUNTY, doh_dashboard.COUNTY_COUNT]:
            dm1 = next(p for p in ph if "DM1" in p)["DM1"]
            removed = dm1.pop()  # York 33
            ph[0]["DM0"][0]["A0"] -= removed["C"][1]
    return b


def test_runner_idempotent_and_county_drop(root: Path) -> None:  # T3.15, E20
    _save(root, bundle(), datetime(2026, 10, 7, 18, tzinfo=UTC))
    rep = runner.run(root)
    assert rep.rows == {"case_state": 2, "case_county": 67, "vaccine_doses": 10}
    assert not rep.failed
    assert runner.run(root).skipped == 1

    _save(root, _later(bundle(), drop_last_county=True), datetime(2026, 10, 9, 18, tzinfo=UTC))
    rep = runner.run(root)
    flags = access.all_rows("data_quality_flag", root=root)
    assert "COUNTY_COUNT_DROP" in set(flags["code"])
    q = access.all_rows("quarantine", root=root)
    assert set(q["reason_code"]) == {"COUNTY_COUNT_DROP"} and q.height == 67
    cur = access.current("case_county", root=root)
    assert set(cur["as_of_date"]) == {date(2026, 10, 5)}  # previous good view unchanged
    assert cur.filter(pl.col("county_fips") == "42133")["cum_cases"].to_list() == [33]


def test_parse_failure_is_quarantined_not_raised(root: Path) -> None:
    _save(root, {"responses": []}, datetime(2026, 10, 7, 18, tzinfo=UTC))
    rep = runner.run(root)
    assert len(rep.failed) == 1
    assert set(access.all_rows("data_quality_flag", root=root)["code"]) == {"PARSE_SCHEMA_CHANGE"}
