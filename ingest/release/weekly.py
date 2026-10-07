"""``measles release --week YYYY-Www`` (WP4, E07, HANDOFF 8.1).

The release for ISO week W covers Monday 00:00 to Sunday 24:00 America/New_York. Everything in
it is read as known at the week's end (``as_known_at``), so re-running later gives the same
manifest (T4.3, T4.6). It never interpolates: missed capture days are listed, not filled.

Writes:
- ``data/releases/data-YYYY-Www.json`` (append-only; a re-run must reproduce it byte for byte)
- ``data/exports/<table>_current.csv`` for the public (curated) tables, as known at week end
- ``data/RELEASE_NOTES.md``, regenerated from all release manifests

Fails closed (no files written) when ``verify`` reports a problem (T4.4).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ingest import access, capture_log, paths, rawstore, schedule
from ingest.timeutil import ET, iso_utc, parse_utc, utc_now
from ingest.verify import verify_all

RELEASE_VERSION = "1.0.0"
EXPORT_TABLES = ("case_state", "case_county", "event")
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
DASHBOARD = "doh_dashboard"


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Week:
    year: int
    week: int

    @classmethod
    def parse(cls, text: str) -> Week:
        m = WEEK_RE.match(text)
        if not m:
            raise ReleaseError(f"week must look like 2026-W41, got {text!r}")
        return cls(int(m.group(1)), int(m.group(2)))

    @property
    def label(self) -> str:
        return f"{self.year}-W{self.week:02d}"

    @property
    def monday(self) -> date:
        return date.fromisocalendar(self.year, self.week, 1)

    @property
    def start_utc(self) -> datetime:
        return datetime.combine(self.monday, time(0), ET).astimezone(UTC)

    @property
    def end_utc(self) -> datetime:
        """Exclusive end: the following Monday 00:00 ET."""
        nxt = self.monday + timedelta(days=7)
        return datetime.combine(nxt, time(0), ET).astimezone(UTC)

    @property
    def capture_days(self) -> list[date]:
        return [self.monday + timedelta(days=d) for d in schedule.CAPTURE_DAYS]


def covered_days(week: Week, log: list[dict[str, Any]]) -> dict[str, list[str]]:
    """HANDOFF 8.1: a capture day is covered by a dashboard capture with outcome changed or
    unchanged finishing between 18:00 and 23:59 UTC that day."""
    out: dict[str, list[str]] = {}
    for day in week.capture_days:
        start = datetime.combine(day, time(schedule.COVER_START_HOUR_UTC), UTC)
        end = datetime.combine(day + timedelta(days=1), time(0), UTC)
        out[day.isoformat()] = sorted(
            r["capture_id"]
            for r in log
            if r["source_id"] == DASHBOARD
            and r["outcome"] in ("changed", "unchanged")
            and start <= parse_utc(r["finished_utc"]) < end
        )
    return out


def _data_commit(root: Path, end: datetime) -> str | None:
    try:
        out = subprocess.run(
            [
                "git",
                "log",
                "-1",
                f"--before={iso_utc(end - timedelta(seconds=1))}",
                "--format=%H",
                "--",
                "data/",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out or None


def _known(table: str, end: datetime, root: Path) -> pl.DataFrame:
    # as_known_at includes rows fetched at exactly T; the week end is exclusive.
    return access.as_known_at(table, end - timedelta(microseconds=1), "curated", root)


def build_manifest(week: Week, root: Path) -> dict[str, Any]:
    start, end = week.start_utc, week.end_utc
    log = capture_log.read_all(root)
    in_week = [r for r in log if start <= parse_utc(r["finished_utc"]) < end]
    cover = covered_days(week, log)
    raws = sorted(
        (
            m
            for m in map(rawstore.load_manifest, rawstore.iter_manifests(None, root))
            if parse_utc(m["fetched_at_utc"]) < end
        ),
        key=lambda m: (m["fetched_at_utc"], m["raw_path"]),
    )
    week_raws = [
        {"source_id": m["source_id"], "raw_path": m["raw_path"], "sha256": m["sha256"]}
        for m in raws
        if parse_utc(m["fetched_at_utc"]) >= start
    ]
    all_digest = hashlib.sha256("\n".join(m["sha256"] for m in raws).encode()).hexdigest()

    tables: dict[str, Any] = {}
    for t in EXPORT_TABLES:
        known = _known(t, end, root)
        new = known.filter(pl.col("fetched_at_utc") >= start)
        entry: dict[str, Any] = {"rows_known": known.height, "rows_new": new.height}
        if t in ("case_state", "case_county") and known.height:
            entry["latest_as_of_date"] = {
                f"{s}|{d}": str(v)
                for s, d, v in known.group_by(["source_id", "count_definition"])
                .agg(pl.col("as_of_date").max())
                .sort(["source_id", "count_definition"])
                .rows()
            }
            entry["count_definitions_new"] = sorted(set(new["count_definition"].to_list()))
        tables[t] = entry

    flags = access.all_rows("data_quality_flag", "curated", root)
    flags = flags.filter((pl.col("raised_utc") >= start) & (pl.col("raised_utc") < end))
    by_code = flags.group_by("code").len().sort("code").rows()

    headline = (
        _known("case_state", end, root).filter(pl.col("source_id") == DASHBOARD).sort("as_of_date")
    )
    latest = {
        r["count_definition"]: {
            "as_of_date": str(r["as_of_date"]),
            "cum_cases": r["cum_cases"],
            "counties_with_cases": r["counties_with_cases"],
            "hospitalizations": r["hospitalizations"],
            "deaths": r["deaths"],
            "new_7day": r["new_7day"],
        }
        for r in headline.to_dicts()
    }

    return {
        "release": f"data-{week.label}",
        "release_version": RELEASE_VERSION,
        "week": week.label,
        "week_start_utc": iso_utc(start),
        "week_end_utc": iso_utc(end),
        "timezone": "America/New_York",
        "data_commit_sha": _data_commit(root, end),
        "capture_days": {d: {"covered": bool(ids), "captures": ids} for d, ids in cover.items()},
        "uncovered_days": [d for d, ids in cover.items() if not ids],
        "captures_in_week": {
            o: sum(1 for r in in_week if r["outcome"] == o)
            for o in ("changed", "unchanged", "failed", "blocked")
        },
        "inputs": {
            "raw_files_in_week": week_raws,
            "raw_files_total": len(raws),
            "raw_sha256_digest": all_digest,
        },
        "tables": tables,
        "flags_raised": dict(by_code),
        "latest_dashboard": latest,
        "interpolated_values": 0,
        "notes": "Counts are a floor. Missed capture days are listed, never filled.",
    }


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def write_exports(week: Week, root: Path) -> list[Path]:
    out = []
    d = paths.data_dir(root) / "exports"
    d.mkdir(parents=True, exist_ok=True)
    for t in EXPORT_TABLES:
        df = _known(t, week.end_utc, root)
        p = d / f"{t}_current.csv"
        df.write_csv(p)
        out.append(p)
    return out


def write_notes(root: Path) -> Path:
    rel = paths.data_dir(root) / "releases"
    lines = [
        "# Release notes",
        "",
        "Weekly data releases (HANDOFF WP4). Unofficial independent project; counts are a "
        "floor. Each release manifest is in `data/releases/`.",
        "",
    ]
    for p in sorted(rel.glob("data-*.json"), reverse=True):
        m = json.loads(p.read_text())
        lines.append(f"## {m['release']} ({m['week_start_utc'][:10]} to week end, ET)")
        lines.append("")
        cal = m["latest_dashboard"].get("calendar_year")
        if cal:
            lines.append(
                f"- Dashboard as of {cal['as_of_date']}: {cal['cum_cases']} cases "
                f"(calendar year), {cal['counties_with_cases']} counties, "
                f"{cal['hospitalizations']} hospitalized, {cal['deaths']} deaths, "
                f"{cal['new_7day']} new in the last 7 days."
            )
        else:
            lines.append("- No dashboard snapshot known by the end of the week.")
        unc = m["uncovered_days"]
        lines.append(
            "- Capture days covered: "
            f"{sum(1 for v in m['capture_days'].values() if v['covered'])} of "
            f"{len(m['capture_days'])}" + (f"; missed: {', '.join(unc)}" if unc else "")
        )
        lines.append(
            "- New rows: " + ", ".join(f"{t} {v['rows_new']}" for t, v in m["tables"].items())
        )
        if m["flags_raised"]:
            lines.append(
                "- Flags raised: " + ", ".join(f"{c} {n}" for c, n in m["flags_raised"].items())
            )
        lines.append(f"- Data commit: `{m['data_commit_sha'] or 'unknown'}`")
        lines.append("")
    p = paths.data_dir(root) / "RELEASE_NOTES.md"
    p.write_text("\n".join(lines))
    return p


def release(
    week_label: str,
    root: Path | None = None,
    *,
    check: bool = True,
    now: datetime | None = None,
) -> Path:
    root = root or paths.repo_root()
    week = Week.parse(week_label)
    now = now or utc_now()
    if now < week.end_utc:
        raise ReleaseError(f"{week.label} has not ended (ends {iso_utc(week.end_utc)})")
    if check:
        problems = verify_all(root)
        if problems:
            raise ReleaseError("verify failed; no release written:\n" + "\n".join(problems))
    manifest = _dump(build_manifest(week, root))
    path = paths.data_dir(root) / "releases" / f"data-{week.label}.json"
    if path.exists():
        if path.read_text() != manifest:
            raise ReleaseError(f"{path} exists with different content; releases are immutable")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(manifest)
    write_exports(week, root)
    write_notes(root)
    return path


def last_closed_week(now: datetime) -> str:
    """The ISO week that most recently ended (America/New_York)."""
    local = now.astimezone(ET).date()
    last_sunday = local - timedelta(days=(local.isoweekday() % 7) or 7)
    y, w, _ = last_sunday.isocalendar()
    return f"{y}-W{w:02d}"
