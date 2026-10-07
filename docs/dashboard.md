# DASHBOARD: executive and epidemiological dashboard with GIS

Design intent: an executive band at the top with a few, impactful, succinct items, then a detailed epidemiological breakdown below. GIS mapping is wanted. The tension between executive simplicity and data uncertainty is intentional, so the executive band must stay simple without hiding uncertainty.

## 1. Build approach
- Static site regenerated after every weekly release and on demand with `make dashboard`. While the repo is private (GitHub Free has no private Pages) the build is a CI artifact; public Pages hosting starts at Gate G5. No server and no database at view time.
- Python generates the pages. Plotly (HTML output) for charts and Plotly choropleth maps (E17: no tile server, no MapLibre). Boundary data is simplified GeoJSON committed to the repo.
- Every chart reads only from curated tables and `capture_status()` through `ingest/access.py` (HANDOFF.md sections 3 and 4). No chart may read raw snapshots or seed files directly. Section 3C reads `case_demographics` (provisional schema).
- Every chart has a CSV export of its underlying data and a footer: source, `as_of_date`, `source_tier`, `count_definition`.
- Page order: one scrolling page. Executive band, then analyst sections, then a Data and trust section, with a sticky in-page nav.

## 2. Executive band (maximum 5 items, fits one screen)
1. Headline tiles, four only: confirmed PA cases (cumulative), new cases in the last 7 days with change versus the prior 7 days, hospitalizations, deaths. Each tile shows `as of` date and the count definition. Add a small "reported counts are a floor" note.
2. Weekly new cases bar chart (by report week), with the model forecast fan for the next 4 weeks shown in a visibly different style (hatched or lighter, labelled "model projection"). Hide the fan if the validation gate (section 5 below) has not passed.
3. County map: cases per 100,000, with a toggle for raw counts. Top 5 counties listed beside the map.
4. "What changed since the last update": 3 to 5 template-generated lines (new counties reported, change in community transmission list, notable jumps, new alerts). Text is generated from data by fixed templates. Do not use free-form LLM text in the published page.
5. Data status line: last successful snapshot time (ET), next expected update, and a stale-data banner if the latest snapshot is older than the expected cadence plus 24 hours.

Executive band rules: no model parameters, no R0, no jargon; no more than two colours per chart; plain-English titles that state the finding; uncertainty shown as a band, never omitted.

## 3. Epidemiological breakdown (below the band)
A. Time series
- Cumulative and new cases (statewide), with the weekday reporting artifact flagged (Wed-Fri versus Fri-Mon reporting).
- Small multiples by county (top N plus an "all other" panel), shared x axis, free y axis toggle.
- County-by-week heatmap of new cases (counties ordered by first-case date).
- Reporting diagnostics: reporting lag, snapshot gaps, `count_definition` break marker (calendar year versus since April).

B. GIS section (all maps use the same FIPS-keyed boundary file and colour scales, so maps are comparable)
1. Choropleth: cases per 100,000 (default), raw counts (toggle). Counties with fewer than 5 cases use a hatched pattern or a footnote because rates are unstable.
2. Graduated symbols (proportional circles at county centroids) layered over adjacency outlines, for raw counts.
3. First-case timing small multiples: one mini map per week or fortnight showing counties newly reporting. Only from dashboard snapshots (and `T3-derived` rows if enabled, labelled).
4. Susceptibility map: county MMR coverage from the 2025-2026 school survey (kindergarten), shown as the share below 95 percent. Footnote the December self-reporting timing, the "ND" suppression for schools under 20 students, and the Amish and Mennonite undercount limitation (section S2).
5. School-level strip plot: schools by coverage within a county, selectable from the map. Dot positions are school coverage, not locations, to avoid implying location precision the data do not have.
6. Model watchlist map: modelled probability of at least one new case in the next 2 weeks for counties with zero reported cases, with a "model output, not an observation" label. Only shown once forecast calibration passes.
7. Optional context layers: community transmission list counties (outlined), commuting-flow edges (top edges only, thin lines), wastewater sites (CDC NWSS) as points where available.
- Map rules: sequential single-hue colour scale for rates, colour-blind safe, no animation, no 3D, keyboard accessible, tooltips repeat the number plus `as of`. Do not use pie charts or dual-axis charts anywhere.

C. Demography and severity
- Age distribution, vaccination status, hospitalization share, deaths (using the DOH definition in section S1), each with the denominators shown. Suppress or merge cells under 5 to reduce re-identification risk.

D. Model outputs (from WP6)
- Posterior predictive fan chart against observed counts.
- Scenario comparison (coupling variants: commuting, adjacency, long-range; intervention timing), with identical axes.
- Forecast calibration: weighted interval score or CRPS and interval coverage versus the persistence baseline, by forecast date.
- Parameter posteriors with prior overlay (flagged as weakly identified, since no line list or onset dates exist).
- Observed data and model outputs must be styled differently in every chart (solid versus hatched or dashed, plus legend text).

## 4. Data and trust section
- Snapshot and gap timeline (what was captured, what was missed; missed snapshots are unrecoverable).
- Definitions: case, hospitalization, death (30 days of onset, lab-confirmed), `count_definition`, source tiers.
- Reconciliation table: DOH dashboard versus CDC national table versus HAN figures, with differences stated.
- Active `data_quality_flag` rows, in plain language.
- Methods summary, model version, code commit hash, run manifest link.

## 5. Gating rules (what may be shown)
- Forecast fan and watchlist map are hidden until forecast replay shows interval coverage within an agreed tolerance (criteria in Gate G4 of HANDOFF.md) and a better score than persistence. Otherwise show "Projection withheld: not yet validated". Forecast panels exist only in private analyst output until `data/validation_gate.json` records a pass (Gate G4); the public site build must not contain them without that file.
- County rates are shown only for counties with a population estimate (Vintage 2025). Missing joins show a flag, never zero.
- `T3-derived` data never appears in the executive band or default charts. If enabled, it appears only in a labelled sensitivity view.
- No interpolation across missing snapshots: draw gaps as gaps.


## 6. Build stages (inside WP5)
- D0 Map assets: PA county boundaries, FIPS crosswalk, centroids, adjacency (from WP1). Check: all 67 counties join to population.
- D1 Executive band from curated `case_state` T1 rows (loaded from `seed/statewide_backfill.csv`), read through `ingest/access.py`. Shows cumulative cases as a step chart labelled "seed data through <latest as_of_date>; live capture pending". Weekly bars, the 7-day tile and the stale-data banner start once captures accumulate. County map shows "county data pending" until G1 passes.
- D2 County time series, choropleth, symbols, first-case maps (needs county snapshots from WP3).
- D3 Susceptibility map and school strip plots (needs the school immunization parse).
- D4 Model panels and gating (needs WP6 and Gate G4).
- D5 Trust section and automated regeneration after each weekly release.

## 7. Acceptance tests
- T5.1 Every number on the page traces to a curated row with `as_of_date` and `source_tier` (a test walks the page's embedded data and asserts this).
- T5.2 The page builds from a fixture dataset with no network access.
- T5.3 All 67 PA counties appear in every map; counties with no data look different from counties with zero.
- T5.4 The stale-data banner appears when the fixture's latest snapshot is older than the threshold.
- T5.5 With failing or absent validation gate fixtures, the forecast fan and watchlist are absent from the built HTML.
- T5.6 Playwright rendering at desktop and phone widths: no horizontal scroll, executive band visible without scrolling on desktop, no console errors.
- T5.7 Colour-blind safe palettes, text alternatives for charts, keyboard-reachable tooltips.
- T5.8 CSV export of each chart matches its plotted values.
- T5.9 No `T3-derived` value appears in the default build (assert by scanning embedded data for the `T3-derived` tier).
