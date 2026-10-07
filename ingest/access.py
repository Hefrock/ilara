"""The only data access module for ``project/`` (I8). DuckDB over Parquet (E01, 4.5).

- ``current(table)``: per natural key, the row with the greatest ``fetched_at_utc``, then
  the highest ``parser_version`` (E20), then the highest ``raw_sha256`` so that ties between
  documents are broken the same way every time. The quality engine flags such ties when the
  documents disagree (``SOURCE_CONFLICT``).
- ``as_known_at(table, T)``: ``current`` over rows with ``fetched_at_utc <= T`` only. The only
  source for validation replay (E11).
- ``capture_status()``: latest capture outcome per source.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb
import polars as pl

from ingest import capture_log, paths
from ingest.curate.schema import NATURAL_KEYS, conform
from ingest.curate.store import store_dir


def _files(table: str, store: str, root: Path | None) -> list[str]:
    base = store_dir(store, root)
    sub = base / "quarantine" if table == "quarantine" else base / table
    return sorted(str(p) for p in sub.rglob("*.parquet")) if sub.exists() else []


def all_rows(table: str, store: str = "curated", root: Path | None = None) -> pl.DataFrame:
    files = _files(table, store, root)
    if not files:
        return conform(table, pl.DataFrame())
    con = duckdb.connect()
    df = con.execute("SELECT * FROM read_parquet(?, union_by_name = true)", [files]).pl()
    return conform(table, df)


def _latest(df: pl.DataFrame, table: str) -> pl.DataFrame:
    keys = list(NATURAL_KEYS[table])
    if df.height == 0:
        return df
    con = duckdb.connect()
    con.register("t", df.to_arrow())
    order = (
        "fetched_at_utc DESC, "
        "list_transform(string_split(coalesce(parser_version, '0'), '.'), "
        "x -> TRY_CAST(x AS INTEGER)) DESC"
    )
    if "raw_sha256" in df.columns:  # deterministic when two documents share a key (rebuild)
        order += ", raw_sha256 DESC"
    part = ", ".join(f'"{k}"' for k in keys)
    sql = (
        f"SELECT * FROM t QUALIFY row_number() OVER (PARTITION BY {part} ORDER BY {order}) = 1 "
        f"ORDER BY {part}"
    )
    return conform(table, con.execute(sql).pl())


def current(table: str, store: str = "curated", root: Path | None = None) -> pl.DataFrame:
    return _latest(all_rows(table, store, root), table)


def as_known_at(
    table: str, t: datetime, store: str = "curated", root: Path | None = None
) -> pl.DataFrame:
    if t.tzinfo is None:
        raise ValueError("as_known_at needs a timezone-aware datetime")
    df = all_rows(table, store, root).filter(pl.col("fetched_at_utc") <= t)
    return _latest(df, table)


def capture_status(root: Path | None = None) -> pl.DataFrame:
    recs = capture_log.read_all(root or paths.repo_root())
    if not recs:
        return pl.DataFrame(
            schema={
                "source_id": pl.Utf8,
                "finished_utc": pl.Utf8,
                "outcome": pl.Utf8,
                "last_good_utc": pl.Utf8,
            }
        )
    df = pl.DataFrame(recs).select("source_id", "finished_utc", "outcome")
    good = (
        df.filter(pl.col("outcome").is_in(["changed", "unchanged"]))
        .group_by("source_id")
        .agg(pl.col("finished_utc").max().alias("last_good_utc"))
    )
    latest = df.sort("finished_utc").group_by("source_id").last()
    return latest.join(good, on="source_id", how="left").sort("source_id")
