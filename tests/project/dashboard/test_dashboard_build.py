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
SCHOOL = REPO / "tests/fixtures/doh_school_imm"
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
    for sid, name, ext in (
        ("doh_school_imm_county", "county_2025-2026.xls", "xls"),
        ("doh_school_imm_school", "school_2025-2026.html.gz", "html"),
    ):
        raw = (SCHOOL / name).read_bytes()
        rawstore.save(
            source_id=sid,
            url="https://school.test",
            data=gzip.decompress(raw) if name.endswith(".gz") else raw,
            ext=ext,
            fetched_at=datetime(2026, 10, 7, 11, 16, tzinfo=UTC),
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
    assert json.loads(embedded)["tiles"]


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


def test_coverage_map_and_strips(site_root: Path, tmp_path: Path) -> None:  # D3
    page = build.build_page(site_root, NOW)
    cov = {r["county_fips"]: r for r in page.data["coverage"]}
    assert len(cov) == 67 and all(r["mmr_pct"] is not None for r in cov.values())
    lan = cov["42071"]
    assert abs(lan["mmr_pct"] - 87.6) <= 0.5 and lan["gap_pts"] == round(95 - lan["mmr_pct"], 1)
    for r in cov.values():
        assert r["source_tier"] == "T1" and r["raw_sha256"]
        assert 0 <= r["gap_pts"] <= 95 and (r["gap_pts"] == 0) == (r["mmr_pct"] >= 95)
    schools = page.data["coverage_schools"]
    shown = [r for r in schools if not r["suppressed_flag"]]
    nd = [r for r in schools if r["suppressed_flag"]]
    assert nd and all(r["mmr_pct"] is None for r in nd)  # ND schools are never given a value
    assert sum(r["schools_suppressed"] or 0 for r in cov.values()) == len(nd)
    assert sum(r["schools_reporting"] or 0 for r in cov.values()) == len(shown)
    # Strip plot: one trace per county, only the default visible, suppressed schools absent.
    geo = json.loads((site_root / "data/reference/county_simplified.geojson").read_text())
    cov_df = build.coverage_county(site_root, build.coverage_schools(site_root))
    fig = build.strip_figure(build.coverage_schools(site_root), cov_df, "42071")
    assert len(fig.data) == 67 and [t.visible for t in fig.data].count(True) == 1
    assert sum(len(t.x) for t in fig.data) == len(shown)
    assert fig.data[page.data["strip_order"].index("42071")].visible is True
    assert len(build.coverage_figure(cov_df, geo).data) == 67 + 1
    for note in ("December", "fewer than 20 students", "Amish and Mennonite"):
        assert note in page.html
    build.write_site(tmp_path / "site", site_root, NOW)
    csv = pl.read_csv(
        tmp_path / "site/data/coverage.csv", schema_overrides={"county_fips": pl.Utf8}
    )
    assert csv["mmr_pct"].to_list() == [cov[f]["mmr_pct"] for f in csv["county_fips"]]
    assert pl.read_csv(tmp_path / "site/data/schools.csv").height == len(schools)
    assert build.build_page(site_root, NOW).html == page.html  # deterministic jitter


def test_strip_follows_map_click(site_root: Path, tmp_path: Path) -> None:  # D3 interaction
    if not CHROMIUM.exists():
        pytest.skip("no local Chromium")
    from playwright.sync_api import sync_playwright

    out = build.write_site(tmp_path / "site", site_root, NOW)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=str(CHROMIUM))
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(out.as_uri())
        pg.wait_for_timeout(1500)
        visible = "document.getElementById('chart-strip').data.findIndex(t => t.visible === true)"
        order = pg.evaluate(
            "JSON.parse(document.getElementById('dashboard-data').textContent).strip_order"
        )
        assert order[pg.evaluate(visible)] == "42071"
        pg.select_option("#strip-county", "42109")  # Snyder
        assert order[pg.evaluate(visible)] == "42109"
        assert "Snyder" in pg.inner_text("#strip-note")
        b.close()
