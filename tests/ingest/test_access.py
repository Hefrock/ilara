"""Curated store and views (WP3e): T3.9, E20 tie-breaks, idempotent writes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from ingest import access
from ingest.capture_log import CaptureLog, CaptureRecord
from ingest.curate import store


def _rows(
    cum: int, fetched: datetime, pv: str = "1.0.0", d: date = date(2026, 10, 5), sha: str = "a" * 64
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "jurisdiction": ["PA"],
            "disease": ["measles"],
            "source_id": ["doh_dashboard"],
            "source_tier": ["T1"],
            "as_of_date": [d],
            "fetched_at_utc": [fetched],
            "ingest_run_id": [store.ingest_run_id(sha, pv)],
            "raw_sha256": [sha],
            "parser_version": [pv],
            "cum_cases": [cum],
            "count_definition": ["calendar_year"],
            "date_precision": ["exact"],
        }
    )


def _write(root: Path, df: pl.DataFrame) -> Path | None:
    r = df.row(0, named=True)
    return store.write("curated", "case_state", df, r["ingest_run_id"], r["fetched_at_utc"], root)


T1 = datetime(2026, 10, 5, 19, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 6, 13, 0, tzinfo=UTC)
T3 = datetime(2026, 10, 7, 19, 0, tzinfo=UTC)


def test_as_known_at_revisions(root: Path) -> None:  # T3.9
    _write(root, _rows(1004, T1, sha="1" * 64))
    _write(root, _rows(1006, T2, sha="2" * 64))  # revision of the same as_of_date
    _write(root, _rows(1030, T3, sha="3" * 64, d=date(2026, 10, 7)))
    before = access.as_known_at("case_state", datetime(2026, 10, 5, 23, tzinfo=UTC), root=root)
    assert before["cum_cases"].to_list() == [1004]
    mid = access.as_known_at("case_state", T2, root=root)
    assert mid["cum_cases"].to_list() == [1006]
    assert (mid["fetched_at_utc"] <= T2).all()
    now = access.current("case_state", root=root)
    assert now.sort("as_of_date")["cum_cases"].to_list() == [1006, 1030]
    with pytest.raises(ValueError):
        access.as_known_at("case_state", datetime(2026, 10, 6), root=root)


def test_parser_version_tie_break(root: Path) -> None:  # E20
    _write(root, _rows(1000, T1, pv="1.9.0"))
    _write(root, _rows(1001, T1, pv="1.10.0"))
    assert access.current("case_state", root=root)["cum_cases"].to_list() == [1001]


def test_write_is_idempotent_and_partitioned(root: Path) -> None:
    df = _rows(1004, T1)
    p = _write(root, df)
    assert p is not None and p.relative_to(root).as_posix().startswith(
        "data/curated/case_state/2026-10/"
    )
    assert _write(root, df) is None
    assert access.all_rows("case_state", root=root).height == 1


def test_empty_table_has_schema(root: Path) -> None:
    df = access.current("case_county", root=root)
    assert df.height == 0 and "county_fips" in df.columns and "raw_sha256" in df.columns


def test_unknown_column_rejected(root: Path) -> None:
    with pytest.raises(ValueError):
        _write(root, _rows(1, T1).with_columns(pl.lit(1).alias("bogus")))


def test_capture_status(root: Path) -> None:
    log = CaptureLog("r1", root)
    for t, outcome in (("2026-10-05T18:00:05Z", "changed"), ("2026-10-07T18:00:05Z", "failed")):
        log.append(
            CaptureRecord(
                capture_id=t,
                source_id="doh_dashboard",
                url="u",
                started_utc=t,
                finished_utc=t,
                http_status=None,
                outcome=outcome,
                raw_path=None,
                sha256=None,
                content_hash=None,
                bytes=None,
                runner="local",
            )
        )
    st = access.capture_status(root).row(0, named=True)
    assert st["outcome"] == "failed" and st["last_good_utc"] == "2026-10-05T18:00:05Z"
