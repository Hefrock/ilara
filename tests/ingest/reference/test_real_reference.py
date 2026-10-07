"""T1.1 to T1.5 on the committed reference build (skipped until it exists)."""

from __future__ import annotations

import json

import polars as pl
import pytest

from conftest import REPO

REF = REPO / "data" / "reference"
pytestmark = pytest.mark.skipif(not (REF / "MANIFEST.json").exists(), reason="no reference build")
S = {"county_fips": pl.Utf8, "a_fips": pl.Utf8, "b_fips": pl.Utf8}


def test_real_geometry_and_population() -> None:
    gpd = pytest.importorskip("geopandas")
    g = gpd.read_file(REF / "county.gpkg")
    assert len(g) == 67 and g.geometry.is_valid.all() and g.crs is not None  # T1.1
    s = gpd.read_file(REF / "county_simplified.geojson")
    assert len(s) == 67
    pop = pl.read_csv(REF / "population_county.csv", schema_overrides=S)
    assert set(pop["county_fips"]) == set(g["county_fips"])  # T1.2
    assert pop["total"].sum() == 13_059_432  # T1.3, sources S3
    m = json.loads((REF / "MANIFEST.json").read_text())
    assert m["statewide_population_check"] == 13_059_432


def test_real_adjacency_and_distance() -> None:  # T1.5
    adj = pl.read_csv(REF / "county_adjacency.csv", schema_overrides=S)
    pairs = set(zip(adj["a_fips"], adj["b_fips"], strict=True))
    assert all((b, a) in pairs for a, b in pairs)
    lancaster = {b for a, b in pairs if a == "42071"}
    assert lancaster == {"42011", "42029", "42043", "42075", "42133"}
    dist = pl.read_csv(REF / "county_distance.csv", schema_overrides=S)
    assert (dist["km"] >= 0).all() and dist.height == 67 * 66
