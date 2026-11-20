"""WP6d validation, scoring and the G4 gate writer: T6.13 to T6.15 (ADR 0013), offline."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from ingest import access
from ingest.curate import store
from project.leak import LeakError
from project.model import calibrate as cal
from project.model import validate as v

Q = {
    "median": 8.0,
    "low_50": 6.0,
    "high_50": 12.0,
    "low_80": 4.0,
    "high_80": 14.0,
    "low_90": 2.0,
    "high_90": 20.0,
}


def test_scores_match_hand_computed_values() -> None:  # T6.14
    assert v.interval_score(0, 2, 4, 0.2) == pytest.approx(2 + 10 * 2)
    assert v.interval_score(30, 2, 20, 0.1) == pytest.approx(18 + 20 * 10)
    # All intervals cover 10: (0.5*2 + 0.25*6 + 0.1*10 + 0.05*18) / 3.5
    assert v.wis(10, Q) == pytest.approx(4.4 / 3.5)
    # 30 misses every interval: penalties 2/alpha * distance.
    expected = (0.5 * 22 + 0.25 * (6 + 4 * 18) + 0.1 * (10 + 10 * 16) + 0.05 * (18 + 20 * 10)) / 3.5
    assert v.wis(30, Q) == pytest.approx(expected)
    assert v.covered(13, Q, 80) and not v.covered(13, Q, 50)
    q = v.quantiles(np.arange(101))
    assert q["median"] == 50 and q["low_90"] == 5 and q["high_90"] == 95


MON = date(2026, 11, 2)
CUM = {MON + timedelta(days=7 * i): c for i, c in enumerate([0, 10, 25, 35, 60, 70, 90])}


def test_persistence_baseline() -> None:  # T6.14
    t = MON + timedelta(days=28)  # weekly increases so far 10, 15, 10, 25
    b = v.persistence(CUM, t)
    assert b is not None and b["median"] == 25
    assert 0 <= b["low_90"] <= b["low_80"] <= b["low_50"] <= 25 <= b["high_50"] <= b["high_90"]
    # Uses only snapshots known at the origin: later values change nothing.
    assert v.persistence({**CUM, MON + timedelta(days=35): 10**6}, t) == b
    # Fewer than three past changes: Poisson around the last increase (lambda 4, 50%: 3 to 5).
    early = v.persistence({MON: 0, MON + timedelta(days=7): 4}, MON + timedelta(days=7))
    assert early is not None and (early["low_50"], early["high_50"]) == (3.0, 5.0)
    assert v.persistence(CUM, MON) is None  # no increase observable yet


def test_score_uses_the_same_targets_for_model_and_baseline_and_skips_gaps() -> None:
    t = MON + timedelta(days=28)
    obs = {"state": CUM, "42071": {d: c for d, c in CUM.items() if d != MON + timedelta(days=42)}}
    fc = {t: {g: {h: np.full(50, 12.0) for h in (1, 2)} for g in obs}}
    s = v.score([t], fc, obs)
    # state: weeks 1 and 2 scored (10 and 20); Lancaster week 2 needs the missing snapshot.
    assert sorted(s.filter(pl.col("geography") == "state")["observed"]) == [10, 20]
    assert s.filter(pl.col("geography") == "42071")["horizon"].to_list() == [1]
    row = s.row(0, named=True)
    assert row["wis_persistence"] == pytest.approx(v.wis(row["observed"], v.persistence(CUM, t)))  # type: ignore[arg-type]


def _scores(
    n_origins: int,
    cover: float,
    model_better: tuple[bool, bool],
    group_wins: tuple[int, int] = (4, 4),
    observed: int = 5,
) -> pl.DataFrame:
    rows = []
    for i in range(n_origins):
        t = MON + timedelta(days=7 * i)
        for h in (1, 2, 3):
            for j in range(10):
                better = model_better[h - 1] if h <= 2 else False
                rows.append(
                    {
                        "origin": t,
                        "geography": "42071",
                        "kind": "county",
                        "horizon": h,
                        "observed": observed,
                        "high_80": 9.0,
                        "wis": 1.0 if better else 3.0,
                        "wis_persistence": 2.0,
                        "covered_80": j < round(10 * cover),
                    }
                )
            for k, g in enumerate(v.GROUPS):
                wins = group_wins[h - 1] if h <= 2 else 0
                rows.append(
                    {
                        "origin": t,
                        "geography": g,
                        "kind": "state" if g == "state" else "group",
                        "horizon": h,
                        "observed": 50,
                        "high_80": 90.0,
                        "wis": 1.0 if k < wins else 3.0,
                        "wis_persistence": 2.0,
                        "covered_80": True,
                    }
                )
    return pl.DataFrame(rows)


def test_gate_passes_only_when_all_g4_criteria_hold(tmp_path: Path) -> None:  # T6.15
    ok = v.gate(_scores(8, 0.8, (True, True)))
    assert ok.status == "pass" and ok.reasons == []
    assert v.gate(_scores(7, 0.8, (True, True))).status == "fail"  # too few origins
    assert v.gate(_scores(8, 0.6, (True, True))).status == "fail"  # under-covers
    assert v.gate(_scores(8, 1.0, (True, True))).status == "fail"  # over-covers
    assert v.gate(pl.DataFrame()).status == "fail"
    path = v.write_gate(v.gate(_scores(8, 0.6, (True, True))), tmp_path / "g.json", {"sha": "x"})
    body = json.loads(path.read_text())
    assert body["status"] == "fail" and body["reasons"] and body["run"] == {"sha": "x"}
    assert body["criteria"]["groups"] == list(v.GROUPS)


def test_gate_coverage_counts_only_targets_with_a_case() -> None:  # ADR 0028 item 2
    s = _scores(8, 0.8, (True, True))
    quiet = s.filter(pl.col("kind") == "county").with_columns(
        pl.lit("42001").alias("geography"),
        pl.lit(0, dtype=pl.Int64).alias("observed"),
        pl.lit(0.0).alias("high_80"),
        pl.lit(True).alias("covered_80"),
    )
    r = v.gate(pl.concat([s, quiet, quiet, quiet]))
    assert r.status == "pass" and r.coverage_80 == pytest.approx(0.8)  # zeros left out
    assert r.coverage_80_all is not None and r.coverage_80_all > 0.9  # still reported


def test_gate_needs_three_of_four_groups_at_each_horizon() -> None:  # ADR 0028 item 3
    assert v.gate(_scores(8, 0.8, (False, False), group_wins=(3, 3))).status == "pass"
    lost = v.gate(_scores(8, 0.8, (True, True), group_wins=(3, 2)))
    assert lost.status == "fail" and any("horizon 2" in r for r in lost.reasons)
    assert (
        lost.groups[1]["group:lancaster"]["wis"]
        < lost.groups[1]["group:lancaster"]["wis_persistence"]
    )


def test_groups_sum_county_forecasts_draw_by_draw() -> None:  # ADR 0028 item 3
    t = MON + timedelta(days=28)
    big = {d: 5 * c for d, c in CUM.items()}
    small = {d: 1 for d in CUM}
    obs = {"state": CUM, "42071": CUM, "42043": big, "42001": small, "42003": small}
    assert v.groups_at(t, obs, ["42071", "42043", "42001", "42003"]) == {
        "group:larger": ["42043"],
        "group:rest": ["42001", "42003"],
        "group:lancaster": ["42071"],
    }
    fc = {t: {g: {1: np.arange(4.0)} for g in obs}}
    s = v.score([t], fc, obs, horizons=(1,))
    rest = s.filter(pl.col("geography") == "group:rest").row(0, named=True)
    assert rest["kind"] == "group" and rest["observed"] == 0  # 1 + 1, unchanged
    assert rest["median"] == pytest.approx(3.0)  # draws 0,2,4,6: summed per draw, median 3
    assert set(s["kind"]) == {"county", "group", "state"}


def _row(d: date, fetched: datetime, cum: int) -> pl.DataFrame:
    sha = "b" * 64
    ver = f"1.0.{d.toordinal()}"
    return pl.DataFrame(
        {
            "jurisdiction": ["PA"],
            "disease": ["measles"],
            "source_id": ["doh_dashboard"],
            "source_tier": ["T1"],
            "as_of_date": [d],
            "fetched_at_utc": [fetched],
            "ingest_run_id": [store.ingest_run_id(sha, ver)],
            "raw_sha256": [sha],
            "parser_version": [ver],
            "county_fips": ["42071"],
            "cum_cases": [cum],
            "count_definition": ["calendar_year"],
            "date_precision": ["exact"],
        }
    )


def test_replay_refuses_rows_fetched_after_the_origin(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # T6.13
    for i in range(12):
        d = date(2026, 9, 1) + timedelta(days=i)
        df = _row(d, datetime(d.year, d.month, d.day, 20, tzinfo=UTC), 100 + i)
        store.write(
            "curated", "case_county", df, df["ingest_run_id"][0], df["fetched_at_utc"][0], root
        )
    t = datetime(2026, 9, 11, 23, tzinfo=UTC)  # 11 snapshots known; the 12th is in the future
    obs, _ = cal.observations_from_curated(["42071"], date(2026, 8, 1), root, known_at=t)
    assert len(obs.series[0][0]) == 11
    # A reader that ignores the cutoff (simulated by an access layer that returns everything)
    # is caught rather than trusted.
    monkeypatch.setattr(
        access, "as_known_at", lambda table, t, root=None: access.current(table, root=root)
    )
    with pytest.raises(LeakError, match="fetched after"):
        cal.observations_from_curated(["42071"], date(2026, 8, 1), root, known_at=t)


def test_replay_scores_each_origin_with_its_own_cutoff() -> None:
    seen: list[datetime] = []

    def forecaster(t: date, cutoff: datetime) -> dict[str, dict[int, np.ndarray]]:
        seen.append(cutoff)
        return {"state": {1: np.full(20, 10.0)}}

    origins = [MON + timedelta(days=21), MON + timedelta(days=28)]
    s = v.replay(
        origins,
        forecaster,
        {"state": CUM},
        lambda t: datetime(t.year, t.month, t.day, 23, tzinfo=UTC),
    )
    assert [c.date() for c in seen] == origins and s.height == 2


def test_origins_are_wednesdays_with_an_observed_first_week() -> None:
    from project.model import run_validation as rv

    ts = rv.origins(date(2026, 10, 26), date(2026, 11, 11))
    assert ts == [date(2026, 10, 28), date(2026, 11, 4)]
    assert rv.origins(date(2026, 10, 28), date(2026, 11, 3)) == []


def test_runs_record_the_model_version() -> None:  # ADR 0026
    from datetime import date

    from project.model import pa
    from project.model import run_validation as rv

    assert pa.MODEL_VERSION == "1"
    params = rv.run_params(date(2026, 10, 28), 300, 8)
    assert params["model_version"] == pa.MODEL_VERSION and params["first"] == date(2026, 10, 28)
