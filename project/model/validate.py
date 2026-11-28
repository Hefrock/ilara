"""Forecast validation and the Gate G4 writer (WP6d, ADR 0013).

Replays archived data through ``access.as_known_at(T)``: at each weekly origin ``T`` a
forecaster sees only rows fetched by ``T``, forecasts the cases newly reported in each of the
next 1 to 4 weeks per county and statewide, and is scored against what was later reported.

- Target: the increase in the calendar-year cumulative count between the snapshot ``7(h-1)``
  days after ``T`` and the one ``7h`` days after (week ``h``). Both snapshots must exist; a
  missing snapshot leaves that target unscored, never filled (I5).
- Scores: weighted interval score (Bracher et al. 2021) over the median and the 50, 80 and 90
  percent central intervals, and coverage of each interval.
- Baseline: persistence. Median = the last observed weekly increase; quantiles from that value
  plus the spread of past week-on-week changes in the same geography (both signs), floored at
  zero; Poisson around it when fewer than three past changes exist. Same origins and targets.
- Groups (ADR 0028 item 3): at each origin the county forecasts are also summed, draw by draw,
  into Lancaster County, the other counties with ``LARGE_AT`` or more cases at the origin, and
  the remaining counties, each scored on its own weekly total against persistence on the same
  total. These rows have ``kind`` "group"; the statewide forecast has ``kind`` "state".
- Gate G4 (HANDOFF, ADR 0028 items 2 and 3): at least 8 weekly origins; over county targets
  where the outcome or the forecast's upper 80 percent bound is at least 1, the 80 percent
  interval covers 70 to 90 percent of outcomes; and at the 1-week and 2-week horizons the model
  has the lower mean WIS in at least 3 of the 4 groups (Lancaster, larger counties, the rest,
  the state). ``write_gate`` records ``pass`` only then (T6.15). Coverage over all county
  targets and the pooled per-county WIS are still reported.
- Frozen outcomes (ADR 0028 item 4): each week's outcome is read as known ``FREEZE_DAYS`` after
  the week ends (``freeze_time``), so later revisions do not change a score. A target whose
  freeze time has not passed is scored on the data known now and marked ``frozen`` False
  (provisional); the gate counts only frozen targets.

Model outputs stay in ``project/outputs/`` (gitignored) until the gate passes (I10, I11).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from project.leak import LeakError, check_known

__all__ = ["LeakError", "check_known"]

ALPHAS = (0.5, 0.2, 0.1)  # 50, 80 and 90 percent central intervals
HORIZONS = (1, 2, 3, 4)
GATE_ORIGINS = 8
GATE_COVERAGE_80 = (0.70, 0.90)
GATE_HORIZONS = (1, 2)
LANCASTER = "42071"
LARGE_AT = 10  # cases at the origin; the same threshold as pa.POOL_BELOW (ADR 0021)
GROUPS = ("group:lancaster", "group:larger", "group:rest", "state")
GATE_GROUP_WINS = 3  # of the 4 groups in GROUPS, at each gate horizon (ADR 0028 item 3)
FREEZE_DAYS = 14  # an outcome is read as known this many days after its week ends (item 4)
ET = ZoneInfo("America/New_York")

Quantiles = dict[str, float]  # "median", "low_50", "high_50", "low_80", ...
Geo = str  # county FIPS or "state"
Series = Mapping[Geo, Mapping[date, int]]  # cumulative counts by snapshot date
Forecaster = Callable[[date, datetime], Mapping[Geo, Mapping[int, np.ndarray]]]
# target day -> (series to read that target's outcome from, whether that series is frozen)
Outcomes = Callable[[date], tuple[Series, bool]]


def freeze_time(target: date) -> datetime:
    """When a week's outcome is frozen (ADR 0028 item 4): the end of the day ``FREEZE_DAYS``
    after the week ends, ET."""
    return datetime.combine(
        target + timedelta(days=FREEZE_DAYS), dt_time(23, 59, 59), ET
    ).astimezone(UTC)


def interval_score(y: float, low: float, high: float, alpha: float) -> float:
    return (high - low) + (2 / alpha) * max(low - y, 0.0) + (2 / alpha) * max(y - high, 0.0)


def wis(y: float, q: Quantiles) -> float:
    """Weighted interval score: (|y - median| / 2 + sum of alpha/2 * IS_alpha) / (K + 1/2)."""
    total = 0.5 * abs(y - q["median"])
    for a in ALPHAS:
        lvl = round(100 * (1 - a))
        total += (a / 2) * interval_score(y, q[f"low_{lvl}"], q[f"high_{lvl}"], a)
    return total / (len(ALPHAS) + 0.5)


def covered(y: float, q: Quantiles, level: int) -> bool:
    return q[f"low_{level}"] <= y <= q[f"high_{level}"]


def quantiles(samples: np.ndarray) -> Quantiles:
    out = {"median": float(np.quantile(samples, 0.5))}
    for a in ALPHAS:
        lvl = round(100 * (1 - a))
        lo, hi = np.quantile(samples, [a / 2, 1 - a / 2])
        out[f"low_{lvl}"], out[f"high_{lvl}"] = float(lo), float(hi)
    return out


def weekly_increase(cum: Mapping[date, int], end: date) -> int | None:
    """Cases newly reported in the week ending ``end``; None when either snapshot is missing."""
    a, b = cum.get(end - timedelta(days=7)), cum.get(end)
    return None if a is None or b is None else b - a


def persistence(cum: Mapping[date, int], origin: date) -> Quantiles | None:
    """The persistence baseline at ``origin`` from snapshots known by then (any horizon)."""
    known = {d: v for d, v in cum.items() if d <= origin}
    last = weekly_increase(known, origin)
    if last is None:
        return None
    vals: list[int] = []  # weekly increases ending origin, origin - 7, ... back to a gap
    d = origin
    while (v := weekly_increase(known, d)) is not None:
        vals.insert(0, v)
        d -= timedelta(days=7)
    diffs = [b - a for a, b in zip(vals, vals[1:], strict=False)]
    out = {"median": float(last)}
    for a in ALPHAS:
        lvl = round(100 * (1 - a))
        if len(diffs) >= 3:
            spread = np.array(diffs + [-x for x in diffs], dtype=float)
            lo, hi = np.quantile(spread, [a / 2, 1 - a / 2])
            lo, hi = last + lo, last + hi
        else:
            lo, hi = _poisson_interval(last, a)
        out[f"low_{lvl}"], out[f"high_{lvl}"] = max(float(lo), 0.0), max(float(hi), 0.0)
    return out


def _poisson_interval(lam: float, alpha: float) -> tuple[float, float]:
    if lam <= 0:
        return 0.0, 0.0
    # Inverse of the Poisson distribution function by summation (small lam; exact enough).
    k, p, cdf = 0, math.exp(-lam), 0.0
    lo = hi = None
    while hi is None:
        cdf += p
        if lo is None and cdf >= alpha / 2:
            lo = k
        if cdf >= 1 - alpha / 2:
            hi = k
        k += 1
        p *= lam / k
        if k > lam + 50 * math.sqrt(lam) + 50:  # far tail: underflow guard
            hi = k
    return float(lo or 0), float(hi)


def _known_value(cum: Mapping[date, int], t: date) -> int | None:
    known = [d for d in cum if d <= t]
    return cum[max(known)] if known else None


def groups_at(origin: date, observed: Series, counties: Sequence[Geo]) -> dict[str, list[Geo]]:
    """County groups at an origin (ADR 0028 item 3): Lancaster; the other counties with
    ``LARGE_AT`` or more cases known at the origin; the rest. A county with no count known at
    the origin is in the rest."""
    larger: list[Geo] = []
    rest: list[Geo] = []
    for c in counties:
        if c == LANCASTER:
            continue
        v = _known_value(observed.get(c, {}), origin)
        (larger if v is not None and v >= LARGE_AT else rest).append(c)
    out = {"group:larger": larger, "group:rest": rest}
    if LANCASTER in counties:
        out["group:lancaster"] = [LANCASTER]
    return {k: v for k, v in out.items() if v}


def _summed(series: Series, members: Sequence[Geo]) -> dict[date, int]:
    """Members' cumulative counts summed on the days all of them have a value (a gap stays a
    gap)."""
    days = set.intersection(*(set(series.get(m, {})) for m in members)) if members else set()
    return {d: sum(series[m][d] for m in members) for d in days}


def with_groups(
    origins: Sequence[date],
    forecasts: Mapping[date, Mapping[Geo, Mapping[int, np.ndarray]]],
    observed: Series,
) -> tuple[dict[date, dict[Geo, dict[int, np.ndarray]]], dict[Geo, dict[date, int]]]:
    """Forecasts and observed series with the county groups added at each origin. Group
    forecasts sum the members' samples draw by draw, so each draw is one simulated epidemic."""
    fc: dict[date, dict[Geo, dict[int, np.ndarray]]] = {}
    obs: dict[Geo, dict[date, int]] = {g: dict(v) for g, v in observed.items()}
    for t in origins:
        by_geo = {g: dict(h) for g, h in forecasts.get(t, {}).items()}
        counties = [g for g in by_geo if g != "state" and not str(g).startswith("group:")]
        for name, members in groups_at(t, observed, counties).items():
            hs = set.intersection(*(set(by_geo[m]) for m in members))
            by_geo[name] = {
                h: np.sum([np.asarray(by_geo[m][h], dtype=float) for m in members], axis=0)
                for h in hs
            }
            obs[f"{name}@{t.isoformat()}"] = _summed(observed, members)
        fc[t] = by_geo
    return fc, obs


def _kind(geo: Geo) -> str:
    return "state" if geo == "state" else "group" if str(geo).startswith("group:") else "county"


def score(
    origins: Sequence[date],
    forecasts: Mapping[date, Mapping[Geo, Mapping[int, np.ndarray]]],
    observed: Series,
    horizons: Sequence[int] = HORIZONS,
    outcomes: Outcomes | None = None,
) -> pl.DataFrame:
    """One row per origin, geography and horizon with an observed target: model and persistence
    WIS and interval coverage. County groups are added at each origin (``with_groups``); their
    rows have ``kind`` "group". With ``outcomes``, each target is read from the series it
    returns for the target day (frozen outcomes, ADR 0028 item 4); without, from ``observed``."""
    raw_forecasts = forecasts
    forecasts, grouped = with_groups(origins, forecasts, observed)
    rows: list[dict[str, Any]] = []
    for t in origins:
        counties = [g for g in raw_forecasts.get(t, {}) if _kind(g) == "county"]
        members = groups_at(t, observed, counties)
        for geo, by_h in forecasts.get(t, {}).items():
            key = f"{geo}@{t.isoformat()}" if _kind(geo) == "group" else geo
            cum = grouped.get(key, {})
            base = persistence(cum, t)
            for h in horizons:
                if h not in by_h:
                    continue
                end = t + timedelta(days=7 * h)
                frozen = True
                target = cum
                if outcomes is not None:
                    series, frozen = outcomes(end)
                    target = (
                        _summed(series, members[geo])
                        if _kind(geo) == "group"
                        else dict(series.get(geo, {}))
                    )
                y = weekly_increase(target, end)
                if y is None or base is None:
                    continue  # unscored: a gap stays a gap (I5)
                q = quantiles(np.asarray(by_h[h], dtype=float))
                row: dict[str, Any] = {
                    "origin": t,
                    "geography": geo,
                    "kind": _kind(geo),
                    "horizon": h,
                    "observed": y,
                    "median": q["median"],
                    "high_80": q["high_80"],
                    "wis": wis(y, q),
                    "wis_persistence": wis(y, base),
                    "frozen": frozen,
                }
                for a in ALPHAS:
                    lvl = round(100 * (1 - a))
                    row[f"covered_{lvl}"] = covered(y, q, lvl)
                    row[f"covered_{lvl}_persistence"] = covered(y, base, lvl)
                rows.append(row)
    schema = {
        "origin": pl.Date,
        "geography": pl.Utf8,
        "kind": pl.Utf8,
        "horizon": pl.Int64,
        "observed": pl.Int64,
        "median": pl.Float64,
        "high_80": pl.Float64,
        "wis": pl.Float64,
        "wis_persistence": pl.Float64,
        "frozen": pl.Boolean,
        **{
            f"covered_{round(100 * (1 - a))}{s}": pl.Boolean
            for a in ALPHAS
            for s in ("", "_persistence")
        },
    }
    return pl.DataFrame(rows, schema=schema)


@dataclass
class GateResult:
    status: str  # "pass" or "fail"
    origins: int
    coverage_80: float | None  # over county targets with a case observed or forecast (item 2)
    wis: dict[int, float]  # pooled per-county mean, reported
    wis_persistence: dict[int, float]
    reasons: list[str]
    coverage_80_all: float | None = None  # over all county targets, reported
    groups: dict[int, dict[str, dict[str, float]]] = field(default_factory=dict)
    provisional: int = 0  # targets left out because their outcome is not yet frozen (item 4)


def _county_rows(scores: pl.DataFrame) -> pl.DataFrame:
    if "kind" in scores.columns:
        return scores.filter(pl.col("kind") == "county")
    return scores.filter(pl.col("geography") != "state")


def gate(scores: pl.DataFrame) -> GateResult:
    """The G4 decision from scored forecasts (HANDOFF section 6, G4; ADR 0028 items 2 and 3)."""
    reasons: list[str] = []
    provisional = 0
    if scores.height and "frozen" in scores.columns:  # ADR 0028 item 4: frozen targets only
        provisional = scores.filter(~pl.col("frozen")).height
        scores = scores.filter(pl.col("frozen"))
    all_rows = scores
    scores = _county_rows(scores) if scores.height else scores
    origins = scores["origin"].n_unique() if scores.height else 0
    if origins < GATE_ORIGINS:
        reasons.append(f"{origins} weekly origins scored; G4 needs {GATE_ORIGINS}")
    cov_all = float(scores["covered_80"].mean()) if scores.height else None  # type: ignore[arg-type]
    if scores.height and "high_80" in scores.columns:
        relevant = scores.filter((pl.col("observed") >= 1) | (pl.col("high_80") >= 1))
    else:
        relevant = scores
    cov = float(relevant["covered_80"].mean()) if relevant.height else None  # type: ignore[arg-type]
    lo, hi = GATE_COVERAGE_80
    if cov is None or not lo <= cov <= hi:
        reasons.append(f"80 percent coverage {cov} outside {lo} to {hi} (targets with a case)")
    w: dict[int, float] = {}
    wp: dict[int, float] = {}
    grp: dict[int, dict[str, dict[str, float]]] = {}
    for h in GATE_HORIZONS:
        sh = scores.filter(pl.col("horizon") == h) if scores.height else scores
        if sh.height:
            w[h], wp[h] = float(sh["wis"].mean()), float(sh["wis_persistence"].mean())  # type: ignore[arg-type]
        gh = (
            all_rows.filter((pl.col("horizon") == h) & pl.col("geography").is_in(list(GROUPS)))
            if all_rows.height and "geography" in all_rows.columns
            else pl.DataFrame()
        )
        grp[h] = {
            g: {
                "wis": float(d["wis"].mean()),  # type: ignore[arg-type]
                "wis_persistence": float(d["wis_persistence"].mean()),  # type: ignore[arg-type]
            }
            for g in GROUPS
            if (d := gh.filter(pl.col("geography") == g) if gh.height else gh).height
        }
        wins = sum(v["wis"] < v["wis_persistence"] for v in grp[h].values())
        if wins < GATE_GROUP_WINS:
            reasons.append(
                f"horizon {h}: model better in {wins} of {len(grp[h])} groups; "
                f"G4 needs {GATE_GROUP_WINS} of {len(GROUPS)}"
            )
    return GateResult(
        "fail" if reasons else "pass", origins, cov, w, wp, reasons, cov_all, grp, provisional
    )


def group_uncertainty(
    scores: pl.DataFrame, n_boot: int = 2000, seed: int = 7
) -> dict[int, dict[str, dict[str, float]]]:
    """Reported, not gated (ADR 0029 revisions): for each gate horizon and group, the mean of
    model WIS minus persistence WIS, with a 90 percent interval from resampling origins with
    replacement. Few origins make these intervals wide; that is the point of showing them."""
    rng = np.random.default_rng(seed)
    out: dict[int, dict[str, dict[str, float]]] = {}
    if not scores.height or "geography" not in scores.columns:
        return out
    for h in GATE_HORIZONS:
        out[h] = {}
        for g in GROUPS:
            d = scores.filter((pl.col("horizon") == h) & (pl.col("geography") == g))
            if not d.height:
                continue
            by_origin = (
                d.group_by("origin")
                .agg((pl.col("wis") - pl.col("wis_persistence")).mean().alias("diff"))
                .sort("origin")["diff"]
                .to_numpy()
            )
            boots = [
                float(np.mean(rng.choice(by_origin, size=len(by_origin), replace=True)))
                for _ in range(n_boot)
            ]
            lo, hi = np.quantile(boots, [0.05, 0.95])
            out[h][g] = {
                "diff": float(np.mean(by_origin)),
                "low": float(lo),
                "high": float(hi),
                "origins": len(by_origin),
            }
    return out


def write_gate(
    result: GateResult, path: Path, manifest: Mapping[str, Any], now: datetime | None = None
) -> Path:
    """``data/validation_gate.json``: summary metrics only, never forecasts (I10)."""
    body = {
        "status": result.status,
        "decided_utc": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": {
            "min_origins": GATE_ORIGINS,
            "coverage_80": list(GATE_COVERAGE_80),
            "coverage_targets": "county targets with an observed case or an upper 80% bound >= 1",
            "groups": list(GROUPS),
            "group_wins_needed": GATE_GROUP_WINS,
            "horizons": list(GATE_HORIZONS),
            "rules": "ADR 0028 items 1 to 5",
            "outcomes_frozen_days": FREEZE_DAYS,
            "rules_note": (
                "rules set on 2026-11-19 to 2026-11-25, after one scored week had been seen, "
                "and applied to every origin from 2026-10-28 with model version 1 unchanged "
                "(ADR 0028 item 5)"
            ),
        },
        "provisional_targets_excluded": result.provisional,
        "origins": result.origins,
        "coverage_80": result.coverage_80,
        "coverage_80_all": result.coverage_80_all,
        "groups": {str(k): v for k, v in result.groups.items()},
        "wis": {str(k): v for k, v in result.wis.items()},
        "wis_persistence": {str(k): v for k, v in result.wis_persistence.items()},
        "reasons": result.reasons,
        "run": dict(manifest),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, sort_keys=True, default=str) + "\n")
    return path


def replay(
    origins: Sequence[date],
    forecaster: Forecaster,
    observed: Series,
    cutoff: Callable[[date], datetime],
    outcomes: Outcomes | None = None,
) -> pl.DataFrame:
    """Fit and forecast at each origin with data known at ``cutoff(origin)``, then score."""
    forecasts = {t: forecaster(t, cutoff(t)) for t in origins}
    return score(origins, forecasts, observed, outcomes=outcomes)


def frozen_outcomes(
    series_at: Callable[[datetime], Series], now: datetime | None = None
) -> Outcomes:
    """``Outcomes`` from a reader of the published series as known at a time (ADR 0028 item 4):
    a target day reads the series as known at its freeze time, or now if that is later than
    now (provisional). Reads are cached, so the not-yet-frozen targets share one read."""
    now = now or datetime.now(UTC)
    cache: dict[datetime, Series] = {}

    def run(target: date) -> tuple[Series, bool]:
        at = freeze_time(target)
        frozen = at <= now
        at = at if frozen else now
        if at not in cache:
            cache[at] = series_at(at)
        return cache[at], frozen

    return run
