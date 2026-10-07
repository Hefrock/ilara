"""Dashboard (WP5): T5.1 to T5.9 on a fixture dataset, offline."""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from ingest import rawstore
from ingest.capture_log import CaptureLog, CaptureRecord
from ingest.curate import seed
from ingest.parse import runner
from project.dashboard import build

from conftest import REPO

FIXTURE = REPO / "tests/fixtures/doh_dashboard/2026-10-05_responses.json.gz"
NOW = datetime(2026, 10, 7, 15, tzinfo=UTC)
CHROMIUM = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


@pytest.fixture
def site_root(root: Path) -> Path:
    if not (REPO / "data/reference/MANIFEST.json").exists():
        pytest.skip("no reference build")
    shutil.copytree(REPO / "data/reference", root / "data/reference")
    for sub in ("data/seed", "data/sensitivity/seed"):
        shutil.copytree(REPO / sub, root / sub, ignore=shutil.ignore_patterns("MANIFEST.json"))
    seed.load(root, datetime(2026, 10, 7, 4, tzinfo=UTC))
    rawstore.save(
        source_id="doh_dashboard",
        url="https://report.test",
        data=gzip.decompress(FIXTURE.read_bytes()),
        ext="json",
        capture_key="responses",
        fetched_at=datetime(2026, 10, 7, 3, 42, tzinfo=UTC),
        root=root,
    )
    runner.run(root)
    t = "2026-10-07T03:43:11Z"
    CaptureLog("r1", root).append(
        CaptureRecord(
            capture_id="r1:01:doh_dashboard",
            source_id="doh_dashboard",
            url="u",
            started_utc=t,
            finished_utc=t,
            http_status=200,
            outcome="changed",
            raw_path=None,
            sha256=None,
            content_hash=None,
            bytes=None,
            runner="local",
        )
    )
    return root


def test_numbers_trace_to_rows(site_root: Path) -> None:  # T5.1
    page = build.build_page(site_root, NOW)
    tiles = {t["key"]: t for t in page.data["tiles"]}
    assert tiles["cum_cases"]["value"] == 1004 and tiles["deaths"]["value"] == 5
    for t in page.data["tiles"]:
        assert t["as_of_date"] and t["source_tier"] == "T1" and t["raw_sha256"]
        assert f">{t['value']:,}<" in page.html  # the number on the page is the row's number
    for r in page.data["statewide"]:
        assert r["as_of_date"] and r["source_tier"]
    for r in page.data["county"]:
        assert r["cum_cases"] is None or (r["as_of_date"] and r["source_tier"])
    embedded = page.html.split('id="dashboard-data">')[1].split("</script>")[0]
    assert json.loads(embedded.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))[
        "tiles"
    ]


def test_builds_offline_and_writes_files(site_root: Path, tmp_path: Path) -> None:  # T5.2
    out = build.write_site(tmp_path / "site", site_root, NOW)
    assert out.exists() and (tmp_path / "site/plotly.min.js").exists()
    assert "https://cdn" not in out.read_text()  # no network assets referenced


def test_all_counties_and_no_data_distinct(site_root: Path) -> None:  # T5.3
    page = build.build_page(site_root, NOW)
    assert len(page.data["county"]) == 67
    assert build.ramp_color(None, 10) == build.NO_DATA
    assert build.ramp_color(0, 10) == build.BLUE_SEQ[0] != build.NO_DATA
    geo = json.loads((site_root / "data/reference/county_simplified.geojson").read_text())
    fig = build.county_figure(build.county_latest(site_root), geo)
    assert len(fig.data) == 67 + 1  # every county shape plus the colorbar


def test_stale_banner(site_root: Path) -> None:  # T5.4
    assert "Data may be stale" not in build.build_page(site_root, NOW).html
    later = datetime(2026, 10, 12, tzinfo=UTC)
    assert "Data may be stale" in build.build_page(site_root, later).html


def test_no_gated_panels(site_root: Path) -> None:  # T5.5
    for public in (False, True):
        page = build.build_page(site_root, NOW, public=public)
        assert page.data["gated_panels"] == []
        assert "forecast" not in page.html.lower().replace("forecasts are withheld", "")
        assert "watchlist" not in page.html.lower()


def test_csv_exports_match_plotted(site_root: Path, tmp_path: Path) -> None:  # T5.8
    build.write_site(tmp_path / "site", site_root, NOW)
    page = build.build_page(site_root, NOW)
    csv = pl.read_csv(tmp_path / "site/data/statewide.csv")
    assert csv["cum_cases"].to_list() == [r["cum_cases"] for r in page.data["statewide"]]
    cty = pl.read_csv(tmp_path / "site/data/county.csv", schema_overrides={"county_fips": pl.Utf8})
    assert cty["cum_cases"].sum() == 1004


def test_no_t3_derived(site_root: Path) -> None:  # T5.9
    page = build.build_page(site_root, NOW)
    assert "T3-derived" not in page.html
    tiers = {r["source_tier"] for r in page.data["statewide"]}
    assert tiers <= {"T1"}


def test_renders_without_errors_or_horizontal_scroll(
    site_root: Path, tmp_path: Path
) -> None:  # T5.6
    if not CHROMIUM.exists():
        pytest.skip("no local Chromium")
    from playwright.sync_api import sync_playwright

    out = build.write_site(tmp_path / "site", site_root, NOW)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=str(CHROMIUM))
        for vp in ({"width": 1280, "height": 900}, {"width": 390, "height": 844}):
            errors: list[str] = []
            pg = b.new_page(viewport=vp)
            pg.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
            pg.goto(out.as_uri())
            pg.wait_for_timeout(1500)
            assert pg.evaluate("document.documentElement.scrollWidth") <= vp["width"]
            assert errors == []
            if vp["width"] == 1280:  # executive band visible without scrolling on desktop
                assert (
                    pg.evaluate("document.querySelector('.tiles').getBoundingClientRect().bottom")
                    < 900
                )
        b.close()
