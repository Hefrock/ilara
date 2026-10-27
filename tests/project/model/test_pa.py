"""WP6c 67-county calibration problem (ADR 0012), offline. Synthetic data only: real county
fits refuse before Gate G3 (ADR 0011)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from ingest.curate import store
from project.model import calibrate as cal
from project.model import pa

from conftest import REPO

START = date(2026, 1, 1)


def test_vaccination_goes_to_counties_known_by_each_day() -> None:
    gains = pl.DataFrame(
        {
            "period_start": [date(2026, 1, 11), date(2026, 1, 21)],
            "period_end": [date(2026, 1, 20), date(2026, 1, 21)],
            "immune_gained": [100.0, 30.0],
        }
    )
    known = pl.DataFrame(
        {"county_fips": ["42001", "42003"], "known_by": [date(2026, 1, 1), date(2026, 1, 16)]}
    )
    pop = np.array([100.0, 300.0, 600.0])
    v = pa.vaccination_array(gains, ["42001", "42003", "42005"], pop, known, START, 30)
    assert v.sum() == pytest.approx(130.0)
    assert (v[:10] == 0).all() and (v[21:] == 0).all() and (v[:, 2] == 0).all()
    assert v[10, 0] == pytest.approx(10.0)  # only the first county is known on Jan 11
    assert v[15, 0] == pytest.approx(2.5) and v[15, 1] == pytest.approx(7.5)  # 1:3 by population
    # Doses before any county is known are not modelled rather than guessed onto counties.
    late = known.with_columns(pl.lit(date(2026, 1, 25)).alias("known_by"))
    assert pa.vaccination_array(gains, ["42001", "42003"], pop[:2], late, START, 30).sum() == 0


def test_snapshot_dates_are_ten_publishing_days() -> None:
    d = pa.snapshot_dates()
    assert len(d) == 10 and d[0] == date(2026, 10, 5) and d[-1] == date(2026, 10, 26)
    assert {x.weekday() for x in d} == {0, 2, 4}


@pytest.fixture(scope="module")
def model() -> pa.PAModel:
    if not (REPO / "data/reference/MANIFEST.json").exists():
        pytest.skip("no reference build")
    return pa.build(date(2026, 10, 26), REPO, n_draws=20)


def test_build_on_repo_data(model: pa.PAModel) -> None:
    assert len(model.fips) == 67 and model.fractions.shape == (20, 67)
    assert ((model.fractions > 0) & (model.fractions < 1)).all()
    first = model.first_known["known_by"].min()
    assert model.start == first - timedelta(days=42 + pa.MARGIN_DAYS)
    assert model.days == (date(2026, 10, 26) - model.start).days + 1
    assert model.vaccination.shape == (model.days, 67) and (model.vaccination >= 0).all()
    names = [p.name for p in pa.priors(model)]
    assert names[:4] == ["r0", "lead_days", "factor_intervention", "factor_health_alert"]
    assert set(names[4:]) == {p.name for p in cal.OBSERVATION_PRIORS}


def test_simulation_is_seeded_and_uses_theta(model: pa.PAModel) -> None:
    f = pa.simulate_fn(model)
    a, b = f(pa.DRY_TRUTH, 3), f(pa.DRY_TRUTH, 3)
    assert a.shape == (model.days, 67) and (a == b).all()
    lead = {**pa.DRY_TRUTH, "lead_days": 7.0}
    first = model.first_known["known_by"].min()
    seed_day = (first - model.start).days - 7
    assert f(lead, 3)[: seed_day + 1].sum() == model.params["seeding"]["exposed"]


def test_synthetic_dry_run_fits_and_writes(model: pa.PAModel, tmp_path: Path) -> None:
    snaps = [(d - model.start).days for d in pa.snapshot_dates()]
    obs = next(
        o
        for o in (pa.synthetic(model, pa.DRY_TRUTH, snaps, s) for s in range(100))
        if o.series["state"][1][-1] >= 100
    )
    assert all(len(days) == 10 for g, (days, _y) in obs.series.items() if g != "state")
    prob = pa.problem(model, obs)
    result = cal.fit(prob, particles=30, generations=2, min_acceptance=0.01, seed=1)
    s = result.summary()
    assert all(p.low <= s[p.name]["low"] <= s[p.name]["high"] <= p.high for p in prob.priors)
    path = cal.write(prob, result, tmp_path, kind="calibration-pa-synthetic", inputs={}, params={})
    assert json.loads(path.read_text())["calibrated"] is True


def test_real_fit_refuses_before_gate_g3(model: pa.PAModel, root: Path) -> None:
    for d in (5, 7, 9, 14):  # the four snapshot dates on hand when this was written
        df = pl.DataFrame(
            {
                "jurisdiction": ["PA"],
                "disease": ["measles"],
                "source_id": ["doh_dashboard"],
                "source_tier": ["T1"],
                "as_of_date": [date(2026, 10, d)],
                "fetched_at_utc": [datetime(2026, 10, d, 19, tzinfo=UTC)],
                "ingest_run_id": [store.ingest_run_id("b" * 64, f"1.0.{d}")],
                "raw_sha256": ["b" * 64],
                "parser_version": [f"1.0.{d}"],
                "county_fips": ["42071"],
                "cum_cases": [100 + d],
                "count_definition": ["calendar_year"],
                "date_precision": ["exact"],
            }
        )
        store.write(
            "curated",
            "case_county",
            df,
            df["ingest_run_id"][0],
            datetime(2026, 10, d, 20, tzinfo=UTC),
            root,
        )
    with pytest.raises(cal.GateError, match="Gate G3"):
        pa.curated_problem(model, root)


def test_fit_real_refuses_before_gate_g3(
    model: pa.PAModel, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Wednesday's entry point (python -m project.model.pa --origin ...) goes through the gate.
    monkeypatch.setattr(pa, "build", lambda *a, **k: model)
    with pytest.raises(cal.GateError, match="Gate G3"):
        pa.fit_real(date(2026, 10, 28), root / "out", root)
    assert not (root / "out").exists()


def test_dry_run_uses_the_real_statewide_dates(model: pa.PAModel) -> None:
    first = pa.snapshot_dates()[0]
    dates = pa.statewide_dates(first, model.start, REPO)
    assert date(2026, 5, 6) in dates and all(model.start <= d < first for d in dates)
    days = [(d - model.start).days for d in dates]
    snaps = [(d - model.start).days for d in pa.snapshot_dates()]
    obs = pa.synthetic(model, pa.DRY_TRUTH, snaps, 1, days)
    assert list(obs.series["state"][0]) == sorted(days) + [snaps[0]]


def test_forecast_samples_from_a_posterior(model: pa.PAModel) -> None:
    pri = pa.priors(model)
    row = np.array([[pa.DRY_TRUTH[p.name] for p in pri]] * 4)
    fit = cal.Fit(pri, row, np.full(4, 0.25), [float("inf")], 1)
    lanc = model.fips.index("42071")
    out = pa.forecast_samples(model, fit, date(2026, 9, 7), [lanc, "state"], draws=30)
    assert set(out) == {"42071", "state"} and set(out["state"]) == {1, 2, 3, 4}
    assert all(len(s) == 30 and (s >= 0).all() for by_h in out.values() for s in by_h.values())
    with pytest.raises(ValueError, match="ends before"):
        pa.forecast_samples(model, fit, date(2026, 10, 20), ["state"], draws=2)


def test_cutoff_is_the_end_of_the_origin_day_eastern() -> None:
    assert pa.cutoff(date(2026, 10, 28)) == datetime(2026, 10, 29, 3, 59, 59, tzinfo=UTC)
    assert pa.cutoff(date(2026, 11, 4)) == datetime(2026, 11, 5, 4, 59, 59, tzinfo=UTC)  # EST


def test_observed_series_from_repo_data() -> None:
    obs = pa.observed_series(REPO)
    assert obs["state"][date(2026, 10, 14)] == 1222
    assert obs["42071"][date(2026, 10, 5)] > 0 and "EXTERNAL" not in obs
