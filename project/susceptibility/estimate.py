"""County susceptibility (WP6a, HANDOFF WP6, T6.1 and T6.3).

Effective susceptible fraction per county = population-weighted mix of age groups, each
``1 - coverage x vaccine effectiveness``, plus an under-covered subpopulation (U19) taken
outside the school survey. Coverage, effectiveness and the adult and under-5 assumptions are
drawn ``n_draws`` times from a seeded generator, so a run is reproducible from its seed.

School coverage is a December 2025 baseline. Post-outbreak vaccination is a separate, dated
statewide adjustment (``dose_adjustment``) that follows the accounting rule: early infant
doses add nothing; first doses add one-dose protection; second doses add the difference
between two-dose and one-dose protection.

Reads only through ``ingest.access`` (I8). Outputs go to ``project/outputs/`` (gitignored
until Gate G4, D07).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml

from ingest import access
from project import manifest

PARAMS = Path(__file__).with_name("params.yml")
OUTPUTS = Path(__file__).resolve().parents[1] / "outputs" / "susceptibility"


def load_params(path: Path = PARAMS) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _table(name: str, root: Path | None, known_at: datetime | None) -> pl.DataFrame:
    if known_at is None:
        return access.current(name, "curated", root)
    return access.as_known_at(name, known_at, "curated", root)


@dataclass
class Inputs:
    counties: pl.DataFrame  # one row per county: fips, name, age groups, grade rates
    grades: list[str]
    raw_refs: dict[str, list[str]]


def county_inputs(
    root: Path | None = None, known_at: datetime | None = None, params: dict | None = None
) -> Inputs:
    params = params or load_params()
    grades: list[str] = params["school"]["grades"]
    imm = _table("immunization_county", root, known_at).filter(
        (pl.col("source_tier") == "T1") & pl.col("grade").is_in(grades)
    )
    if imm.height and imm["school_year"].n_unique() > 1:
        imm = imm.filter(pl.col("school_year") == imm["school_year"].max())
    wide = imm.pivot(on="grade", index="county_fips", values=["mmr_up_to_date_pct", "enrolled"])
    geo = access.reference_table("geography_county", root).select("county_fips", "name")
    pop = access.reference_table("population_county", root).select(
        "county_fips",
        pl.col("total").alias("pop_total"),
        pl.col("under5_tot").alias("pop_u5"),
        (pl.col("age513_tot") + pl.col("age1417_tot")).alias("pop_child"),
        pl.col("age18plus_tot").alias("pop_adult"),
    )
    out = geo.join(pop, on="county_fips", how="left").join(wide, on="county_fips", how="left")
    for g in grades:  # a grade absent from the source stays a gap (I5)
        for col in (f"mmr_up_to_date_pct_{g}", f"enrolled_{g}"):
            if col not in out.columns:
                out = out.with_columns(pl.lit(None, pl.Float64).alias(col))
    return Inputs(
        out.sort("county_fips"),
        grades,
        {"immunization_county": imm["raw_sha256"].drop_nulls().to_list()},
    )


def _beta_mean_sd(rng: np.random.Generator, mean: float, sd: float, size: Any) -> np.ndarray:
    k = mean * (1 - mean) / sd**2 - 1
    return rng.beta(mean * k, (1 - mean) * k, size=size)


def draws(
    inp: Inputs, params: dict[str, Any], scenario: str, n_draws: int, seed: int
) -> dict[str, np.ndarray]:
    """Arrays of shape (n_draws, counties). NaN where a county lacks an input (never filled)."""
    rng = np.random.default_rng(seed)
    c = inp.counties
    n_c = c.height
    shape = (n_draws, n_c)
    ve = params["vaccine_effectiveness"]
    ve1 = _beta_mean_sd(rng, ve["one_dose"]["mean"], ve["one_dose"]["sd"], (n_draws, 1))
    ve2 = _beta_mean_sd(rng, ve["two_dose"]["mean"], ve["two_dose"]["sd"], (n_draws, 1))
    cap = params["school"]["max_effective_n"]

    cov: dict[str, np.ndarray] = {}
    weight: dict[str, np.ndarray] = {}
    for g in inp.grades:
        p = c[f"mmr_up_to_date_pct_{g}"].cast(pl.Float64).to_numpy() / 100
        n = np.minimum(c[f"enrolled_{g}"].cast(pl.Float64).to_numpy(), cap)
        ok = ~(np.isnan(p) | np.isnan(n))
        a = np.where(ok, p * n + 1, 1.0)
        b = np.where(ok, (1 - p) * n + 1, 1.0)
        d = rng.beta(a, b, size=shape)
        cov[g] = np.where(ok, d, np.nan)
        weight[g] = np.where(ok, c[f"enrolled_{g}"].cast(pl.Float64).to_numpy(), np.nan)
    wsum = sum(weight.values())
    cov_child = sum(cov[g] * weight[g] for g in inp.grades) / wsum
    cov_k = cov[inp.grades[0]]

    u5 = params["under5"]
    ratio = rng.uniform(u5["coverage_ratio"]["low"], u5["coverage_ratio"]["high"], (n_draws, 1))
    infant = u5["infant_share"]["value"]
    adult_imm = rng.uniform(
        params["adults"]["immune"]["low"], params["adults"]["immune"]["high"], (n_draws, 1)
    )
    sc = params["under_covered"]["scenarios"][scenario]

    s_u5 = infant + (1 - infant) * (1 - np.clip(cov_k * ratio, 0, 1) * ve1)
    s_child = 1 - cov_child * ve2
    s_adult = np.broadcast_to(1 - adult_imm, shape)
    pops = {k: c[k].cast(pl.Float64).to_numpy() for k in ("pop_u5", "pop_child", "pop_adult")}
    total = pops["pop_u5"] + pops["pop_child"] + pops["pop_adult"]
    s_main = pops["pop_u5"] * s_u5 + pops["pop_child"] * s_child + pops["pop_adult"] * s_adult
    s_main = s_main / total
    s_under = 1 - sc["coverage"] * ve2
    s_all = (1 - sc["share"]) * s_main + sc["share"] * s_under
    s_kids = (1 - sc["share"]) * s_child + sc["share"] * s_under
    return {
        "susceptible_fraction": s_all,
        "child_susceptible_fraction": s_kids,
        "child_coverage": cov_child,
        "population": np.broadcast_to(total, shape),
    }


def summarize(inp: Inputs, d: dict[str, np.ndarray], scenario: str) -> pl.DataFrame:
    s = d["susceptible_fraction"]
    pop = d["population"][0]

    def q(a: np.ndarray, p: float) -> np.ndarray:
        return np.quantile(a, p, axis=0)

    cols = {
        "county_fips": inp.counties["county_fips"].to_list(),
        "name": inp.counties["name"].to_list(),
        "scenario": [scenario] * len(pop),
        "population": pop,
        "child_coverage_mean": d["child_coverage"].mean(axis=0),
        "susceptible_fraction_mean": s.mean(axis=0),
        "susceptible_fraction_q05": q(s, 0.05),
        "susceptible_fraction_q50": q(s, 0.5),
        "susceptible_fraction_q95": q(s, 0.95),
        "child_susceptible_fraction_mean": d["child_susceptible_fraction"].mean(axis=0),
        "susceptibles_mean": (s * pop).mean(axis=0),
    }
    df = pl.DataFrame(cols)
    # NaN marks a missing input; store it as null, never as a number.
    return df.with_columns(pl.col(pl.Float64).fill_nan(None)).with_columns(
        pl.col(pl.Float64).round(6)
    )


def dose_adjustment(
    doses: pl.DataFrame,
    infant_share: float,
    second_dose_share: float,
    ve1: float,
    ve2: float,
) -> pl.DataFrame:
    """Expected people made immune by dated statewide doses (S8 accounting rule).

    ``doses`` has ``period_start``, ``period_end``, ``period_complete`` and ``doses``.
    Early infant doses (``infant_share``) add nothing; of the rest, first doses add ``ve1``
    each and second doses add ``ve2 - ve1`` each. Recipients of a first dose are assumed
    susceptible beforehand, which overstates the effect slightly."""
    if not 0 <= infant_share <= 1 or not 0 <= second_dose_share <= 1:
        raise ValueError("shares must lie in [0, 1]")
    countable = pl.col("doses") * (1 - infant_share)
    gain = countable * ((1 - second_dose_share) * ve1 + second_dose_share * (ve2 - ve1))
    return (
        doses.sort("period_start")
        .select(
            "period_start",
            "period_end",
            "period_complete",
            "doses",
            countable.alias("countable_doses"),
            gain.alias("immune_gained"),
        )
        .with_columns(pl.col("immune_gained").cum_sum().alias("immune_gained_cumulative"))
    )


def latest_doses(root: Path | None = None, known_at: datetime | None = None) -> pl.DataFrame:
    d = _table("vaccine_doses", root, known_at).filter(
        (pl.col("source_tier") == "T1") & (pl.col("geography") == "state")
    )
    if d.height == 0:
        return d
    return d.filter(pl.col("as_of_date") == d["as_of_date"].max())


def run(
    root: Path | None = None,
    out_dir: Path | None = None,
    seed: int = 20261008,
    n_draws: int = 2000,
    known_at: datetime | None = None,
) -> Path:
    params = load_params()
    inp = county_inputs(root, known_at, params)
    tables = []
    for i, scenario in enumerate(params["under_covered"]["scenarios"]):
        tables.append(summarize(inp, draws(inp, params, scenario, n_draws, seed + i), scenario))
    county = pl.concat(tables)

    doses = latest_doses(root, known_at)
    ve = params["vaccine_effectiveness"]
    adj = []
    for name, sc in params["post_outbreak"]["scenarios"].items():
        if doses.height:
            a = dose_adjustment(
                doses,
                sc["infant_share"],
                sc["second_dose_share"],
                ve["one_dose"]["mean"],
                ve["two_dose"]["mean"],
            )
            adj.append(a.with_columns(pl.lit(name).alias("scenario")))
    adjustment = pl.concat(adj) if adj else pl.DataFrame()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir or OUTPUTS / stamp
    out.mkdir(parents=True, exist_ok=True)
    county.write_csv(out / "county.csv")
    adjustment.write_csv(out / "dose_adjustment.csv")
    manifest.write(
        out,
        "susceptibility",
        seed,
        params,
        {**inp.raw_refs, "vaccine_doses": doses["raw_sha256"].drop_nulls().to_list()},
        {
            "n_draws": n_draws,
            "as_known_at": known_at.isoformat() if known_at else None,
            "doses_as_of": str(doses["as_of_date"].max()) if doses.height else None,
        },
    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m project.susceptibility.estimate")
    ap.add_argument("--seed", type=int, default=20261008)
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    out = run(out_dir=a.out, seed=a.seed, n_draws=a.draws)
    print(f"susceptibility: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
