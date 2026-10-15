"""Replay leak guard (T6.13): every read made at a cutoff passes through ``check_known``, so a
reader that ignored the cutoff cannot bring future data into a validation fit."""

from __future__ import annotations

from datetime import datetime

import polars as pl


class LeakError(RuntimeError):
    """A replay read a row fetched after its cutoff."""


def check_known(df: pl.DataFrame, known_at: datetime | None, table: str) -> pl.DataFrame:
    if known_at is not None and df.height and "fetched_at_utc" in df.columns:
        late = df.filter(pl.col("fetched_at_utc") > known_at)
        if late.height:
            raise LeakError(f"{table}: {late.height} rows fetched after {known_at.isoformat()}")
    return df
