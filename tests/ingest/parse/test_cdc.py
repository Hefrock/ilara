"""CDC jurisdiction map parser (S6): golden test on real captures, offline."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ingest import access, rawstore
from ingest.parse import cdc, runner

from conftest import REPO

FX = REPO / "tests/fixtures/cdc"
MAP = (FX / "cases_map_2026-10-08.json").read_bytes()
PAGE = gzip.decompress((FX / "cases_page_2026-10-07.html.gz").read_bytes())


def test_page_snapshot() -> None:
    assert cdc.page_snapshot(PAGE) == {
        "as_of_date": date(2026, 10, 1),
        "us_total": 3887,
        "jurisdiction_total": 3869,
        "jurisdictions": 47,
    }


def test_golden_pennsylvania_count() -> None:  # T3.1
    out = cdc.parse(MAP, cdc.page_snapshot(PAGE))
    assert out["flags"] == []
    [row] = out["state"]
    assert row["as_of_date"] == date(2026, 10, 1) and row["cum_cases"] == 963
    assert row["count_definition"] == "calendar_year" and row["date_precision"] == "exact"


def test_no_date_without_a_matching_page() -> None:  # I6: never guess a date
    page = {**cdc.page_snapshot(PAGE), "jurisdiction_total": 3870}  # a different snapshot
    out = cdc.parse(MAP, page)
    assert out["state"] == [] and out["flags"][0][0] == "DATE_TO_CONFIRM"
    out = cdc.parse(MAP, None)
    assert out["state"] == [] and out["flags"][0][0] == "DATE_TO_CONFIRM"


def test_malformed_map_is_an_error() -> None:
    with pytest.raises(cdc.CdcParseError):
        cdc.parse(b"[]", cdc.page_snapshot(PAGE))
    rows = [r for r in json.loads(MAP) if r["geography"] != "Pennsylvania"]
    with pytest.raises(cdc.CdcParseError):
        cdc.parse(json.dumps(rows).encode(), cdc.page_snapshot(PAGE))


def _save(root: Path, source: str, data: bytes, ext: str, when: datetime) -> None:
    rawstore.save(
        source_id=source, url="https://cdc.test", data=data, ext=ext, fetched_at=when, root=root
    )


def test_runner_dates_the_map_from_the_page_seen_before_it(root: Path) -> None:
    _save(root, "cdc_measles_national", PAGE, "html", datetime(2026, 10, 7, 11, tzinfo=UTC))
    _save(root, "cdc_measles_cases_map", MAP, "json", datetime(2026, 10, 8, 17, tzinfo=UTC))
    # A page fetched after the map must not be used to date it.
    later = PAGE.replace(b"As of October 1, 2026", b"As of October 8, 2026")
    _save(root, "cdc_measles_national", later, "html", datetime(2026, 10, 9, 11, tzinfo=UTC))
    rep = runner.run(root)
    assert not rep.failed and rep.rows == {"case_state": 1}
    cs = access.current("case_state", root=root)
    assert cs["as_of_date"].to_list() == [date(2026, 10, 1)] and cs["cum_cases"].to_list() == [963]
    assert cs["source_id"].to_list() == ["cdc_measles_cases_map"]
    assert "cdc_measles_cases_map" in access.CROSSCHECK_SOURCES
