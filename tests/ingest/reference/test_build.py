"""WP1 reference build on synthetic inputs shaped like the Census files (T1.1 to T1.7)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from ingest import rawstore
from ingest.reference import build as rb
from ingest.reference import crosswalk, pa_counties
from ingest.verify import verify_all

gpd = pytest.importorskip("geopandas")
shapely = pytest.importorskip("shapely")

TS = datetime(2026, 10, 7, 14, 30, tzinfo=UTC)
FIPS = list(pa_counties.COUNTIES)


def _shapefile_zip(tmp: Path) -> bytes:
    from shapely.geometry import box

    rows = []
    for i, fips in enumerate(FIPS):
        x, y = -80.5 + (i % 10) * 0.5, 40.0 + (i // 10) * 0.4
        rows.append(
            {
                "STATEFP": "42",
                "COUNTYFP": fips[2:],
                "GEOID": fips,
                "NAME": pa_counties.COUNTIES[fips],
                "ALAND": 1_000_000_000 + i,
                "geometry": box(x, y, x + 0.5, y + 0.4),
            }
        )
    rows.append(
        {
            "STATEFP": "36",
            "COUNTYFP": "001",
            "GEOID": "36001",
            "NAME": "Albany",
            "ALAND": 1,
            "geometry": box(-74, 42, -73.5, 42.4),
        }
    )
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4269")
    d = tmp / "shp"
    d.mkdir()
    gdf.to_file(d / "cb_test_us_county_500k.shp")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in sorted(d.iterdir()):
            z.write(f, f.name)
    return buf.getvalue()


def _totals_csv() -> bytes:
    lines = ["SUMLEV,STATE,COUNTY,STNAME,CTYNAME,POPESTIMATE2024,POPESTIMATE2025"]
    total = 0
    for i, f in enumerate(FIPS):
        pop = 10_000 + 1_000 * i
        if i == len(FIPS) - 1:
            pop = rb.STATE_CHECK["2025"] - total  # sum to the sources S3 check value
        total += pop
        lines.append(f"050,42,{f[2:]},Pennsylvania,{pa_counties.COUNTIES[f]} County,1,{pop}")
    lines.insert(1, f"040,42,000,Pennsylvania,Pennsylvania,1,{total}")
    lines.append("050,36,001,New York,Albany County,1,300000")
    return ("\n".join(lines) + "\n").encode("latin1")


def _agesex_csv() -> bytes:
    lines = [
        "SUMLEV,STATE,COUNTY,STNAME,CTYNAME,YEAR,POPESTIMATE,UNDER5_TOT,AGE513_TOT,"
        "AGE85PLUS_TOT,MEDIAN_AGE_TOT"
    ]
    for year in (6, 7):
        for f in FIPS:
            lines.append(f"050,42,{f[2:]},Pennsylvania,X County,{year},100,5,{year},1,40.1")
    return ("\n".join(lines) + "\n").encode()


def _commuting_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Table 1. Residence County to Workplace County Commuting Flows"])
    ws.append([])
    # The published file labels residence and workplace on a row above the column names.
    ws.append(["Residence", "", "", "", "Place of Work", "", "", "", "Commuting Flow", ""])
    ws.append(
        [
            "State FIPS Code",
            "County FIPS Code",
            "State Name",
            "County Name",
            "State FIPS Code",
            "County FIPS Code",
            "State Name",
            "County Name",
            "Workers in Commuting Flow",
            "Margin of Error",
        ]
    )
    ws.append(["42", "071", "", "", "042", "029", "", "", "1,200", "50"])
    ws.append(["42", "071", "", "", "042", "071", "", "", 50000, "50"])
    ws.append(["42", "029", "", "", "010", "003", "", "", 300, "20"])  # to Delaware state
    ws.append(["34", "005", "", "", "042", "101", "", "", 700, "20"])  # NJ into Philadelphia
    ws.append(["34", "005", "", "", "034", "007", "", "", 900, "20"])  # not PA at all
    ws.append(["42", "003", "", "", "", "", "", "", 15, "9"])  # abroad
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def built(root: Path, tmp_path: Path) -> tuple[Path, dict]:
    for sid, data, ext in (
        ("census_cartographic", _shapefile_zip(tmp_path), "zip"),
        ("census_popest_totals", _totals_csv(), "csv"),
        ("census_popest_agesex", _agesex_csv(), "csv"),
        ("census_commuting", _commuting_xlsx(), "xlsx"),
    ):
        rawstore.save(
            source_id=sid,
            url=f"https://example.org/{sid}",
            data=data,
            ext=ext,
            fetched_at=TS,
            root=root,
        )
    return root, rb.build(root)


def ref(root: Path, name: str) -> pl.DataFrame:
    return pl.read_csv(
        root / "data" / "reference" / name,
        schema_overrides={
            "county_fips": pl.Utf8,
            "a_fips": pl.Utf8,
            "b_fips": pl.Utf8,
            "origin": pl.Utf8,
            "dest": pl.Utf8,
            "variant_normalized": pl.Utf8,
        },
    )


def test_geometry(built) -> None:  # T1.1
    root, m = built
    g = gpd.read_file(root / "data/reference/county.gpkg")
    assert len(g) == 67 and g.geometry.is_valid.all() and g.crs is not None
    s = gpd.read_file(root / "data/reference/county_simplified.geojson")
    assert len(s) == 67 and set(s["county_fips"]) == set(FIPS)
    assert m["crs_geojson"] == "EPSG:4326"


def test_fips_sets(built) -> None:  # T1.2
    root, _ = built
    geo, pop = ref(root, "geography_county.csv"), ref(root, "population_county.csv")
    assert set(geo["county_fips"]) == set(pop["county_fips"])
    assert all(f.startswith("42") and len(f) == 5 for f in geo["county_fips"])


def test_population_sum(built) -> None:  # T1.3
    root, m = built
    pop = ref(root, "population_county.csv")
    assert pop["total"].sum() == m["statewide_population_check"] == 13_059_432
    assert pop["agesex_year_code"].unique().to_list() == [7]
    assert "under5_tot" in pop.columns and "median_age_tot" not in pop.columns


def test_crosswalk(built) -> None:  # T1.4
    root, _ = built
    xw = ref(root, "county_crosswalk.csv")
    assert xw["variant_normalized"].n_unique() == xw.height
    d = dict(xw.rows())
    for name in (
        "McKean County",
        "Mc Kean Co.",
        "MCKEAN",
        "Lancaster County, Pennsylvania",
        "lancaster co",
        "Northumberland, PA",
    ):
        assert crosswalk.resolve(name, d) in ("42083", "42071", "42097")
    assert crosswalk.resolve("Mc Kean", d) == "42083"
    with pytest.raises(KeyError):
        crosswalk.resolve("Albany County", d)


def test_crosswalk_collision_detected() -> None:
    with pytest.raises(ValueError):
        crosswalk.build({"42001": "Adams"}, extra={"Adams Co": "42003"})


def test_adjacency_and_distance(built) -> None:  # T1.5
    root, _ = built
    adj = ref(root, "county_adjacency.csv")
    pairs = set(zip(adj["a_fips"], adj["b_fips"], strict=True))
    assert pairs and all((b, a) in pairs for a, b in pairs)
    assert (adj["shared_boundary_m"] > 0).all()
    dist = ref(root, "county_distance.csv")
    dd = {(a, b): k for a, b, k in dist.rows()}
    assert dist.height == 67 * 66
    assert all(k >= 0 and dd[(b, a)] == k for (a, b), k in dd.items())


def test_commuting(built) -> None:  # T1.6
    root, _ = built
    e = ref(root, "mobility_edge.csv")
    ok = set(FIPS) | {"EXTERNAL"}
    assert set(e["origin"]) <= ok and set(e["dest"]) <= ok
    assert (e["flow"] >= 0).all()
    flows = {(o, d): f for o, d, f, _ in e.rows()}
    assert flows[("42071", "42029")] == 1200
    assert flows[("42029", "EXTERNAL")] == 300
    assert flows[("EXTERNAL", "42101")] == 700
    assert flows[("42003", "EXTERNAL")] == 15
    assert ("EXTERNAL", "EXTERNAL") not in flows


def test_verify_and_determinism(built) -> None:  # T1.7
    root, m = built
    assert verify_all(root) == []
    assert rb.build(root).get("skipped") is True
    m2 = rb.build(root, force=True)
    assert {k: v["sha256"] for k, v in m["files"].items() if k != "county.gpkg"} == {
        k: v["sha256"] for k, v in m2["files"].items() if k != "county.gpkg"
    }
    p = root / "data/reference/county_adjacency.csv"
    p.write_text(p.read_text() + "x\n")
    assert any("HASH_MISMATCH" in x for x in verify_all(root))


def test_manifest_records_inputs(built) -> None:
    root, m = built
    saved = json.loads((root / "data/reference/MANIFEST.json").read_text())
    assert set(saved["inputs"]) == {
        "census_cartographic",
        "census_popest_totals",
        "census_popest_agesex",
        "census_commuting",
    }
