"""Simulator inputs from the event table and county data (WP6b, ADR 0008).

Three inputs, each a (days, counties) array aligned with ``simulator.simulate``:

- ``school_mult``: transmission factor from ``school_calendar`` events. In session 1; out of
  session ``1 - share``; where no event says which, 1 (no adjustment) and the gap is reported.
- ``intervention_mult``: transmission factor ``factor`` from ``event_date + lag_days`` in the
  event's counties, for the event types listed in ``params.yml``. A factor of 1 is no effect;
  calibration (6c) estimates it.
- ``seeding``: fixed exposures placed ``lead_days`` before the earliest date a source shows a
  county had an infectious case (``first_known``). That date is an upper bound on the true
  first case, so ``lead_days`` is a model parameter, not a claim about onset dates (I6).

Evidence that a county had a case by a date (``first_known``):

- an event listed in ``seeding.case_events`` (an alert that states cases in that county);
- an event of a type in ``seeding.presence_types`` (an exposure notice: an infectious person
  was present there, which is what matters for transmission, though residence may differ);
- the first county snapshot with ``cum_cases > 0``. When that is the first snapshot captured,
  earlier presence is unknown and the date is marked ``censored``.

Nothing is filled in where the data are silent (I5): gaps are listed in ``Inputs.notes``. Data
are read only through ``ingest.access`` (I8), and ``known_at`` restricts every read to what was
known at a time, for validation replay (E11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from ingest import access

IN_SESSION = {"term_start": True, "break_end": True, "term_end": False, "break_start": False}


@dataclass
class Inputs:
    fips: list[str]
    start: date
    days: int
    mult: np.ndarray  # school x interventions
    seeds: np.ndarray
    first_known: pl.DataFrame
    notes: list[str] = field(default_factory=list)


def _day(d: date, start: date) -> int:
    return (d - start).days


def _expand(scope: list[str], fips: list[str], affected: set[str]) -> list[str]:
    out: list[str] = []
    for part in scope:
        if part == "state":
            out.extend(fips)
        elif part == "affected_counties":
            out.extend(sorted(affected))
        else:
            out.append(part)
    return [f for f in dict.fromkeys(out) if f in fips]


def first_known(
    events: pl.DataFrame,
    scopes: dict[str, list[str]],
    snapshots: pl.DataFrame,
    *,
    case_events: list[str],
    presence_types: list[str],
) -> pl.DataFrame:
    """Earliest date per county by which a source shows an infectious case there.

    ``scopes`` maps event_id to resolved county_scope. ``snapshots`` has ``county_fips``,
    ``as_of_date`` and ``cum_cases``. Columns: county_fips, known_by, basis, censored."""
    rows: list[dict[str, Any]] = []
    for ev in events.iter_rows(named=True):
        if ev["event_date"] is None:
            continue
        if ev["event_id"] in case_events or ev["event_type"] in presence_types:
            for f in scopes[ev["event_id"]]:
                if f not in ("state", "affected_counties"):
                    rows.append(
                        {"county_fips": f, "known_by": ev["event_date"], "basis": ev["event_id"]}
                    )
    if snapshots.height:
        first_snapshot = snapshots["as_of_date"].min()
        pos = (
            snapshots.filter(pl.col("cum_cases") > 0)
            .group_by("county_fips")
            .agg(pl.col("as_of_date").min().alias("known_by"))
        )
        for f, d in pos.rows():
            basis = "snapshot_first" if d == first_snapshot else "snapshot"
            rows.append({"county_fips": f, "known_by": d, "basis": basis})
    schema = {"county_fips": pl.Utf8, "known_by": pl.Date, "basis": pl.Utf8}
    df = pl.DataFrame(rows, schema=schema)
    if not df.height:
        return df.with_columns(pl.lit(False).alias("censored"))
    return (
        df.sort("known_by", "basis")
        .group_by("county_fips", maintain_order=True)
        .first()
        .with_columns((pl.col("basis") == "snapshot_first").alias("censored"))
        .sort("known_by", "county_fips")
    )


def school_mult(
    events: pl.DataFrame,
    scopes: dict[str, list[str]],
    fips: list[str],
    start: date,
    days: int,
    share: float,
) -> tuple[np.ndarray, list[str]]:
    if not 0 <= share <= 1:
        raise ValueError("school share must lie in [0, 1]")
    cal = events.filter(pl.col("event_type") == "school_calendar").sort("event_date")
    status = np.full((days, len(fips)), np.nan)  # 1 in session, 0 out, nan unknown
    idx = {f: i for i, f in enumerate(fips)}
    for ev in cal.iter_rows(named=True):
        if ev["title"] not in access.SCHOOL_CALENDAR_TITLES:
            raise ValueError(f"school_calendar event {ev['event_id']} has title {ev['title']!r}")
        if "affected_counties" in scopes[ev["event_id"]]:
            raise ValueError(f"school_calendar event {ev['event_id']} cannot use affected_counties")
        t0 = max(_day(ev["event_date"], start), 0)
        for f in _expand(scopes[ev["event_id"]], fips, set()):
            status[t0:, idx[f]] = 1.0 if IN_SESSION[ev["title"]] else 0.0
    notes = []
    unknown = np.isnan(status)
    if share > 0 and unknown.any():
        n = int(unknown.any(axis=0).sum())
        notes.append(
            f"school calendar unknown for part of the period in {n} counties: no adjustment"
        )
    mult = np.where(status == 0.0, 1.0 - share, 1.0)
    return mult, notes


def intervention_mult(
    events: pl.DataFrame,
    scopes: dict[str, list[str]],
    fips: list[str],
    start: date,
    days: int,
    effects: dict[str, dict[str, float]],
    known: pl.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    """``effects`` maps event_type to ``{"factor": f, "lag_days": n}``. ``affected_counties``
    means counties with a ``first_known`` date on or before the event date."""
    m = np.ones((days, len(fips)))
    idx = {f: i for i, f in enumerate(fips)}
    notes = []
    for ev in events.filter(pl.col("event_type").is_in(list(effects))).iter_rows(named=True):
        eff = effects[ev["event_type"]]
        if not 0 <= eff["factor"] <= 1:
            raise ValueError("an intervention factor must lie in [0, 1]")
        if ev["event_date"] is None:
            notes.append(f"{ev['event_id']}: no date, not applied")
            continue
        affected = set(known.filter(pl.col("known_by") <= ev["event_date"])["county_fips"])
        where = _expand(scopes[ev["event_id"]], fips, affected)
        if not where:
            notes.append(f"{ev['event_id']}: no counties resolved, not applied")
            continue
        t0 = max(_day(ev["event_date"], start) + int(eff["lag_days"]), 0)
        for f in where:
            m[t0:, idx[f]] *= eff["factor"]
    return m, notes


def seeding(
    known: pl.DataFrame,
    fips: list[str],
    start: date,
    days: int,
    *,
    mode: str,
    exposed: int,
    lead_days: int,
) -> tuple[np.ndarray, list[str]]:
    """Fixed exposures ``lead_days`` before each county's first known date: the earliest
    county only (``first``) or every county (``all``, a sensitivity variant)."""
    if mode not in ("first", "all"):
        raise ValueError("seeding mode must be 'first' or 'all'")
    seeds = np.zeros((days, len(fips)), dtype=np.int64)
    notes = []
    rows = known.filter(pl.col("county_fips").is_in(fips)).sort("known_by", "county_fips")
    if mode == "first":
        rows = rows.filter(pl.col("known_by") == rows["known_by"].min()) if rows.height else rows
    for f, d, censored in rows.select("county_fips", "known_by", "censored").rows():
        t = _day(d, start) - lead_days
        if t < 0:
            notes.append(f"{f}: seeding day before the run start, seeded on day 0")
            t = 0
        if t >= days:
            continue
        if censored:
            notes.append(f"{f}: first known only from the first snapshot ({d}), so seeding is late")
        seeds[t, fips.index(f)] += exposed
    if not rows.height:
        notes.append("no county has a known first case: nothing seeded")
    return seeds, notes


def build(
    start: date,
    days: int,
    fips: list[str],
    params: dict[str, Any],
    root: Path | None = None,
    known_at: datetime | None = None,
) -> Inputs:
    """All three inputs from the curated event and county tables."""

    def read(table: str) -> pl.DataFrame:
        if known_at is None:
            return access.current(table, root=root)
        return access.as_known_at(table, known_at, root=root)

    events = read("event")
    county = read("case_county")
    if county.height:
        county = county.filter(~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES)))
    scopes = {
        e: access.county_scope(s, root) for e, s in events.select("event_id", "county_scope").rows()
    }
    sp = params["seeding"]
    known = first_known(
        events,
        scopes,
        county.select("county_fips", "as_of_date", "cum_cases") if county.height else county,
        case_events=list(sp["case_events"]),
        presence_types=list(sp["presence_types"]),
    )
    school, n1 = school_mult(
        events, scopes, fips, start, days, float(params["school"]["share"]["value"])
    )
    effects = {
        t: {"factor": float(v["factor"]), "lag_days": int(v["lag_days"])}
        for t, v in params["interventions"].items()
    }
    interv, n2 = intervention_mult(events, scopes, fips, start, days, effects, known)
    seeds, n3 = seeding(
        known,
        fips,
        start,
        days,
        mode=sp["mode"],
        exposed=int(sp["exposed"]),
        lead_days=int(sp["lead_days"]["value"]),
    )
    return Inputs(fips, start, days, school * interv, seeds, known, n1 + n2 + n3)
