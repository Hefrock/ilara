"""Gate G3 pre-flight (WP6): runs the real path up to the gate, offline, on repo data."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from project.model import calibrate as cal
from project.model import preflight

from conftest import REPO


def test_preflight_on_repo_data_stops_at_the_gate() -> None:
    if not (REPO / "data/reference/MANIFEST.json").exists():
        pytest.skip("no reference build")
    known = datetime(2026, 10, 24, tzinfo=UTC)  # before the tenth snapshot date
    rep = preflight.run(date(2026, 10, 28), known, REPO)
    checks = {n: (ok, d) for n, ok, d in rep.checks}
    assert rep.ok, rep.text()
    assert len(preflight.snapshot_dates(REPO, known)) < cal.G3_SNAPSHOTS
    assert checks["gate"][1].startswith("refuses as it should")
    assert checks["model inputs"][1].startswith("67 counties")
    assert "first scored once data for 2026-11-04" in checks["validation origins"][1]
