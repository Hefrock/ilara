"""T3.15 baseline (ADR 0016, 0020): only what was known at the capture, never an `unknown` load."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from ingest.curate import store
from ingest.parse import runner


def _county(root: Path, as_of: date, total: int, definition: str, fetched: datetime) -> None:
    fips = [f"420{n:02d}" for n in range(1, 134, 2)]  # 67 county keys
    counts = [total - 66] + [1] * 66
    run_id = store.ingest_run_id(f"{as_of}{definition}{fetched}".ljust(64, "0")[:64], "1.0.0")
    df = pl.DataFrame(
        {
            "jurisdiction": "PA",
            "disease": "measles",
            "source_id": "doh_dashboard",
            "source_tier": "T1",
            "as_of_date": as_of,
            "fetched_at_utc": fetched,
            "ingest_run_id": run_id,
            "raw_sha256": "c" * 64,
            "parser_version": "1.0.0",
            "county_fips": fips,
            "cum_cases": counts,
            "count_definition": definition,
            "date_precision": "exact",
        }
    )
    store.write("curated", "case_county", df, run_id, fetched, root)


def _rows(as_of: date, total: int) -> list[dict[str, object]]:
    return [
        {"source_id": "doh_dashboard", "as_of_date": as_of, "cum_cases": n}
        for n in [total - 66] + [1] * 66
    ]


def test_a_later_mixed_load_is_not_a_baseline(root: Path) -> None:
    # 2026-10-26 19:41 a mixed load was stored under the date the report stated (Oct 16),
    # with a county sum (1,360) above the real Oct 19 snapshot (1,286).
    _county(root, date(2026, 10, 16), 1260, "calendar_year", datetime(2026, 10, 16, 20, tzinfo=UTC))
    _county(root, date(2026, 10, 16), 1360, "unknown", datetime(2026, 10, 26, 19, 41, tzinfo=UTC))
    oct19 = _rows(date(2026, 10, 19), 1286)
    # Re-parsing the Oct 19 capture later must decide as it did at the time.
    assert runner._county_drop(oct19, datetime(2026, 10, 19, 20, tzinfo=UTC), root) is None
    # Even a capture fetched after the mixed load never uses it as a baseline.
    assert runner._county_drop(oct19, datetime(2026, 10, 27, tzinfo=UTC), root) is None
    # A genuine broken load is still caught against the trusted baseline.
    low = _rows(date(2026, 10, 19), 1200)
    assert "county sum 1200" in str(
        runner._county_drop(low, datetime(2026, 10, 19, 20, tzinfo=UTC), root)
    )
