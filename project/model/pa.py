"""The Pennsylvania calibration problem: 67 counties (WP6c, ADR 0012).

Assembles everything the ABC calibration (``calibrate``) needs for the real outbreak:

- counties, populations and coupling (``sensitivity.build``, WP6b);
- susceptible fractions: ``n_draws`` seeded draws (WP6a, the ``under_covered`` scenario in
  ``project/susceptibility/params.yml``); each simulation takes one draw, so that uncertainty
  enters the fit;
- seeding from the earliest known case dates and intervention factors from events
  (``inputs``, ADR 0008), rebuilt for each candidate's ``lead_days`` and ``factor_<type>``;
- post-outbreak vaccination: statewide immunity gained from DOH-staff doses (``estimate``,
  the ``post_outbreak`` default scenario), spread evenly over each dose period and across the
  counties with a known case by that day, in proportion to population (an assumption: the
  doses are statewide, ADR 0012).

Calibrated parameters: R0, ``lead_days``, one transmission factor per intervention event type,
and the observation parameters (ascertainment, reporting delay, weekend factor, dispersion).
Real observations come from ``calibrate.observations_from_curated``, which refuses before
Gate G3; ``synthetic`` builds a dataset from the same model for dry runs.

Reads only through ``ingest.access`` and the WP6 modules (I8).
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

from ingest import access
from project.leak import check_known
from project.model import calibrate as cal
from project.model import inputs, sensitivity, simulator, validate
from project.susceptibility import estimate

MARGIN_DAYS = 7
OUTPUTS = Path(__file__).resolve().parents[1] / "outputs" / "calibration_pa"
# Dry-run truth: inside every prior; factors below 1 so the event effects are exercised.
DRY_TRUTH = {
    "r0": 15.0,
    "lead_days": 21.0,
    "censored_lead_days": 60.0,
    "factor_intervention": 0.8,
    "factor_health_alert": 0.9,
    "rho": 0.7,
    "k": 20.0,
    "report_delay": 3.0,
    "weekend": 0.6,
}
# The model that forecasts are scored with (ADR 0026). Frozen from the 2026-11-04 scoring on:
# any change to the model, its inputs' handling or its priors is a new version, scored only on
# origins after it is introduced, never silently re-scored on past ones.
MODEL_VERSION = "1"
POOL_BELOW = 10  # counties with fewer cases are fitted as one "rest" group (ADR 0021)
FIRST_SNAPSHOT = date(2026, 10, 5)  # the first county snapshot (Gate G3 counts from here)


@dataclass
class PAModel:
    fips: list[str]
    population: np.ndarray
    coupling: np.ndarray
    fractions: np.ndarray  # (draws, counties) susceptible fractions
    start: date
    days: int
    first_known: pl.DataFrame
    events: pl.DataFrame
    scopes: dict[str, list[str]]
    vaccination: np.ndarray  # (days, counties) expected people made immune per day
    params: dict[str, Any]
    refs: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _read(table: str, root: Path | None, known_at: datetime | None) -> pl.DataFrame:
    if known_at is None:
        return access.current(table, root=root)
    return check_known(access.as_known_at(table, known_at, root=root), known_at, table)


def vaccination_array(
    gains: pl.DataFrame,
    fips: list[str],
    population: np.ndarray,
    known: pl.DataFrame,
    start: date,
    days: int,
) -> np.ndarray:
    """Immunity gained per day and county. Each dose period's ``immune_gained`` is spread
    evenly over its days, then over counties with a known case by that day in proportion to
    population; days with no such county get none (doses there are not modelled)."""
    out = np.zeros((days, len(fips)))
    idx = {f: i for i, f in enumerate(fips)}
    known_day = np.full(len(fips), np.inf)
    for f, d in known.select("county_fips", "known_by").rows():
        if f in idx:
            known_day[idx[f]] = (d - start).days
    for r in gains.iter_rows(named=True):
        a, b = (r["period_start"] - start).days, (r["period_end"] - start).days
        span = max(b - a + 1, 1)
        per_day = float(r["immune_gained"] or 0.0) / span
        for t in range(max(a, 0), min(b + 1, days)):
            on = known_day <= t
            if on.any() and per_day > 0:
                w = population * on
                out[t] += per_day * w / w.sum()
    return out


def build(
    end: date,
    root: Path | None = None,
    known_at: datetime | None = None,
    n_draws: int = 200,
    seed: int = 20261015,
    scenario: str | None = None,
) -> PAModel:
    mp = simulator.load_params()
    sp = estimate.load_params()
    base = sensitivity.build(root, mp)
    inp = estimate.county_inputs(root, known_at, sp)
    if inp.counties["county_fips"].to_list() != base.fips:
        raise ValueError("susceptibility and population counties differ")
    scen = scenario or sp["under_covered"]["default"]
    frac = estimate.draws(inp, sp, scen, n_draws, seed)["susceptible_fraction"]
    if np.isnan(frac).any():
        raise ValueError("a county has no susceptibility estimate; refusing to guess (I5)")
    events = _read("event", root, known_at)
    scopes = {
        e: access.county_scope(s, root) for e, s in events.select("event_id", "county_scope").rows()
    }
    county = _read("case_county", root, known_at)
    if county.height:
        county = county.filter(~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES)))
    sp_seed = mp["seeding"]
    known = inputs.first_known(
        events,
        scopes,
        county.select("county_fips", "as_of_date", "cum_cases") if county.height else county,
        case_events=list(sp_seed["case_events"]),
        presence_types=list(sp_seed["presence_types"]),
    )
    if not known.height:
        raise ValueError("no county has a known first case; nothing to seed")
    lead_max = int(sp_seed["lead_days"]["high"])
    first: date = known["known_by"].min()  # type: ignore[assignment]
    start = first - timedelta(days=lead_max + MARGIN_DAYS)
    days = (end - start).days + 1
    notes = []
    doses = estimate.latest_doses(root, known_at)
    vacc = np.zeros((days, len(base.fips)))
    if doses.height:
        po = sp["post_outbreak"]["scenarios"][sp["post_outbreak"]["default"]]
        ve = sp["vaccine_effectiveness"]
        gains = estimate.dose_adjustment(
            doses,
            po["infant_share"],
            po["second_dose_share"],
            ve["one_dose"]["mean"],
            ve["two_dose"]["mean"],
        )
        vacc = vaccination_array(gains, base.fips, base.population, known, start, days)
    else:
        notes.append("no dose data: post-outbreak vaccination not modelled")
    refs = {
        **inp.raw_refs,
        "case_county": [r for r in county["raw_sha256"].to_list() if r] if county.height else [],
        "vaccine_doses": doses["raw_sha256"].drop_nulls().to_list() if doses.height else [],
    }
    return PAModel(
        base.fips,
        base.population,
        base.coupling,
        frac,
        start,
        days,
        known,
        events,
        scopes,
        vacc,
        mp,
        refs,
        notes,
    )


def priors(model: PAModel) -> list[cal.Prior]:
    d = model.params["disease"]
    out = [
        cal.Prior("r0", d["r0"]["low"], d["r0"]["high"]),
        cal.Prior(
            "lead_days",
            float(model.params["seeding"]["lead_days"]["low"]),
            float(model.params["seeding"]["lead_days"]["high"]),
        ),
    ]
    if "censored_lead_days" in model.params["seeding"]:  # ADR 0022
        c = model.params["seeding"]["censored_lead_days"]
        out.append(cal.Prior("censored_lead_days", float(c["low"]), float(c["high"])))
    for etype, v in model.params["interventions"].items():
        out.append(cal.Prior(f"factor_{etype}", float(v["low"]), 1.0))
    return out + list(cal.OBSERVATION_PRIORS)


def simulate_fn(model: PAModel) -> cal.Simulate:
    """theta, seed -> daily infections (days, counties) for the 67-county model."""
    d = model.params["disease"]
    sp_seed = model.params["seeding"]
    lags = {t: int(v["lag_days"]) for t, v in model.params["interventions"].items()}
    n = model.population.astype(np.int64)

    def run(theta: dict[str, float], seed: int) -> np.ndarray:
        frac = model.fractions[seed % len(model.fractions)]
        s0 = np.round(model.population * frac).astype(np.int64)
        seeds, _ = inputs.seeding(
            model.first_known,
            model.fips,
            model.start,
            model.days,
            mode=sp_seed["mode"],
            exposed=int(sp_seed["exposed"]),
            lead_days=int(round(theta["lead_days"])),
            censored_lead_days=(
                int(round(theta["censored_lead_days"])) if "censored_lead_days" in theta else None
            ),
        )
        effects = {t: {"factor": theta[f"factor_{t}"], "lag_days": lag} for t, lag in lags.items()}
        mult, _ = inputs.intervention_mult(
            model.events,
            model.scopes,
            model.fips,
            model.start,
            model.days,
            effects,
            model.first_known,
        )
        return simulator.simulate(
            n,
            s0,
            np.zeros(len(n), np.int64),
            np.zeros(len(n), np.int64),
            r0=theta["r0"],
            latent_days=d["latent_days"]["value"],
            infectious_days=d["infectious_days"]["value"],
            latent_stages=d["latent_days"]["stages"],
            infectious_stages=d["infectious_days"]["stages"],
            coupling=model.coupling,
            days=model.days,
            seed=seed,
            mult=mult,
            seeds=seeds,
            vaccination=model.vaccination,
        ).incidence

    return run


def problem(model: PAModel, obs: cal.Observations) -> cal.Problem:
    if obs.start != model.start:
        raise ValueError("observations and model must share a start date")
    return cal.Problem(simulate_fn(model), priors(model), obs)


def curated_problem(
    model: PAModel, root: Path | None = None, known_at: datetime | None = None
) -> tuple[cal.Problem, dict[str, list[str]]]:
    """The real fit's problem; ``observations_from_curated`` refuses before Gate G3."""
    obs, refs = cal.observations_from_curated(
        model.fips, model.start, root, known_at, pool_below=POOL_BELOW
    )
    return problem(model, obs), {**model.refs, **refs}


def statewide_dates(
    first: date, start: date, root: Path | None = None, known_at: datetime | None = None
) -> list[date]:
    """Dates of the T1 calendar-year statewide counts the real fit uses before the first county
    snapshot (the selection in ``calibrate.observations_from_curated``); dates only, no counts."""
    st = _read("case_state", root, known_at)
    if not st.height:
        return []
    st = st.filter(
        ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
        & (pl.col("source_tier") == "T1")
        & (pl.col("count_definition") == "calendar_year")
        & (pl.col("as_of_date") < first)
        & (pl.col("as_of_date") >= start)
    )
    return sorted(set(st["as_of_date"].to_list()))


def synthetic(
    model: PAModel,
    truth: dict[str, float],
    snapshot_days: list[int],
    seed: int,
    state_days: list[int] | None = None,
) -> cal.Observations:
    """A dataset from the model itself at ``truth``: county snapshots on ``snapshot_days``
    (counties with any reported case by the last one) plus statewide totals on ``state_days``
    before them (default: weekly for 60 days), ending at the first snapshot."""
    first = snapshot_days[0]
    if state_days is None:
        state_days = list(range(max(first - 60, 0), first, 7))
    state_days = sorted(d for d in state_days if 0 <= d < first) + [first]
    skeleton = cal.Observations(
        model.start,
        {
            **{
                c: (np.array(snapshot_days), np.zeros(len(snapshot_days)))
                for c in range(len(model.fips))
            },
            "state": (np.array(state_days), np.zeros(len(state_days))),
        },
    )
    sim = problem(model, skeleton).dataset(truth, seed)
    series: dict[Any, tuple[np.ndarray, np.ndarray]] = {}
    for geo, inc in sim.items():
        days = state_days if geo == "state" else snapshot_days
        if geo != "state" and inc.sum() == 0:
            continue
        series[geo] = (np.array(days), np.concatenate([[0.0], np.cumsum(inc)]))
    return cal.Observations(model.start, series)


def snapshot_dates(first: date = FIRST_SNAPSHOT, n: int = 10) -> list[date]:
    """``n`` Monday, Wednesday and Friday dates from ``first``: the dashboard's publishing days
    (ADR 0010); ten is Gate G3."""
    out: list[date] = []
    d = first
    while len(out) < n:
        if d.weekday() in (0, 2, 4):
            out.append(d)
        d += timedelta(days=1)
    return out


def dry_run(
    out_dir: Path | None = None,
    root: Path | None = None,
    *,
    particles: int = 300,
    generations: int = 8,
    min_cases: int = 500,
    seed: int = 20261015,
    now: datetime | None = None,
) -> Path:
    """Fit the 67-county problem to one synthetic dataset made from the model at ``DRY_TRUTH``
    on ten snapshot dates. The dataset is the first simulation seed whose statewide count over
    the observed window reaches ``min_cases``: an outbreak the size of the real one, not a
    fade-out (the real data are conditioned on a large outbreak too). Writes the posterior,
    predictive checks and a manifest under ``project/outputs/`` (gitignored, I10)."""
    dates = snapshot_dates()
    model = build(dates[-1] + timedelta(days=35), root, seed=seed)
    snaps = [(d - model.start).days for d in dates]
    # Statewide counts on the dates the real fit has them (DOH releases), simulated values.
    state = [(d - model.start).days for d in statewide_dates(dates[0], model.start, root)]
    data_seed, obs = None, None
    for s in range(seed, seed + 200):
        obs = synthetic(model, DRY_TRUTH, snaps, s, state)
        if obs.series["state"][1][-1] >= min_cases:
            data_seed = s
            break
    if obs is None or data_seed is None:
        raise RuntimeError(f"no synthetic outbreak reached {min_cases} cases in 200 seeds")
    full = obs
    obs = cal.drop_superseded(cal.pool_small(obs, POOL_BELOW), str)
    prob = problem(model, obs)
    t0 = time.monotonic()
    result = cal.fit(prob, particles=particles, generations=generations, seed=seed)
    secs = time.monotonic() - t0
    check = forecast_check(model, result, dates[-1], DRY_TRUTH, data_seed, full)
    path = cal.write(
        prob,
        result,
        out_dir or OUTPUTS / "synthetic",
        kind="calibration-pa-synthetic",
        inputs=model.refs,
        params={
            "truth": DRY_TRUTH,
            "data_seed": data_seed,
            "snapshot_days": snaps,
            "statewide_days": state,
            "start": model.start.isoformat(),
            "particles": particles,
            "generations": generations,
            "fit_seconds": round(secs, 1),
            "pool_below": POOL_BELOW,
            "forecast_check": check,
            "notes": model.notes,
        },
        now=now,
    )
    return path


def forecast_check(
    model: PAModel,
    result: cal.Fit,
    origin: date,
    truth: dict[str, float],
    data_seed: int,
    obs: cal.Observations,
    min_cases: int = POOL_BELOW,
    draws: int = 200,
) -> dict[str, dict[str, float]]:
    """Synthetic forecast check (ADR 0021): forecasts 1 to 4 weeks after ``origin``, made both
    ways (continuing the accepted trajectories, and fresh simulations), scored against what the
    synthetic truth went on to report: its own trajectory (``data_seed``) reported with
    negative binomial noise. Geographies: the state and counties with at least ``min_cases``.
    Returns, per method, the share of targets inside the 50 and 90 percent intervals and the
    median absolute error of the forecast median."""
    run = simulate_fn(model)
    cum = cal.expected_cumulative(run(truth, data_seed), truth, model.start)
    rng = np.random.default_rng(data_seed + 1)
    t0 = (origin - model.start).days
    geos: list[Any] = ["state"] + [
        g for g, (_d, c) in obs.series.items() if g != "state" and float(c[-1]) >= min_cases
    ]
    out: dict[str, dict[str, float]] = {}
    for name, cond in (("conditioned", True), ("fresh", False)):
        fc = forecast_samples(model, result, origin, geos, draws=draws, conditioned=cond)
        in50 = in90 = n = 0
        errors = []
        for g in geos:
            series = cum.sum(axis=1) if g == "state" else cum[:, g]
            for h in (1, 2, 3, 4):
                mu = max(float(series[t0 + 7 * h] - series[t0 + 7 * (h - 1)]), 1e-9)
                y = float(rng.negative_binomial(truth["k"], truth["k"] / (truth["k"] + mu)))
                x = fc[_geo_key(model, g)][h]
                lo50, hi50, lo90, hi90 = np.quantile(x, [0.25, 0.75, 0.05, 0.95])
                in50 += lo50 <= y <= hi50
                in90 += lo90 <= y <= hi90
                errors.append(abs(float(np.median(x)) - y))
                n += 1
        out[name] = {
            "targets": n,
            "coverage_50": round(in50 / n, 3),
            "coverage_90": round(in90 / n, 3),
            "median_abs_error": round(float(np.median(errors)), 2),
        }
    return out


def fit_real(
    origin: date,
    out_dir: Path | None = None,
    root: Path | None = None,
    *,
    particles: int = 300,
    generations: int = 8,
    draws: int = 200,
    seed: int = 20261015,
) -> Path:
    """The real fit at a forecast origin on the data known at its cutoff, and its 1 to 4 week
    forecast samples. Refuses before Gate G3 (``GateError``). Writes under
    ``project/outputs/calibration_pa/real/<origin>/`` (gitignored; nothing public before G4)."""
    known_at = cutoff(origin)
    model = build(origin + timedelta(days=35), root, known_at=known_at, seed=seed)
    prob, refs = curated_problem(model, root, known_at)
    t0 = time.monotonic()
    result = cal.fit(prob, particles=particles, generations=generations, seed=seed)
    secs = time.monotonic() - t0
    out = out_dir or OUTPUTS / "real" / origin.isoformat()
    samples = forecast_samples(model, result, origin, all_geographies(model), draws=draws)
    rows = [
        {"geography": g, "horizon_weeks": h, "draw": i, "new_cases": float(v)}
        for g, by_h in samples.items()
        for h, vals in by_h.items()
        for i, v in enumerate(vals)
    ]
    out.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(out / "forecast_samples.csv")
    return cal.write(
        prob,
        result,
        out,
        kind="calibration-pa-real",
        inputs=refs,
        params={
            "model_version": MODEL_VERSION,
            "origin": origin.isoformat(),
            "known_at": known_at.isoformat(),
            "start": model.start.isoformat(),
            "particles": particles,
            "generations": generations,
            "draws": draws,
            "seconds": round(secs, 1),
            "superseded_snapshots": prob.obs.superseded,
        },
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m project.model.pa")
    ap.add_argument("--particles", type=int, default=300)
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--origin",
        type=date.fromisoformat,
        help="fit the real data known at this origin (refuses before Gate G3)",
    )
    a = ap.parse_args(argv)
    if a.origin is not None:
        path = fit_real(
            a.origin, a.out, particles=a.particles, generations=a.generations, seed=a.seed
        )
        print(f"real fit at origin {a.origin}: wrote {path}")
        return 0
    path = dry_run(a.out, particles=a.particles, generations=a.generations, seed=a.seed)
    print(f"calibration dry run (synthetic data): wrote {path}")
    return 0


ET = ZoneInfo("America/New_York")


def cutoff(origin: date) -> datetime:
    """Data known at a forecast origin: everything fetched by the end of that day, ET (I6)."""
    return datetime.combine(origin, dt_time(23, 59, 59), ET).astimezone(UTC)


def forecast_samples(
    model: PAModel,
    result: cal.Fit,
    origin: date,
    geographies: list[Any],
    horizons: tuple[int, ...] = (1, 2, 3, 4),
    draws: int = 200,
    seed: int = 11,
    conditioned: bool = True,
) -> dict[str, dict[int, np.ndarray]]:
    """Posterior predictive samples of cases newly reported in each week after ``origin``, per
    geography (county index or "state"): report the epidemic through the observation model and
    draw negative binomial weekly counts. ``conditioned`` (the default, ADR 0021) continues each
    resampled particle's own accepted trajectory (its simulation seed), so a forecast starts
    from an epidemic that matched the data; otherwise each draw is a fresh simulation."""
    run = simulate_fn(model)
    t0 = (origin - model.start).days
    if t0 + 7 * max(horizons) >= model.days:
        raise ValueError("the model run ends before the last forecast week")
    if conditioned and result.seeds is None:
        raise ValueError("the fit kept no particle seeds; cannot continue its trajectories")
    rng = np.random.default_rng(seed)
    out: dict[str, dict[int, list[float]]] = {
        _geo_key(model, g): {h: [] for h in horizons} for g in geographies
    }
    for n, i in enumerate(result.resample_index(draws, seed)):
        theta = {p.name: float(x) for p, x in zip(result.priors, result.samples[i], strict=True)}
        sim_seed = int(result.seeds[i]) if conditioned and result.seeds is not None else 700_000 + n
        cum = cal.expected_cumulative(run(theta, sim_seed), theta, model.start)
        k = theta["k"]
        for g in geographies:
            series = cum.sum(axis=1) if g == "state" else cum[:, g]
            for h in horizons:
                mu = max(float(series[t0 + 7 * h] - series[t0 + 7 * (h - 1)]), 1e-9)
                out[_geo_key(model, g)][h].append(float(rng.negative_binomial(k, k / (k + mu))))
    return {g: {h: np.array(v) for h, v in by_h.items()} for g, by_h in out.items()}


def all_geographies(model: PAModel) -> list[Any]:
    """Every county (by index) and the state: forecasts are made for each, pooled or not."""
    return [*range(len(model.fips)), "state"]


def _geo_key(model: PAModel, g: Any) -> str:
    return "state" if g == "state" else model.fips[g]


def forecaster(
    root: Path | None = None,
    *,
    particles: int = 300,
    generations: int = 8,
    draws: int = 200,
    seed: int = 20261015,
) -> validate.Forecaster:
    """Fit at each origin with data known at its cutoff, then forecast 1 to 4 weeks ahead.
    Refuses (``GateError``) at origins with fewer than ten county snapshot dates."""

    def run(origin: date, known_at: datetime) -> dict[str, dict[int, np.ndarray]]:
        model = build(origin + timedelta(days=35), root, known_at=known_at, seed=seed)
        prob, _ = curated_problem(model, root, known_at)
        result = cal.fit(prob, particles=particles, generations=generations, seed=seed)
        return forecast_samples(model, result, origin, all_geographies(model), draws=draws)

    return run


def observed_series(root: Path | None = None) -> dict[str, dict[date, int]]:
    """What was later reported: T1 calendar-year county snapshots and the dashboard's statewide
    total, by snapshot date (latest revision). Missing counts are absent, not zero (I5)."""
    out: dict[str, dict[date, int]] = {}
    county = access.current("case_county", root=root)
    if county.height:
        county = county.filter(
            ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
            & (pl.col("source_tier") == "T1")
            & (pl.col("count_definition") == "calendar_year")
            & pl.col("cum_cases").is_not_null()
        )
        for f, d, c in county.select("county_fips", "as_of_date", "cum_cases").rows():
            out.setdefault(f, {})[d] = c
    state = access.current("case_state", root=root)
    if state.height:
        state = state.filter(
            (pl.col("source_id") == "doh_dashboard")
            & (pl.col("source_tier") == "T1")
            & (pl.col("count_definition") == "calendar_year")
            & pl.col("cum_cases").is_not_null()
        )
        out["state"] = dict(state.select("as_of_date", "cum_cases").rows())  # type: ignore[arg-type]
    return out


if __name__ == "__main__":
    raise SystemExit(main())
