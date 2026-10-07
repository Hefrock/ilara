"""Seed loader (WP3b, HANDOFF 4.1 and 4.3).

- The location decides the store: ``data/seed/`` loads to curated and must be tier T1 only;
  ``data/sensitivity/seed/`` loads to the sensitivity store whatever the tier.
- The name decides the table: ``statewide_*`` to ``case_state``, ``county_*`` to
  ``case_county``, ``events*`` to ``event``.
- ``date_precision = to_confirm`` rows go to the store's quarantine with ``DATE_TO_CONFIRM``.
- Seed files are immutable once loaded. ``MANIFEST.json`` in each seed folder records each
  file's sha256 and ``seeded_utc`` the first time it is loaded; a later change of content is an
  error (corrections are new rows in a new file). ``seeded_utc`` is each row's
  ``fetched_at_utc``, so loading is deterministic and rebuilds are identical (I2).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from ingest import paths
from ingest.curate import store
from ingest.curate.schema import (
    COUNT_DEFINITIONS,
    DATE_PRECISIONS,
    EVENT_TYPES,
    TIERS,
)
from ingest.reference import crosswalk, pa_counties
from ingest.timeutil import ET, iso_utc, parse_utc, utc_now

PARSER_VERSION = "1.0.0"
COUNTY_TOKENS = frozenset({"state", "affected_counties"})
SOURCE_BY_TABLE = {
    "case_state": "seed_statewide",
    "case_county": "seed_t3_county",
    "event": "seed_events",
}
DEFAULT_TIER = {"case_county": "T3-derived"}  # the county seed file has no tier column


class SeedError(Exception):
    pass


@dataclass
class LoadReport:
    loaded: dict[str, int] = field(default_factory=dict)
    quarantined: dict[str, int] = field(default_factory=dict)
    flags: int = 0
    new_files: list[str] = field(default_factory=list)


def seed_dirs(root: Path) -> list[tuple[str, Path]]:
    return [
        ("curated", paths.data_dir(root) / "seed"),
        ("sensitivity", paths.sensitivity_dir(root) / "seed"),
    ]


def table_for(name: str) -> str | None:
    if name.startswith("statewide_"):
        return "case_state"
    if name.startswith("county_"):
        return "case_county"
    if name.startswith("events"):
        return "event"
    return None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def update_manifest(seed_dir: Path, now: datetime) -> tuple[dict[str, Any], list[str]]:
    """Add unseen files; fail on any changed file. Existing entries are never rewritten."""
    mpath = seed_dir / "MANIFEST.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {"files": {}}
    new: list[str] = []
    for f in sorted(seed_dir.glob("*.csv")):
        sha = _sha(f)
        entry = manifest["files"].get(f.name)
        if entry is None:
            manifest["files"][f.name] = {"sha256": sha, "seeded_utc": iso_utc(now)}
            new.append(f.name)
        elif entry["sha256"] != sha:
            raise SeedError(f"{f} changed after it was seeded; add corrections as a new file")
    for name in manifest["files"]:
        if not (seed_dir / name).exists():
            raise SeedError(f"{seed_dir / name} is listed in MANIFEST.json but missing")
    if new:
        mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest, new


def _blank(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _int(v: str | None) -> int | None:
    v = _blank(v)
    return int(v.replace(",", "")) if v is not None else None


def _resolve_scope(scope: str, xw: dict[str, str]) -> None:
    for part in scope.split(";"):
        part = part.strip()
        if part not in COUNTY_TOKENS:
            crosswalk.resolve(part, xw)


def _base(
    row: dict[str, str], table: str, file: str, entry: dict[str, Any], source_ids: dict[str, str]
) -> dict[str, Any]:
    fetched = parse_utc(entry["seeded_utc"])
    tier = _blank(row.get("source_tier")) or DEFAULT_TIER.get(table)
    return {
        "jurisdiction": "PA",
        "disease": "measles",
        "source_id": source_ids[table],
        "source_tier": tier,
        "fetched_at_utc": fetched,
        "fetched_at_et": fetched.astimezone(ET).isoformat(timespec="seconds"),
        "ingest_run_id": store.ingest_run_id(entry["sha256"], PARSER_VERSION),
        "raw_sha256": entry["sha256"],
        "seed_file": file,
        "seed_row": _blank(row.get("row_id")) or _blank(row.get("event_id")),
        "parser_version": PARSER_VERSION,
        "source_label": _blank(row.get("source_label")),
        "source_url": _blank(row.get("source_url")),
        "url_status": _blank(row.get("url_status")),
    }


def convert(
    row: dict[str, str], table: str, file: str, entry: dict[str, Any], xw: dict[str, str]
) -> dict[str, Any]:
    """One seed row to one table row. Raises ValueError for anything invalid."""
    out = _base(row, table, file, entry, SOURCE_BY_TABLE)
    if out["source_tier"] not in TIERS:
        raise ValueError(f"bad source_tier {out['source_tier']!r}")
    if table == "event":
        if row["event_type"] not in EVENT_TYPES:
            raise ValueError(f"bad event_type {row['event_type']!r}")
        _resolve_scope(row["county_scope"], xw)
        out.update(
            event_id=row["event_id"],
            event_type=row["event_type"],
            event_date=_blank(row.get("event_date")),
            county_scope=row["county_scope"],
            title=_blank(row.get("title")),
            detail=_blank(row.get("detail")),
            date_precision=_blank(row.get("date_precision")) or "exact",
        )
        return out
    precision = _blank(row.get("date_precision")) or "exact"
    definition = _blank(row.get("count_definition")) or "unknown"
    if precision not in DATE_PRECISIONS:
        raise ValueError(f"bad date_precision {precision!r}")
    if definition not in COUNT_DEFINITIONS:
        raise ValueError(f"bad count_definition {definition!r}")
    out.update(
        as_of_date=_blank(row.get("as_of_date")),
        cum_cases=_int(row.get("cum_cases")),
        count_definition=definition,
        date_precision=precision,
        as_of_date_end=_blank(row.get("as_of_date_end")),
        is_backfill=True,
        notes=_blank(row.get("notes")),
    )
    if table == "case_state":
        out.update(
            counties_with_cases=_int(row.get("counties_with_cases")),
            hospitalizations=_int(row.get("hospitalizations")),
            deaths=_int(row.get("deaths")),
            vaccinated_cases=_int(row.get("vaccinated_cases")),
            new_since_count=_int(row.get("new_since_count")),
            new_since_date=_blank(row.get("new_since_date")),
            new_7day=_int(row.get("new_7day")),
        )
    else:
        out["county_fips"] = crosswalk.resolve(row["county_name"], xw)
    if precision != "to_confirm" and out["as_of_date"] is None:
        raise ValueError("as_of_date missing for a row not marked to_confirm")
    return out


def _flag(
    code: str, ref: str, seed_row: str | None, desc: str, raised: datetime, run_id: str
) -> dict[str, Any]:
    fid = hashlib.sha256(f"{code}|{ref}|{seed_row}".encode()).hexdigest()[:16]
    return {
        "flag_id": fid,
        "raised_utc": raised,
        "severity": "warning",
        "code": code,
        "ref_raw_sha256": ref,
        "description": desc,
        "status": "open",
        "ingest_run_id": run_id,
        "parser_version": PARSER_VERSION,
        "fetched_at_utc": raised,
    }


def _quarantine(
    table: str, row: dict[str, str], reason: str, ref: str, run_id: str, fetched: datetime
) -> dict[str, Any]:
    return {
        "table": table,
        "row_json": json.dumps(row, sort_keys=True),
        "reason_code": reason,
        "ref": ref,
        "ingest_run_id": run_id,
        "parser_version": PARSER_VERSION,
        "fetched_at_utc": fetched,
    }


def load(root: Path | None = None, now: datetime | None = None) -> LoadReport:
    root = root or paths.repo_root()
    now = now or utc_now()
    xw = crosswalk.build(pa_counties.COUNTIES)
    report = LoadReport()
    for store_name, seed_dir in seed_dirs(root):
        if not seed_dir.exists():
            continue
        manifest, new = update_manifest(seed_dir, now)
        report.new_files += [f"{seed_dir.relative_to(root)}/{n}" for n in new]
        for file in sorted(manifest["files"]):
            table = table_for(file)
            if table is None:
                raise SeedError(f"{seed_dir / file}: name does not map to a table")
            entry = manifest["files"][file]
            rel = f"{seed_dir.relative_to(root).as_posix()}/{file}"
            rows = list(csv.DictReader(io.StringIO((seed_dir / file).read_text())))
            run_id = store.ingest_run_id(entry["sha256"], PARSER_VERSION)
            fetched = parse_utc(entry["seeded_utc"])
            good: list[dict[str, Any]] = []
            quarantine: list[dict[str, Any]] = []
            flags: list[dict[str, Any]] = []
            for row in rows:
                tier = _blank(row.get("source_tier")) or DEFAULT_TIER.get(table)
                if store_name == "curated" and tier != "T1":
                    raise SeedError(
                        f"{rel} row {row.get('row_id') or row.get('event_id')}: "
                        f"tier {tier!r} in data/seed (only T1 allowed)"
                    )
                seed_row = _blank(row.get("row_id")) or _blank(row.get("event_id"))
                try:
                    converted = convert(row, table, rel, entry, xw)
                except (ValueError, KeyError) as e:
                    quarantine.append(
                        _quarantine(table, row, "PARSE_SCHEMA_CHANGE", rel, run_id, fetched)
                    )
                    flags.append(
                        _flag(
                            "PARSE_SCHEMA_CHANGE",
                            entry["sha256"],
                            seed_row,
                            f"{rel} {seed_row}: {e}",
                            fetched,
                            run_id,
                        )
                    )
                    continue
                if converted.get("date_precision") == "to_confirm":
                    quarantine.append(
                        _quarantine(table, row, "DATE_TO_CONFIRM", rel, run_id, fetched)
                    )
                    flags.append(
                        _flag(
                            "DATE_TO_CONFIRM",
                            entry["sha256"],
                            seed_row,
                            f"{rel} {seed_row}: date to confirm",
                            fetched,
                            run_id,
                        )
                    )
                    continue
                good.append(converted)
            if good:
                df = pl.DataFrame(good, infer_schema_length=None)
                store.write(store_name, table, df, run_id, fetched, root)
            if quarantine:
                store.write(
                    store_name, "quarantine", pl.DataFrame(quarantine), run_id, fetched, root
                )
            if flags:
                store.write(
                    store_name, "data_quality_flag", pl.DataFrame(flags), run_id, fetched, root
                )
            key = f"{store_name}/{table}"
            report.loaded[key] = report.loaded.get(key, 0) + len(good)
            report.quarantined[key] = report.quarantined.get(key, 0) + len(quarantine)
            report.flags += len(flags)
    return report
