"""``measles rebuild`` (HANDOFF 4.4, T3.2, I2).

Rebuild the curated and sensitivity tables from ``data/raw`` and the seed folders into a
temporary directory, then compare the rebuilt ``current`` views (as logical rows) and the
quarantine contents with the committed ones. Data quality flags raised by the quality engine
carry their run time and are not compared. Quarantine is compared for the newest parser
version of each raw reference only.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import polars as pl

from ingest import access, paths
from ingest.curate import seed
from ingest.curate.schema import NATURAL_KEYS
from ingest.parse import runner

COPY = ("raw", "seed", "registry", "capture_log", "reference")
TABLES = tuple(t for t in NATURAL_KEYS if t != "data_quality_flag")


def _logical(df: pl.DataFrame) -> pl.DataFrame:
    if df.height == 0:
        return df
    return df.sort(df.columns, nulls_last=True)


def _quarantine(st: str, root: Path) -> pl.DataFrame:
    """Quarantine rows from the newest parser version per raw reference: a parser upgrade
    re-parses old raw files, and a rebuild only runs the current parsers."""
    q = access.all_rows("quarantine", st, root)
    if q.height:
        v = pl.col("parser_version").fill_null("0").str.split(".").cast(pl.List(pl.Int64))
        q = q.with_columns(v.alias("_v")).filter(pl.col("_v") == pl.col("_v").max().over("ref"))
    return _logical(q.select("table", "row_json", "reason_code", "ref", "ingest_run_id"))


def build_into(src_root: Path, dest_root: Path) -> None:
    for name in COPY:
        src = paths.data_dir(src_root) / name
        if src.exists():
            shutil.copytree(src, paths.data_dir(dest_root) / name)
    sens_seed = paths.sensitivity_dir(src_root) / "seed"
    if sens_seed.exists():
        shutil.copytree(sens_seed, paths.sensitivity_dir(dest_root) / "seed")
    for mf in (
        paths.data_dir(dest_root) / "seed" / "MANIFEST.json",
        paths.sensitivity_dir(dest_root) / "seed" / "MANIFEST.json",
    ):
        if not mf.exists() and mf.parent.exists() and any(mf.parent.glob("*.csv")):
            raise seed.SeedError(f"{mf} missing: seed files were never loaded and committed")
    seed.load(dest_root)
    runner.run(dest_root)


def compare(a_root: Path, b_root: Path) -> list[str]:
    diffs: list[str] = []
    for st in ("curated", "sensitivity"):
        for table in TABLES:
            a = _logical(access.current(table, st, a_root))
            b = _logical(access.current(table, st, b_root))
            if a.height != b.height or not a.equals(b):
                diffs.append(
                    f"{st}/{table}: committed {a.height} rows, rebuilt {b.height} rows differ"
                )
        qa, qb = _quarantine(st, a_root), _quarantine(st, b_root)
        if qa.height != qb.height or not qa.equals(qb):
            diffs.append(f"{st}/quarantine: committed {qa.height} rows, rebuilt {qb.height}")
    return diffs


def rebuild(root: Path | None = None) -> list[str]:
    root = root or paths.repo_root()
    with tempfile.TemporaryDirectory(prefix="measles-rebuild-") as td:
        tmp = Path(td)
        build_into(root, tmp)
        return compare(root, tmp)
