"""Synthetic parameter recovery for calibration (T6.10, ADR 0011).

A small three-county outbreak simulated by the WP6b simulator and reported through the
calibration observation model; parameters are drawn from the priors, the data are simulated,
and the fit's 90 percent intervals are checked against the truth. Runs in separate processes
(spawned, so no thread state is copied into children).
"""

from __future__ import annotations

import multiprocessing as mp
from datetime import date, timedelta

import numpy as np

from project.model import calibrate as cal
from project.model import simulator as sm

POP = np.array([200_000, 100_000, 50_000])
SUSCEPTIBLE = (POP * 0.12).astype(np.int64)
SEEDED = np.array([20, 0, 0])
DAYS = 140
START = date(2026, 3, 2)  # a Monday
SNAPS = [d for d in range(35, DAYS) if (START + timedelta(days=d)).weekday() in (0, 2, 4)]
PRIORS = (cal.Prior("r0", 9.9, 18.1), *cal.OBSERVATION_PRIORS)


def _coupling() -> np.ndarray:
    return sm.coupling_matrix(
        ["a", "b", "c"],
        commuting=[("a", "b", 1.0), ("b", "c", 1.0), ("c", "a", 1.0)],
        strengths={"commuting": 0.05},
    )


COUPLING = _coupling()


def simulate(theta: dict[str, float], seed: int) -> np.ndarray:
    return sm.simulate(
        POP,
        SUSCEPTIBLE - SEEDED,
        np.zeros(3, np.int64),
        SEEDED,
        r0=theta["r0"],
        latent_days=7.0,
        infectious_days=8.0,
        latent_stages=4,
        infectious_stages=4,
        coupling=COUPLING,
        days=DAYS,
        seed=seed,
    ).incidence


def synthetic(theta: dict[str, float], seed: int) -> cal.Observations:
    """Observed cumulative counts at Monday, Wednesday and Friday snapshots, from the model."""
    skeleton = cal.Observations(
        START, {c: (np.array(SNAPS), np.zeros(len(SNAPS))) for c in range(3)}
    )
    sim = cal.Problem(simulate, PRIORS, skeleton).dataset(theta, seed)
    return cal.Observations(
        START,
        {c: (np.array(SNAPS), np.concatenate([[0.0], np.cumsum(sim[c])])) for c in range(3)},
    )


def recover(i: int) -> dict[str, bool]:
    """Draw parameters from the priors, simulate, fit; which 90 percent intervals cover."""
    rng = np.random.default_rng(10_000 + i)
    truth = {p.name: float(p.from_unit(rng.random())) for p in PRIORS}
    problem = cal.Problem(simulate, PRIORS, synthetic(truth, 20_000 + i))
    s = cal.fit(problem, particles=200, generations=8, min_acceptance=0.01, seed=i).summary()
    return {p.name: s[p.name]["low"] <= truth[p.name] <= s[p.name]["high"] for p in PRIORS}


def coverage(datasets: int = 20, processes: int | None = None) -> dict[str, int]:
    with mp.get_context("spawn").Pool(processes) as pool:
        results = pool.map(recover, range(datasets))
    return {p.name: sum(r[p.name] for r in results) for p in PRIORS}
