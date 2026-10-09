"""WP6b simulator: T6.2 and T6.4 to T6.9, offline."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from project.model import sensitivity, simulator

from conftest import REPO

FIPS = ["a", "b", "c", "d"]
POP = np.array([500_000, 40_000, 200_000, 80_000])
COMMUTE = [("a", "b", 900.0), ("b", "a", 300.0), ("a", "c", 50.0), ("c", "d", 20.0)]
ADJ = [("a", "b", 10.0), ("b", "c", 5.0)]
LINKS = [["a", "d"]]
DISEASE = {"latent_days": 8.0, "infectious_days": 8.0}


def _k(**strengths: float) -> np.ndarray:
    return simulator.coupling_matrix(
        FIPS, commuting=COMMUTE, adjacency=ADJ, long_range=LINKS, strengths=strengths
    )


def _run(
    s_frac: float, r0: float, seed: int, k: np.ndarray | None = None, **kw
) -> simulator.Result:  # type: ignore[no-untyped-def]
    s = (POP * s_frac).astype(np.int64)
    i = np.array([5, 0, 0, 0])
    s[0] -= 5
    return simulator.simulate(
        POP,
        s,
        np.zeros(4, np.int64),
        i,
        r0=r0,
        coupling=_k(commuting=0.05, adjacency=0.02) if k is None else k,
        days=kw.pop("days", 365),
        seed=seed,
        **DISEASE,
        **kw,
    )


@settings(max_examples=40, deadline=None)
@given(
    pops=st.lists(st.integers(1, 50_000), min_size=1, max_size=5),
    s_frac=st.floats(0, 1),
    r0=st.floats(0, 25),
    seed=st.integers(0, 2**31 - 1),
    vacc=st.floats(0, 50),
    imports=st.floats(0, 3),
    stages=st.tuples(st.integers(1, 8), st.integers(1, 8)),
)
def test_population_conserved_and_final_size_bounded(  # T6.4, T6.5
    pops: list[int],
    s_frac: float,
    r0: float,
    seed: int,
    vacc: float,
    imports: float,
    stages: tuple[int, int],
) -> None:
    n = np.array(pops, dtype=np.int64)
    c = n.size
    s = np.floor(n * s_frac).astype(np.int64)
    i = np.minimum(n - s, 3)
    days = 60
    res = simulator.simulate(
        n,
        s,
        np.zeros(c, np.int64),
        i,
        r0=r0,
        coupling=np.full((c, c), 1.0 / c),
        days=days,
        seed=seed,
        imports=np.full((days, c), imports),
        vaccination=np.full((days, c), vacc),
        latent_stages=stages[0],
        infectious_stages=stages[1],
        **DISEASE,
    )
    assert (res.state.sum(axis=2) == n).all()  # every day, every county
    assert (res.state >= 0).all()
    assert (res.final_size + res.vaccinated.sum(axis=0) <= s).all()


def _large(s_frac: float, runs: int = 200) -> int:
    s0 = (POP * s_frac).sum()
    return sum(_run(s_frac, 15.0, seed).final_size.sum() > 0.10 * s0 for seed in range(runs))


def test_subcritical_outbreaks_stay_small() -> None:  # T6.6
    # R0 15 with 5% susceptible: effective R 0.75 in every county.
    assert _large(0.05) < 0.05 * 200
    # Contrast, so the check can fail: with 9% susceptible (effective R 1.35) many runs are large.
    assert _large(0.09) > 0.25 * 200


def test_fixed_seed_identical() -> None:  # T6.7
    a, b = _run(0.09, 15.0, 42), _run(0.09, 15.0, 42)
    assert np.array_equal(a.state, b.state) and np.array_equal(a.incidence, b.incidence)
    assert not np.array_equal(a.incidence, _run(0.09, 15.0, 43).incidence)


def test_interventions_off_never_lower_final_size() -> None:  # T6.8
    days = 365
    mult = simulator.intervention_mult(days, 4, [(30, 120, None, 0.6), (60, 365, [0], 0.8)])
    on = np.mean([_run(0.09, 15.0, s, mult=mult, days=days).final_size.sum() for s in range(200)])
    off = np.mean([_run(0.09, 15.0, s, days=days).final_size.sum() for s in range(200)])
    assert off - on >= -0.01 * off
    with pytest.raises(ValueError):
        simulator.intervention_mult(10, 4, [(0, 5, None, 1.2)])  # cannot raise transmission


@pytest.mark.parametrize("term", ["commuting", "adjacency", "long_range"])
def test_zero_strength_is_no_coupling(term: str) -> None:  # T6.9
    k0 = _k(**{term: 0.0})
    assert np.array_equal(k0, np.eye(4))
    a = _run(0.09, 15.0, 7, k=k0)
    b = _run(0.09, 15.0, 7, k=np.eye(4))
    assert np.array_equal(a.state, b.state)
    assert a.final_size[1:].sum() == 0  # nothing reaches unseeded counties without coupling
    # The same term switched on carries infection out of the seeded county in most runs.
    k1 = _k(**{term: 0.2})
    assert np.allclose(k1.sum(axis=1), 1.0) and not np.array_equal(k1, np.eye(4))
    spread = sum(_run(0.12, 15.0, s, k=k1).final_size[1:].sum() > 0 for s in range(20))
    assert spread >= 10


def test_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        _k(commuting=0.7, adjacency=0.5)  # strengths sum above 1
    with pytest.raises(ValueError):
        _k(gravity=0.1)
    with pytest.raises(ValueError):
        simulator.simulate(
            POP,
            POP + 1,
            np.zeros(4, np.int64),
            np.zeros(4, np.int64),
            r0=15,
            coupling=np.eye(4),
            days=5,
            seed=1,
            **DISEASE,
        )
    with pytest.raises(ValueError):
        simulator.simulate(
            POP,
            POP // 10,
            np.zeros(4, np.int64),
            np.zeros(4, np.int64),
            r0=15,
            coupling=np.full((4, 4), 0.5),
            days=5,
            seed=1,
            **DISEASE,
        )


def test_u19_sensitivity_output(tmp_path: Path) -> None:  # T6.2
    if not (REPO / "data/reference/MANIFEST.json").exists():
        pytest.skip("no reference build")
    out = sensitivity.run(out_dir=tmp_path / "s", seed=3, n_runs=20)
    s = pl.read_csv(out / "final_size_by_scenario.csv")
    assert s["scenario"].to_list() == ["none", "low", "mid", "high"]
    means = s["final_size_mean"].to_list()
    assert means == sorted(means)  # more under-covered people, larger outbreaks on average
    county = pl.read_csv(
        out / "final_size_by_county.csv", schema_overrides={"county_fips": pl.Utf8}
    )
    assert county.height == 4 * 67
    m = json.loads((out / "manifest.json").read_text())
    assert m["calibrated"] is False and m["seed"] == 3 and m["n_runs"] == 20


def _final_size_theory(r: float) -> float:
    z = 0.9
    for _ in range(2000):
        z = 1 - np.exp(-r * z)
    return z


STAGED = {"latent_days": 7.0, "infectious_days": 8.0, "latent_stages": 4, "infectious_stages": 4}


@pytest.mark.parametrize("disease", [DISEASE, STAGED], ids=["geometric", "staged"])
@pytest.mark.parametrize("r0,s_frac", [(15.0, 0.10), (12.0, 0.10)])
def test_matches_final_size_relation(r0: float, s_frac: float, disease: dict) -> None:
    # One well-mixed county: the share of susceptibles infected in a major outbreak must solve
    # z = 1 - exp(-R z) with R = R0 x susceptible share. Catches any bias in R from the daily
    # step (stays of 1 - exp(-1/D) per day inflated R by about 6 percent) or from staging.
    n = 2_000_000
    s0 = int(n * s_frac)
    z = []
    for seed in range(40):
        res = simulator.simulate(
            np.array([n]),
            np.array([s0 - 50]),
            np.array([0]),
            np.array([50]),
            r0=r0,
            coupling=np.eye(1),
            days=2000,
            seed=seed,
            **disease,
        )
        z.append(res.final_size.sum() / s0)
    assert abs(np.mean(z) - _final_size_theory(r0 * s_frac)) < 0.005


def _linear_map(r0: float, s_frac: float, d: dict) -> np.ndarray:
    """Expected daily map of the stage counts early on, built independently of the simulator."""
    ke, ki = d.get("latent_stages", 1), d.get("infectious_stages", 1)
    pe, pi = ke / d["latent_days"], ki / d["infectious_days"]
    m = ke + ki
    a = np.zeros((m, m))
    for q in range(m):
        p = pe if q < ke else pi
        a[q, q] = 1 - p
        if q + 1 < m:
            a[q + 1, q] = p
    a[0, ke:] += r0 / d["infectious_days"] * s_frac  # new exposures from every infectious stage
    return a


@pytest.mark.parametrize("disease", [DISEASE, STAGED], ids=["geometric", "staged"])
def test_matches_early_growth_rate(disease: dict) -> None:
    # Early exponential growth must equal the dominant eigenvalue of the linear daily map.
    n, s_frac, r0 = 10**9, 0.10, 15.0
    theory = np.log(max(abs(np.linalg.eigvals(_linear_map(r0, s_frac, disease)))))
    s0 = int(n * s_frac)
    res = simulator.simulate(
        np.array([n]),
        np.array([s0 - 2000]),
        np.array([0]),
        np.array([2000]),
        r0=r0,
        coupling=np.eye(1),
        days=120,
        seed=1,
        **disease,
    )
    t = np.arange(20, 100)
    rate = np.polyfit(t, np.log(res.incidence[t, 0].astype(float)), 1)[0]
    assert abs(rate - theory) < 0.05 * theory


def test_growth_rate_follows_generation_time() -> None:
    # Euler-Lotka for the simulator's own generation-interval weights: sum_t g(t) e^(-r t) = 1/R.
    # Ties generation_time to what simulate does, so the literature check below is meaningful.
    r = np.log(max(abs(np.linalg.eigvals(_linear_map(15.0, 0.10, STAGED)))))
    ke, ki = STAGED["latent_stages"], STAGED["infectious_stages"]
    x = np.zeros(ke + ki)
    x[0] = 1.0
    a = _linear_map(0.0, 0.0, STAGED)
    total = 0.0
    for t in range(1, 1000):
        total += x[ke:].sum() / STAGED["infectious_days"] * np.exp(-r * t)
        x = a @ x
    assert abs(total - 1 / 1.5) < 1e-6
    # A longer generation time means slower growth at the same R.
    assert simulator.generation_time(**STAGED) < simulator.generation_time(**DISEASE)


def test_generation_time_matches_literature() -> None:
    # klinkenberg2011 (doi:10.1016/j.jtbi.2011.06.015, VERIFIED): mean generation time 11-12
    # days; vink2014 (doi:10.1093/aje/kwu209, VERIFIED): mean measles serial interval 11.7
    # days. docs/references/README.md.
    d = simulator.load_params()["disease"]
    g = simulator.generation_time(
        d["latent_days"]["value"],
        d["infectious_days"]["value"],
        d["latent_days"]["stages"],
        d["infectious_days"]["stages"],
    )
    lo, hi = d["generation_time_days"]["low"], d["generation_time_days"]["high"]
    assert lo <= g <= hi
    assert lo <= 11.7 <= hi  # the serial interval agrees with the band used
    # Geometric single stages with the same periods are outside it: the bug this fixes.
    assert simulator.generation_time(d["latent_days"]["value"], 8.0) > hi


def test_rejects_bad_stages() -> None:
    for bad in ({"latent_stages": 0}, {"infectious_stages": 9}, {"latent_stages": 8}):
        kw = {**STAGED, **bad}
        with pytest.raises(ValueError):
            simulator.generation_time(**kw)
        with pytest.raises(ValueError):
            simulator.simulate(
                POP,
                POP // 10,
                np.zeros(4, np.int64),
                np.array([5, 0, 0, 0]),
                r0=15,
                coupling=np.eye(4),
                days=5,
                seed=1,
                **kw,
            )
