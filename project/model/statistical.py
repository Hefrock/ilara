"""A simple statistical comparator for the mechanistic model (ADR 0029 revisions).

It answers one question: does the transmission model forecast better than a model that knows
nothing about transmission? Frozen on the same day as model version 2 and scored the same way
(``validate``), at the same origins and on the same targets.

For each geography, from the weekly increases in the published total known at the origin
(``access.published_on_capture_days`` as known then, so nothing later is read):

- level: the mean of the last two weekly increases;
- growth: the per-week ratio of the last two weeks to the two before, ``((a + b + 1) /
  (c + d + 1)) ** 0.5``, clipped to [``GROWTH_MIN``, ``GROWTH_MAX``];
- forecast mean at horizon h: ``level * growth ** h``;
- counts: negative binomial with size from the last four increases by the method of moments,
  clipped to [``K_MIN``, ``K_MAX``] (Poisson-like when they vary less than their mean).

A geography with fewer than four weekly increases known gets no forecast (a gap, I5). The
rules are fixed here and not tuned to scores.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta

import numpy as np

from ingest import access

VERSION = "s1"
GROWTH_MIN, GROWTH_MAX = 0.5, 2.0
K_MIN, K_MAX = 1.0, 1000.0
WEEKS = 4


def weekly_increases(cum: Mapping[date, int], origin: date, weeks: int = WEEKS) -> list[int] | None:
    """The last ``weeks`` weekly increases ending at ``origin``, oldest first; None if any week
    lacks a value at either end."""
    out = []
    for i in range(weeks, 0, -1):
        end = origin - timedelta(days=7 * (i - 1))
        a, b = cum.get(end - timedelta(days=7)), cum.get(end)
        if a is None or b is None:
            return None
        out.append(b - a)
    return out


def parameters(inc: list[int]) -> tuple[float, float, float]:
    """(level, growth, size) from four weekly increases, oldest first."""
    d, c, b, a = (max(float(x), 0.0) for x in inc)
    level = (a + b) / 2
    growth = float(np.clip(((a + b + 1) / (c + d + 1)) ** 0.5, GROWTH_MIN, GROWTH_MAX))
    mean, var = float(np.mean(inc)), float(np.var(inc, ddof=1))
    size = K_MAX if var <= mean or mean <= 0 else mean**2 / (var - mean)
    return level, growth, float(np.clip(size, K_MIN, K_MAX))


def forecast(
    observed: Mapping[str, Mapping[date, int]],
    origin: date,
    horizons: tuple[int, ...] = (1, 2, 3, 4),
    draws: int = 200,
    seed: int = 11,
) -> dict[str, dict[int, np.ndarray]]:
    rng = np.random.default_rng(seed)
    out: dict[str, dict[int, np.ndarray]] = {}
    for geo in sorted(observed):
        inc = weekly_increases(observed[geo], origin)
        if inc is None:
            continue
        level, growth, size = parameters(inc)
        out[geo] = {}
        for h in horizons:
            mu = max(level * growth**h, 1e-9)
            out[geo][h] = rng.negative_binomial(size, size / (size + mu), draws).astype(float)
    return out


def forecaster(root=None, draws: int = 200, seed: int = 11):  # type: ignore[no-untyped-def]
    """A ``validate.Forecaster``: reads the published totals as known at the cutoff."""

    def run(origin: date, known_at: datetime) -> dict[str, dict[int, np.ndarray]]:
        obs = access.published_on_capture_days(known_at, root)
        known = {g: {d: v for d, v in s.items() if d <= origin} for g, s in obs.items()}
        return forecast(known, origin, draws=draws, seed=seed)

    return run
