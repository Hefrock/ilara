"""T3.2: rebuild from raw plus seed reproduces the committed current views, twice."""

from __future__ import annotations

import gzip
import shutil
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from ingest import rawstore
from ingest.curate import rebuild, seed, store
from ingest.parse import runner

from conftest import REPO

FIXTURE = REPO / "tests/fixtures/doh_dashboard/2026-10-05_responses.json.gz"


def _repo(root: Path) -> Path:
    for sub in ("data/seed", "data/sensitivity/seed"):
        shutil.copytree(REPO / sub, root / sub, ignore=shutil.ignore_patterns("MANIFEST.json"))
    seed.load(root, datetime(2026, 10, 7, 4, tzinfo=UTC))
    rawstore.save(
        source_id="doh_dashboard",
        url="https://report.test",
        data=gzip.decompress(FIXTURE.read_bytes()),
        ext="json",
        capture_key="responses",
        fetched_at=datetime(2026, 10, 7, 18, tzinfo=UTC),
        root=root,
    )
    runner.run(root)
    return root


def test_rebuild_matches_and_is_repeatable(root: Path) -> None:
    _repo(root)
    assert rebuild.rebuild(root) == []
    assert rebuild.rebuild(root) == []


def test_rebuild_detects_a_hand_edit(root: Path) -> None:
    _repo(root)
    # A hand-added row in curated (not derivable from raw or seed) must show up.
    fetched = datetime(2026, 10, 8, tzinfo=UTC)
    store.write(
        "curated",
        "case_state",
        pl.DataFrame(
            [
                {
                    "jurisdiction": "PA",
                    "disease": "measles",
                    "source_id": "doh_dashboard",
                    "source_tier": "T1",
                    "as_of_date": datetime(2026, 10, 7).date(),
                    "fetched_at_utc": fetched,
                    "ingest_run_id": "deadbeef0000",
                    "raw_sha256": "x" * 64,
                    "parser_version": "1.0.0",
                    "cum_cases": 1,
                    "count_definition": "calendar_year",
                    "date_precision": "exact",
                }
            ]
        ),
        "deadbeef0000",
        fetched,
        root,
    )
    assert any("curated/case_state" in d for d in rebuild.rebuild(root))
