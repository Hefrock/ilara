"""Golden tests for the DOH release parser (WP3c)."""

from __future__ import annotations

import gzip
from datetime import date

from ingest.parse import doh_release

from conftest import REPO

FX = REPO / "tests/fixtures/doh_release"


def parse(name: str) -> dict:
    return doh_release.parse(gzip.decompress((FX / name).read_bytes()))


def test_key_updates_block() -> None:
    out = parse("2026-08-31_497.html.gz")
    assert out["as_of_date"] == date(2026, 8, 31)
    [r] = out["state"]
    assert (r["cum_cases"], r["counties_with_cases"], r["hospitalizations"], r["deaths"]) == (
        497,
        34,
        87,
        2,
    )
    assert (r["new_since_date"], r["new_since_count"]) == (date(2026, 8, 28), 37)
    assert r["count_definition"] == "calendar_year"  # "so far in 2026"


def test_sept_28_release_has_13_new_since_sept_25() -> None:
    [r] = parse("2026-09-28_903.html.gz")["state"]
    assert (
        r["cum_cases"],
        r["counties_with_cases"],
        r["hospitalizations"],
        r["deaths"],
        r["vaccinated_cases"],
    ) == (903, 39, 176, 4, 4)
    assert (r["new_since_date"], r["new_since_count"]) == (date(2026, 9, 25), 13)


def test_headline_only_release() -> None:
    out = parse("2026-08-25_deaths.html.gz")
    [r] = out["state"]
    assert out["as_of_date"] == date(2026, 8, 25)
    assert (r["cum_cases"], r["counties_with_cases"]) == (393, 28)
    assert "new_since_count" not in r


def test_exposure_notice_has_no_case_rows() -> None:
    out = parse("exposure.html.gz")
    assert out["state"] == [] and out["as_of_date"].year == 2026
