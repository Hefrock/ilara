"""How DOH's onset-week curve is revised from one dashboard update to the next (ADR 0015).

    python -m project.validation.onset_review

Observed data only (T1 ``case_demographics``, dimension ``onset_week``); no model. It prints the
tables in ``docs/onset_review.md``: the recent weeks as each data date showed them; for weeks
old enough to have settled, each earlier count as a share of the latest count by how long after
the week started it was seen; and how often counts move, including down.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl

from ingest import access

DASHBOARD = "doh_dashboard"
SETTLED_DAYS = 21  # a week whose latest count was seen this long after it started


def onset_snapshots(root: Path | None = None) -> pl.DataFrame:
    """One row per (data date, onset week): ``as_of_date``, ``week`` (its Monday), ``cases``.
    Every capture and parser version of the same data date must agree; one value is kept."""
    d = access.all_rows("case_demographics", root=root).filter(
        (pl.col("source_id") == DASHBOARD)
        & (pl.col("source_tier") == "T1")
        & (pl.col("dimension") == "onset_week")
        & pl.col("county_fips").is_null()
    )
    if d.height == 0:
        return pl.DataFrame(schema={"as_of_date": pl.Date, "week": pl.Date, "cases": pl.Int64})
    g = d.group_by("as_of_date", "category").agg(
        pl.col("cases").n_unique().alias("n"), pl.col("cases").first()
    )
    bad = g.filter(pl.col("n") > 1)
    if bad.height:
        raise ValueError(f"captures of the same data date disagree: {bad.head(5).to_dicts()}")
    return g.select(
        "as_of_date",
        pl.col("category").str.to_date().alias("week"),
        pl.col("cases").cast(pl.Int64),
    ).sort("as_of_date", "week")


def recent_table(s: pl.DataFrame, weeks: int = 8) -> pl.DataFrame:
    """The last ``weeks`` onset weeks (rows) as each data date showed them (columns)."""
    keep = s["week"].unique().sort()[-weeks:].to_list()
    dates = [d.isoformat() for d in s["as_of_date"].unique().sort()]
    return (
        s.filter(pl.col("week").is_in(keep))
        .with_columns(pl.col("as_of_date").cast(pl.String))
        .pivot(on="as_of_date", index="week", values="cases")
        .select("week", *dates)
        .sort("week")
    )


def share_of_latest(
    s: pl.DataFrame, settled_days: int = SETTLED_DAYS, max_lag_weeks: int = 6
) -> pl.DataFrame:
    """Earlier counts of settled weeks (latest count seen at least ``settled_days`` after the
    week started, and above zero) as a share of that latest count, by week of lag at which
    the earlier count was seen (1 = 7 to 13 days after the week started), up to
    ``max_lag_weeks`` (older weeks of the year have small counts, so their shares are noise)."""
    latest_date: date = s["as_of_date"].max()  # type: ignore[assignment]
    last = s.filter(pl.col("as_of_date") == latest_date).select(
        "week", pl.col("cases").alias("latest")
    )
    settled = last.filter(
        (pl.col("latest") > 0) & (pl.col("week") <= latest_date - timedelta(days=settled_days))
    )
    return (
        s.filter(pl.col("as_of_date") < latest_date)
        .join(settled, on="week")
        .with_columns(
            ((pl.col("as_of_date") - pl.col("week")).dt.total_days() // 7).alias("lag_weeks"),
            (pl.col("cases") / pl.col("latest")).alias("share"),
        )
        .filter(pl.col("lag_weeks") <= max_lag_weeks)
        .group_by("lag_weeks")
        .agg(
            pl.len().alias("counts"),
            pl.col("share").min().round(2).alias("min_share"),
            pl.col("share").median().round(2).alias("median_share"),
            pl.col("share").max().round(2).alias("max_share"),
        )
        .sort("lag_weeks")
    )


def moves(s: pl.DataFrame) -> pl.DataFrame:
    """Every change in a week's count between consecutive data dates."""
    return (
        s.sort("week", "as_of_date")
        .with_columns(pl.col("cases").shift(1).over("week").alias("before"))
        .filter(pl.col("before").is_not_null() & (pl.col("cases") != pl.col("before")))
        .with_columns(
            (pl.col("cases") - pl.col("before")).alias("change"),
            (pl.col("as_of_date") - pl.col("week")).dt.total_days().alias("days_after_start"),
        )
        .select("as_of_date", "week", "days_after_start", "before", "cases", "change")
    )


def main() -> int:
    s = onset_snapshots()
    if s.height == 0:
        print("no onset-week data")
        return 0
    pl.Config.set_tbl_rows(100)
    pl.Config.set_tbl_formatting("MARKDOWN")
    pl.Config.set_tbl_hide_column_data_types(True)
    pl.Config.set_tbl_hide_dataframe_shape(True)
    dates = s["as_of_date"].unique().sort()
    print(f"data dates: {', '.join(d.isoformat() for d in dates)}\n")
    print(recent_table(s), "\n")
    print(share_of_latest(s), "\n")
    m = moves(s)
    old = m.filter(pl.col("days_after_start") > 28)
    largest = int(old["change"].abs().max()) if old.height else 0  # type: ignore[arg-type]
    print(
        f"changes: {m.height}; decreases: {m.filter(pl.col('change') < 0).height}; "
        f"to weeks over four weeks old: {old.height} (largest {largest})\n"
    )
    print(m.filter(pl.col("days_after_start") <= 28))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
