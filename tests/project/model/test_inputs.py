"""WP6b simulator inputs from events and county data (ADR 0008), offline."""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import polars as pl
import pytest

from project.model import inputs, simulator

from conftest import REPO

FIPS = ["42071", "42075", "42045"]  # Lancaster, Lebanon, Delaware
START = date(2026, 1, 1)


def _events(rows: list[tuple[str, str, date | None, str, str]]) -> tuple[pl.DataFrame, dict]:
    df = pl.DataFrame(
        rows,
        schema={
            "event_id": pl.Utf8,
            "event_type": pl.Utf8,
            "event_date": pl.Date,
            "county_scope": pl.Utf8,
            "title": pl.Utf8,
        },
        orient="row",
    )
    names = {"Lancaster": "42071", "Lebanon": "42075", "Delaware": "42045"}
    scopes = {
        e: [names.get(p.strip(), p.strip()) for p in s.split(";")]
        for e, s in df.select("event_id", "county_scope").rows()
    }
    return df, scopes


def _snap(rows: list[tuple[str, date, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={"county_fips": pl.Utf8, "as_of_date": pl.Date, "cum_cases": pl.Int64},
        orient="row",
    )


EV, SCOPES = _events(
    [
        ("ev-001", "health_alert", date(2026, 2, 3), "Lancaster", "HAN 817"),
        ("ev-003", "health_alert", date(2026, 6, 17), "Delaware", "HAN 830"),  # wastewater only
        ("ev-013", "exposure", date(2026, 5, 6), "Lebanon", "Exposure notice"),
        ("ev-006", "intervention", date(2026, 6, 24), "affected_counties", "Early MMR"),
    ]
)


def _known(snapshots: pl.DataFrame | None = None) -> pl.DataFrame:
    return inputs.first_known(
        EV,
        SCOPES,
        snapshots if snapshots is not None else _snap([]),
        case_events=["ev-001"],
        presence_types=["exposure"],
    )


def test_first_known_uses_only_stated_evidence() -> None:
    snap = _snap(
        [
            ("42071", date(2026, 10, 5), 600),
            ("42045", date(2026, 10, 5), 3),
            ("42045", date(2026, 10, 7), 4),
            ("42075", date(2026, 10, 7), 20),
        ]
    )
    k = {r["county_fips"]: r for r in _known(snap).iter_rows(named=True)}
    # Lancaster from the alert that states cases; Lebanon from the exposure notice.
    assert (k["42071"]["known_by"], k["42071"]["basis"]) == (date(2026, 2, 3), "ev-001")
    assert (k["42075"]["known_by"], k["42075"]["basis"]) == (date(2026, 5, 6), "ev-013")
    # Delaware's wastewater alert is not case evidence: only the first snapshot, so censored.
    assert (k["42045"]["known_by"], k["42045"]["censored"]) == (date(2026, 10, 5), True)
    assert not k["42071"]["censored"] and not k["42075"]["censored"]


def test_snapshot_after_the_first_is_not_censored() -> None:
    snap = _snap([("42045", date(2026, 10, 5), 0), ("42045", date(2026, 10, 7), 2)])
    k = inputs.first_known(EV.head(0), {}, snap, case_events=[], presence_types=[])
    assert k.rows() == [("42045", date(2026, 10, 7), "snapshot", False)]


def test_seeding_first_and_all() -> None:
    known = _known()
    seeds, notes = inputs.seeding(known, FIPS, START, 365, mode="first", exposed=5, lead_days=21)
    assert seeds.sum() == 5 and seeds[(date(2026, 2, 3) - START).days - 21, 0] == 5
    seeds, _ = inputs.seeding(known, FIPS, START, 365, mode="all", exposed=5, lead_days=21)
    assert seeds[:, 1].sum() == 5 and seeds[(date(2026, 5, 6) - START).days - 21, 1] == 5
    assert seeds[:, 2].sum() == 0  # Delaware: no case evidence, never seeded
    late = date(2026, 1, 20)  # seeding day Jan 13 falls before this start
    seeds, notes = inputs.seeding(known, FIPS, late, 365, mode="first", exposed=5, lead_days=21)
    assert seeds[0, 0] == 5 and any("before the run start" in n for n in notes)
    with pytest.raises(ValueError):
        inputs.seeding(known, FIPS, START, 10, mode="some", exposed=1, lead_days=1)


def test_seeding_reports_when_nothing_is_known() -> None:
    empty = _known().head(0)
    seeds, notes = inputs.seeding(empty, FIPS, START, 30, mode="first", exposed=5, lead_days=21)
    assert seeds.sum() == 0 and notes == ["no county has a known first case: nothing seeded"]


def test_interventions_apply_from_date_plus_lag_in_scope() -> None:
    known = _known()
    eff = {"intervention": {"factor": 0.5, "lag_days": 14}}
    m, notes = inputs.intervention_mult(EV, SCOPES, FIPS, START, 365, eff, known)
    t0 = (date(2026, 6, 24) - START).days + 14
    # affected_counties on Jun 24: Lancaster (Feb 3) and Lebanon (May 6), not Delaware.
    assert (m[:t0] == 1).all()
    assert (m[t0:, 0] == 0.5).all() and (m[t0:, 1] == 0.5).all() and (m[:, 2] == 1).all()
    off = {
        "intervention": {"factor": 1.0, "lag_days": 14},
        "health_alert": {"factor": 1.0, "lag_days": 7},
    }
    assert (inputs.intervention_mult(EV, SCOPES, FIPS, START, 365, off, known)[0] == 1).all()
    with pytest.raises(ValueError):
        inputs.intervention_mult(
            EV, SCOPES, FIPS, START, 365, {"intervention": {"factor": 1.5, "lag_days": 0}}, known
        )


def test_affected_counties_with_no_evidence_is_reported_not_guessed() -> None:
    m, notes = inputs.intervention_mult(
        EV,
        SCOPES,
        FIPS,
        START,
        365,
        {"intervention": {"factor": 0.5, "lag_days": 0}},
        _known().head(0),
    )
    assert (m == 1).all() and notes == ["ev-006: no counties resolved, not applied"]


def test_school_calendar_from_events_and_unknown_stays_unadjusted() -> None:
    ev, scopes = _events(
        [
            ("sc-1", "school_calendar", date(2026, 1, 5), "Lancaster", "term_start"),
            ("sc-2", "school_calendar", date(2026, 3, 30), "Lancaster", "break_start"),
            ("sc-3", "school_calendar", date(2026, 4, 6), "Lancaster", "break_end"),
            ("sc-4", "school_calendar", date(2026, 6, 10), "Lancaster", "term_end"),
        ]
    )
    m, notes = inputs.school_mult(ev, scopes, FIPS, START, 365, 0.3)
    d = lambda y, mo, da: (date(y, mo, da) - START).days  # noqa: E731
    assert m[d(2026, 2, 1), 0] == 1.0  # in session
    assert m[d(2026, 4, 1), 0] == pytest.approx(0.7)  # spring break
    assert m[d(2026, 5, 1), 0] == 1.0
    assert m[d(2026, 7, 1), 0] == pytest.approx(0.7)  # summer
    assert m[d(2026, 1, 2), 0] == 1.0  # before any event: unknown, no adjustment
    assert (m[:, 1:] == 1).all() and notes and "unknown" in notes[0]
    assert (inputs.school_mult(ev, scopes, FIPS, START, 365, 0.0)[0] == 1).all()  # share 0: off
    bad, bs = _events([("sc-9", "school_calendar", date(2026, 1, 5), "Lancaster", "holiday")])
    with pytest.raises(ValueError):
        inputs.school_mult(bad, bs, FIPS, START, 365, 0.3)


def test_seeds_enter_the_simulator_exactly() -> None:
    n = np.array([1_000_000, 50_000, 50_000])
    seeds = np.zeros((40, 3), np.int64)
    seeds[3, 1] = 7
    res = simulator.simulate(
        n,
        n // 10,
        np.zeros(3, np.int64),
        np.zeros(3, np.int64),
        r0=0.0,  # no onward transmission: only the seeds are infected
        latent_days=7.0,
        infectious_days=8.0,
        coupling=np.eye(3),
        days=40,
        seed=1,
        seeds=seeds,
    )
    assert res.incidence[3, 1] == 7 and res.final_size.sum() == 7
    assert (res.state.sum(axis=2) == n).all()


def test_build_on_curated_data() -> None:
    if not (REPO / "data/reference/MANIFEST.json").exists():
        pytest.skip("no reference build")
    params = simulator.load_params()
    from ingest import access

    fips = access.reference_table("population_county").sort("county_fips")["county_fips"].to_list()
    out = inputs.build(START, 300, fips, params)
    k = {r["county_fips"]: r for r in out.first_known.iter_rows(named=True)}
    assert (k["42071"]["known_by"], k["42071"]["basis"]) == (date(2026, 2, 3), "ev-001")
    # Default seeding: the earliest county only, 21 days before its first known date.
    assert out.seeds.sum() == params["seeding"]["exposed"]
    assert out.seeds[(date(2026, 2, 3) - START).days - 21, fips.index("42071")] > 0
    assert (out.mult == 1).all()  # all factors default to no effect until calibrated
    # Replay: nothing fetched after a cutoff is used (E11).
    early = inputs.build(START, 300, fips, params, known_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert early.seeds.sum() == 0 and early.first_known.height == 0
