"""``measles parse``: run registered parsers over saved raw files (E13, E19, E20).

Deterministic and idempotent: one ``ingest_run_id`` per (raw file, parser version), and a
run whose outputs exist is skipped. A parser error never loses data: the raw file stays, a
quarantine row and a ``PARSE_SCHEMA_CHANGE`` flag record it, and a fixed parser re-runs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from ingest import access, paths, rawstore
from ingest.curate import store
from ingest.parse import doh_dashboard, doh_release, school_imm
from ingest.timeutil import ET, parse_utc


@dataclass
class ParseReport:
    parsed: list[str] = field(default_factory=list)
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    rows: dict[str, int] = field(default_factory=dict)
    flags: int = 0


@dataclass(frozen=True)
class Parser:
    source_id: str
    capture_key: str | None
    version: str
    fn: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, pl.DataFrame | list]]


def _flag(
    code: str, ref: str, text: str, run_id: str, version: str, when: datetime
) -> dict[str, Any]:
    fid = hashlib.sha256(f"{code}|{ref}|{text}".encode()).hexdigest()[:16]
    return {
        "flag_id": fid,
        "raised_utc": when,
        "severity": "warning",
        "code": code,
        "ref_raw_sha256": ref,
        "description": text,
        "status": "open",
        "ingest_run_id": run_id,
        "parser_version": version,
        "fetched_at_utc": when,
    }


def _common(
    m: dict[str, Any],
    run_id: str,
    version: str,
    tier: str = "T1",
    label: str = doh_dashboard.SOURCE_LABEL,
) -> dict[str, Any]:
    fetched = parse_utc(m["fetched_at_utc"])
    return {
        "jurisdiction": "PA",
        "disease": "measles",
        "source_id": m["source_id"],
        "source_tier": tier,
        "fetched_at_utc": fetched,
        "fetched_at_et": fetched.astimezone(ET).isoformat(timespec="seconds"),
        "ingest_run_id": run_id,
        "raw_sha256": m["sha256"],
        "parser_version": version,
        "source_label": label,
        "source_url": m["url"],
        "url_status": "verified",
    }


def _dashboard(m: dict[str, Any], run_id: str, root: Path) -> dict[str, Any]:
    bundle = json.loads(rawstore.read_payload(m, root))
    out = doh_dashboard.parse(bundle)
    common = _common(m, run_id, doh_dashboard.PARSER_VERSION)
    state = [{**common, **r} for r in out["state"]]
    county = [{**common, **r} for r in out["county"]]
    doses = [{**common, **r} for r in out["doses"]]
    return {
        "case_state": state,
        "case_county": county,
        "vaccine_doses": doses,
        "flags": out["flags"],
    }


def _school_county(m: dict[str, Any], run_id: str, root: Path) -> dict[str, Any]:
    rows = school_imm.parse(rawstore.read_payload(m, root))
    common = _common(m, run_id, school_imm.PARSER_VERSION, label=school_imm.SOURCE_LABEL)
    return {"immunization_county": [{**common, **r} for r in rows], "flags": []}


def _school_level(m: dict[str, Any], run_id: str, root: Path) -> dict[str, Any]:
    rows = school_imm.parse_school(rawstore.read_payload(m, root))
    common = _common(m, run_id, school_imm.PARSER_VERSION, label=school_imm.SCHOOL_SOURCE_LABEL)
    return {"immunization_school": [{**common, **r} for r in rows], "flags": []}


def _release(m: dict[str, Any], run_id: str, root: Path) -> dict[str, Any]:
    out = doh_release.parse(rawstore.read_payload(m, root))
    common = _common(m, run_id, doh_release.PARSER_VERSION, label=doh_release.SOURCE_LABEL)
    return {"case_state": [{**common, **r} for r in out["state"]], "flags": []}


PARSERS = {
    ("doh_dashboard", "responses"): (doh_dashboard.PARSER_VERSION, _dashboard),
    ("doh_school_imm_county", None): (school_imm.PARSER_VERSION, _school_county),
    ("doh_school_imm_school", None): (school_imm.PARSER_VERSION, _school_level),
    ("doh_release", "*"): (doh_release.PARSER_VERSION, _release),  # one document per URL
}
OUTPUT_TABLES = (
    "case_state",
    "case_county",
    "immunization_county",
    "immunization_school",
    "vaccine_doses",
)


def _outputs_exist(run_id: str, when: datetime, root: Path) -> bool:
    month = f"{when:%Y-%m}"
    base = paths.curated_dir(root)
    return any(base.glob(f"*/{month}/{run_id}.parquet")) or any(
        (base / "quarantine").glob(f"{month}/{run_id}.parquet")
    )


def _county_drop(rows: list[dict[str, Any]], root: Path) -> str | None:
    """T3.15: fewer counties with cases than the latest earlier snapshot of the same source."""
    if not rows:
        return None
    as_of = rows[0]["as_of_date"]
    prev = access.current("case_county", root=root)
    prev = prev.filter(
        (pl.col("source_id") == rows[0]["source_id"]) & (pl.col("as_of_date") < as_of)
    )
    if prev.height == 0:
        return None
    last = str(prev["as_of_date"].max())
    before = prev.filter(
        (pl.col("as_of_date") == prev["as_of_date"].max()) & (pl.col("cum_cases") > 0)
    ).height
    now = sum(1 for r in rows if (r["cum_cases"] or 0) > 0)
    if now < before:
        return f"{now} counties with cases on {as_of}, {before} on {last}"
    return None


def run(root: Path | None = None, source: str | None = None) -> ParseReport:
    root = root or paths.repo_root()
    rep = ParseReport()
    manifests = [rawstore.load_manifest(p) for p in rawstore.iter_manifests(source, root)]
    manifests.sort(key=lambda m: m["fetched_at_utc"])  # oldest first, for T3.15
    for m in manifests:
        key = (m["source_id"], m.get("capture_key"))
        if key not in PARSERS:
            key = (m["source_id"], "*")
            if key not in PARSERS:
                continue
        version, fn = PARSERS[key]
        run_id = store.ingest_run_id(m["sha256"], version)
        when = parse_utc(m["fetched_at_utc"])
        if _outputs_exist(run_id, when, root):
            rep.skipped += 1
            continue
        try:
            out = fn(m, run_id, root)
        except Exception as e:  # noqa: BLE001 - quarantine, never crash or lose data
            text = f"{m['raw_path']}: {type(e).__name__}: {e}"
            store.write(
                "curated",
                "quarantine",
                pl.DataFrame(
                    [
                        {
                            "table": key[0],
                            "row_json": json.dumps({"raw_path": m["raw_path"]}),
                            "reason_code": "PARSE_SCHEMA_CHANGE",
                            "ref": m["sha256"],
                            "ingest_run_id": run_id,
                            "parser_version": version,
                            "fetched_at_utc": when,
                        }
                    ]
                ),
                run_id,
                when,
                root,
            )
            store.write(
                "curated",
                "data_quality_flag",
                pl.DataFrame(
                    [_flag("PARSE_SCHEMA_CHANGE", m["sha256"], text, run_id, version, when)]
                ),
                run_id,
                when,
                root,
            )
            rep.failed.append(text)
            rep.flags += 1
            continue
        flags = [_flag(c, m["sha256"], t, run_id, version, when) for c, t in out["flags"]]
        drop = _county_drop(out.get("case_county", []), root)
        if drop:
            flags.append(_flag("COUNTY_COUNT_DROP", m["sha256"], drop, run_id, version, when))
            store.write(
                "curated",
                "quarantine",
                pl.DataFrame(
                    [
                        {
                            "table": "case_county",
                            "row_json": json.dumps(r, default=str, sort_keys=True),
                            "reason_code": "COUNTY_COUNT_DROP",
                            "ref": m["sha256"],
                            "ingest_run_id": run_id,
                            "parser_version": version,
                            "fetched_at_utc": when,
                        }
                        for r in out["case_county"]
                    ]
                ),
                run_id,
                when,
                root,
            )
            out["case_county"] = []
        for table in OUTPUT_TABLES:
            if out.get(table):
                store.write(
                    "curated",
                    table,
                    pl.DataFrame(out[table], infer_schema_length=None),
                    run_id,
                    when,
                    root,
                )
                rep.rows[table] = rep.rows.get(table, 0) + len(out[table])
        if flags:
            store.write("curated", "data_quality_flag", pl.DataFrame(flags), run_id, when, root)
            rep.flags += len(flags)
        rep.parsed.append(m["raw_path"])
    return rep
