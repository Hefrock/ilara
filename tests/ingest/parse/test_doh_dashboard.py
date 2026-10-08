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


def _dose_rows(b: dict[str, Any]) -> list[dict[str, Any]]:
    for r in b["responses"]:
        if r["view"] == "vaccine" and "Hierarchy.Month" in json.dumps(r["body"]):
            return r["body"]["results"][0]["result"]["data"]["dsr"]["DS"][0]["PH"][0]["DM0"]
    raise AssertionError("no dose chart in the fixture")


def test_golden_demographics() -> None:  # T3.1
    out = doh_dashboard.parse(bundle())
    d = {(r["dimension"], r["category"]): r["cases"] for r in out["demographics"]}
    assert d[("age_group", "0-4")] == 112 and d[("age_group", "25-49")] == 380
    assert d[("age_group", "Unk")] is None  # blank in the report: not reported, not zero (I5)
    assert sum(v or 0 for (dim, _), v in d.items() if dim == "age_group") == 1004
    months = [c for dim, c in d if dim == "report_month"]
    assert months == [f"2026-{m:02d}" for m in range(1, 11)]  # nothing after the as-of month
    assert d[("report_month", "2026-03")] is None and d[("report_month", "2026-09")] == 441
    assert sum(v or 0 for (dim, _), v in d.items() if dim == "report_month") == 1004
    assert d[("age_band", "all")] == 1004 and d[("hospitalized_age_band", "all")] == 198
    assert d[("age_band", "under18")] == 112 + 55 + 152  # matches the age groups
    assert d[("hospitalized_age_band", "under18")] == 59
    assert d[("hospitalized_age_band", "18plus")] == 139
    assert {r["count_definition"] for r in out["demographics"]} == {"calendar_year"}
    assert not [f for f in out["flags"] if f[0] == "DEMOGRAPHIC_SUM_MISMATCH"]


def _query_rows(b: dict[str, Any], first_name: str) -> list[list[dict[str, Any]]]:
    out = []
    for r in b["responses"]:
        if "querydata" not in r["url"]:
            continue
        data = r["body"]["results"][0]["result"]["data"]
        if data["descriptor"]["Select"][0]["Name"] == first_name:
            out.append(data["dsr"]["DS"][0]["PH"][0]["DM0"])
    assert out, first_name
    return out


def test_breakdown_that_does_not_add_up_is_flagged_not_stored() -> None:
    b = bundle()
    for rows in _query_rows(b, doh_dashboard.AGE[0]):
        rows[0]["C"][1] += 1  # 0-4 group one case too many
    out = doh_dashboard.parse(b)
    dims = {r["dimension"] for r in out["demographics"]}
    assert "age_group" not in dims and "report_month" in dims
    assert any(c == "DEMOGRAPHIC_SUM_MISMATCH" and "age group" in t for c, t in out["flags"])
    assert len(out["state"]) == 2 and len(out["county"]) == 67  # case data still parsed


def test_unreadable_hospitalization_card_is_flagged() -> None:
    b = bundle()
    first = f"Min({doh_dashboard.T}.hosptotal)"
    for r in b["responses"]:
        if "querydata" not in r["url"]:
            continue
        data = r["body"]["results"][0]["result"]["data"]
        if data["descriptor"]["Select"][0]["Name"] == first:
            data["dsr"]["DS"][0]["PH"][0]["DM0"][0]["M0"] = "198 out of about 1,004"
    out = doh_dashboard.parse(b)
    dims = {r["dimension"] for r in out["demographics"]}
    assert "age_band" not in dims and "hospitalized_age_band" not in dims
    assert any(c == "DEMOGRAPHIC_SUM_MISMATCH" for c, _ in out["flags"])


def test_bad_dose_chart_flags_but_keeps_case_rows() -> None:
    b = bundle()
    ph = _dose_rows(b)
    ph[0]["C"] = [0]  # January with its count marked null
    ph[0]["Ø"] = 2
    out = doh_dashboard.parse(b)
    assert out["doses"] == []
    assert any(c == "PARSE_SCHEMA_CHANGE" and "January" in t for c, t in out["flags"])
    assert len(out["state"]) == 2 and len(out["county"]) == 67  # case data still parsed


def test_dose_year_comes_from_the_report_not_the_as_of_date() -> None:
    # In January 2027 the 2026 chart would still show December 2026: never relabel it 2027.
    b = _later(bundle(), drop_last_county=False)
    for r in b["responses"]:
        data = r["body"]["results"][0]["result"]["data"] if "querydata" in r["url"] else None
        if data and [s["Name"] for s in data["descriptor"]["Select"]] == [
            doh_dashboard.LAST_UPDATED
        ]:
            jan_2027 = int(datetime(2027, 1, 6, 19, tzinfo=UTC).timestamp() * 1000)
            data["dsr"]["DS"][0]["PH"][0]["DM0"][0]["M0"] = jan_2027
    ph = _dose_rows(b)
    ph[10] = {"C": [10, 40]}  # by then November and December 2026 have counts
    ph[11] = {"C": [11, 30]}
    out = doh_dashboard.parse(b)
    assert len(out["doses"]) == 12 and out["doses"][-1]["doses"] == 30
    assert {r["period_start"].year for r in out["doses"]} == {2026}
    assert all(r["period_complete"] for r in out["doses"])


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
    codes = [c for c, _ in out["flags"]]
    assert codes[0] == "DEFINITION_UNKNOWN"
    # The breakdowns no longer add up to the altered total either, so all three are held back.
    assert codes[1:] == ["DEMOGRAPHIC_SUM_MISMATCH"] * 3 and out["demographics"] == []


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
    assert rep.rows == {
        "case_state": 2,
        "case_county": 67,
        "vaccine_doses": 10,
        "case_demographics": 24,
    }
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
