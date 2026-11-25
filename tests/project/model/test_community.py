"""Model version 2: the community group (ADR 0029), offline."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from project.model import community, pa, simulator


def _schools(rows: list[tuple[str, str, int, float | None, bool]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema=["county_fips", "grade", "enrolled", "mmr_pct", "suppressed_flag"],
        orient="row",
    )


def test_school_proxy_shrinks_small_counties_and_fills_missing() -> None:
    s = _schools(
        [
            ("A", "kindergarten", 1000, 80.0, False),  # all low
            ("A", "kindergarten", 1000, 99.0, False),
            ("B", "grade_7", 10, 50.0, False),  # tiny county, all low
            ("B", "grade_12", 999, 10.0, False),  # wrong grade: ignored
            ("C", "kindergarten", 500, None, True),  # suppressed only
        ]
    )
    p = community.school_proxy(
        s,
        ["A", "B", "C", "D"],
        grades=["kindergarten", "grade_7"],
        threshold_pct=90,
        prior_weight=500,
    )
    state = 1010 / 2010
    assert p[0] == pytest.approx((1000 + 500 * state) / (2000 + 500))
    assert p[1] == pytest.approx((10 + 500 * state) / (10 + 500))  # pulled toward the state
    assert abs(p[1] - state) < abs(1.0 - state)
    assert p[2] == pytest.approx(state) and p[3] == pytest.approx(state)  # no usable rows
    above = community.school_proxy(
        s,
        ["A", "B", "C", "D"],
        grades=["kindergarten", "grade_7"],
        threshold_pct=90,
        prior_weight=500,
        above_state_only=True,
    )
    assert p[0] < state and p[1] > state  # A is mostly high-coverage pupils, B is not
    assert above.tolist() == [0.0, p[1], 0.0, 0.0]  # at or below the state value: none


def test_patch_coupling_rows_sum_to_one_and_closed_community_keeps_to_itself() -> None:
    k = np.array([[0.9, 0.1], [0.2, 0.8]])
    k2 = community.patch_coupling(k, np.array([90, 100]), np.array([10, 0]), within=0.7)
    assert k2.shape == (4, 4) and np.allclose(k2.sum(axis=1), 1.0)
    assert k2[2, 2] == pytest.approx(0.7 + 0.3 * 0.9 * 0.1)  # own community: within + share
    closed = community.patch_coupling(k, np.array([90, 100]), np.array([10, 0]), within=1.0)
    assert closed[2].tolist() == [0.0, 0.0, 1.0, 0.0]
    with pytest.raises(ValueError):
        community.patch_coupling(k, np.array([1, 1]), np.array([1, 1]), within=1.5)


def test_seed_and_dose_allocation() -> None:
    arr = np.array([[5, 3]])
    s_g, s_m = np.array([100, 100]), np.array([100, 0])
    assert community.to_patches(arr, s_g, s_m, into="general").tolist() == [[5, 3, 0, 0]]
    seeded = community.to_patches(arr, s_g, s_m, into="community")
    assert seeded.tolist() == [[0, 3, 5, 0]]  # county 2 has no community: general
    doses = community.to_patches(arr.astype(float), s_g, s_m, into="susceptible")
    assert doses.tolist() == [[2.5, 3.0, 2.5, 0.0]]
    with pytest.raises(ValueError):
        community.to_patches(arr, s_g, s_m, into="elsewhere")


def test_a_closed_community_can_sustain_an_outbreak_the_county_average_cannot() -> None:
    # One county, 6% susceptible overall: R0 15 x 0.06 < 1 when everyone mixes evenly. A 5%
    # community with 70% susceptible that mixes mostly within itself sustains spread.
    k = np.eye(1)
    n = np.array([100_000])
    seeds = np.zeros((200, 1), np.int64)
    seeds[0, 0] = 5
    common = dict(
        r0=15.0,
        latent_days=7.0,
        infectious_days=8.0,
        days=200,
        latent_stages=4,
        infectious_stages=4,
    )
    flat = simulator.simulate(
        n,
        np.array([6000]),
        np.zeros(1, np.int64),
        np.zeros(1, np.int64),
        coupling=k,
        seed=1,
        seeds=seeds,
        **common,
    ).incidence.sum()
    n_g, n_m, s_g, s_m = community.split(n, np.array([0.06]), np.array([0.05]), 0.7)
    k2 = community.patch_coupling(k, n_g, n_m, within=0.9)
    grouped = simulator.simulate(
        np.concatenate([n_g, n_m]),
        np.concatenate([s_g, s_m]),
        np.zeros(2, np.int64),
        np.zeros(2, np.int64),
        coupling=k2,
        seed=1,
        seeds=community.to_patches(seeds, s_g, s_m, into="community"),
        **common,
    ).incidence.sum()
    assert flat < 1000 and grouped > 2000  # the community (3,500 susceptible) mostly burns


@pytest.fixture(scope="module")
def models() -> dict[str, pa.PAModel]:
    o = date(2026, 11, 18)
    return {
        v: pa.build(o + timedelta(days=35), None, known_at=pa.cutoff(o), seed=20261015, version=v)
        for v in ("1", "2")
    }


def test_version_2_with_no_community_is_version_1(models: dict[str, pa.PAModel]) -> None:
    v1, v2 = models["1"], models["2"]
    th1 = {p.name: float(p.from_unit(0.5)) for p in pa.priors(v1)}
    th2 = {**th1, "community_scale": 0.0, "community_within": 0.8}
    v2_same_seeds = pa.PAModel(**{**v2.__dict__, "exposed_by_county": {}})
    assert np.array_equal(pa.simulate_fn(v1)(th1, 3), pa.simulate_fn(v2_same_seeds)(th2, 3))


def test_version_2_inputs(models: dict[str, pa.PAModel]) -> None:
    v2 = models["2"]
    assert v2.proxy is not None and v2.proxy.shape == (67,)
    # Round 2 (ADR 0029): only counties above the statewide share have a community.
    assert 0 < (v2.proxy > 0).sum() < 67 and v2.proxy[v2.fips.index("42071")] > 0
    assert v2.params["community"]["seed_into"] == "general"
    assert v2.s_community == pytest.approx(1 - 0.3 * 0.97)
    assert set(v2.exposed_by_county.values()) <= {1, 2, 3, 4, 5} and v2.exposed_by_county
    names = [p.name for p in pa.priors(v2)]
    # community_within failed the recovery test (ADR 0029): fixed, not fitted.
    assert "community_scale" in names and "community_within" not in names
    assert v2.params["community"]["within"]["value"] == pytest.approx(0.725)
    assert models["1"].proxy is None and "community_scale" not in [
        p.name for p in pa.priors(models["1"])
    ]
    with pytest.raises(ValueError):
        pa.build(date(2026, 12, 1), None, version="3")
