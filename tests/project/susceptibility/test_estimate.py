"""WP6a susceptibility: T6.1 and T6.3, offline, on the committed curated data."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from project.susceptibility import estimate

from conftest import REPO


@pytest.fixture(scope="module")
def inp() -> estimate.Inputs:
    if not (REPO / "data/reference/MANIFEST.json").exists():
        pytest.skip("no reference build")
    got = estimate.county_inputs()
    if got.counties["mmr_up_to_date_pct_kindergarten"].null_count() == 67:
        pytest.skip("no school survey parsed")
    return got


PARAMS = estimate.load_params()


def test_fractions_in_unit_interval_and_reproducible(inp: estimate.Inputs) -> None:  # T6.1
    assert inp.counties.height == 67
    a = estimate.draws(inp, PARAMS, "mid", 300, seed=7)
    for key in ("susceptible_fraction", "child_susceptible_fraction", "child_coverage"):
        v = a[key][~np.isnan(a[key])]
        assert v.size and (v >= 0).all() and (v <= 1).all()
    b = estimate.draws(inp, PARAMS, "mid", 300, seed=7)
    assert all(np.array_equal(a[k], b[k], equal_nan=True) for k in a)
    c = estimate.draws(inp, PARAMS, "mid", 300, seed=8)
    assert not np.array_equal(a["susceptible_fraction"], c["susceptible_fraction"])
    s1 = estimate.summarize(inp, a, "mid")
    s2 = estimate.summarize(inp, b, "mid")
    assert s1.equals(s2)


def test_suppression_handling_is_deterministic(inp: estimate.Inputs) -> None:  # T6.1
    # County rates come from the DOH county summary, which already includes schools whose own
    # values are suppressed; reading twice gives the same inputs.
    again = estimate.county_inputs()
    assert inp.counties.equals(again.counties)


def test_missing_county_input_stays_a_gap(inp: estimate.Inputs) -> None:  # I5
    gap = estimate.Inputs(
        inp.counties.with_columns(
            pl.when(pl.col("county_fips") == "42071")
            .then(None)
            .otherwise(pl.col("mmr_up_to_date_pct_kindergarten"))
            .alias("mmr_up_to_date_pct_kindergarten")
        ),
        inp.grades,
        inp.raw_refs,
    )
    s = estimate.summarize(gap, estimate.draws(gap, PARAMS, "none", 50, 1), "none")
    lan = s.filter(pl.col("county_fips") == "42071")
    assert lan["susceptible_fraction_mean"][0] is None
    assert s.filter(pl.col("county_fips") != "42071")["susceptible_fraction_mean"].null_count() == 0


def test_under_covered_scenarios_raise_susceptibility(inp: estimate.Inputs) -> None:  # U19
    means = [
        estimate.draws(inp, PARAMS, sc, 200, seed=3)["susceptible_fraction"].mean(axis=0)
        for sc in ("none", "low", "mid", "high")
    ]
    for lo, hi in zip(means, means[1:], strict=False):
        assert (hi >= lo).all()


DOSES = pl.DataFrame(
    {
        "period_start": [date(2026, 8, 1), date(2026, 9, 1)],
        "period_end": [date(2026, 8, 31), date(2026, 9, 30)],
        "period_complete": [True, True],
        "doses": [1000, 500],
    }
)


def test_dose_adjustment_excludes_infant_doses() -> None:  # T6.3
    none = estimate.dose_adjustment(
        DOSES, infant_share=1.0, second_dose_share=0.4, ve1=0.93, ve2=0.97
    )
    assert none["immune_gained"].to_list() == [0.0, 0.0]
    # Hand-computed: 1000 doses, 20% infant, 25% of the rest second doses:
    # 800 countable = 600 first x 0.93 + 200 second x 0.04 = 558 + 8 = 566.
    a = estimate.dose_adjustment(DOSES, 0.2, 0.25, 0.93, 0.97)
    assert a["countable_doses"][0] == pytest.approx(800)
    assert a["immune_gained"][0] == pytest.approx(566)
    assert a["immune_gained_cumulative"][1] == pytest.approx(566 + 283)
    more_infant = estimate.dose_adjustment(DOSES, 0.5, 0.25, 0.93, 0.97)
    assert (more_infant["immune_gained"] < a["immune_gained"]).all()
    with pytest.raises(ValueError):
        estimate.dose_adjustment(DOSES, 1.5, 0.2, 0.93, 0.97)


def test_run_writes_outputs_and_manifest(inp: estimate.Inputs, tmp_path: Path) -> None:  # I9
    out = estimate.run(out_dir=tmp_path / "run", seed=11, n_draws=100)
    county = pl.read_csv(out / "county.csv", schema_overrides={"county_fips": pl.Utf8})
    assert county.height == 67 * len(PARAMS["under_covered"]["scenarios"])
    m = json.loads((out / "manifest.json").read_text())
    assert m["seed"] == 11 and m["n_draws"] == 100 and m["params"] == PARAMS
    assert m["git_sha"] and m["inputs"]["immunization_county"]["digest"]
    again = estimate.run(out_dir=tmp_path / "again", seed=11, n_draws=100)
    assert (again / "county.csv").read_bytes() == (out / "county.csv").read_bytes()


def test_scenarios_share_draws_in_a_run(inp: estimate.Inputs, tmp_path: Path) -> None:
    out = estimate.run(out_dir=tmp_path / "crn", seed=5, n_draws=200)
    c = pl.read_csv(out / "county.csv", schema_overrides={"county_fips": pl.Utf8})
    wide = c.pivot(on="scenario", index="county_fips", values="susceptible_fraction_mean")
    # With common random numbers the ordering holds county by county, not only on average.
    assert (wide["none"] <= wide["low"]).all() and (wide["low"] <= wide["mid"]).all()
    assert (wide["mid"] <= wide["high"]).all()
