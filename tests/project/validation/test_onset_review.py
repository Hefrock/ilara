"""Onset-week revision review (ADR 0015): observed data only, offline."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from project.validation import onset_review as r


def _s(rows: list[tuple[str, str, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "as_of_date": [date.fromisoformat(a) for a, _w, _c in rows],
            "week": [date.fromisoformat(w) for _a, w, _c in rows],
            "cases": [c for _a, _w, c in rows],
        }
    )


S = _s(
    [
        ("2026-10-16", "2026-09-21", 105),
        ("2026-10-16", "2026-10-12", 22),
        ("2026-10-23", "2026-09-21", 111),
        ("2026-10-23", "2026-10-12", 62),
        ("2026-10-23", "2026-10-19", 4),
        ("2026-10-26", "2026-09-21", 111),
        ("2026-10-26", "2026-10-12", 68),
        ("2026-10-26", "2026-10-19", 16),
    ]
)


def test_recent_table_shows_each_data_date() -> None:
    t = r.recent_table(S, weeks=2)
    assert t.columns == ["week", "2026-10-16", "2026-10-23", "2026-10-26"]
    assert t.filter(pl.col("week") == date(2026, 10, 19))["2026-10-16"].to_list() == [None]


def test_share_of_latest_uses_settled_weeks_only() -> None:
    sh = r.share_of_latest(S)
    # Only the week of Sep 21 is settled (latest seen 35 days after it started).
    assert sh["counts"].sum() == 2
    assert sh.filter(pl.col("lag_weeks") == 3)["median_share"].item() == round(105 / 111, 2)


def test_moves_include_decreases() -> None:
    s = _s([("2026-10-19", "2026-10-19", 6), ("2026-10-21", "2026-10-19", 2)])
    m = r.moves(s)
    assert m["change"].to_list() == [-4] and m["days_after_start"].to_list() == [2]


def test_disagreeing_captures_of_one_data_date_are_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = pl.DataFrame(
        {
            "source_id": ["doh_dashboard"] * 2,
            "source_tier": ["T1"] * 2,
            "dimension": ["onset_week"] * 2,
            "county_fips": [None, None],
            "as_of_date": [date(2026, 10, 19)] * 2,
            "category": ["2026-10-12"] * 2,
            "cases": [27, 28],
        }
    )
    monkeypatch.setattr(r.access, "all_rows", lambda *a, **k: rows)
    with pytest.raises(ValueError, match="disagree"):
        r.onset_snapshots()
