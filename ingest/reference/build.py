"""Build ``data/reference/`` from the latest saved raw Census files (WP1).

Inputs (source ids): census_cartographic, census_popest_totals, census_popest_agesex,
census_commuting. Outputs are deterministic, so rebuilding unchanged inputs changes nothing.
``data/reference/MANIFEST.json`` records each output's sha256 and the raw inputs used.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import polars as pl

from ingest import paths, rawstore
from ingest.reference import crosswalk, pa_counties

BUILDER_VERSION = "1"
STATE_FIPS = "42"
EXPECTED_COUNTIES = 67
EQUAL_AREA = "EPSG:5070"  # CONUS Albers, metres
PERIOD_COMMUTING = "ACS 2016-2020"


class ReferenceError(Exception):
    pass


def _latest(source_id: str, root: Path) -> dict[str, Any]:
    m = rawstore.latest_manifest(source_id, root)
    if m is None:
        raise ReferenceError(f"no raw capture for {source_id}; run capture first")
    return m


# ---------------------------------------------------------------- geometry


def load_counties(zip_bytes: bytes):  # -> GeoDataFrame
    import geopandas as gpd

    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(zip_bytes)).extractall(td)
        shp = next(Path(td).rglob("*.shp"))
        gdf = gpd.read_file(shp)
    gdf = gdf[gdf["STATEFP"] == STATE_FIPS].copy()
    gdf["county_fips"] = gdf["STATEFP"] + gdf["COUNTYFP"]
    gdf = gdf.sort_values("county_fips").reset_index(drop=True)
    return gdf[["county_fips", "NAME", "ALAND", "geometry"]].rename(columns={"NAME": "name"})


def geography_table(gdf) -> pl.DataFrame:
    proj = gdf.to_crs(EQUAL_AREA)
    cent = proj.geometry.centroid.to_crs("EPSG:4326")
    return pl.DataFrame(
        {
            "county_fips": gdf["county_fips"].tolist(),
            "name": gdf["name"].tolist(),
            "land_area_km2": [round(a / 1e6, 3) for a in gdf["ALAND"].astype(float)],
            "centroid_lat": [round(p.y, 6) for p in cent],
            "centroid_lon": [round(p.x, 6) for p in cent],
        }
    )


def adjacency_table(gdf) -> pl.DataFrame:
    proj = gdf.to_crs(EQUAL_AREA).reset_index(drop=True)
    rows = []
    sindex = proj.sindex
    for i, geom in enumerate(proj.geometry):
        for j in sindex.query(geom, predicate="intersects"):
            if i == j:
                continue
            shared = geom.boundary.intersection(proj.geometry[j].boundary).length
            if shared > 1.0:  # rook adjacency; point contacts excluded
                rows.append((proj["county_fips"][i], proj["county_fips"][j], round(shared, 1)))
    rows.sort()
    return pl.DataFrame(rows, schema=["a_fips", "b_fips", "shared_boundary_m"], orient="row")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_table(geo: pl.DataFrame) -> pl.DataFrame:
    recs = geo.select("county_fips", "centroid_lat", "centroid_lon").rows()
    rows = [
        (a, b, round(haversine_km(la, lo, lb, lob), 3))
        for a, la, lo in recs
        for b, lb, lob in recs
        if a != b
    ]
    return pl.DataFrame(rows, schema=["a_fips", "b_fips", "km"], orient="row")


# ---------------------------------------------------------------- population


def _read_census_csv(data: bytes) -> pl.DataFrame:
    return pl.read_csv(io.BytesIO(data), encoding="latin1", infer_schema_length=0)


def population_totals(data: bytes, vintage: str) -> tuple[pl.DataFrame, int]:
    df = _read_census_csv(data)
    col = f"POPESTIMATE{vintage}"
    if col not in df.columns:
        raise ReferenceError(f"{col} not in totals file; columns: {df.columns[:12]}...")
    pa = df.filter(pl.col("STATE") == STATE_FIPS)
    state = pa.filter(pl.col("SUMLEV") == "040")
    if state.height != 1:
        raise ReferenceError("statewide row (SUMLEV 040) not found")
    counties = pa.filter(pl.col("SUMLEV") == "050").select(
        (pl.col("STATE") + pl.col("COUNTY")).alias("county_fips"),
        pl.col(col).cast(pl.Int64).alias("total"),
    )
    return counties.sort("county_fips"), int(state[col][0])


def population_agesex(data: bytes) -> pl.DataFrame:
    df = _read_census_csv(data).filter(pl.col("SUMLEV") == "050")
    year = df["YEAR"].cast(pl.Int64).max()
    df = df.filter(pl.col("YEAR").cast(pl.Int64) == year)
    bands = [c for c in df.columns if c.endswith("_TOT") and c not in ("MEDIAN_AGE_TOT",)]
    return df.select(
        (pl.col("STATE") + pl.col("COUNTY")).alias("county_fips"),
        pl.lit(year).cast(pl.Int64).alias("agesex_year_code"),
        *[pl.col(c).cast(pl.Int64).alias(c.lower()) for c in bands],
    ).sort("county_fips")


# ---------------------------------------------------------------- commuting


def commuting_edges(xlsx: bytes) -> pl.DataFrame:
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header: list[str] | None = None
    for r in rows:
        cells = [str(c).strip() if c is not None else "" for c in r]
        if any("State FIPS Code" in c for c in cells):
            header = cells
            break
    if header is None:
        raise ReferenceError("commuting table header not found")

    def idx(*words: str) -> int:
        for i, c in enumerate(header):
            if all(w.lower() in c.lower() for w in words):
                return i
        raise ReferenceError(f"column with {words} not found in {header}")

    states = [i for i, c in enumerate(header) if "state fips code" in c.lower()]
    counties = [i for i, c in enumerate(header) if "county fips code" in c.lower()]
    if len(states) != 2 or len(counties) != 2:
        raise ReferenceError(f"expected two state and two county FIPS columns in {header}")
    # Residence columns come first and workplace columns second, whether or not the
    # header row itself says so (the published file puts that on a separate row).
    rs, ws_ = states
    rc, wc = counties
    fl = idx("Workers in Commuting Flow")

    def fips(state: Any, county: Any) -> str | None:
        if state in (None, "") or county in (None, ""):
            return None
        s, c = str(state).strip(), str(county).strip()
        s = s[-2:].zfill(2) if s.isdigit() else s
        return s + c[-3:].zfill(3)

    agg: dict[tuple[str, str], int] = {}
    for r in rows:
        if r is None or len(r) <= fl or r[fl] in (None, ""):
            continue
        try:
            flow = int(float(str(r[fl]).replace(",", "")))
        except ValueError:
            continue
        o, d = fips(r[rs], r[rc]), fips(r[ws_], r[wc])
        if o is None or d is None:
            # work outside the US (no county code) counts as external
            d = d or "EXTERNAL"
            o = o or "EXTERNAL"
        o_pa, d_pa = o.startswith(STATE_FIPS), d.startswith(STATE_FIPS)
        if not (o_pa or d_pa):
            continue
        key = (o if o_pa else "EXTERNAL", d if d_pa else "EXTERNAL")
        agg[key] = agg.get(key, 0) + flow
    rows_out = sorted((o, d, f) for (o, d), f in agg.items())
    return pl.DataFrame(rows_out, schema=["origin", "dest", "flow"], orient="row").with_columns(
        pl.lit(PERIOD_COMMUTING).alias("period")
    )


# ---------------------------------------------------------------- build


def _write_csv(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(path)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path | None = None, vintage: str = "2025", force: bool = False) -> dict[str, Any]:
    """Build the reference tables. Skips (returns the existing manifest) when the inputs,
    builder version and vintage are unchanged, because the GeoPackage embeds a timestamp
    and would otherwise add a new binary to history on every run."""
    root = root or paths.repo_root()
    out = paths.reference_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    inputs = {
        s: _latest(s, root)
        for s in (
            "census_cartographic",
            "census_popest_totals",
            "census_popest_agesex",
            "census_commuting",
        )
    }
    mf = out / "MANIFEST.json"
    if mf.exists() and not force:
        old = json.loads(mf.read_text())
        same = (
            old.get("builder_version") == BUILDER_VERSION
            and old.get("vintage") == vintage
            and {k: v["sha256"] for k, v in old["inputs"].items()}
            == {k: v["sha256"] for k, v in inputs.items()}
        )
        if same:
            old["skipped"] = True
            return dict(old)
    payload = {s: rawstore.read_payload(m, root) for s, m in inputs.items()}

    gdf = load_counties(payload["census_cartographic"])
    if len(gdf) != EXPECTED_COUNTIES:
        raise ReferenceError(f"expected {EXPECTED_COUNTIES} PA counties, got {len(gdf)}")
    for fips, name in zip(gdf["county_fips"], gdf["name"], strict=True):
        if pa_counties.COUNTIES.get(fips) != name:
            raise ReferenceError(f"geometry county {fips} {name!r} does not match the PA list")
    if not gdf.geometry.is_valid.all():
        gdf["geometry"] = gdf.geometry.make_valid()
    geo = geography_table(gdf)
    _write_csv(geo, out / "geography_county.csv")

    gpkg = out / "county.gpkg"
    gpkg.unlink(missing_ok=True)
    gdf.drop(columns=["ALAND"]).to_file(gpkg, driver="GPKG", layer="county")
    simple = gdf[["county_fips", "name", "geometry"]].copy()
    simple["geometry"] = simple.geometry.simplify(0.002, preserve_topology=True)
    simple = simple.to_crs("EPSG:4326")
    gj = out / "county_simplified.geojson"
    gj.unlink(missing_ok=True)
    simple.to_file(gj, driver="GeoJSON", COORDINATE_PRECISION=5)

    _write_csv(adjacency_table(gdf), out / "county_adjacency.csv")
    _write_csv(distance_table(geo), out / "county_distance.csv")

    xw = crosswalk.build(dict(zip(geo["county_fips"], geo["name"], strict=True)))
    _write_csv(
        pl.DataFrame(
            sorted(xw.items()), schema=["variant_normalized", "county_fips"], orient="row"
        ),
        out / "county_crosswalk.csv",
    )

    totals, state_total = population_totals(payload["census_popest_totals"], vintage)
    ages = population_agesex(payload["census_popest_agesex"])
    if set(totals["county_fips"]) != set(geo["county_fips"]):
        raise ReferenceError("population FIPS set differs from geometry FIPS set (T1.2)")
    if int(totals["total"].sum()) != state_total:
        raise ReferenceError(
            f"county populations sum to {int(totals['total'].sum())}, state row {state_total}"
        )
    pop = (
        totals.join(ages, on="county_fips", how="left")
        .with_columns(pl.lit(vintage).alias("vintage"))
        .select("vintage", pl.exclude("vintage"))
    )
    _write_csv(pop, out / "population_county.csv")
    _write_csv(commuting_edges(payload["census_commuting"]), out / "mobility_edge.csv")

    files = sorted(p for p in out.iterdir() if p.is_file() and p.name != "MANIFEST.json")
    manifest = {
        "builder_version": BUILDER_VERSION,
        "crs_geopackage": str(gdf.crs),
        "crs_geojson": "EPSG:4326",
        "vintage": vintage,
        "statewide_population_check": state_total,
        "inputs": {
            s: {
                "raw_path": m["raw_path"],
                "sha256": m["sha256"],
                "fetched_at_utc": m["fetched_at_utc"],
            }
            for s, m in inputs.items()
        },
        "files": {p.name: {"sha256": _sha(p), "bytes": p.stat().st_size} for p in files},
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
