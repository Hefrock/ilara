"""WP6c calibration: T6.10 to T6.12 (ADR 0011), offline. T6.10 is marked slow (run by
`make calibration-check` and its own CI step); the rest run in `make check`."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from ingest.curate import store
from project.model import calibrate as cal
from project.model import recovery

SNAPS, START, PRIORS = recovery.SNAPS, recovery.START, list(recovery.PRIORS)
simulate, synthetic = recovery.simulate, recovery.synthetic


@pytest.mark.slow
def test_calibration_recovers_known_parameters() -> None:  # T6.10
    covered = recovery.coverage(20)
    print("T6.10 coverage of 90% intervals out of 20:", covered)
    assert all(n >= 16 for n in covered.values()), covered  # at least 80 percent of runs


def test_observation_model_pieces() -> None:
    g = cal.delay_pmf(3.0)
    assert g.sum() == pytest.approx(1.0)
    assert (np.arange(len(g)) + 0.5) @ g == pytest.approx(cal.ONSET_DAYS + 3.0, abs=0.3)
    w = cal.weekday_weights(START, 14, 0.4)
    assert w[:7].sum() == pytest.approx(7.0) and w[5] == pytest.approx(0.4 * w[0])
    inf = np.zeros((120, 2))
    inf[10, 0], inf[20, 1] = 100, 50
    cum = cal.expected_cumulative(inf, {"rho": 0.5, "report_delay": 2.0, "weekend": 1.0}, START)
    assert cum[-1] == pytest.approx([50.0, 25.0], rel=1e-6)  # all infections reported by then
    assert cum[10, 0] == pytest.approx(0.0, abs=1e-3)  # none reported on the day of infection


def test_increments_use_the_first_snapshot_as_baseline() -> None:
    obs = cal.Observations(
        START,
        {0: (np.array([30, 10, 20]), np.array([9, 5, 7])), 1: (np.array([10]), np.array([3]))},
    )
    inc = obs.increments()
    assert list(inc) == [0]  # one snapshot gives no increment
    days, y = inc[0]
    assert list(days) == [10, 20, 30] and list(y) == [2.0, 2.0]


def test_fit_learns_and_writes_checks_and_manifest(tmp_path: Path) -> None:  # T6.11
    truth = {"r0": 14.0, "rho": 0.6, "k": 30.0, "report_delay": 4.0, "weekend": 0.6}
    problem = cal.Problem(simulate, PRIORS, synthetic(truth, 5))
    result = cal.fit(problem, particles=100, generations=4, min_acceptance=0.01, seed=3)
    s = result.summary()
    assert s["r0"]["high"] - s["r0"]["low"] < 0.7 * (18.1 - 9.9)  # narrower than the prior
    assert all(p.low <= s[p.name]["low"] <= s[p.name]["high"] <= p.high for p in PRIORS)
    path = cal.write(
        problem, result, tmp_path / "fit", kind="calibration-synthetic", inputs={}, params={}
    )
    m = json.loads(path.read_text())
    assert m["calibrated"] is True and set(m["summary"]) == {p.name for p in PRIORS}
    ppc = pl.read_csv(tmp_path / "fit" / "posterior_predictive.csv")
    assert ppc.height == 3 * (len(SNAPS) - 1) and 0 <= m["ppc_coverage_90"] <= 1
    assert (tmp_path / "fit" / "posterior.csv").exists()


def _county_rows(tier: str, d: date) -> pl.DataFrame:
    sha = ("b" if tier == "T1" else "c") * 64
    return pl.DataFrame(
        {
            "jurisdiction": ["PA"],
            "disease": ["measles"],
            "source_id": ["doh_dashboard"],
            "source_tier": [tier],
            "as_of_date": [d],
            "fetched_at_utc": [datetime(2026, 10, 5, 19, tzinfo=UTC)],
            "ingest_run_id": [store.ingest_run_id(sha, f"1.0.{d.day}")],
            "raw_sha256": [sha],
            "parser_version": [f"1.0.{d.day}"],
            "county_fips": ["42071"],
            "cum_cases": [100],
            "count_definition": ["calendar_year"],
            "date_precision": ["exact"],
        }
    )


def test_default_fit_refuses_t3_derived_rows(root: Path) -> None:  # T6.12
    for d in range(1, 12):
        df = _county_rows("T1", date(2026, 9, d))
        store.write(
            "curated",
            "case_county",
            df,
            df["ingest_run_id"][0],
            datetime(2026, 9, d, tzinfo=UTC),
            root,
        )
    obs, _ = cal.observations_from_curated(["42071"], date(2026, 8, 1), root)  # 11 dates: ok
    assert 0 in obs.series
    bad = _county_rows("T3-derived", date(2026, 9, 20))
    store.write(
        "curated",
        "case_county",
        bad,
        bad["ingest_run_id"][0],
        datetime(2026, 9, 21, tzinfo=UTC),
        root,
    )
    with pytest.raises(cal.TierError):
        cal.observations_from_curated(["42071"], date(2026, 8, 1), root)


def test_real_county_fit_waits_for_gate_g3(root: Path) -> None:  # E12, ADR 0011
    for d in range(1, 5):
        df = _county_rows("T1", date(2026, 10, d))
        store.write(
            "curated",
            "case_county",
            df,
            df["ingest_run_id"][0],
            datetime(2026, 10, d, tzinfo=UTC),
            root,
        )
    with pytest.raises(cal.GateError, match="Gate G3"):
        cal.observations_from_curated(["42071"], date(2026, 8, 1), root)


def test_a_missing_county_count_is_a_gap_not_a_zero(root: Path) -> None:  # I5
    for d in range(1, 12):
        df = _county_rows("T1", date(2026, 9, d))
        if d == 5:
            df = df.with_columns(pl.lit(None, pl.Int64).alias("cum_cases"))
        store.write(
            "curated",
            "case_county",
            df,
            df["ingest_run_id"][0],
            datetime(2026, 9, d, tzinfo=UTC),
            root,
        )
    obs, _ = cal.observations_from_curated(["42071"], date(2026, 8, 1), root)
    days, y = obs.series[0]
    assert len(days) == 10 and (date(2026, 9, 5) - date(2026, 8, 1)).days not in days
    assert (y == 100).all()


def test_a_count_revised_down_later_is_superseded_not_changed() -> None:  # I5, ADR 0020
    # Forest County on the real dashboard: 2 cases on Oct 14 and 16, then 0 from Oct 19.
    keep = cal.superseded_mask(np.array([0, 0, 0, 2, 2, 0, 0]))
    assert keep.tolist() == [True, True, True, False, False, True, True]
    # Mifflin County: 194 on Oct 19, then 193; the later 194 is kept.
    keep = cal.superseded_mask(np.array([183, 193, 194, 193, 193, 194, 198]))
    assert keep.tolist() == [True, True, False, True, True, True, True]
    assert cal.superseded_mask(np.array([1, 2, 3])).all()


def test_decreasing_observations_and_nan_distances_fail_loudly() -> None:  # ADR 0020
    obs = cal.Observations(date(2026, 1, 1), {0: (np.array([0, 7, 14]), np.array([2, 0, 0]))})
    with pytest.raises(ValueError, match="decrease"):
        cal.Problem(lambda theta, seed: np.zeros((30, 1)), [cal.Prior("rho", 0.1, 1.0)], obs)


def test_a_fit_with_no_finite_distance_raises() -> None:  # ADR 0020
    obs = cal.Observations(date(2026, 1, 1), {0: (np.array([0, 7, 14]), np.array([0, 1, 2]))})

    class Broken(cal.Problem):
        def dataset(self, theta: dict, seed: int) -> dict:  # type: ignore[type-arg]
            return {}

        def distance(self, sim: dict) -> float:  # type: ignore[type-arg]
            return float("nan")

    prob = Broken(lambda theta, seed: np.zeros((30, 1)), [cal.Prior("rho", 0.1, 1.0)], obs)
    with pytest.raises(ValueError, match="not finite"):
        cal.fit(prob, particles=5, generations=1)
