"""Quality checks (WP3d, HANDOFF T3.5 to T3.8) and ``data/quality/quality_report.md``.

Checks run per store (curated, sensitivity). Problems inside one store raise data quality
flags; comparisons across stores are reported, never flagged (T3.5). Flags are append-only and
idempotent: a flag's id is derived from its code and subject, and only new ids are written.
Nothing here edits a count (I5): the report shows conflicts, it does not resolve them.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from ingest import access, paths
from ingest.curate import store
from ingest.reference import pa_counties
from ingest.timeutil import iso_utc, parse_utc, utc_now

ENGINE_VERSION = "1.0.0"
STORES = ("curated", "sensitivity")
STALE_HOURS = {"doh_dashboard": 72 + 24}  # Mon/Wed/Fri cadence plus 24 h (HANDOFF 8.2)
STALE_HOURS_DEFAULT = 24 + 24  # daily light sources
DOUBLING_DAYS_REVIEW = 21.0  # growth steps worth a human look (T3.8)
MIN_STEP_CASES = 50


@dataclass
class Flag:
    code: str
    subject: str
    description: str
    severity: str = "warning"
    ref: str | None = None

    @property
    def flag_id(self) -> str:
        return hashlib.sha256(f"{self.code}|{self.subject}".encode()).hexdigest()[:16]


@dataclass
class Findings:
    flags: list[Flag] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)

    def add(self, section: str, line: str) -> None:
        self.sections.setdefault(section, []).append(line)


def _label(r: dict[str, Any]) -> str:
    who = r.get("seed_row") or (r.get("raw_sha256") or "")[:12]
    return f"{r['source_id']}:{who} ({r['source_tier']})"


def state_rows(store_name: str, root: Path) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
    """Current statewide rows of a store, plus statewide rows held in its quarantine."""
    main = access.current("case_state", store_name, root).filter(
        ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
    )
    q = access.all_rows("quarantine", store_name, root)
    held = [json.loads(r) for r in q.filter(pl.col("table") == "case_state")["row_json"]]
    return main, held


def _int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    return int(str(v).replace(",", ""))


def _date(v: Any) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v))


# ---------------------------------------------------------------- T3.5 implied counts


def implied_counts(root: Path, f: Findings) -> list[dict[str, Any]]:
    out = []
    by_store: dict[str, pl.DataFrame] = {}
    for st in STORES:
        main, held_rows = state_rows(st, root)
        by_store[st] = main
        rows = main.to_dicts() + [dict(h, _held=True) for h in held_rows]
        for r in rows:
            n, since = _int(r.get("new_since_count")), _date(r.get("new_since_date"))
            cum = _int(r.get("cum_cases"))
            if n is None or cum is None:
                continue
            who = (
                r.get("row_id")
                or r.get("seed_row")
                or f"{r.get('source_id')}:{(r.get('raw_sha256') or '')[:12]}"
            )
            if since is None:
                f.add(
                    "Implied counts",
                    f"- {st} {who}: {n} new with no start date; "
                    "no implied count computed (see the weekly comparison below).",
                )
                continue
            out.append(
                {
                    "store": st,
                    "row": who,
                    "implied_date": since,
                    "implied_cum": cum - n,
                    "from": f"{cum} - {n}",
                    "held": bool(r.get("_held")),
                }
            )
    for x in out:
        held_note = " (row is quarantined: date to confirm)" if x["held"] else ""
        f.add(
            "Implied counts",
            f"- {x['store']} {x['row']}: implies {x['implied_cum']} on "
            f"{x['implied_date']} ({x['from']}){held_note}",
        )
        for st, df in by_store.items():
            same = df.filter(pl.col("as_of_date") == x["implied_date"])
            for r in same.to_dicts():
                agree = r["cum_cases"] == x["implied_cum"]
                verdict = "agrees" if agree else "DISAGREES"
                f.add(
                    "Implied counts",
                    f"  - {verdict} with {st} {_label(r)} = {r['cum_cases']} on {r['as_of_date']}",
                )
                if st == x["store"] and not agree:
                    f.flags.append(
                        Flag(
                            "IMPLIED_COUNT_BREAK",
                            f"{st}|{x['row']}|{x['implied_date']}",
                            f"{st} {x['row']} implies {x['implied_cum']} on "
                            f"{x['implied_date']}, row {_label(r)} says "
                            f"{r['cum_cases']}",
                        )
                    )
        for st in STORES:
            _, held = state_rows(st, root)
            for h in held:
                if _int(h.get("cum_cases")) == x["implied_cum"] and not h.get("as_of_date"):
                    f.add(
                        "Implied counts",
                        f"  - hint: {st} {h.get('row_id')} "
                        f"(date to confirm) has the same count {x['implied_cum']}, so it may "
                        f"be as of {x['implied_date']}",
                    )
    return out


# ---------------------------------------------------------------- T3.6 monotonicity


def _check_series(df: pl.DataFrame, keys: list[str], label: str, st: str, f: Findings) -> None:
    if df.height == 0:
        return
    df = df.filter(pl.col("date_precision") == "exact").sort(keys + ["as_of_date"])
    for _, g in df.group_by(keys, maintain_order=True):
        prev: dict[str, Any] | None = None
        for r in g.to_dicts():
            if (
                prev is not None
                and r["cum_cases"] is not None
                and prev["cum_cases"] is not None
                and r["cum_cases"] < prev["cum_cases"]
            ):
                subject = "|".join(str(r[k]) for k in keys)
                f.flags.append(
                    Flag(
                        "CUM_DECREASE",
                        f"{st}|{label}|{subject}|{r['as_of_date']}",
                        f"{st} {label} {subject}: {prev['cum_cases']} on {prev['as_of_date']} "
                        f"({_label(prev)}) then {r['cum_cases']} on {r['as_of_date']} "
                        f"({_label(r)})",
                    )
                )
                f.add(
                    "Non-monotonic series",
                    f"- {st} {label} {subject}: "
                    f"{prev['cum_cases']} ({prev['as_of_date']}) -> {r['cum_cases']} "
                    f"({r['as_of_date']})",
                )
            prev = r


def monotonic(root: Path, f: Findings) -> None:
    for st in STORES:
        cs = access.current("case_state", st, root)
        cross = pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
        _check_series(cs.filter(~cross), ["count_definition"], "statewide", st, f)
        # Each cross-check source is a series of its own (CDC lags DOH by design).
        _check_series(
            cs.filter(cross), ["source_id", "count_definition"], "statewide cross-check", st, f
        )
        _check_series(
            access.current("case_county", st, root),
            ["count_definition", "county_fips"],
            "county",
            st,
            f,
        )
    if "Non-monotonic series" not in f.sections:
        f.add("Non-monotonic series", "- none within any store and count definition")


# ---------------------------------------------------------------- T3.7 county sums


def county_sums(root: Path, f: Findings) -> None:
    states = {
        st: access.current("case_state", st, root).filter(
            ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
        )
        for st in STORES
    }
    for st in STORES:
        cty = access.current("case_county", st, root)
        if cty.height == 0:
            continue
        snaps = (
            cty.group_by(["source_id", "as_of_date", "count_definition"])
            .agg(
                pl.col("cum_cases").sum().alias("county_sum"),
                (pl.col("cum_cases") > 0).sum().alias("with_cases"),
                pl.len().alias("rows"),
            )
            .sort("as_of_date")
        )
        for s in snaps.to_dicts():
            for st2, sdf in states.items():
                match = sdf.filter(
                    (pl.col("as_of_date") == s["as_of_date"])
                    & (pl.col("count_definition") == s["count_definition"])
                )
                for r in match.to_dicts():
                    total = r["cum_cases"]
                    same = st2 == st and r["source_id"] == s["source_id"]
                    complete = r.get("counties_with_cases") == s["with_cases"]
                    diff = s["county_sum"] - total
                    line = (
                        f"- {st} {s['source_id']} {s['as_of_date']} "
                        f"({s['count_definition']}): {s['rows']} county rows sum to "
                        f"{s['county_sum']}; {st2} {_label(r)} total {total}"
                    )
                    if same:
                        bad = diff != 0 if complete else diff > 0
                        if bad:
                            f.flags.append(
                                Flag(
                                    "COUNTY_SUM_MISMATCH",
                                    f"{st}|{s['source_id']}|{s['as_of_date']}|"
                                    f"{s['count_definition']}",
                                    line[2:],
                                )
                            )
                        f.add("County sums", line + (" MISMATCH" if bad else " (consistent)"))
                    else:
                        tolerance = 1 + 0.01 * total
                        tag = "differs" if abs(diff) > tolerance and complete else "compared"
                        f.add("County sums", line + f" [{tag}, cross-source, not flagged]")
    if "County sums" not in f.sections:
        f.add("County sums", "- no county snapshot yet")


# ---------------------------------------------------------------- T3.8 known issues


def series_review(root: Path, f: Findings) -> None:
    rows: list[dict[str, Any]] = []
    for st in STORES:
        main, held = state_rows(st, root)
        for r in main.to_dicts():
            rows.append({**r, "store": st})
        for h in held:
            rows.append(
                {
                    "store": st,
                    "as_of_date": None,
                    "cum_cases": _int(h.get("cum_cases")),
                    "count_definition": h.get("count_definition"),
                    "source_tier": h.get("source_tier") or "?",
                    "source_id": "seed",
                    "seed_row": h.get("row_id"),
                    "notes": h.get("notes"),
                    "date_precision": "to_confirm",
                }
            )
    dated = sorted(
        (r for r in rows if r["as_of_date"] is not None),
        key=lambda r: (r["as_of_date"], r["cum_cases"] or 0),
    )
    unknown = [r for r in rows if r.get("count_definition") == "unknown"]
    f.add(
        "Count definitions",
        f"- {len(unknown)} statewide rows have count_definition "
        "`unknown`: "
        + ", ".join(sorted(f"{r['store']}:{r.get('seed_row') or 'dashboard'}" for r in unknown)),
    )
    for r in rows:
        if r.get("source_id") == "doh_dashboard":
            f.add(
                "Count definitions",
                f"- dashboard {r['as_of_date']}: {r['count_definition']} {r['cum_cases']}",
            )

    # Growth steps between consecutive dated values (all stores, tiers labelled).
    for a, b in zip(dated, dated[1:], strict=False):
        if (
            not a["cum_cases"]
            or b["cum_cases"] is None
            or a["count_definition"] != b["count_definition"]
            and "unknown" not in (a["count_definition"], b["count_definition"])
        ):
            continue
        days = (b["as_of_date"] - a["as_of_date"]).days or 1
        ratio = b["cum_cases"] / a["cum_cases"]
        if ratio <= 1 or b["cum_cases"] - a["cum_cases"] < MIN_STEP_CASES:
            continue
        doubling = days * math.log(2) / math.log(ratio)
        if doubling < DOUBLING_DAYS_REVIEW:
            f.add(
                "Growth steps",
                f"- {a['cum_cases']} ({a['as_of_date']}, {a['store']} "
                f"{a.get('seed_row') or a['source_id']}, {a['source_tier']}) -> "
                f"{b['cum_cases']} ({b['as_of_date']}, {b['store']} "
                f"{b.get('seed_row') or b['source_id']}, {b['source_tier']}): doubling every "
                f"{doubling:.0f} days over {days} days. Verify against DOH; do not smooth.",
            )
    if "Growth steps" not in f.sections:
        f.add("Growth steps", "- none above the review threshold")

    # Values by month across stores (shows disagreements such as July 114 vs 134).
    months: dict[str, list[str]] = {}
    for r in rows:
        note = (r.get("notes") or "").lower()
        month = (
            r["as_of_date"].strftime("%Y-%m")
            if r["as_of_date"]
            else ("2026-07" if "late july" in note or "late-july" in note else None)
        )
        if month is None:
            continue
        when = str(r["as_of_date"]) if r["as_of_date"] else "date to confirm"
        months.setdefault(month, []).append(
            f"{r['cum_cases']} ({when}, {r['store']} {r.get('seed_row') or r['source_id']}, "
            f"{r['source_tier']}, {r.get('count_definition')})"
        )
    for m in sorted(months):
        if len(months[m]) > 1:
            f.add("Values by month (all tiers)", f"- {m}: " + "; ".join(months[m]))

    # Weekly comparison for rows giving "N new in the week" without a start date.
    for r in rows:
        n, cum, as_of = _int(r.get("new_since_count")), r.get("cum_cases"), r["as_of_date"]
        if n is None or r.get("new_since_date") or as_of is None or cum is None:
            continue
        week_before = as_of - timedelta(days=7)
        for o in rows:
            if o["as_of_date"] == week_before:
                verdict = "agrees" if o["cum_cases"] == cum - n else "conflicts"
                f.add(
                    "Seed conflicts",
                    f"- {r['store']} {r.get('seed_row')}: {cum} on {as_of} "
                    f"with {n} new in the week implies {cum - n} on {week_before}; "
                    f"{o['store']} {o.get('seed_row') or o['source_id']} "
                    f"({o['source_tier']}) says {o['cum_cases']}: {verdict}",
                )


# ---------------------------------------------------------------- same-key conflicts

VALUE_COLS = {
    "case_state": ["cum_cases", "counties_with_cases", "hospitalizations", "deaths"],
    "case_county": ["cum_cases"],
}


def source_conflicts(root: Path, f: Findings) -> None:
    """Two documents fetched together that give different values for the same key (for
    example two releases of one day). ``current`` keeps one by a fixed tie-break; the
    disagreement is flagged, never resolved by hand."""
    from ingest.curate.schema import NATURAL_KEYS

    for st in STORES:
        for table, vals in VALUE_COLS.items():
            df = access.all_rows(table, st, root)
            if df.height == 0:
                continue
            keys = list(NATURAL_KEYS[table])
            # Latest row per document (source_url); a later capture of the same document is a
            # revision, not a conflict.
            per_doc = df.sort("fetched_at_utc").group_by([*keys, "source_url"]).last()
            g = per_doc.group_by(keys).agg(
                pl.col("source_url").n_unique().alias("docs"),
                pl.struct(vals).n_unique().alias("variants"),
                pl.struct([*vals, "raw_sha256", "seed_row"]).alias("rows"),
            )
            for r in g.filter((pl.col("docs") > 1) & (pl.col("variants") > 1)).to_dicts():
                subject = "|".join(str(r[k]) for k in keys)
                desc = "; ".join(
                    ", ".join(f"{c} {x[c]}" for c in vals if x[c] is not None)
                    + f" ({x['seed_row'] or (x['raw_sha256'] or '')[:12]})"
                    for x in r["rows"]
                )
                f.flags.append(
                    Flag(
                        "SOURCE_CONFLICT",
                        f"{st}|{table}|{subject}",
                        f"{st} {table} {subject}: {desc}",
                    )
                )
                f.add("Source conflicts", f"- {st} {table} {subject}: {desc}")
    if "Source conflicts" not in f.sections:
        f.add("Source conflicts", "- none")


# ---------------------------------------------------------------- freshness


def freshness(root: Path, now: datetime, f: Findings) -> None:
    status = access.capture_status(root)
    if status.height == 0:
        f.add("Capture freshness", "- no captures logged yet")
        return
    for r in status.to_dicts():
        limit = STALE_HOURS.get(r["source_id"], STALE_HOURS_DEFAULT)
        good = r.get("last_good_utc")
        age = (now - parse_utc(good)).total_seconds() / 3600 if good else None
        stale = age is None or age > limit
        f.add(
            "Capture freshness",
            f"- {r['source_id']}: last outcome {r['outcome']}, last good "
            f"{good or 'never'}"
            + (f" ({age:.0f} h ago)" if age is not None else "")
            + (" STALE" if stale else ""),
        )
        if stale:
            day = now.date().isoformat()
            f.flags.append(
                Flag(
                    "STALE_SNAPSHOT",
                    f"{r['source_id']}|{day}",
                    f"{r['source_id']}: no good capture within {limit} h "
                    f"(last good {good or 'never'})",
                )
            )
        if r["outcome"] == "blocked":
            f.flags.append(
                Flag(
                    "BLOCKED",
                    f"{r['source_id']}|{r['finished_utc']}",
                    f"{r['source_id']} blocked at {r['finished_utc']}",
                    "error",
                )
            )


# ---------------------------------------------------------------- run and report


def run_checks(root: Path, now: datetime) -> Findings:
    f = Findings()
    implied_counts(root, f)
    monotonic(root, f)
    county_sums(root, f)
    series_review(root, f)
    source_conflicts(root, f)
    freshness(root, now, f)
    return f


def write_flags(f: Findings, root: Path, now: datetime) -> int:
    existing = set(access.all_rows("data_quality_flag", "curated", root)["flag_id"])
    new = {fl.flag_id: fl for fl in f.flags if fl.flag_id not in existing}
    if not new:
        return 0
    run_id = hashlib.sha256(("|".join(sorted(new)) + ENGINE_VERSION).encode()).hexdigest()[:12]
    rows = [
        {
            "flag_id": k,
            "raised_utc": now,
            "severity": fl.severity,
            "code": fl.code,
            "ref_raw_sha256": fl.ref,
            "description": fl.description,
            "status": "open",
            "ingest_run_id": run_id,
            "parser_version": f"quality-{ENGINE_VERSION}",
            "fetched_at_utc": now,
        }
        for k, fl in sorted(new.items())
    ]
    store.write("curated", "data_quality_flag", pl.DataFrame(rows), run_id, now, root)
    return len(rows)


def open_flags(root: Path) -> pl.DataFrame:
    frames = []
    for st in STORES:
        df = access.current("data_quality_flag", st, root)
        if df.height:
            frames.append(df.with_columns(pl.lit(st).alias("store")))
    if not frames:
        return pl.DataFrame()
    df = pl.concat(frames, how="diagonal_relaxed")
    return df.filter(pl.col("status") == "open").sort(["code", "raised_utc"])


def render(f: Findings, root: Path, now: datetime) -> str:
    flags = open_flags(root)
    snap = access.current("case_state", "curated", root).filter(
        pl.col("source_id") == "doh_dashboard"
    )
    latest = str(snap["as_of_date"].max()) if snap.height else None
    lines = [
        "# Data quality report",
        "",
        f"Generated {iso_utc(now)} by `measles quality` (engine {ENGINE_VERSION}). Latest "
        f"dashboard data as of {latest or 'none yet'}. Regenerated on every capture run; "
        "flags are the durable record (`data_quality_flag`).",
        "",
        "Reported counts are a floor. Conflicts below are shown, not resolved (I5). Rows from "
        "the sensitivity store (news-derived, secondary) are labelled with their tier and are "
        "never used in default views.",
        "",
        "## Open flags",
        "",
    ]
    if flags.height == 0:
        lines.append("- none")
    else:
        for code, g in flags.group_by("code", maintain_order=True):
            lines.append(f"- **{code[0]}** ({g.height})")
            for r in g.to_dicts()[:20]:
                lines.append(f"  - {r['store']}: {r['description']}")
    order = [
        "Capture freshness",
        "Implied counts",
        "Seed conflicts",
        "Source conflicts",
        "Non-monotonic series",
        "County sums",
        "Count definitions",
        "Growth steps",
        "Values by month (all tiers)",
    ]
    for sec in order:
        if sec in f.sections:
            lines += ["", f"## {sec}", "", *f.sections[sec]]
    q = [(st, access.all_rows("quarantine", st, root)) for st in STORES]
    lines += ["", "## Quarantine", ""]
    for st, df in q:
        if df.height:
            for (table, reason), g in df.group_by(["table", "reason_code"], maintain_order=True):
                lines.append(f"- {st} {table}: {g.height} row(s), {reason}")
    if all(df.height == 0 for _, df in q):
        lines.append("- empty")
    counties = len(pa_counties.COUNTIES)
    lines += ["", f"_Reference: {counties} Pennsylvania counties._", ""]
    return "\n".join(lines)


def run(root: Path | None = None, now: datetime | None = None) -> tuple[int, Path]:
    root = root or paths.repo_root()
    now = now or utc_now()
    f = run_checks(root, now)
    n = write_flags(f, root, now)
    out = paths.data_dir(root) / "quality" / "quality_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(f, root, now))
    return n, out
