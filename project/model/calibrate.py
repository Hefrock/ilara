"""Calibration (WP6c, HANDOFF 6c, T6.10 to T6.12, ADR 0011).

Fits simulator parameters to reported counts by approximate Bayesian computation with population
Monte Carlo (ABC-SMC): each candidate simulates a whole dataset (stochastic epidemic, then the
observation model below) and is kept when its snapshot increments are close to the observed
ones. A likelihood estimated from single simulator runs was tried first and rejected: the
outbreak's random timing makes it vary by thousands of log units at fixed parameters (ADR 0011).

Observation model (HANDOFF 6c), applied to the simulated daily infections of each county:

- under-ascertainment: each infection is reported with probability ``rho``;
- reporting delay: infection to report follows a discretised gamma with mean
  ``ONSET_DAYS + report_delay`` days (incubation to rash, then rash to report) and fixed spread;
- day of week: reports on Saturday and Sunday are scaled by ``weekend``, weekdays raised so a
  week's total is unchanged (the dashboard's weekday pattern, S1);
- counts: the increase in cumulative reported cases between consecutive snapshots of a
  geography (a county, or the state) is negative binomial with that expected value and size
  ``k``. Increments, not cumulative totals, are compared, so snapshots are not counted twice;
  each geography's first snapshot is its baseline.

Before Gate G3 (ten county snapshot dates, E12) the code runs on synthetic data only:
``observations_from_curated`` refuses to build a county fit with fewer snapshot dates, and any
input row of tier ``T3-derived`` stops the default fit (T6.12). Every fit writes posterior
predictive checks (T6.11) and a run manifest (I9) to ``project/outputs/`` (gitignored).
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from ingest import access
from project import manifest

ONSET_DAYS = 11.5  # infection to rash onset: mean incubation (klinkenberg2011, 11-12 days)
DELAY_SD = 3.0  # spread of infection to report, days (assumption, ADR 0011)
MAX_DELAY = 40
G3_SNAPSHOTS = 10  # E12

Simulate = Callable[
    [dict[str, float], int], np.ndarray
]  # theta, seed -> (days, counties) infections


@dataclass(frozen=True)
class Prior:
    """Uniform on [low, high], or log-uniform when ``log``."""

    name: str
    low: float
    high: float
    log: bool = False

    def to_unit(self, x: Any) -> Any:
        if self.log:
            return (np.log(x) - math.log(self.low)) / (math.log(self.high) - math.log(self.low))
        return (x - self.low) / (self.high - self.low)

    def from_unit(self, u: Any) -> Any:
        if self.log:
            return np.exp(math.log(self.low) + u * (math.log(self.high) - math.log(self.low)))
        return self.low + u * (self.high - self.low)


OBSERVATION_PRIORS = (
    Prior("rho", 0.2, 1.0),
    Prior("k", 1.0, 200.0, log=True),
    Prior("report_delay", 1.0, 10.0),
    Prior("weekend", 0.2, 1.0),
)


@dataclass
class Observations:
    """Cumulative reported cases by geography at snapshot days (day 0 = simulation start).
    Geographies are county indices into the simulated counties, or ``"state"`` (all)."""

    start: date
    series: dict[Any, tuple[np.ndarray, np.ndarray]]  # geo -> (days, cumulative counts)

    def increments(self) -> dict[Any, tuple[np.ndarray, np.ndarray]]:
        """Per geography: the snapshot days and the increases between consecutive snapshots.
        The first snapshot is the baseline (its total includes cases before the simulation
        starts), so ``days`` has one more entry than the increments."""
        out = {}
        for geo, (days, cum) in self.series.items():
            order = np.argsort(days)
            d, c = np.asarray(days)[order], np.asarray(cum, dtype=float)[order]
            if len(d) >= 2:
                out[geo] = (d, np.diff(c))
        return out


def delay_pmf(report_delay: float) -> np.ndarray:
    """Probability that an infection on day 0 is reported on day d, d = 0..MAX_DELAY: a gamma
    density with mean ``ONSET_DAYS + report_delay`` and sd ``DELAY_SD``, taken at day
    midpoints and normalised."""
    mean = ONSET_DAYS + report_delay
    shape = (mean / DELAY_SD) ** 2
    scale = DELAY_SD**2 / mean
    t = np.arange(MAX_DELAY + 1) + 0.5
    logpdf = (shape - 1) * np.log(t) - t / scale
    pmf = np.exp(logpdf - logpdf.max())
    return pmf / pmf.sum()


def weekday_weights(start: date, days: int, weekend: float) -> np.ndarray:
    """Reporting weight per day: ``weekend`` on Saturday and Sunday, weekdays scaled so seven
    consecutive days sum to seven."""
    weekday = 7 / (5 + 2 * weekend)
    dow = (start.weekday() + np.arange(days)) % 7
    return np.where(dow >= 5, weekend * weekday, weekday)


def expected_cumulative(infections: np.ndarray, theta: dict[str, float], start: date) -> np.ndarray:
    """Expected cumulative reported cases by day and county, shape (days, counties)."""
    days = infections.shape[0]
    g = delay_pmf(theta["report_delay"])
    rep = np.zeros(infections.shape)
    for c in range(infections.shape[1]):
        rep[:, c] = np.convolve(infections[:, c], g)[:days]
    rep *= theta["rho"] * weekday_weights(start, days, theta["weekend"])[:, None]
    return np.cumsum(rep, axis=0)


@dataclass
class Problem:
    simulate: Simulate
    priors: Sequence[Prior]
    obs: Observations

    def __post_init__(self) -> None:
        self._inc = self.obs.increments()

    def dataset(self, theta: dict[str, float], seed: int) -> dict[Any, np.ndarray]:
        """One simulated dataset: snapshot increments per geography drawn from the full model
        (stochastic epidemic, then negative binomial reporting)."""
        rng = np.random.default_rng(seed)
        cum = expected_cumulative(self.simulate(theta, seed), theta, self.obs.start)
        k = theta["k"]
        out = {}
        for geo, (days, _y) in self._inc.items():
            series = cum.sum(axis=1) if geo == "state" else cum[:, geo]
            mu = np.maximum(np.diff(series[np.minimum(days, len(series) - 1)]), 1e-9)
            out[geo] = rng.negative_binomial(k, k / (k + mu)).astype(float)
        return out

    def distance(self, sim: dict[Any, np.ndarray]) -> float:
        """Two parts, averaged over geographies: the root mean square difference of
        Anscombe-transformed increments (level and timing; variance near 1/4 for Poisson
        counts), plus the absolute difference in log roughness, the mean squared change between
        consecutive transformed increments (reporting noise, which informs ``k``). Without the
        second part the distance favours low-noise simulations and biases ``k`` upward."""
        total = 0.0
        for geo, (_days, y) in self._inc.items():
            a_sim, a_obs = np.sqrt(sim[geo] + 0.375), np.sqrt(y + 0.375)
            level = math.sqrt(float(np.mean((a_sim - a_obs) ** 2)))
            rough = abs(math.log(_roughness(a_sim)) - math.log(_roughness(a_obs)))
            total += level + rough
        return total / max(len(self._inc), 1)


def _roughness(a: np.ndarray) -> float:
    return float(np.mean(np.diff(a) ** 2)) + 0.05 if len(a) > 1 else 0.05


@dataclass
class Fit:
    priors: Sequence[Prior]
    samples: np.ndarray  # (particles, params) on the natural scale
    weights: np.ndarray  # normalised importance weights
    tolerances: list[float]
    seed: int
    simulations: int = 0
    acceptance: list[float] = field(default_factory=list)

    def summary(self, level: float = 0.9) -> dict[str, dict[str, float]]:
        lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
        out = {}
        for i, p in enumerate(self.priors):
            order = np.argsort(self.samples[:, i])
            v, cw = self.samples[order, i], np.cumsum(self.weights[order])
            q = [float(v[min(np.searchsorted(cw, t), len(v) - 1)]) for t in (lo, 0.5, hi)]
            out[p.name] = {"low": q[0], "median": q[1], "high": q[2]}
        return out

    def resample(self, n: int, seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return self.samples[rng.choice(len(self.samples), size=n, p=self.weights)]


def _theta(priors: Sequence[Prior], row: np.ndarray) -> dict[str, float]:
    return {p.name: float(v) for p, v in zip(priors, row, strict=True)}


def fit(
    problem: Problem,
    *,
    particles: int = 300,
    generations: int = 8,
    quantile: float = 0.5,
    min_acceptance: float = 0.02,
    seed: int = 1,
) -> Fit:
    """ABC population Monte Carlo (Beaumont et al. 2009) in the unit cube of the priors.

    Generation 0 draws from the prior and keeps all draws; each later generation sets the
    tolerance to the ``quantile`` of the previous accepted distances, proposes from the previous
    weighted particles with a Gaussian kernel of twice their weighted covariance, keeps
    proposals within tolerance, and weights them by prior over kernel mixture density. Stops
    after ``generations`` or when acceptance falls below ``min_acceptance``."""
    rng = np.random.default_rng(seed)
    pri = list(problem.priors)
    d = len(pri)
    sims = 0

    def run(u: np.ndarray) -> float:
        nonlocal sims
        sims += 1
        x = np.array([p.from_unit(u[j]) for j, p in enumerate(pri)])
        return problem.distance(problem.dataset(_theta(pri, x), int(rng.integers(2**31))))

    u = rng.random((particles, d))
    dist = np.array([run(r) for r in u])
    w = np.full(particles, 1.0 / particles)
    tols = [float("inf")]
    acc_rates: list[float] = []
    for _ in range(generations):
        eps = float(np.quantile(dist, quantile))
        mean = w @ u
        cov = 2 * ((u - mean).T * w) @ (u - mean) + 1e-9 * np.eye(d)
        chol = np.linalg.cholesky(cov)
        inv = np.linalg.inv(cov)
        new_u: list[np.ndarray] = []
        new_d: list[float] = []
        tries = 0
        while len(new_u) < particles:
            tries += 1
            if tries > particles / min_acceptance:
                break
            prop = u[rng.choice(particles, p=w)] + chol @ rng.normal(size=d)
            if np.any(prop <= 0) or np.any(prop >= 1):
                continue
            dd = run(prop)
            if dd <= eps:
                new_u.append(prop)
                new_d.append(dd)
        if len(new_u) < particles:
            break  # acceptance too low: keep the previous generation
        nu = np.array(new_u)
        diff = nu[:, None, :] - u[None, :, :]
        kern = np.exp(-0.5 * np.einsum("ijk,kl,ijl->ij", diff, inv, diff))
        nw = 1.0 / (kern @ w)
        u, dist, w = nu, np.array(new_d), nw / nw.sum()
        tols.append(eps)
        acc_rates.append(particles / tries)
    x = np.column_stack([p.from_unit(u[:, i]) for i, p in enumerate(pri)])
    return Fit(pri, x, w, tols, seed, sims, acc_rates)


def posterior_predictive(
    problem: Problem, result: Fit, draws: int = 200, seed: int = 7, level: float = 0.9
) -> pl.DataFrame:
    """T6.11: for each observed increment, the posterior predictive interval from ``draws``
    datasets simulated from posterior draws, and whether the observation falls inside it."""
    rows = []
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    thetas = result.resample(draws, seed)
    sims = [problem.dataset(_theta(result.priors, t), 900_000 + n) for n, t in enumerate(thetas)]
    for geo, (days, y) in problem.obs.increments().items():
        arr = np.array([s[geo] for s in sims])
        for j, d in enumerate(days[1:]):
            a, b = np.quantile(arr[:, j], [lo, hi])
            rows.append(
                {
                    "geography": str(geo),
                    "day": int(d),
                    "observed": float(y[j]),
                    "median": float(np.median(arr[:, j])),
                    "low": float(a),
                    "high": float(b),
                    "inside": bool(a <= y[j] <= b),
                }
            )
    return pl.DataFrame(rows)


def write(
    problem: Problem,
    result: Fit,
    out_dir: Path,
    *,
    kind: str,
    inputs: dict[str, list[str]],
    params: dict[str, Any],
    now: datetime | None = None,
) -> Path:
    """Posterior samples, summary, posterior predictive checks (T6.11) and a manifest (I9)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "posterior.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow([p.name for p in result.priors] + ["weight"])
        for row, wt in zip(result.samples, result.weights, strict=True):
            wr.writerow([f"{v:.6g}" for v in row] + [f"{wt:.6g}"])
    ppc = posterior_predictive(problem, result)
    ppc.write_csv(out_dir / "posterior_predictive.csv")
    summ = result.summary()
    return manifest.write(
        out_dir,
        kind,
        result.seed,
        params,
        inputs,
        extra={
            "calibrated": True,
            "summary": summ,
            "tolerances": result.tolerances,
            "acceptance": result.acceptance,
            "simulations": result.simulations,
            "ppc_coverage_90": ppc["inside"].sum() / ppc.height if ppc.height else None,
            "priors": [p.__dict__ for p in result.priors],
        },
        now=now,
    )


class TierError(ValueError):
    pass


class GateError(RuntimeError):
    pass


def observations_from_curated(
    fips: list[str],
    start: date,
    root: Path | None = None,
    known_at: datetime | None = None,
    allow_tiers: frozenset[str] = frozenset({"T1"}),
) -> tuple[Observations, dict[str, list[str]]]:
    """County snapshots (and statewide totals before them) from the curated store, for the
    default fit: T1 rows only (T6.12), calendar-year counts, DOH source. Refuses before Gate G3.
    Returns the observations and the raw references read, for the run manifest."""

    def read(table: str) -> pl.DataFrame:
        if known_at is None:
            return access.current(table, root=root)
        return access.as_known_at(table, known_at, root=root)

    county = read("case_county")
    state = read("case_state")
    for name, df in (("case_county", county), ("case_state", state)):
        if df.height and (df["source_tier"] == "T3-derived").any():
            raise TierError(f"{name} contains T3-derived rows; the default fit uses T1 only")
    county = county.filter(
        ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
        & pl.col("source_tier").is_in(list(allow_tiers))
        & (pl.col("count_definition") == "calendar_year")
    )
    dates = county["as_of_date"].unique().sort().to_list() if county.height else []
    if len(dates) < G3_SNAPSHOTS:
        raise GateError(
            f"{len(dates)} county snapshot dates; Gate G3 needs {G3_SNAPSHOTS} (E12) before a "
            "county fit on real data"
        )
    series: dict[Any, tuple[np.ndarray, np.ndarray]] = {}
    for i, f in enumerate(fips):
        rows = county.filter(pl.col("county_fips") == f).sort("as_of_date")
        if rows.height:
            series[i] = (
                np.array([(d - start).days for d in rows["as_of_date"]]),
                rows["cum_cases"].fill_null(0).to_numpy(),
            )
    st = (
        state.filter(
            ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
            & pl.col("source_tier").is_in(list(allow_tiers))
            & (pl.col("count_definition") == "calendar_year")
            & (pl.col("as_of_date") < dates[0])
            & (pl.col("as_of_date") >= start)
        )
        .sort("as_of_date")
        .unique("as_of_date", keep="last", maintain_order=True)
    )
    if st.height:
        series["state"] = (
            np.array([(d - start).days for d in st["as_of_date"]]),
            st["cum_cases"].to_numpy(),
        )
    refs = {
        "case_county": [r for r in county["raw_sha256"].to_list() if r],
        "case_state": [r for r in st["raw_sha256"].to_list() if r] if st.height else [],
    }
    return Observations(start, series), refs
