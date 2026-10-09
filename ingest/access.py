"""The only data access module for ``project/`` (I8). DuckDB over Parquet (E01, 4.5).

- ``current(table)``: per natural key, the row with the greatest ``fetched_at_utc``, then
  the highest ``parser_version`` (E20), then the highest ``raw_sha256`` so that ties between
  documents are broken the same way every time. The quality engine flags such ties when the
  documents disagree (``SOURCE_CONFLICT``).
- ``as_known_at(table, T)``: ``current`` over rows with ``fetched_at_utc <= T`` only. The only
  source for validation replay (E11).
- ``capture_status()``: latest capture outcome per source.
- ``county_scope(scope)``: an event's ``county_scope`` resolved through the crosswalk.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import duckdb
import polars as pl

from ingest import capture_log, paths, schedule
from ingest.curate.schema import NATURAL_KEYS, conform
from ingest.curate.schema import SCHOOL_CALENDAR_TITLES as SCHOOL_CALENDAR_TITLES  # for project/
from ingest.curate.store import store_dir
from ingest.reference import crosswalk


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


def capture_days(now: datetime, root: Path | None = None) -> pl.DataFrame:
    """Every scheduled dashboard capture day (HANDOFF 8.1) from the first scheduled window to
    ``now``. ``status`` is ``covered`` (a changed or unchanged dashboard capture finished
    between 18:00 and 23:59 UTC that day), ``missed``, or ``pending`` while that window is
    still open. ``catch_up`` counts good captures the next morning before 18:00 UTC; they do
    not cover the day (the data shown that afternoon may be lost) but are listed."""
    recs = [
        r
        for r in capture_log.read_all(root or paths.repo_root())
        if r["source_id"] == "doh_dashboard" and r["outcome"] in ("changed", "unchanged")
    ]
    done = [datetime.fromisoformat(r["finished_utc"].replace("Z", "+00:00")) for r in recs]
    rows = []
    day = schedule.SCHEDULE_START
    while day <= now.astimezone(UTC).date():
        if day.weekday() in schedule.CAPTURE_DAYS:
            start = datetime.combine(day, time(schedule.COVER_START_HOUR_UTC), UTC)
            end = datetime.combine(day + timedelta(days=1), time(0), UTC)
            catch_end = end + timedelta(hours=schedule.COVER_START_HOUR_UTC)
            n = sum(start <= t < end for t in done)
            status = "covered" if n else ("pending" if now < end else "missed")
            rows.append(
                {
                    "day": day,
                    "status": status,
                    "captures": n,
                    "catch_up": sum(end <= t < catch_end for t in done),
                }
            )
        day += timedelta(days=1)
    return pl.DataFrame(
        rows,
        schema={"day": pl.Date, "status": pl.Utf8, "captures": pl.Int64, "catch_up": pl.Int64},
    )


# Sources whose statewide counts are cross-checks of the DOH figures (S6), not part of the DOH
# series: they are compared with it but never joined to it.
CROSSCHECK_SOURCES = frozenset({"cdc_measles_cases_map"})


# ---------------------------------------------------------------- reference data (WP1)

_REF_SCHEMA = {
    "county_fips": pl.Utf8,
    "a_fips": pl.Utf8,
    "b_fips": pl.Utf8,
    "origin": pl.Utf8,
    "dest": pl.Utf8,
}


def reference_table(name: str, root: Path | None = None) -> pl.DataFrame:
    """A reference CSV such as ``geography_county`` or ``population_county``."""
    p = paths.reference_dir(root) / f"{name}.csv"
    if not p.exists():
        raise FileNotFoundError(f"reference table {name} not built (run measles reference build)")
    head = p.read_text().splitlines()[0].split(",")
    return pl.read_csv(p, schema_overrides={k: v for k, v in _REF_SCHEMA.items() if k in head})


def reference_geojson(root: Path | None = None) -> dict:
    """Simplified county boundaries (EPSG:4326) keyed by ``county_fips``."""
    import json

    p = paths.reference_dir(root) / "county_simplified.geojson"
    return json.loads(p.read_text())


def open_flags(root: Path | None = None) -> pl.DataFrame:
    """Open data quality flags of the curated store (latest row per flag)."""
    df = current("data_quality_flag", "curated", root)
    return df.filter(pl.col("status") == "open") if df.height else df


SCOPE_TOKENS = frozenset({"state", "affected_counties"})


def county_scope(scope: str, root: Path | None = None) -> list[str]:
    """FIPS codes (or the tokens ``state`` and ``affected_counties``) for an event's
    ``;``-separated ``county_scope``. Names resolve only through the crosswalk; an unknown name
    raises rather than being guessed."""
    ref = reference_table("county_crosswalk", root)
    xw = dict(ref.select("variant_normalized", "county_fips").rows())
    out = []
    for part in (p.strip() for p in scope.split(";")):
        out.append(part if part in SCOPE_TOKENS else crosswalk.resolve(part, xw))
    return out
