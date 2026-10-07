"""Static dashboard (WP5 stages D0 to D2; docs/dashboard.md, E17).

Reads only through ``ingest.access`` (I8). Builds ``site/index.html`` with Plotly charts, an
embedded JSON copy of every number on the page (T5.1), a CSV per chart (T5.8) and a table
view per chart. Default and public builds use the curated store only, so no ``T3-derived``
value can appear (T5.9). Model panels do not exist yet; when they do, they stay out of the
build until ``data/validation_gate.json`` records a pass (I11, T5.5).
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import polars as pl

from ingest import access

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


def county_figure(cty: pl.DataFrame, geo: dict) -> go.Figure:
    """Counties drawn as filled shapes on plain axes: no basemap download, works offline
    (E17). Fill is the sequential blue ramp; no data is a neutral fill, distinct from zero
    (T5.3). Buttons switch between rate per 100,000 and case count."""
    by_fips = {f["properties"]["county_fips"]: f for f in geo["features"]}
    rows = {r["county_fips"]: r for r in cty.to_dicts()}
    rate_max = max((r["rate_per_100k"] or 0) for r in rows.values()) or 1.0
    count_max = max((r["cum_cases"] or 0) for r in rows.values()) or 1.0
    fig = go.Figure()
    rate_fill, count_fill = [], []
    for fips in sorted(rows):
        r, feat = rows[fips], by_fips.get(fips)
        if feat is None:
            continue
        xs, ys = _rings(feat["geometry"])
        n = r["cum_cases"]
        if n is None:
            tip = f"<b>{r['name']}</b><br>no data"
        else:
            unstable = "<br>rate unstable (fewer than 5 cases)" if n < 5 else ""
            tip = (
                f"<b>{r['name']}</b><br>{n:,} cases · {r['rate_per_100k']} per 100k"
                f"{unstable}<br>as of {_d(r['as_of_date'])}"
            )
        rate_fill.append(ramp_color(r["rate_per_100k"], rate_max))
        count_fill.append(ramp_color(None if n is None else float(n), count_max))
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor=rate_fill[-1],
                line={"width": 0.8, "color": "#fcfcfb"},
                hoveron="fills",
                text=tip,
                hoverinfo="text",
                name=r["name"],
                showlegend=False,
            )
        )
    scale = [[i / (len(BLUE_SEQ) - 1), c] for i, c in enumerate(BLUE_SEQ)]

    def colorbar(vmax: float, title: str) -> dict:
        return {
            "color": [0, vmax],
            "colorscale": scale,
            "cmin": 0,
            "cmax": vmax,
            "showscale": True,
            "size": 0.1,
            "colorbar": {"title": {"text": title}, "thickness": 12, "len": 0.8},
        }

    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            hoverinfo="skip",
            showlegend=False,
            marker=colorbar(rate_max, "per 100k"),
        )
    )
    n_shapes = len(fig.data) - 1
    _layout(fig, 420)
    fig.update_xaxes(visible=False, fixedrange=True)
    # Equal-area look at Pennsylvania's latitude: one degree of latitude ~ 1.32 of longitude.
    fig.update_yaxes(visible=False, fixedrange=True, scaleanchor="x", scaleratio=1.32)
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        hovermode="closest",
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
                "buttons": [
                    {
                        "label": "Per 100,000",
                        "method": "restyle",
                        "args": [_mode(rate_fill, rate_max, "per 100k"), list(range(n_shapes + 1))],
                    },
                    {
                        "label": "Case count",
                        "method": "restyle",
                        "args": [_mode(count_fill, count_max, "cases"), list(range(n_shapes + 1))],
                    },
                ],
            }
        ],
    )
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
    flag_items = (
        "".join(
            f"<li><b>{html.escape(r['code'])}</b>: {html.escape(r['description'])}</li>"
            for r in flags.sort("code").to_dicts()[:25]
        )
        or "<li>None open.</li>"
    )

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

    data = {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "build": "public" if public else "private",
        "tiles": tiles,
        "statewide": series.with_columns(pl.col("as_of_date").cast(pl.Utf8)).to_dicts(),
        "county": county_rows,
        "status": st,
        "gated_panels": [],  # forecast and watchlist: absent until G4 (I11)
    }
    csv = {
        "tiles": pl.DataFrame(tiles) if tiles else pl.DataFrame(),
        "statewide": series,
        "county": cty,
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
        flags=flag_items,
        data_json=html.escape(json.dumps(data, default=str, sort_keys=True), quote=False),
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
section, .map-wrap > div {{ min-width: 0; }}
.tableview table {{ border-collapse: collapse; width: 100%; }}
.tableview th, .tableview td {{ text-align: left; padding: 4px 8px;
  border-bottom: 1px solid var(--border); font-variant-numeric: tabular-nums; }}
.tableview caption {{ text-align: left; color: var(--ink2); padding: 4px 0; }}
.dl {{ font-size: .85rem; }}
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
<a href="#counties">Counties</a><a href="#trust">Data and trust</a></nav>
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
<section id="trust">
<h2>Data and trust</h2>
<p>Every number on this page comes from a saved, hashed capture of a public source and is
traceable to its raw file. Definitions: a case is a confirmed measles case reported by the
Pennsylvania Department of Health; deaths follow the DOH definition (within 30 days of onset,
lab-confirmed, no unrelated cause). Calendar-year counts include January to March.</p>
<h3 style="font-size:1rem">Open data quality flags</h3>
<ul>{flags}</ul>
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
    ['chart-statewide', 'chart-county'].forEach(function (id) {{
      var el = document.getElementById(id);
      if (!el || !el.data) return;
      Plotly.relayout(el, {{ 'font.color': c.ink, 'yaxis.gridcolor': c.grid }});
      if (id === 'chart-statewide') {{
        Plotly.restyle(el, {{ 'line.color': c.accent, 'marker.color': c.accent }}, [0]);
      }} else {{
        var shapes = el.data.map(function (_, i) {{ return i; }}).slice(0, -1);
        Plotly.restyle(el, {{ 'line.color': c.surface }}, shapes);
      }}
    }});
  }}
  window.addEventListener('load', apply);
  if (window.matchMedia) {{
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply);
  }}
}})();
</script>
</body></html>
"""
