"""Run forecast validation on the real data (WP6d, ADR 0013).

    python -m project.model.run_validation [--first 2026-10-28] [--write-gate]

Weekly origins on Wednesdays from ``--first`` (the date Gate G3 is expected to pass) up to the
last origin whose first forecast week has been reported. Each origin is fitted on the data known
at its cutoff (``pa.cutoff``) and refuses before G3 (``GateError``). Scores and a manifest go to
``project/outputs/validation/`` (gitignored); ``--write-gate`` also writes
``data/validation_gate.json``, which holds summary metrics only.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from project import manifest
from project.model import pa, validate

OUTPUTS = Path(__file__).resolve().parents[1] / "outputs" / "validation"


def origins(first: date, last_observed: date) -> list[date]:
    """Wednesdays from ``first`` whose week-1 target (seven days later) has been reported."""
    t = first + timedelta(days=(2 - first.weekday()) % 7)
    out = []
    while t + timedelta(days=7) <= last_observed:
        out.append(t)
        t += timedelta(days=7)
    return out


def run_params(first: date, particles: int, generations: int) -> dict[str, object]:
    """What a validation run records about itself, the model version included (ADR 0026)."""
    return {
        "model_version": pa.MODEL_VERSION,
        "first": first,
        "particles": particles,
        "generations": generations,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m project.model.run_validation")
    ap.add_argument("--first", type=date.fromisoformat, default=date(2026, 10, 28))
    ap.add_argument("--particles", type=int, default=300)
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--out", type=Path, default=OUTPUTS)
    ap.add_argument("--write-gate", action="store_true")
    a = ap.parse_args(argv)
    observed = pa.observed_series()
    last = max(observed.get("state", {}), default=a.first)
    ts = origins(a.first, last)
    fc = pa.forecaster(particles=a.particles, generations=a.generations, seed=a.seed)
    scores = validate.replay(ts, fc, observed, pa.cutoff)
    scores = scores.with_columns(pl.lit(pa.MODEL_VERSION).alias("model_version"))  # ADR 0026
    a.out.mkdir(parents=True, exist_ok=True)
    scores.write_csv(a.out / "scores.csv")
    result = validate.gate(scores)
    params = run_params(a.first, a.particles, a.generations)
    m = manifest.write(a.out, "validation", a.seed, params, {}, extra={"gate": result.__dict__})
    print(f"validation: {len(ts)} origins, gate {result.status}; wrote {m}")
    if a.write_gate:
        root = Path(__file__).resolve().parents[2]
        run = {"manifest": str(m.relative_to(root)), "seed": a.seed, **params}
        print(f"wrote {validate.write_gate(result, root / 'data' / 'validation_gate.json', run)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
