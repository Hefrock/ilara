"""Static dashboard (WP5 stages D0 to D3; docs/dashboard.md, E17).

Reads only through ``ingest.access`` (I8). Builds ``site/index.html`` with Plotly charts, an
embedded JSON copy of every number on the page (T5.1), a CSV per chart (T5.8) and a table
view per chart. Default and public builds use the curated store only, so no ``T3-derived``
value can appear (T5.9). Model panels do not exist yet; when they do, they stay out of the
build until ``data/validation_gate.json`` records a pass (I11, T5.5).
"""

from __future__ import annotations

import html
import json
import zlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import polars as pl

from ingest import access
from project import manifest

ET = ZoneInfo("America/New_York")
DASHBOARD = "doh_dashboard"
STALE_HOURS = 72 + 24  # Mon/Wed/Fri cadence plus 24 h (docs/dashboard.md section 2)
UPDATE_DAYS = (0, 2, 4)  # Monday, Wednesday, Friday
UPDATE_TIME_ET = time(14, 0)

# Reference palette (dataviz skill references/palette.md). Sequential blue for magnitude;
# slot-1 blue for the one statewide series; muted gray for de-emphasised points.
BLUE_SEQ = [
    "#cde2fb",
    "#b7d3f6",
    "#9ec5f4",
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
]
SERIES_LIGHT, SERIES_DARK = "#2a78d6", "#3987e5"
MUTED = "#898781"
NO_DATA = "#e1e0d9"
TARGET = 95.0  # kindergarten MMR coverage target, percent
DEFAULT_COUNTY = "42071"  # Lancaster: the outbreak's centre, shown first in the strip plot


@dataclass
class Page:
    html: str
    data: dict[str, Any]
    csv: dict[str, pl.DataFrame]


def _num(v: Any) -> str:
    return "n/a" if v is None else f"{int(v):,}"


def _d(v: Any) -> str:
    return v.isoformat() if isinstance(v, date) else str(v)


# ---------------------------------------------------------------- data


def headline(root: Path | None) -> dict[str, Any] | None:
    st = (
        access.current("case_state", "curated", root)
        .filter(
            (pl.col("source_id") == DASHBOARD)
            & (pl.col("count_definition") == "calendar_year")
            & (pl.col("source_tier") == "T1")
        )
        .sort("as_of_date")
    )
    if st.height == 0:
        return None
    last = st.row(-1, named=True)
    prior = st.filter(pl.col("as_of_date") == last["as_of_date"] - timedelta(days=7))
    last["prior_new_7day"] = prior["new_7day"][0] if prior.height else None
    return last


def statewide_series(root: Path | None) -> pl.DataFrame:
    df = access.current("case_state", "curated", root).filter(
        (pl.col("source_tier") == "T1")
        & ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
        & (pl.col("date_precision") == "exact")
        & pl.col("count_definition").is_in(["calendar_year", "unknown"])
        & pl.col("cum_cases").is_not_null()
    )
    # One point per date and definition: prefer the dashboard, then releases, then seeds.
    rank = {DASHBOARD: 0, "doh_release": 1}
    df = df.with_columns(pl.col("source_id").replace_strict(rank, default=2).alias("_r"))
    df = (
        df.sort(["as_of_date", "count_definition", "_r"])
        .group_by(["as_of_date", "count_definition"], maintain_order=True)
        .first()
    )
    return df.select(
        "as_of_date",
        "cum_cases",
        "count_definition",
        "source_id",
        "source_tier",
        "raw_sha256",
        "seed_row",
    ).sort("as_of_date")


def county_latest(root: Path | None) -> pl.DataFrame:
    cty = access.current("case_county", "curated", root).filter(
        (pl.col("source_id") == DASHBOARD) & (pl.col("source_tier") == "T1")
    )
    geo = access.reference_table("geography_county", root).select("county_fips", "name")
    pop = access.reference_table("population_county", root).select(
        "county_fips", pl.col("total").alias("population")
    )
    base = geo.join(pop, on="county_fips", how="left")
    if cty.height == 0:
        return base.with_columns(
            pl.lit(None, pl.Int64).alias("cum_cases"),
            pl.lit(None, pl.Date).alias("as_of_date"),
            pl.lit(None, pl.Utf8).alias("source_tier"),
            pl.lit(None, pl.Utf8).alias("count_definition"),
            pl.lit(None, pl.Boolean).alias("community_transmission"),
            pl.lit(None, pl.Float64).alias("rate_per_100k"),
        )
    latest = cty["as_of_date"].max()
    snap = cty.filter(pl.col("as_of_date") == latest).select(
        "county_fips",
        "cum_cases",
        "as_of_date",
        "source_tier",
        "count_definition",
        "community_transmission",
    )
    out = base.join(snap, on="county_fips", how="left")
    return out.with_columns(
        pl.when(pl.col("population").is_not_null() & pl.col("cum_cases").is_not_null())
        .then((pl.col("cum_cases") / pl.col("population") * 100_000).round(1))
        .otherwise(None)
        .alias("rate_per_100k")
    ).sort("county_fips")


def coverage_schools(root: Path | None) -> pl.DataFrame:
    """Kindergarten rows from the school survey, suppressed ("ND") schools included and
    flagged; they are counted on the page but never plotted (no value to plot)."""
    sch = access.current("immunization_school", "curated", root).filter(
        (pl.col("grade") == "kindergarten") & (pl.col("source_tier") == "T1")
    )
    names = access.reference_table("geography_county", root).select(
        "county_fips", pl.col("name").alias("county")
    )
    return (
        sch.join(names, on="county_fips", how="left")
        .select(
            "county_fips",
            "county",
            "school_name",
            "enrolled",
            "mmr_pct",
            "suppressed_flag",
            "school_year",
            "source_id",
            "source_tier",
            "raw_sha256",
        )
        .sort("county_fips", "school_name")
    )


def coverage_county(root: Path | None, schools: pl.DataFrame) -> pl.DataFrame:
    """County kindergarten MMR coverage (DOH county summary) for all 67 counties, with the gap
    to the 95 percent target and the share of reporting schools below it."""
    imm = access.current("immunization_county", "curated", root).filter(
        (pl.col("grade") == "kindergarten") & (pl.col("source_tier") == "T1")
    )
    base = access.reference_table("geography_county", root).select("county_fips", "name")
    cty = imm.select(
        "county_fips",
        "school_year",
        "enrolled",
        pl.col("mmr_up_to_date_pct").round(1).alias("mmr_pct"),
        "source_id",
        "source_tier",
        "raw_sha256",
    )
    shown = schools.filter(~pl.col("suppressed_flag") & pl.col("mmr_pct").is_not_null())
    counts = (
        schools.group_by("county_fips")
        .agg(
            (~pl.col("suppressed_flag") & pl.col("mmr_pct").is_not_null())
            .sum()
            .cast(pl.Int64)
            .alias("schools_reporting"),
            pl.col("suppressed_flag").sum().cast(pl.Int64).alias("schools_suppressed"),
        )
        .join(
            shown.group_by("county_fips").agg(
                (pl.col("mmr_pct") < TARGET).sum().cast(pl.Int64).alias("schools_below_95")
            ),
            on="county_fips",
            how="left",
        )
    )
    out = base.join(cty, on="county_fips", how="left").join(counts, on="county_fips", how="left")
    return out.with_columns(
        pl.when(pl.col("mmr_pct").is_not_null())
        .then((TARGET - pl.col("mmr_pct")).clip(lower_bound=0).round(1))
        .otherwise(None)
        .alias("gap_pts"),
        pl.when(pl.col("schools_reporting") > 0)
        .then((pl.col("schools_below_95") / pl.col("schools_reporting") * 100).round(1))
        .otherwise(None)
        .alias("share_schools_below_95"),
    ).sort("county_fips")


DEFINITION_TEXT = {
    "calendar_year": "calendar year",
    "since_april": "since April",
    "unknown": "not stated",
}


def reconciliation(root: Path | None) -> pl.DataFrame:
    """Dates on which more than one T1 report gives a statewide total, with the spread between
    them (docs/dashboard.md section 4). Values are shown side by side, never merged."""
    cs = access.current("case_state", "curated", root).filter(
        (pl.col("source_tier") == "T1")
        & ~pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
        & pl.col("count_definition").is_in(["calendar_year", "unknown"])
        & pl.col("cum_cases").is_not_null()
    )
    if cs.height == 0:
        return pl.DataFrame(
            schema={
                "as_of_date": pl.Date,
                "reports": pl.Utf8,
                "values": pl.Utf8,
                "spread": pl.Int64,
                "agree": pl.Boolean,
            }
        )
    cs = cs.with_columns(
        (
            pl.col("source_label")
            + pl.when(pl.col("seed_file").is_not_null())
            .then(pl.lit(", seed transcription"))
            .otherwise(pl.lit(""))
            + " ("
            + pl.col("count_definition").replace_strict(DEFINITION_TEXT, default="not stated")
            + ")"
        ).alias("report")
    ).sort("as_of_date", "source_label", "count_definition")
    out = (
        cs.group_by("as_of_date", maintain_order=True)
        .agg(
            pl.len().alias("n"),
            pl.col("report").str.join("; ").alias("reports"),
            pl.col("cum_cases").cast(pl.Utf8).str.join("; ").alias("values"),
            (pl.col("cum_cases").max() - pl.col("cum_cases").min()).alias("spread"),
        )
        .filter(pl.col("n") > 1)
        .with_columns((pl.col("spread") == 0).alias("agree"))
        .drop("n")
    )
    return out.sort("as_of_date")


def cdc_comparison(root: Path | None) -> pl.DataFrame:
    """Each CDC Pennsylvania count beside the nearest DOH calendar-year totals before and after
    its date. CDC counts cases reported to CDC, which lag DOH; a CDC value between the two DOH
    values is consistent. Nothing is merged or adjusted (S6)."""
    cs = access.current("case_state", "curated", root).filter(
        (pl.col("source_tier") == "T1")
        & (pl.col("count_definition") == "calendar_year")
        & (pl.col("date_precision") == "exact")
        & pl.col("cum_cases").is_not_null()
    )
    cross = pl.col("source_id").is_in(list(access.CROSSCHECK_SOURCES))
    cdc = cs.filter(cross).sort("as_of_date")
    doh = cs.filter(~cross).sort("as_of_date")
    rows = []
    for r in cdc.to_dicts():
        d = r["as_of_date"]
        before = doh.filter(pl.col("as_of_date") <= d).tail(1).to_dicts()
        after = doh.filter(pl.col("as_of_date") >= d).head(1).to_dicts()
        b = before[0] if before else None
        a = after[0] if after else None
        rows.append(
            {
                "cdc_as_of": d,
                "cdc_cases": r["cum_cases"],
                "doh_before_date": b["as_of_date"] if b else None,
                "doh_before": b["cum_cases"] if b else None,
                "doh_after_date": a["as_of_date"] if a else None,
                "doh_after": a["cum_cases"] if a else None,
                "consistent": None
                if b is None or a is None
                else b["cum_cases"] <= r["cum_cases"] <= a["cum_cases"],
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "cdc_as_of": pl.Date,
            "cdc_cases": pl.Int64,
            "doh_before_date": pl.Date,
            "doh_before": pl.Int64,
            "doh_after_date": pl.Date,
            "doh_after": pl.Int64,
            "consistent": pl.Boolean,
        },
    )


# Plain-language meaning of each open flag code (docs/dashboard.md section 4).
FLAG_TEXT = {
    "PARSE_SCHEMA_CHANGE": "A saved file could not be read as expected. The raw file is kept; "
    "no numbers were taken from it.",
    "STALE_SNAPSHOT": "A source has not been captured successfully within its expected interval.",
    "SOURCE_CONFLICT": "Two official documents give different figures for the same date. Both "
    "are kept and neither is used to overwrite the other.",
    "DATE_TO_CONFIRM": "A figure's date is not yet confirmed from an official source.",
    "CUM_DECREASE": "A cumulative count went down between two reports.",
    "IMPLIED_COUNT_BREAK": "Reported new cases do not match the change in the cumulative total.",
    "COUNTY_SUM_MISMATCH": "County counts do not add up to the statewide total.",
    "COUNTY_COUNT_DROP": "Fewer counties reported cases than in the previous snapshot; that "
    "snapshot is held back for review.",
    "DEFINITION_UNKNOWN": "The source does not say whether a count covers the calendar year or "
    "only since April.",
    "BLOCKED": "A source refused or challenged the capture; the archive stopped and did not "
    "work around it.",
    "SIZE_BUDGET": "The archive is close to its storage budget.",
    "DEMOGRAPHIC_SUM_MISMATCH": "Cases by age, month or hospitalization did not add up to the "
    "statewide total, so that breakdown was not stored.",
    "HASH_MISMATCH": "A saved raw file no longer matches its recorded hash.",
}


def flag_groups(flags: pl.DataFrame) -> list[dict[str, Any]]:
    out = []
    for code in sorted(set(flags["code"])) if flags.height else []:
        rows = flags.filter(pl.col("code") == code).sort("description")
        out.append(
            {
                "code": code,
                "meaning": FLAG_TEXT.get(code, "See the details."),
                "count": rows.height,
                "details": rows["description"].to_list(),
            }
        )
    return out


def status(root: Path | None, now: datetime) -> dict[str, Any]:
    cs = access.capture_status(root).filter(pl.col("source_id") == DASHBOARD)
    good = cs["last_good_utc"][0] if cs.height else None
    good_dt = datetime.fromisoformat(good.replace("Z", "+00:00")) if good else None
    nxt = now.astimezone(ET)
    for _ in range(8):
        cand = datetime.combine(nxt.date(), UPDATE_TIME_ET, ET)
        if nxt.weekday() in UPDATE_DAYS and cand > now.astimezone(ET):
            break
        nxt = datetime.combine(nxt.date() + timedelta(days=1), time(0), ET)
    nxt_upd = datetime.combine(nxt.date(), UPDATE_TIME_ET, ET)
    stale = good_dt is None or (now - good_dt) > timedelta(hours=STALE_HOURS)
    return {
        "last_good_utc": good,
        "last_good_et": good_dt.astimezone(ET).strftime("%a %b %-d, %Y %-I:%M %p ET")
        if good_dt
        else None,
        "next_update_et": nxt_upd.strftime("%a %b %-d, %Y %-I:%M %p ET"),
        "stale": stale,
    }


# ---------------------------------------------------------------- charts


SMALL_CELL = 5  # docs/dashboard.md C: suppress cells under 5 to reduce re-identification risk
AGE_ORDER = ("0-4", "5-9", "10-17", "18-24", "25-49", "50-64", "65+")


def _small(v: int | None) -> bool:
    return v is not None and 0 < v < SMALL_CELL


def _safe(v: int | None) -> int | None:
    """The count as published on this site: suppressed small cells carry no number at all."""
    return None if _small(v) else v


def _shown(v: int | None) -> str:
    """Display value for a count: blank in the source stays blank, 1 to 4 become "<5"."""
    if v is None:
        return "not reported"
    return "<5" if 0 < v < SMALL_CELL else f"{v:,}"


def demographics(root: Path | None) -> dict[str, Any] | None:
    """Latest dashboard snapshot of cases by age group, by month of report, and hospitalized
    cases with denominators by age band. Counts of 1 to 4 are suppressed for display."""
    d = access.current("case_demographics", "curated", root).filter(
        (pl.col("source_id") == DASHBOARD)
        & (pl.col("source_tier") == "T1")
        & pl.col("county_fips").is_null()
    )
    if d.height == 0:
        return None
    as_of = d["as_of_date"].max()
    d = d.filter(pl.col("as_of_date") == as_of)
    val = {(r["dimension"], r["category"]): r["cases"] for r in d.to_dicts()}
    ages = [
        {
            "age_group": g,
            "cases": _safe(val.get(("age_group", g))),
            "suppressed": _small(val.get(("age_group", g))),
            "shown": _shown(val.get(("age_group", g))),
        }
        for g in AGE_ORDER
        if ("age_group", g) in val
    ]
    months = sorted(c for dim, c in val if dim == "report_month")
    month_rows = [
        {
            "report_month": m,
            "cases": _safe(val[("report_month", m)]),
            "suppressed": _small(val[("report_month", m)]),
            "shown": _shown(val[("report_month", m)]),
            "partial": m == str(as_of)[:7],
        }
        for m in months
    ]
    hosp = []
    for band, label in (("under18", "Under 18"), ("18plus", "18 and over"), ("all", "All ages")):
        h, n = val.get(("hospitalized_age_band", band)), val.get(("age_band", band))
        if h is None or not n:
            continue
        hosp.append(
            {
                "age_band": label,
                "hospitalized": _safe(h),
                "cases": _safe(n),
                "share_pct": None if _small(h) or _small(n) else round(100 * h / n, 1),
                "shown": f"{_shown(h)} of {_shown(n)}",
            }
        )
    return {
        "as_of_date": as_of,
        "source_tier": "T1",
        "raw_sha256": sorted(set(d["raw_sha256"].drop_nulls())),
        "unknown_age": _safe(val.get(("age_group", "Unk"))),
        "ages": ages,
        "months": month_rows,
        "hospitalization": hosp,
    }


def _bar(x: list[Any], y: list[Any], text: list[str], colors: list[str], hover: str) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=x,
            y=y,
            text=text,
            textposition="outside",
            cliponaxis=False,
            marker={"color": colors},
            hovertemplate=hover,
        )
    )
    _layout(fig, 300)
    fig.update_layout(margin={"l": 48, "r": 16, "t": 24, "b": 40}, showlegend=False)
    # A bar with no number still says why: "<5" (suppressed) or "n/r" (blank in the report).
    for xi, yi, ti in zip(x, y, text, strict=True):
        if yi is None:
            fig.add_annotation(
                x=xi,
                y=0,
                yanchor="bottom",
                text="n/r" if ti.startswith("not reported") else ti,
                showarrow=False,
                font={"color": MUTED, "size": 12},
            )
    fig.update_xaxes(showgrid=False, type="category", fixedrange=True)
    fig.update_yaxes(
        gridcolor=NO_DATA, zeroline=False, tickformat=",", fixedrange=True, rangemode="tozero"
    )
    return fig


def months_figure(demo: dict[str, Any]) -> go.Figure:
    """Cases by month of report date. Suppressed and blank months have no bar; the current
    month is partial and drawn lighter."""
    rows = demo["months"]
    y = [r["cases"] for r in rows]
    colors = [BLUE_SEQ[4] if r["partial"] else SERIES_LIGHT for r in rows]
    labels = [r["shown"] for r in rows]
    return _bar(
        [r["report_month"] for r in rows],
        y,
        labels,
        colors,
        "%{x}<br><b>%{text}</b> cases by report date<extra></extra>",
    )


def ages_figure(demo: dict[str, Any]) -> go.Figure:
    rows = demo["ages"]
    y = [r["cases"] for r in rows]
    return _bar(
        [r["age_group"] for r in rows],
        y,
        [r["shown"] for r in rows],
        [SERIES_LIGHT] * len(rows),
        "Age %{x}<br><b>%{text}</b> cases<extra></extra>",
    )


def _layout(fig: go.Figure, height: int) -> None:
    fig.update_layout(
        height=height,
        margin={"l": 48, "r": 16, "t": 8, "b": 40},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "system-ui, -apple-system, Segoe UI, sans-serif", "size": 13},
        hoverlabel={"font": {"family": "system-ui, -apple-system, Segoe UI, sans-serif"}},
    )


def statewide_figure(series: pl.DataFrame) -> go.Figure:
    fig = go.Figure()
    cal = series.filter(pl.col("count_definition") == "calendar_year")
    unk = series.filter(pl.col("count_definition") == "unknown")
    fig.add_trace(
        go.Scatter(
            x=cal["as_of_date"].to_list(),
            y=cal["cum_cases"].to_list(),
            name="Calendar-year total",
            mode="lines+markers",
            line={"shape": "hv", "width": 2, "color": SERIES_LIGHT},
            marker={"size": 8, "color": SERIES_LIGHT},
            customdata=list(zip(cal["source_id"], strict=True)),
            hovertemplate="%{x|%b %-d, %Y}<br><b>%{y:,}</b> cases (calendar year)"
            "<br>source: %{customdata[0]}<extra></extra>",
        )
    )
    if unk.height:
        fig.add_trace(
            go.Scatter(
                x=unk["as_of_date"].to_list(),
                y=unk["cum_cases"].to_list(),
                name="Definition not stated",
                mode="markers",
                marker={"size": 9, "color": "rgba(0,0,0,0)", "line": {"width": 2, "color": MUTED}},
                customdata=list(zip(unk["source_id"], strict=True)),
                hovertemplate="%{x|%b %-d, %Y}<br><b>%{y:,}</b> cases (definition not stated)"
                "<br>source: %{customdata[0]}<extra></extra>",
            )
        )
    _layout(fig, 340)
    fig.update_layout(
        showlegend=unk.height > 0,
        legend={"orientation": "h", "y": 1.08, "x": 0},
        hovermode="closest",
    )
    fig.update_xaxes(showgrid=False, ticks="outside", tickformat="%b %-d")
    fig.update_yaxes(rangemode="tozero", gridcolor=NO_DATA, zeroline=False, tickformat=",")
    return fig


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def ramp_color(v: float | None, vmax: float) -> str:
    """Interpolate the sequential blue ramp; None (no data) gets the neutral fill."""
    if v is None:
        return NO_DATA
    t = 0.0 if vmax <= 0 else max(0.0, min(1.0, v / vmax))
    pos = t * (len(BLUE_SEQ) - 1)
    i = min(int(pos), len(BLUE_SEQ) - 2)
    f = pos - i
    a, b = _hex(BLUE_SEQ[i]), _hex(BLUE_SEQ[i + 1])
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b, strict=True))


def _rings(geom: dict) -> tuple[list[float | None], list[float | None]]:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    xs: list[float | None] = []
    ys: list[float | None] = []
    for poly in polys:
        for ring in poly:
            xs += [p[0] for p in ring] + [None]
            ys += [p[1] for p in ring] + [None]
    return xs, ys


def _mode(fills: list[str], vmax: float, title: str) -> dict[str, list[Any]]:
    """Restyle values for every county shape plus the colorbar trace (last)."""
    n = len(fills)
    return {
        "fillcolor": [*fills, None],
        "marker.cmax": [None] * n + [vmax],
        "marker.colorbar.title.text": [None] * n + [title],
    }


def _choropleth(
    geo: dict,
    fips: list[str],
    tips: list[str],
    modes: list[tuple[str, list[float | None], str]],
    height: int = 420,
) -> go.Figure:
    """Counties drawn as filled shapes on plain axes: no basemap download, works offline
    (E17). Fill is the sequential blue ramp; no data is a neutral fill, distinct from zero
    (T5.3). Each mode is (button label, value per county, colorbar title); buttons appear
    when there is more than one. Each shape carries its FIPS code in ``customdata``."""
    by_fips = {f["properties"]["county_fips"]: f for f in geo["features"]}
    maxes = [max((v or 0) for v in vals) or 1.0 for _, vals, _ in modes]
    fills = [[ramp_color(v, m) for v in vals] for (_, vals, _), m in zip(modes, maxes, strict=True)]
    fig = go.Figure()
    kept: list[int] = []
    for i, code in enumerate(fips):
        feat = by_fips.get(code)
        if feat is None:
            continue
        kept.append(i)
        xs, ys = _rings(feat["geometry"])
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor=fills[0][i],
                line={"width": 0.8, "color": "#fcfcfb"},
                hoveron="fills",
                text=tips[i],
                hoverinfo="text",
                customdata=[code] * len(xs),
                name=feat["properties"].get("name", code),
                showlegend=False,
            )
        )
    scale = [[i / (len(BLUE_SEQ) - 1), c] for i, c in enumerate(BLUE_SEQ)]
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            hoverinfo="skip",
            showlegend=False,
            marker={
                "color": [0, maxes[0]],
                "colorscale": scale,
                "cmin": 0,
                "cmax": maxes[0],
                "showscale": True,
                "size": 0.1,
                "colorbar": {"title": {"text": modes[0][2]}, "thickness": 12, "len": 0.8},
            },
        )
    )
    n_shapes = len(fig.data) - 1
    _layout(fig, height)
    fig.update_xaxes(visible=False, fixedrange=True)
    # Equal-area look at Pennsylvania's latitude: one degree of latitude ~ 1.32 of longitude.
    fig.update_yaxes(visible=False, fixedrange=True, scaleanchor="x", scaleratio=1.32)
    fig.update_layout(margin={"l": 0, "r": 0, "t": 40 if len(modes) > 1 else 8, "b": 0})
    fig.update_layout(hovermode="closest")
    if len(modes) > 1:
        buttons = [
            {
                "label": label,
                "method": "restyle",
                "args": [_mode([f[i] for i in kept], m, title), list(range(n_shapes + 1))],
            }
            for (label, _, title), f, m in zip(modes, fills, maxes, strict=True)
        ]
        fig.update_layout(
            updatemenus=[
                {
                    "type": "buttons",
                    "direction": "right",
                    "x": 0,
                    "y": 1.1,
                    "xanchor": "left",
                    "showactive": True,
                    # Fixed light chips in both modes so the active state stays legible.
                    "bgcolor": "#f0efec",
                    "bordercolor": "#c3c2b7",
                    "font": {"color": "#0b0b0b"},
                    "buttons": buttons,
                }
            ]
        )
    return fig


def county_figure(cty: pl.DataFrame, geo: dict) -> go.Figure:
    """Case map: rate per 100,000 or case count."""
    rows = cty.sort("county_fips").to_dicts()
    tips = []
    for r in rows:
        n = r["cum_cases"]
        if n is None:
            tips.append(f"<b>{r['name']}</b><br>no data")
            continue
        unstable = "<br>rate unstable (fewer than 5 cases)" if n < 5 else ""
        tips.append(
            f"<b>{r['name']}</b><br>{n:,} cases · {r['rate_per_100k']} per 100k"
            f"{unstable}<br>as of {_d(r['as_of_date'])}"
        )
    return _choropleth(
        geo,
        [r["county_fips"] for r in rows],
        tips,
        [
            ("Per 100,000", [r["rate_per_100k"] for r in rows], "per 100k"),
            (
                "Case count",
                [None if r["cum_cases"] is None else float(r["cum_cases"]) for r in rows],
                "cases",
            ),
        ],
    )


def coverage_figure(cov: pl.DataFrame, geo: dict) -> go.Figure:
    """Susceptibility map: how far county kindergarten MMR coverage falls below 95 percent,
    or the share of reporting schools below 95 percent. Darker means more susceptible."""
    rows = cov.sort("county_fips").to_dicts()
    tips = []
    for r in rows:
        if r["mmr_pct"] is None:
            tips.append(f"<b>{r['name']}</b><br>no data")
            continue
        below = (
            f"{r['schools_below_95']} of {r['schools_reporting']} reporting schools below 95%"
            if r["schools_reporting"]
            else "no school-level values"
        )
        tips.append(
            f"<b>{r['name']}</b><br>kindergarten MMR {r['mmr_pct']}%"
            f" · {r['gap_pts']} points below 95%<br>{below}"
            f"<br>{r['schools_suppressed'] or 0} schools suppressed (ND)"
            f"<br>{_num(r['enrolled'])} kindergartners · click for schools"
        )
    return _choropleth(
        geo,
        [r["county_fips"] for r in rows],
        tips,
        [
            ("Points below 95%", [r["gap_pts"] for r in rows], "points"),
            ("Schools below 95%", [r["share_schools_below_95"] for r in rows], "% schools"),
        ],
    )


def _jitter(name: str) -> float:
    """Deterministic vertical spread in [-0.35, 0.35] so a rebuild draws the same plot."""
    return (zlib.crc32(name.encode()) % 1000) / 1000 * 0.7 - 0.35


def strip_figure(schools: pl.DataFrame, cov: pl.DataFrame, default: str) -> go.Figure:
    """One strip of schools per county (one trace each, only ``default`` visible). Position is
    school coverage on the x axis, never location. Schools below 95 percent use the accent
    colour; the rest are muted."""
    shown = schools.filter(~pl.col("suppressed_flag") & pl.col("mmr_pct").is_not_null())
    lo = min(50.0, (shown["mmr_pct"].min() or 50.0) // 10 * 10)  # type: ignore[operator]
    fig = go.Figure()
    for r in cov.sort("county_fips").to_dicts():
        s = shown.filter(pl.col("county_fips") == r["county_fips"])
        pct = s["mmr_pct"].to_list()
        fig.add_trace(
            go.Scatter(
                x=pct,
                y=[_jitter(n) for n in s["school_name"]],
                mode="markers",
                name=r["name"],
                visible=r["county_fips"] == default,
                marker={
                    "size": 9,
                    "opacity": 0.85,
                    "color": [SERIES_LIGHT if p < TARGET else MUTED for p in pct],
                    "line": {"width": 0},
                },
                customdata=list(zip(s["school_name"], s["enrolled"], strict=True)),
                hovertemplate="<b>%{customdata[0]}</b><br>kindergarten MMR %{x}%"
                "<br>%{customdata[1]:,} enrolled<extra></extra>",
                showlegend=False,
            )
        )
    _layout(fig, 220)
    fig.update_layout(
        margin={"l": 16, "r": 16, "t": 24, "b": 40},
        hovermode="closest",
        shapes=[
            {
                "type": "line",
                "x0": TARGET,
                "x1": TARGET,
                "y0": 0,
                "y1": 1,
                "yref": "paper",
                "line": {"color": MUTED, "width": 1.5, "dash": "dash"},
            }
        ],
        annotations=[
            {
                "x": TARGET,
                "y": 1,
                "yref": "paper",
                "yanchor": "bottom",
                "text": "95% target",
                "showarrow": False,
                "font": {"size": 12, "color": MUTED},
            }
        ],
    )
    fig.update_xaxes(
        range=[lo, 101],
        ticksuffix="%",
        title={"text": "Kindergarten MMR coverage by school"},
        gridcolor=NO_DATA,
        fixedrange=True,
    )
    fig.update_yaxes(visible=False, range=[-0.5, 0.5], fixedrange=True)
    return fig


# ---------------------------------------------------------------- page


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, date):
        return _d(v)
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    return str(v)


def _table(df: pl.DataFrame, cols: dict[str, str], caption: str) -> str:
    head = "".join(f"<th scope='col'>{html.escape(v)}</th>" for v in cols.values())
    rows = []
    for r in df.select(list(cols)).iter_rows():
        cells = "".join(f"<td>{html.escape(_cell(v))}</td>" for v in r)
        rows.append(f"<tr>{cells}</tr>")
    return (
        f"<details class='tableview'><summary>Show the data as a table</summary>"
        f"<div class='tablewrap'><table><caption>{html.escape(caption)}</caption><thead>"
        f"<tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>"
    )


def _tile(label: str, value: Any, sub: str, key: str) -> str:
    return (
        f"<div class='tile' data-key='{key}'><div class='tile-label'>{html.escape(label)}"
        f"</div><div class='tile-value'>{_num(value)}</div><div class='tile-sub'>"
        f"{html.escape(sub)}</div></div>"
    )


def build_page(root: Path | None = None, now: datetime | None = None, public: bool = False) -> Page:
    now = now or datetime.now(UTC)
    head = headline(root)
    series = statewide_series(root)
    cty = county_latest(root)
    st = status(root, now)
    flags = access.open_flags(root)

    tiles: list[dict[str, Any]] = []
    tiles_html = ""
    if head is not None:
        as_of = _d(head["as_of_date"])
        base = {
            "as_of_date": as_of,
            "source_tier": head["source_tier"],
            "source_id": head["source_id"],
            "raw_sha256": head["raw_sha256"],
            "count_definition": head["count_definition"],
        }
        prior = head["prior_new_7day"]
        delta = (
            "prior 7 days not captured yet"
            if prior is None or head["new_7day"] is None
            else f"{head['new_7day'] - prior:+,} vs prior 7 days"
        )
        spec = [
            ("cum_cases", "Confirmed cases, 2026", f"calendar year · as of {as_of}"),
            ("new_7day", "New cases, last 7 days", delta),
            ("hospitalizations", "Hospitalized", f"cumulative · as of {as_of}"),
            ("deaths", "Measles-associated deaths", f"DOH definition · as of {as_of}"),
        ]
        for key, label, sub in spec:
            tiles.append({**base, "key": key, "label": label, "value": head[key]})
            tiles_html += _tile(label, head[key], sub, key)
    else:
        tiles_html = "<p class='muted'>No dashboard snapshot captured yet.</p>"

    county_rows = cty.with_columns(pl.col("as_of_date").cast(pl.Utf8)).to_dicts()
    top5 = cty.filter(pl.col("cum_cases").is_not_null()).sort("cum_cases", descending=True).head(5)
    top_html = "".join(
        f"<li><span>{html.escape(r['name'])}</span><span class='num'>{r['cum_cases']:,}</span></li>"
        for r in top5.to_dicts()
    )

    stale_html = (
        (
            "<div class='banner' role='status'>Data may be stale: no dashboard capture "
            f"in the last {STALE_HOURS} hours.</div>"
        )
        if st["stale"]
        else ""
    )
    groups = flag_groups(flags)
    flag_items = (
        "".join(
            f"<li><b>{html.escape(g['meaning'])}</b> <span class='muted'>({g['code']}, "
            f"{g['count']} open)</span><details><summary>Details</summary><ul>"
            + "".join(f"<li>{html.escape(d)}</li>" for d in g["details"][:25])
            + "</ul></details></li>"
            for g in groups
        )
        or "<li>None open.</li>"
    )
    days = access.capture_days(now, root)
    mark = {"covered": "✓ covered", "missed": "✗ missed", "pending": "… pending"}
    timeline = (
        "".join(
            f"<li class='day day-{r['status']}'><span>{r['day']:%a %b %-d}</span>"
            f"<span>{mark[r['status']]}</span></li>"
            for r in days.to_dicts()
        )
        or "<li>No scheduled capture day yet.</li>"
    )
    missed = days.filter(pl.col("status") == "missed").height
    recon = reconciliation(root)
    differ = recon.filter(~pl.col("agree")).height
    cdc = cdc_comparison(root)
    if cdc.height:
        last = cdc.row(-1, named=True)
        cdc_text = (
            f"CDC counts {last['cdc_cases']:,} Pennsylvania cases as of {_d(last['cdc_as_of'])}. "
            + (
                f"DOH reported {last['doh_before']:,} on {_d(last['doh_before_date'])} and "
                f"{last['doh_after']:,} on {_d(last['doh_after_date'])}; "
                + (
                    "the CDC figure falls between them, as expected for cases reported to "
                    "CDC with a lag."
                    if last["consistent"]
                    else "the CDC figure falls outside them (see the table)."
                )
                if last["consistent"] is not None
                else "No DOH total on both sides of that date yet."
            )
        )
    else:
        cdc_text = "The CDC national figures are captured daily; no dated Pennsylvania count yet."
    info = manifest.git_info()

    s_fig = statewide_figure(series).to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id="chart-statewide",
        config={"displayModeBar": False, "responsive": True},
    )
    geo = access.reference_geojson(root)
    c_fig = county_figure(cty, geo).to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id="chart-county",
        config={"displayModeBar": False, "responsive": True},
    )

    schools = coverage_schools(root)
    cov = coverage_county(root, schools)
    cov_ok = cov["mmr_pct"].drop_nulls().len() > 0
    v_fig = coverage_figure(cov, geo).to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id="chart-coverage",
        config={"displayModeBar": False, "responsive": True},
    )
    k_fig = strip_figure(schools, cov, DEFAULT_COUNTY).to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id="chart-strip",
        config={"displayModeBar": False, "responsive": True},
    )
    strip_notes = {
        r["county_fips"]: (
            f"{r['name']}: {r['schools_reporting'] or 0} schools shown, "
            f"{r['schools_below_95'] or 0} below 95 percent; "
            f"{r['schools_suppressed'] or 0} suppressed (ND, fewer than 20 students) not shown."
        )
        for r in cov.to_dicts()
    }
    options = "".join(
        f"<option value='{r['county_fips']}'"
        f"{' selected' if r['county_fips'] == DEFAULT_COUNTY else ''}>"
        f"{html.escape(r['name'])}</option>"
        for r in cov.sort("name").to_dicts()
    )
    n_below = cov.filter(pl.col("mmr_pct") < TARGET).height
    school_year = cov["school_year"].drop_nulls()
    year = school_year[0] if school_year.len() else "not yet captured"

    demo = demographics(root)
    if demo is not None:
        m_fig = months_figure(demo).to_html(
            include_plotlyjs=False,
            full_html=False,
            div_id="chart-months",
            config={"displayModeBar": False, "responsive": True},
        )
        a_fig = ages_figure(demo).to_html(
            include_plotlyjs=False,
            full_html=False,
            div_id="chart-ages",
            config={"displayModeBar": False, "responsive": True},
        )
        months_df = pl.DataFrame(demo["months"])
        ages_df = pl.DataFrame(demo["ages"])
        hosp_df = pl.DataFrame(demo["hospitalization"])
        demo_as_of = _d(demo["as_of_date"])
        unk = demo["unknown_age"]
        who_html = f"""<p class="muted">As of {
            demo_as_of
        }, calendar year. Counts of 1 to 4 are shown as
"&lt;5" and carry no number in the downloads, to protect privacy.</p>
<h3 style="font-size:1rem;margin:8px 0 4px">Cases by month of report</h3>
<p class="muted">Month the case was reported, not when the illness began; the dashboard gives no
onset dates. The lighter bar is the current month, still partial. "n/r": blank on the
dashboard (not stated as zero).</p>
{m_fig}
{
            _table(
                months_df,
                {"report_month": "Month reported", "shown": "Cases"},
                "Cases by month of report",
            )
        }
<h3 style="font-size:1rem;margin:16px 0 4px">Cases by age</h3>
{a_fig}
<p class="muted">Unknown age: {
            html.escape(
                _shown(unk) if unk is not None else "blank on the dashboard (not stated as zero)"
            )
        }.</p>
{_table(ages_df, {"age_group": "Age group", "shown": "Cases"}, "Cases by age group")}
<h3 style="font-size:1rem;margin:16px 0 4px">Hospitalized</h3>
{
            _table(
                hosp_df,
                {"age_band": "Ages", "shown": "Hospitalized of cases", "share_pct": "Percent"},
                "Hospitalized cases by age band",
            ).replace("<details class='tableview'>", "<details class='tableview' open>")
        }
<a class="dl" href="data/demographics.csv">Download CSV</a>"""
        demo_rows = months_df.select(
            pl.lit("report_month").alias("dimension"),
            pl.col("report_month").alias("category"),
            "cases",
            "suppressed",
        ).vstack(
            ages_df.select(
                pl.lit("age_group").alias("dimension"),
                pl.col("age_group").alias("category"),
                "cases",
                "suppressed",
            )
        )
    else:
        who_html = "<p class='muted'>No dashboard snapshot captured yet.</p>"
        demo_rows = pl.DataFrame()

    data = {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "build": "public" if public else "private",
        "tiles": tiles,
        "statewide": series.with_columns(pl.col("as_of_date").cast(pl.Utf8)).to_dicts(),
        "county": county_rows,
        "demographics": json.loads(json.dumps(demo, default=str)) if demo else None,
        "coverage": cov.to_dicts(),
        "coverage_schools": schools.to_dicts(),
        "strip_order": cov.sort("county_fips")["county_fips"].to_list(),
        "strip_notes": strip_notes,
        "status": st,
        "capture_days": days.with_columns(pl.col("day").cast(pl.Utf8)).to_dicts(),
        "reconciliation": recon.with_columns(pl.col("as_of_date").cast(pl.Utf8)).to_dicts(),
        "cdc_comparison": json.loads(json.dumps(cdc.to_dicts(), default=str)),
        "flags": groups,
        "build_info": info,
        "gated_panels": [],  # forecast and watchlist: absent until G4 (I11)
    }
    csv = {
        "tiles": pl.DataFrame(tiles) if tiles else pl.DataFrame(),
        "statewide": series,
        "county": cty,
        "coverage": cov,
        "schools": schools,
        "capture_days": days,
        "demographics": demo_rows,
        "reconciliation": recon,
        "cdc_comparison": cdc,
    }

    county_as_of = cty["as_of_date"].drop_nulls().max() if cty.height else None
    body = PAGE.format(
        tiles=tiles_html,
        stale=stale_html,
        last_good=html.escape(st["last_good_et"] or "never"),
        next_update=html.escape(st["next_update_et"]),
        statewide_chart=s_fig,
        statewide_table=_table(
            series,
            {
                "as_of_date": "As of",
                "cum_cases": "Cases",
                "count_definition": "Definition",
                "source_id": "Source",
            },
            "Statewide cumulative cases",
        ),
        county_as_of=html.escape(_d(county_as_of) if county_as_of else "not yet captured"),
        county_chart=c_fig,
        top5=top_html,
        county_table=_table(
            cty,
            {
                "name": "County",
                "cum_cases": "Cases",
                "rate_per_100k": "Per 100k",
                "population": "Population",
                "community_transmission": "Community transmission",
            },
            "Cases by county",
        ),
        who=who_html,
        coverage_title=html.escape(
            f"Kindergarten MMR coverage is below 95 percent in {n_below} of "
            f"{cov['mmr_pct'].drop_nulls().len()} counties"
            if cov_ok
            else "Kindergarten MMR coverage"
        ),
        coverage_year=html.escape(year),
        coverage_chart=v_fig if cov_ok else "<p class='muted'>School survey not yet parsed.</p>",
        strip_chart=k_fig,
        strip_options=options,
        strip_note=html.escape(strip_notes.get(DEFAULT_COUNTY, "")),
        coverage_table=_table(
            cov,
            {
                "name": "County",
                "mmr_pct": "Kindergarten MMR %",
                "gap_pts": "Points below 95%",
                "schools_below_95": "Schools below 95%",
                "schools_reporting": "Schools reporting",
                "schools_suppressed": "Schools suppressed (ND)",
                "enrolled": "Kindergartners",
            },
            "Kindergarten MMR coverage by county, " + year,
        ),
        school_table=_table(
            schools.filter(~pl.col("suppressed_flag")),
            {
                "county": "County",
                "school_name": "School",
                "mmr_pct": "Kindergarten MMR %",
                "enrolled": "Kindergartners",
            },
            "Kindergarten MMR coverage by school (suppressed schools omitted), " + year,
        ),
        flags=flag_items,
        timeline=timeline,
        timeline_summary=html.escape(
            f"{days.height - missed - days.filter(pl.col('status') == 'pending').height} of "
            f"{days.height} scheduled capture days covered"
            + (
                f"; {missed} missed (data shown on those days cannot be recovered)"
                if missed
                else ""
            )
            + "."
        ),
        recon_summary=html.escape(
            "No date has more than one official statewide total yet."
            if recon.height == 0
            else f"{recon.height} date{'s have' if recon.height > 1 else ' has'} more than "
            "one official statewide total; " + (f"{differ} differ." if differ else "all agree.")
        ),
        recon_table=_table(
            recon,
            {
                "as_of_date": "As of",
                "reports": "Reports",
                "values": "Cases",
                "spread": "Spread",
            },
            "Statewide totals reported by more than one official document",
        ),
        cdc_text=html.escape(cdc_text),
        cdc_table=_table(
            cdc,
            {
                "cdc_as_of": "CDC as of",
                "cdc_cases": "CDC",
                "doh_before_date": "DOH before",
                "doh_before": "DOH",
                "doh_after_date": "DOH after",
                "doh_after": "DOH",
                "consistent": "Between",
            },
            "CDC Pennsylvania counts beside the nearest DOH totals",
        ),
        git_sha=html.escape((info["git_sha"] or "unknown")[:12]),
        data_release=html.escape(info["data_release"] or "none yet"),
        # Raw JSON in a script element: only "</" needs escaping; entities would not be decoded.
        data_json=json.dumps(data, default=str, sort_keys=True).replace("</", "<\\/"),
        generated=data["generated_utc"],
    )
    return Page(body, data, csv)


def write_site(
    out: Path, root: Path | None = None, now: datetime | None = None, public: bool = False
) -> Path:
    from plotly.offline import get_plotlyjs

    page = build_page(root, now, public)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    js = out / "plotly.min.js"
    if not js.exists():
        js.write_text(get_plotlyjs())
    for name, df in page.csv.items():
        df.write_csv(out / "data" / f"{name}.csv")
    (out / "index.html").write_text(page.html)
    return out / "index.html"


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pennsylvania measles data</title>
<style>
:root {{ color-scheme: light; --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b;
  --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --border:rgba(11,11,11,0.10);
  --accent:#2a78d6; --warn-bg:#fff4dc; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark;
  --surface:#1a1a19; --plane:#0d0d0d; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --border:rgba(255,255,255,0.10); --accent:#3987e5; --warn-bg:#3a2e12; }} }}
:root[data-theme="dark"] {{ color-scheme: dark; --surface:#1a1a19; --plane:#0d0d0d;
  --ink:#ffffff; --ink2:#c3c2b7; --grid:#2c2c2a; --border:rgba(255,255,255,0.10);
  --accent:#3987e5; --warn-bg:#3a2e12; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--plane); color:var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
header, main, footer {{ max-width: 1120px; margin: 0 auto; padding: 0 16px; }}
header {{ padding-top: 20px; }}
h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
h2 {{ font-size: 1.1rem; margin: 0 0 8px; }}
.notice {{ color: var(--ink2); font-size: .9rem; margin: 0 0 12px; }}
nav {{ position: sticky; top: 0; background: var(--plane); padding: 8px 0;
  border-bottom: 1px solid var(--border); z-index: 5; display: flex; gap: 16px;
  flex-wrap: wrap; font-size: .9rem; }}
nav a {{ color: var(--ink2); }}
section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px; margin: 16px 0; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px; }}
.tile {{ border: 1px solid var(--border); border-radius: 8px; padding: 12px; }}
.tile-label {{ color: var(--ink2); font-size: .85rem; }}
.tile-value {{ font-size: 2rem; font-weight: 600; }}
.tile-sub {{ color: var(--muted); font-size: .8rem; }}
.floor {{ color: var(--ink2); font-size: .85rem; margin-top: 8px; }}
.status {{ font-size: .9rem; color: var(--ink2); margin-top: 8px; }}
.banner {{ background: var(--warn-bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 12px; margin: 8px 0; }}
.map-wrap {{ display: grid; grid-template-columns: minmax(0, 3fr) minmax(180px, 1fr);
  gap: 16px; }}
@media (max-width: 720px) {{ .map-wrap {{ grid-template-columns: 1fr; }} }}
.top5 {{ list-style: none; padding: 0; margin: 0; }}
.top5 li {{ display: flex; justify-content: space-between; padding: 6px 0;
  border-bottom: 1px solid var(--border); }}
.num {{ font-variant-numeric: tabular-nums; }}
.muted {{ color: var(--muted); }}
.tableview {{ margin-top: 8px; font-size: .9rem; }}
.tablewrap {{ max-width: 100%; overflow-x: auto; }}
#trust li {{ overflow-wrap: anywhere; }}
.timeline {{ list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }}
.timeline li {{ border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px;
  font-size: .85rem; display: flex; gap: 8px; }}
.day-missed {{ background: var(--warn-bg); }}
.flags > li {{ margin-bottom: 6px; }}
section, .map-wrap > div {{ min-width: 0; }}
.tableview table {{ border-collapse: collapse; width: 100%; }}
.tableview th, .tableview td {{ text-align: left; padding: 4px 8px;
  border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }}
.tableview caption {{ text-align: left; color: var(--ink2); padding: 4px 0; }}
.dl {{ font-size: .85rem; }}
.notes {{ color: var(--ink2); font-size: .85rem; padding-left: 18px; }}
#strip-county {{ font: inherit; max-width: 100%; }}
footer {{ color: var(--muted); font-size: .8rem; padding-bottom: 24px; }}
.js-plotly-plot, .plot-container {{ max-width: 100%; }}
</style>
<script src="plotly.min.js"></script>
</head><body>
<header>
<h1>Pennsylvania measles, 2026</h1>
<p class="notice">Unofficial independent project, not public health guidance. Counts are a floor:
reported cases are those known to and published by the Pennsylvania Department of Health.</p>
<nav><a href="#summary">Summary</a><a href="#trend">Statewide trend</a>
<a href="#counties">Counties</a><a href="#who">Who is affected</a>
<a href="#coverage">Vaccination coverage</a>
<a href="#trust">Data and trust</a></nav>
</header>
<main>
<section id="summary" aria-label="Summary">
{stale}
<div class="tiles">{tiles}</div>
<p class="floor">Forecasts are withheld until validated. Reported counts are a floor.</p>
<p class="status">Last dashboard capture: {last_good}. Next expected update: {next_update}.</p>
</section>
<section id="trend">
<h2>Statewide cases have risen through 2026</h2>
<p class="muted">Cumulative confirmed cases by report date. Points from different sources are
not interpolated; values whose count definition was not stated are shown separately.</p>
{statewide_chart}
<a class="dl" href="data/statewide.csv">Download CSV</a>
{statewide_table}
</section>
<section id="counties">
<h2>Cases are concentrated in a few counties</h2>
<p class="muted">Confirmed cases per 100,000 residents (Census Vintage 2025), as of
{county_as_of}. Rates for counties with fewer than 5 cases are unstable.</p>
<div class="map-wrap"><div>{county_chart}</div>
<div><h3 style="font-size:1rem;margin:0 0 6px">Most cases</h3><ul class="top5">{top5}</ul></div>
</div>
<a class="dl" href="data/county.csv">Download CSV</a>
{county_table}
</section>
<section id="who">
<h2>Who is affected</h2>
{who}
</section>
<section id="coverage">
<h2>{coverage_title}</h2>
<p class="muted">How far each county's kindergarten MMR coverage falls below 95 percent,
{coverage_year} school survey. Darker means a larger gap. Select a county on the map or in the
list to see its schools.</p>
{coverage_chart}
<a class="dl" href="data/coverage.csv">Download CSV</a>
{coverage_table}
<h3 style="font-size:1rem;margin:16px 0 6px">Schools by coverage</h3>
<label for="strip-county">County </label><select id="strip-county">{strip_options}</select>
<p class="muted" id="strip-note">{strip_note}</p>
{strip_chart}
<p class="muted">Each dot is one school's kindergarten class, placed by its coverage, not by its
location.</p>
<a class="dl" href="data/schools.csv">Download CSV</a>
{school_table}
<ul class="notes">
<li>Schools self-report each December, so these figures predate the outbreak by about four
months and do not reflect the vaccination that followed.</li>
<li>Values for schools with fewer than 20 students are suppressed ("ND") by the Department of
Health; they count toward county totals but cannot be shown.</li>
<li>Small private and one-room schools, common in Amish and Mennonite communities where the
outbreak is concentrated, may be suppressed or not report at all, so these rates likely
overstate immunity in the communities most at risk.</li>
</ul>
</section>
<section id="trust">
<h2>Data and trust</h2>
<p>Every number on this page comes from a saved, hashed capture of a public source and is
traceable to its raw file. Definitions: a case is a confirmed measles case reported by the
Pennsylvania Department of Health; deaths follow the DOH definition (within 30 days of onset,
lab-confirmed, no unrelated cause). Calendar-year counts include January to March.</p>
<h3 style="font-size:1rem">Capture days</h3>
<p class="muted">The dashboard keeps no public history, so each Monday, Wednesday and Friday
update must be captured that afternoon. {timeline_summary}</p>
<ul class="timeline">{timeline}</ul>
<a class="dl" href="data/capture_days.csv">Download CSV</a>
<h3 style="font-size:1rem">Where official figures overlap</h3>
<p class="muted">{recon_summary} Each figure is kept as published; none is overwritten.</p>
<a class="dl" href="data/reconciliation.csv">Download CSV</a>
{recon_table}
<h3 style="font-size:1rem">CDC cross-check</h3>
<p class="muted">{cdc_text}</p>
<a class="dl" href="data/cdc_comparison.csv">Download CSV</a>
{cdc_table}
<h3 style="font-size:1rem">Open data quality flags</h3>
<ul class="flags">{flags}</ul>
<h3 style="font-size:1rem">Methods</h3>
<p class="muted">Raw captures are saved before anything else and never edited; tables are
rebuilt from them with one command and checked in CI. No model output is published: projections
stay withheld until they pass validation. Code commit {git_sha}; data release {data_release}.</p>
</section>
</main>
<footer>Generated {generated}. Source: Pennsylvania Department of Health dashboard and
releases; population and boundaries: US Census Bureau.</footer>
<script type="application/json" id="dashboard-data">{data_json}</script>
<script>
(function () {{
  function ink() {{
    var s = getComputedStyle(document.documentElement);
    return {{ ink: s.getPropertyValue('--ink').trim(), grid: s.getPropertyValue('--grid').trim(),
             accent: s.getPropertyValue('--accent').trim(),
             surface: s.getPropertyValue('--surface').trim() }};
  }}
  function apply() {{
    if (!window.Plotly) return;
    var c = ink();
    ['chart-statewide', 'chart-county', 'chart-coverage', 'chart-strip', 'chart-months',
     'chart-ages'].forEach(function (id) {{
      var el = document.getElementById(id);
      if (!el || !el.data) return;
      Plotly.relayout(el, {{ 'font.color': c.ink, 'yaxis.gridcolor': c.grid }});
      if (id === 'chart-statewide') {{
        Plotly.restyle(el, {{ 'line.color': c.accent, 'marker.color': c.accent }}, [0]);
      }} else if (id === 'chart-months' || id === 'chart-ages') {{
        Plotly.relayout(el, {{ 'yaxis.gridcolor': c.grid }});
      }} else if (id === 'chart-strip') {{
        Plotly.relayout(el, {{ 'xaxis.gridcolor': c.grid }});
      }} else {{
        var shapes = el.data.map(function (_, i) {{ return i; }}).slice(0, -1);
        Plotly.restyle(el, {{ 'line.color': c.surface }}, shapes);
      }}
    }});
  }}
  var dataEl = document.getElementById('dashboard-data');
  var D = dataEl ? JSON.parse(dataEl.textContent) : {{}};
  function showCounty(fips) {{
    var el = document.getElementById('chart-strip');
    var sel = document.getElementById('strip-county');
    var order = D.strip_order || [];
    if (!el || !el.data || order.indexOf(fips) < 0) return;
    Plotly.restyle(el, {{ visible: order.map(function (f) {{ return f === fips; }}) }});
    if (sel) sel.value = fips;
    var note = document.getElementById('strip-note');
    if (note) note.textContent = (D.strip_notes || {{}})[fips] || '';
  }}
  function wire() {{
    var sel = document.getElementById('strip-county');
    if (sel) sel.addEventListener('change', function () {{ showCounty(sel.value); }});
    var map = document.getElementById('chart-coverage');
    if (map && map.on) map.on('plotly_click', function (ev) {{
      var p = ev && ev.points && ev.points[0];
      var fips = p && p.data && p.data.customdata && p.data.customdata[0];
      if (fips) {{
        showCounty(fips);
        var st = document.getElementById('chart-strip');
        if (st) st.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      }}
    }});
  }}
  window.addEventListener('load', function () {{ apply(); wire(); }});
  if (window.matchMedia) {{
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply);
  }}
}})();
</script>
</body></html>
"""
