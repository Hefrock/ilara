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
- Gate G4 (HANDOFF): at least 8 weekly origins; pooled over counties and weeks, the 80 percent
  interval covers 70 to 90 percent of held-out values, and pooled WIS is lower than persistence
  at the 1-week and 2-week horizons. ``write_gate`` records ``pass`` only then (T6.15).

Model outputs stay in ``project/outputs/`` (gitignored) until the gate passes (I10, I11).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from project.leak import LeakError, check_known

__all__ = ["LeakError", "check_known"]

ALPHAS = (0.5, 0.2, 0.1)  # 50, 80 and 90 percent central intervals
HORIZONS = (1, 2, 3, 4)
GATE_ORIGINS = 8
GATE_COVERAGE_80 = (0.70, 0.90)
GATE_HORIZONS = (1, 2)

Quantiles = dict[str, float]  # "median", "low_50", "high_50", "low_80", ...
Geo = str  # county FIPS or "state"
Series = Mapping[Geo, Mapping[date, int]]  # cumulative counts by snapshot date
Forecaster = Callable[[date, datetime], Mapping[Geo, Mapping[int, np.ndarray]]]


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


def score(
    origins: Sequence[date],
    forecasts: Mapping[date, Mapping[Geo, Mapping[int, np.ndarray]]],
    observed: Series,
    horizons: Sequence[int] = HORIZONS,
) -> pl.DataFrame:
    """One row per origin, geography and horizon with an observed target: model and persistence
    WIS and interval coverage."""
    rows: list[dict[str, Any]] = []
    for t in origins:
        for geo, by_h in forecasts.get(t, {}).items():
            cum = observed.get(geo, {})
            base = persistence(cum, t)
            for h in horizons:
                if h not in by_h:
                    continue
                y = weekly_increase(cum, t + timedelta(days=7 * h))
                if y is None or base is None:
                    continue  # unscored: a gap stays a gap (I5)
                q = quantiles(np.asarray(by_h[h], dtype=float))
                row: dict[str, Any] = {
                    "origin": t,
                    "geography": geo,
                    "horizon": h,
                    "observed": y,
                    "median": q["median"],
                    "wis": wis(y, q),
                    "wis_persistence": wis(y, base),
                }
                for a in ALPHAS:
                    lvl = round(100 * (1 - a))
                    row[f"covered_{lvl}"] = covered(y, q, lvl)
                    row[f"covered_{lvl}_persistence"] = covered(y, base, lvl)
                rows.append(row)
    schema = {
        "origin": pl.Date,
        "geography": pl.Utf8,
        "horizon": pl.Int64,
        "observed": pl.Int64,
        "median": pl.Float64,
        "wis": pl.Float64,
        "wis_persistence": pl.Float64,
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
    coverage_80: float | None
    wis: dict[int, float]
    wis_persistence: dict[int, float]
    reasons: list[str]


def gate(scores: pl.DataFrame) -> GateResult:
    """The G4 decision from scored forecasts (HANDOFF section 5, G4): pooled over counties and
    weeks, so statewide rows are scored and reported but do not enter the decision."""
    reasons = []
    if scores.height:
        scores = scores.filter(pl.col("geography") != "state")
    origins = scores["origin"].n_unique() if scores.height else 0
    if origins < GATE_ORIGINS:
        reasons.append(f"{origins} weekly origins scored; G4 needs {GATE_ORIGINS}")
    cov = float(scores["covered_80"].mean()) if scores.height else None  # type: ignore[arg-type]
    lo, hi = GATE_COVERAGE_80
    if cov is None or not lo <= cov <= hi:
        reasons.append(f"80 percent coverage {cov} outside {lo} to {hi}")
    w: dict[int, float] = {}
    wp: dict[int, float] = {}
    for h in GATE_HORIZONS:
        sh = scores.filter(pl.col("horizon") == h) if scores.height else scores
        if not sh.height:
            reasons.append(f"no scored targets at horizon {h}")
            continue
        w[h], wp[h] = float(sh["wis"].mean()), float(sh["wis_persistence"].mean())  # type: ignore[arg-type]
        if not w[h] < wp[h]:
            reasons.append(f"horizon {h}: WIS {w[h]:.3f} not below persistence {wp[h]:.3f}")
    return GateResult("fail" if reasons else "pass", origins, cov, w, wp, reasons)


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
            "wis_below_persistence_at_horizons": list(GATE_HORIZONS),
        },
        "origins": result.origins,
        "coverage_80": result.coverage_80,
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
) -> pl.DataFrame:
    """Fit and forecast at each origin with data known at ``cutoff(origin)``, then score."""
    forecasts = {t: forecaster(t, cutoff(t)) for t in origins}
    return score(origins, forecasts, observed)
