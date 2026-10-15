"""Dashboard link drift on the DOH measles page (ADR 0009), from real captured pages."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from ingest import access, rawstore
from ingest.parse import doh_measles_page, runner

from conftest import REPO

TENANT = "IiwidCI6IjQxOGUyODQxLTAxMjgtNGRkNS05YjZjLTQ3ZmM1YTlhMWJkZSJ9"
OLD = "eyJrIjoiOGVkYzBiYjYtYTBhNy00MjVjLWFjZGQtM2Y3NDc4NmYxYzBi" + TENANT
NEW = "eyJrIjoiMjRlZmUwMzEtNDQ3Yi00YmUyLWE1ODYtZGJiZjZjMmQ4M2Q4" + TENANT
PAGES = REPO / "data/raw/doh_measles_page/2026"
BEFORE = PAGES / "20261012T221202Z_90ca8edf0913.html.gz"
AFTER = PAGES / "20261014T184825Z_e77ec0340eb5.html.gz"


def _payload(p: Path) -> bytes:
    m = rawstore.load_manifest(Path(str(p) + ".manifest.json"))
    return rawstore.read_payload(m, REPO)


def test_links_read_from_real_pages() -> None:
    url = "https://app.powerbigov.us/view?r="
    assert doh_measles_page.dashboard_links(_payload(BEFORE)) == [url + OLD]
    assert doh_measles_page.dashboard_links(_payload(AFTER)) == [url + NEW]


def test_compare() -> None:
    assert doh_measles_page.compare(["a"], ["a"]) == []
    assert doh_measles_page.compare(["a"], None) == []  # first page: nothing to compare
    ((code, text),) = doh_measles_page.compare(["b"], ["a"])
    assert code == "DASHBOARD_LINK_CHANGED" and "b" in text and "a" in text
    assert doh_measles_page.compare([], ["a"])[0][0] == "DASHBOARD_LINK_CHANGED"


def test_runner_flags_the_change_once(root: Path) -> None:
    for p, t in (
        (BEFORE, datetime(2026, 10, 12, 22, 12, tzinfo=UTC)),
        (AFTER, datetime(2026, 10, 14, 18, 48, tzinfo=UTC)),
    ):
        rawstore.save(
            source_id="doh_measles_page",
            url="https://www.pa.gov/measles",
            data=_payload(p),
            ext="html",
            fetched_at=t,
            root=root,
        )
    runner.run(root)
    runner.run(root)  # idempotent
    flags = access.current("data_quality_flag", root=root).filter(
        pl.col("code") == "DASHBOARD_LINK_CHANGED"
    )
    assert flags.height == 1 and NEW in flags["description"][0]
