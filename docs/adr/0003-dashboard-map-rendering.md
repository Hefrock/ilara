# ADR 0003: county map drawn as filled shapes, not a Plotly geo map

Status: accepted (2026-10-07).

## Context

E17 chooses Plotly with simplified GeoJSON and no tile server, so the site stays static and
offline-capable. Plotly's geo choropleth (`go.Choropleth`) still downloads a world topojson
basemap from the Plotly CDN, even with the basemap hidden. Offline, or behind a strict proxy,
the map renders blank and the page logs network errors (seen in the first build).

## Decision

Draw each county as a filled `go.Scatter` polygon on plain, hidden axes from
`data/reference/county_simplified.geojson`, with the y axis scaled 1.32 to 1 (one degree of
latitude to one of longitude at Pennsylvania's latitude). Fill colors come from the reference
sequential blue ramp, interpolated in Python; a hidden marker trace carries the colorbar.
Buttons switch the fills between rate per 100,000 and case count. Counties without data use
the neutral fill, distinct from the lightest ramp step used for zero (T5.3).

## Consequences

- No network request at view time; `tests/project/dashboard` checks there are no console
  errors and no horizontal scroll at desktop and phone widths (T5.6).
- Still Plotly only (E17): no MapLibre, no tiles.
- The projection is a simple aspect correction, adequate for one state.
