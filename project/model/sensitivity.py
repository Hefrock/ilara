"""T6.2: final outbreak size versus the under-covered subpopulation parameter (U19).

For each ``under_covered`` scenario in ``project/susceptibility/params.yml``, draw county
susceptible fractions (WP6a), R0 from its prior range, and simulate a year from a fixed,
illustrative seeding. The output answers "how much does the U19 assumption move the final
size", not "how big will the outbreak be": nothing here is calibrated (6c needs Gate G3).

Reads only through ``ingest.access`` (I8). Outputs go to ``project/outputs/`` (gitignored
until Gate G4) with a run manifest (I9).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from ingest import access
from project import manifest
from project.model import simulator
from project.susceptibility import estimate

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs" / "sensitivity_u19"
SEED_COUNTY = "42071"  # illustrative seeding in Lancaster, the county with the most reported cases
SEED_INFECTIOUS = 5
DAYS = 365


@dataclass
class Model:
    fips: list[str]
    population: np.ndarray
    coupling: np.ndarray


def build(root: Path | None = None, params: dict | None = None) -> Model:
    params = params or simulator.load_params()
    pop = access.reference_table("population_county", root).sort("county_fips")
    fips = pop["county_fips"].to_list()
    mob = access.reference_table("mobility_edge", root)
    adj = access.reference_table("county_adjacency", root)
    cp = params["coupling"]
    k = simulator.coupling_matrix(
        fips,
        commuting=[(a, b, float(w)) for a, b, w in mob.select("origin", "dest", "flow").rows()],
        adjacency=[
            (a, b, float(w))
            for a, b, w in adj.select("a_fips", "b_fips", "shared_boundary_m").rows()
        ],
        long_range=cp["long_range"]["links"],
        strengths={
            name: float(cp[name]["strength"]) for name in ("commuting", "adjacency", "long_range")
        },
    )
    return Model(fips, pop["total"].to_numpy().astype(np.int64), k)


def run(
    root: Path | None = None,
    out_dir: Path | None = None,
    seed: int = 20261008,
    n_runs: int = 200,
) -> Path:
    mp = simulator.load_params()
    sp = estimate.load_params()
    model = build(root, mp)
    inp = estimate.county_inputs(root, params=sp)
    if inp.counties["county_fips"].to_list() != model.fips:
        raise ValueError("susceptibility and population counties differ")
    seed_idx = model.fips.index(SEED_COUNTY)
    d = mp["disease"]
    rows = []
    summary = []
    for scenario in sp["under_covered"]["scenarios"]:
        # Same seed for every scenario (common random numbers): differences are the scenario's.
        frac = estimate.draws(inp, sp, scenario, n_runs, seed)["susceptible_fraction"]
        if np.isnan(frac).any():
            raise ValueError("a county has no susceptibility estimate; refusing to guess (I5)")
        rng = np.random.default_rng(seed)
        r0s = rng.uniform(d["r0"]["low"], d["r0"]["high"], n_runs)
        finals = np.zeros((n_runs, len(model.fips)), dtype=np.int64)
        s0_tot = np.zeros(n_runs, dtype=np.int64)
        for k in range(n_runs):
            s0 = np.round(model.population * frac[k]).astype(np.int64)
            i0 = np.zeros_like(s0)
            i0[seed_idx] = min(SEED_INFECTIOUS, int(s0[seed_idx]))
            s0[seed_idx] -= i0[seed_idx]
            res = simulator.simulate(
                model.population,
                s0,
                np.zeros_like(s0),
                i0,
                r0=float(r0s[k]),
                latent_days=d["latent_days"]["value"],
                infectious_days=d["infectious_days"]["value"],
                latent_stages=d["latent_days"]["stages"],
                infectious_stages=d["infectious_days"]["stages"],
                coupling=model.coupling,
                days=DAYS,
                seed=seed + k,
            )
            finals[k] = res.final_size
            s0_tot[k] = s0.sum()
        total = finals.sum(axis=1)
        summary.append(
            {
                "scenario": scenario,
                "share": sp["under_covered"]["scenarios"][scenario]["share"],
                "coverage": sp["under_covered"]["scenarios"][scenario]["coverage"],
                "runs": n_runs,
                "final_size_mean": float(total.mean()),
                "final_size_q05": float(np.quantile(total, 0.05)),
                "final_size_q50": float(np.quantile(total, 0.5)),
                "final_size_q95": float(np.quantile(total, 0.95)),
                "susceptibles_mean": float(s0_tot.mean()),
            }
        )
        for j, f in enumerate(model.fips):
            rows.append(
                {
                    "scenario": scenario,
                    "county_fips": f,
                    "final_size_mean": float(finals[:, j].mean()),
                }
            )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = out_dir or OUTPUTS / stamp
    out.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(summary).write_csv(out / "final_size_by_scenario.csv")
    pl.DataFrame(rows).write_csv(out / "final_size_by_county.csv")
    manifest.write(
        out,
        "sensitivity_u19",
        seed,
        {"model": mp, "susceptibility": sp},
        inp.raw_refs,
        {
            "n_runs": n_runs,
            "days": DAYS,
            "seeding": {"county_fips": SEED_COUNTY, "infectious": SEED_INFECTIOUS},
            "calibrated": False,
        },
    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m project.model.sensitivity")
    ap.add_argument("--seed", type=int, default=20261008)
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    print(f"sensitivity: wrote {run(out_dir=a.out, seed=a.seed, n_runs=a.runs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
