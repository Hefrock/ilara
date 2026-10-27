"""Gate G3 pre-flight: run the real fit's path up to the step the gate blocks (WP6, ADR 0011).

    python -m project.model.preflight [--origin 2026-10-28] [--known-at 2026-10-27T12:00Z]

Builds the real model inputs as known at ``--known-at`` (default: now), counts the county
snapshot dates the fit would use, checks the gate refuses (or, once it passes, that the real
problem builds), times one simulation, and lists the validation origins scoreable so far. No
fitting and no counts are printed: dates, sizes and checks only. Nothing is written.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ingest import access
from project.leak import check_known
from project.model import calibrate as cal
from project.model import pa, run_validation


@dataclass
class Report:
    origin: date
    known_at: datetime
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append((name, ok, detail))

    @property
    def ok(self) -> bool:
        return all(ok for _n, ok, _d in self.checks)

    def text(self) -> str:
        when = f"{self.known_at:%Y-%m-%d %H:%M} UTC"
        lines = [f"G3 pre-flight for origin {self.origin}, data known at {when}"]
        lines += [f"  [{'ok' if ok else '!!'}] {n}: {d}" for n, ok, d in self.checks]
        return "\n".join(lines)


def snapshot_dates(root: Path | None, known_at: datetime) -> list[date]:
    """The county snapshot dates Gate G3 counts, as known at ``known_at``."""
    county = check_known(
        access.as_known_at("case_county", known_at, root=root), known_at, "case_county"
    )
    rows = cal.default_county_rows(county)
    return sorted(set(rows["as_of_date"].to_list())) if rows.height else []


def run(
    origin: date,
    known_at: datetime | None = None,
    root: Path | None = None,
    seed: int = 20261015,
) -> Report:
    known_at = known_at or datetime.now(UTC)
    rep = Report(origin, known_at)

    dates = snapshot_dates(root, known_at)
    need = cal.G3_SNAPSHOTS
    rep.add(
        "county snapshot dates",
        True,
        f"{len(dates)} of {need} ({', '.join(d.strftime('%b %d') for d in dates)})",
    )

    model = pa.build(origin + timedelta(days=35), root, known_at=known_at, seed=seed)
    rep.add(
        "model inputs",
        len(model.fips) == 67,
        f"{len(model.fips)} counties, start {model.start}, {model.days} days, "
        f"{model.fractions.shape[0]} susceptibility draws",
    )

    county = cal.default_county_rows(access.as_known_at("case_county", known_at, root=root))
    stray = sorted(set(county["county_fips"].to_list()) - set(model.fips)) if county.height else []
    rep.add("county keys", not stray, "all in the model" if not stray else f"not in model: {stray}")

    state = pa.statewide_dates(
        dates[0] if dates else pa.FIRST_SNAPSHOT, model.start, root, known_at
    )
    rep.add("statewide dates before the first snapshot", bool(state), f"{len(state)} dates")

    try:
        prob, refs = pa.curated_problem(model, root, known_at)
    except cal.GateError as e:
        rep.add(
            "gate",
            len(dates) < need,
            f"refuses as it should: {e}"
            if len(dates) < need
            else f"refused with {len(dates)} dates: {e}",
        )
    else:
        rep.add(
            "gate",
            len(dates) >= need,
            f"passes; problem built with {len(prob.obs.series)} series and "
            f"{sum(len(v) for v in refs.values())} raw references",
        )

    run_sim = pa.simulate_fn(model)
    theta = {p.name: float(p.from_unit(0.5)) for p in pa.priors(model)}
    run_sim(theta, seed)  # the first call compiles (numba)
    t0 = time.monotonic()
    run_sim(theta, seed + 1)
    secs = time.monotonic() - t0
    rep.add(
        "simulation",
        True,
        f"{secs:.2f} s each; a 300-particle, 8-generation fit runs roughly 5,000 to 12,000, "
        f"so about {secs * 5000 / 60:.0f} to {secs * 12000 / 60:.0f} min",
    )

    observed = pa.observed_series(root)
    last = max(observed.get("state", {}), default=origin)
    ts = run_validation.origins(origin, last)
    first_scoreable = origin + timedelta(days=7)
    rep.add(
        "validation origins",
        True,
        f"{len(ts)} scoreable with data to {last}; the {origin} origin is first scored once "
        f"data for {first_scoreable} are in",
    )
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m project.model.preflight")
    ap.add_argument("--origin", type=date.fromisoformat, default=date(2026, 10, 28))
    ap.add_argument("--known-at", type=datetime.fromisoformat)
    ap.add_argument("--seed", type=int, default=20261015)
    a = ap.parse_args(argv)
    known = a.known_at.astimezone(UTC) if a.known_at else None
    rep = run(a.origin, known, seed=a.seed)
    print(rep.text())
    print(f"pre-flight {'clean' if rep.ok else 'found problems'}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
