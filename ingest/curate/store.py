"""Write curated rows: ``data/<store>/<table>/<YYYY-MM>/<ingest_run_id>.parquet``."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import polars as pl

from ingest import paths
from ingest.curate.schema import STORES, conform


def ingest_run_id(raw_sha256: str, parser_version: str) -> str:
    return hashlib.sha256((raw_sha256 + parser_version).encode()).hexdigest()[:12]


def store_dir(store: str, root: Path | None = None) -> Path:
    if store not in STORES:
        raise ValueError(store)
    return paths.curated_dir(root) if store == "curated" else paths.sensitivity_dir(root)


def table_path(
    store: str, table: str, run_id: str, fetched_at: datetime, root: Path | None = None
) -> Path:
    base = store_dir(store, root)
    if table == "quarantine":
        return base / "quarantine" / f"{fetched_at:%Y-%m}" / f"{run_id}.parquet"
    return base / table / f"{fetched_at:%Y-%m}" / f"{run_id}.parquet"


def write(
    store: str,
    table: str,
    df: pl.DataFrame,
    run_id: str,
    fetched_at: datetime,
    root: Path | None = None,
) -> Path | None:
    """Write one ingest run's rows. Returns None when the file already exists: the same raw
    file and parser version always produce the same rows (E20), so this is idempotent."""
    if df.height == 0:
        return None
    path = table_path(store, table, run_id, fetched_at, root)
    if path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    out = conform(table, df)
    tmp = path.with_suffix(".tmp")
    out.write_parquet(tmp, compression="zstd", statistics=False)
    tmp.rename(path)
    return path
