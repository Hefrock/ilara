"""Seed loader (WP3b): T3.3, T3.4, immutability, determinism."""

from __future__ import annotations

import csv
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingest import access
from ingest.curate import seed
from ingest.reference import crosswalk, pa_counties
from ingest.verify import verify_all

from conftest import REPO

NOW = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)


@pytest.fixture
def seeded(root: Path) -> Path:
    shutil.copytree(
        REPO / "data" / "seed",
        root / "data" / "seed",
        ignore=shutil.ignore_patterns("MANIFEST.json"),
    )
    shutil.copytree(
        REPO / "data" / "sensitivity" / "seed",
        root / "data" / "sensitivity" / "seed",
        ignore=shutil.ignore_patterns("MANIFEST.json"),
    )
    return root


def test_all_seed_files_load(seeded: Path) -> None:  # T3.3
    rep = seed.load(seeded, NOW)
    assert rep.loaded == {
        "curated/case_state": 5,
        "curated/event": 15,
        "sensitivity/case_county": 27,
        "sensitivity/case_state": 8,
        "sensitivity/event": 6,
    }
    assert rep.quarantined["curated/case_state"] == 2
    assert rep.quarantined["sensitivity/case_state"] == 2
    assert verify_all(seeded) == []


def test_to_confirm_rows_quarantined_with_flag(seeded: Path) -> None:  # T3.3
    seed.load(seeded, NOW)
    for st in ("curated", "sensitivity"):
        q = access.all_rows("quarantine", st, seeded)
        assert set(q["reason_code"]) == {"DATE_TO_CONFIRM"}
        flags = access.all_rows("data_quality_flag", st, seeded)
        assert set(flags["code"]) == {"DATE_TO_CONFIRM"} and flags.height == 2
    main = access.current("case_state", root=seeded)
    assert "to_confirm" not in set(main["date_precision"])
    assert set(main["seed_row"]) == {"sw-001", "sw-002", "sw-003", "sw-006", "sw-009"}


def test_sensitivity_never_reaches_curated(seeded: Path) -> None:  # T3.3, I4
    seed.load(seeded, NOW)
    for table in ("case_state", "case_county", "event"):
        cur = access.all_rows(table, "curated", seeded)
        assert set(cur["source_tier"]) <= {"T1"}
        assert not any("sensitivity" in (f or "") for f in cur["seed_file"].to_list())
    assert access.all_rows("case_county", "curated", seeded).height == 0


def test_non_t1_row_in_data_seed_rejected(seeded: Path) -> None:  # T3.3
    p = seeded / "data" / "seed" / "statewide_extra.csv"
    rows = list(csv.reader((seeded / "data/seed/statewide_backfill.csv").open()))
    rows[1][rows[0].index("source_tier")] = "T3-derived"
    with p.open("w", newline="") as fh:
        csv.writer(fh).writerows(rows[:2])
    with pytest.raises(seed.SeedError, match="only T1"):
        seed.load(seeded, NOW)


def test_seed_names_resolve(seeded: Path) -> None:  # T3.4
    xw = crosswalk.build(pa_counties.COUNTIES)
    for sub in ("data/seed", "data/sensitivity/seed"):
        for f in (seeded / sub).glob("*.csv"):
            for row in csv.DictReader(f.open()):
                if "county_name" in row:
                    crosswalk.resolve(row["county_name"], xw)
                if "county_scope" in row:
                    for part in row["county_scope"].split(";"):
                        if part not in seed.COUNTY_TOKENS:
                            crosswalk.resolve(part, xw)
    seed.load(seeded, NOW)
    cy = access.current("case_county", "sensitivity", seeded)
    assert set(cy.filter(cy["seed_row"] == "cy-019")["county_fips"]) == {"42071"}


def test_idempotent_and_deterministic(seeded: Path) -> None:  # I2
    seed.load(seeded, NOW)
    files = sorted(p.relative_to(seeded) for p in seeded.rglob("*.parquet"))
    before = {p: (seeded / p).read_bytes() for p in files}
    rep = seed.load(seeded, datetime(2026, 12, 1, tzinfo=UTC))
    assert rep.new_files == []
    assert sorted(p.relative_to(seeded) for p in seeded.rglob("*.parquet")) == files
    assert all((seeded / p).read_bytes() == b for p, b in before.items())
    st = access.current("case_state", root=seeded)
    assert set(st["fetched_at_utc"].to_list()) == {NOW}


def test_changed_seed_file_is_an_error(seeded: Path) -> None:
    seed.load(seeded, NOW)
    p = seeded / "data/seed/events.csv"
    p.write_text(p.read_text().replace("HAN 817", "HAN 818"))
    with pytest.raises(seed.SeedError, match="changed after it was seeded"):
        seed.load(seeded, NOW)
