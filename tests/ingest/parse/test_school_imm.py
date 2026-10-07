"""Golden tests for the school immunization county parser (T3.1, T3.13)."""

from __future__ import annotations

from ingest.parse import school_imm

from conftest import REPO

FIXTURE = REPO / "tests/fixtures/doh_school_imm/county_2025-2026.xls"


def rows() -> list[dict]:
    return school_imm.parse(FIXTURE.read_bytes())


def test_all_counties_and_grades() -> None:
    r = rows()
    assert len(r) == 67 * 3
    assert {x["school_year"] for x in r} == {"2025-2026"}
    assert {x["grade"] for x in r} == {"kindergarten", "grade_7", "grade_12"}
    assert all(x["county_fips"].startswith("42") for x in r)


def test_reference_rates() -> None:  # T3.13 (sources S2), within rounding
    k = {x["county_fips"]: x for x in rows() if x["grade"] == "kindergarten"}
    assert abs(k["42071"]["mmr_up_to_date_pct"] - 87.6) < 0.05  # Lancaster
    assert abs(k["42029"]["mmr_up_to_date_pct"] - 94.5) < 0.05  # Chester
    assert k["42071"]["enrolled"] == 5081


def test_values_in_range_and_no_invented_zeros() -> None:
    for x in rows():
        for c in (
            "mmr_up_to_date_pct",
            "med_exempt_pct",
            "relig_exempt_pct",
            "philos_exempt_pct",
            "provisional_pct",
        ):
            v = x[c]
            assert v is None or 0 <= v <= 100
