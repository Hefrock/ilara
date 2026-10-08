# PROGRESS: where the build stands

Purpose: lets a new session (or a returning owner) pick up without rereading history. The agent reads this first and updates it before ending every session. Keep it short; evidence lives in linked files, not here.

## Rules
1. Update `Status` and `Evidence` for any work package or gate whose state changed. Evidence is a file path, test IDs that passed, or a commit hash, never a claim without a pointer.
2. `Status` values: `not started`, `in progress`, `done`, `blocked` (link the blocker ID from docs/BLOCKERS.md).
3. A work package is `done` only when every acceptance test listed for it in docs/HANDOFF.md passes (CLAUDE.md session protocol).
4. Record non-obvious decisions as `docs/adr/NNN-title.md` and link them in the log below.

## Work packages

| WP | Status | Tests passing | Evidence | Blocker |
|---|---|---|---|---|
| WP0 Foundation | done | T0.1 to T0.7 | `make check`; first `ci` run green (commit c69a446); `docs/adr/0001-github-free-limits.md` | |
| WP1 Reference data | in progress | T1.1 to T1.5, T1.7 on real Census files; T1.6 on synthetic only | `data/reference/` built 2026-10-07 (statewide 13,059,432); commuting file URL still to find (issue 7) | |
| WP2 Capture | in progress | T2.1 to T2.11 | MVC live on `main` (merge 310f47f); probe run 37562037581, `docs/probe_report.md` | |
| WP3 Parse and curate | in progress | T3.1 (dashboard, school, release), T3.2 to T3.15 | Seed loader `ingest/curate/seed.py`; dashboard parser `ingest/parse/`; quality engine `ingest/quality/` and `data/quality/quality_report.md`; first seed load and Oct 5 snapshot in `data/curated/` | |
| WP4 Release | in progress | T4.1 to T4.6 | `ingest/release/weekly.py`, `release.yml`; first scheduled release Monday 2026-10-12 13:30 UTC (data-2026-W41) | |
| WP5 Dashboard | in progress | T5.1 to T5.6, T5.8, T5.9 (T5.7 partly: palette validated, table views, keyboard tooltips not yet audited) | `project/dashboard/build.py`; stages D0 to D3 (tiles, statewide step chart, county map, status line, trust section, kindergarten MMR coverage map with school strip plots); ADR 0003 | |
| WP6 Susceptibility and model | not started | T6.16 (outputs guard) | `ingest/guards/outputs.py` | |
| WP7 Documentation | in progress | | README with unofficial notice, "counts are a floor", "forecasts withheld until validated" | |

## Gates

| Gate | Status | Evidence |
|---|---|---|
| G0 Repo and CI | done | `ci` run 37558441571 green on the working branch; T0.1 to T0.7 |
| G1 Dashboard access path decided | done | `docs/probe_report.md`: runners reach the dashboard (U22); path B works for page 1; path A decided; first county snapshot parsed (as of 2026-10-05, 67 counties, T3.11 values met); `docs/probe_report.md` |
| G2 Unattended capture proven | not started | |
| G3 Modelling go | not started | |
| G4 Forecast publication | not started | |
| G5 Public flip | not started | B13 must be decided first |

## Capture clock
First capture (UTC): 2026-10-07 02:27 (probe, data as of 2026-10-05). First county snapshot: 2026-10-07 03:42 (as of 2026-10-05). First scheduled window: 2026-10-07 18:00. Covered capture days so far: 0 (definition in docs/HANDOFF.md 8.1).

## Session log (newest first, 5 lines max per session)

| Date | Work done | Next step |
|---|---|---|
| 2026-10-07 (14) | Dashboard D3: kindergarten MMR coverage map (points below 95 percent, or share of reporting schools below 95 percent), school strip plot per county selectable from the map or a list, ND schools counted but never plotted, December timing and Amish and Mennonite footnotes, CSV and table views | D4 (events timeline); T5.7 keyboard tooltip audit; Friday capture check |
| 2026-10-07 (13) | Dashboard stages D0 to D2: offline static site with headline tiles, statewide calendar-year step chart, county map (rate and count), status and stale banner, quality flags, CSV and table views; dark mode chosen, not inverted | Check the 14:30 and evening captures; WP1 commuting; dashboard D3 (school coverage map) |
| 2026-10-07 (12) | Backfill captured (14 releases, 3 HAN PDFs, Wayback index); release parser adds dated T1 statewide rows; U11 and U16 resolved; SOURCE_CONFLICT check; 7 event URLs verified; commuting link found; docs/backfill_report.md (T3.12) | Next capture fetches the commuting file and 9 more releases; HAN PDF text; dashboard captures tonight |
| 2026-10-07 (11) | Backfill capture: `data/registry/backfill_urls.yml` (14 DOH releases, 3 HAN PDFs, a Wayback CDX query) fetched once each by `measles capture --backfill` inside capture-light | Parse release stats blocks and HAN PDFs; write docs/backfill_report.md (T3.12) |
| 2026-10-07 (10) | School-level immunization parser (U4, T3.14): 5,943 school-grade rows, 2,228 suppressed kept as null; issue 7 closed with the commuting-page solution | Backfill capture of DOH releases and HAN PDFs (WP3c); commuting link from the Census page |
| 2026-10-07 (9) | Manual capture-light run: 10 of 11 HTTP sources captured, commuting URL 404 (issue 7, alert worked); reference tables built from real Census files; school county immunization parser (T3.13 met) | Read the commuting link from the captured Census page; school-level page (U4); backfill (WP3c) |
| 2026-10-07 (8) | `measles rebuild` (T3.2, also in CI); weekly release with coverage, exports, notes, fail-closed verify and immutable manifests (T4.1 to T4.6) | Confirm tonight's scheduled captures; first release Monday; then backfill (WP3c) and school immunization parsers |
| 2026-10-07 (7) | Quality engine: implied counts, monotonicity, county sums, growth steps, values by month, weekly seed conflicts, capture freshness; idempotent flags; report regenerated on every capture run | `measles rebuild` (T3.2), weekly release (WP4) |
| 2026-10-07 (6) | Seed loader and first seed load; manual probe of the multi-view capture (all 9 views, 44 data responses, none refused); dashboard parser (path A) with golden test; G1 done | Quality engine (WP3d), rebuild (T3.2), weekly release (WP4) |
| 2026-10-07 (5) | Dashboard capture clicks the visible tabs and slicer states in one page load; case-level safeguard refuses identifier-bearing responses; static Power BI files no longer stored; partial captures raise an anomaly issue; offline fake-report tests (ADR 0002) | Merge, then confirm the first scheduled capture; county parser from it; seed loader |
| 2026-10-07 (4) | Owner decisions: B04 (accept E01 to E20, Plotly maps), B05 (commit sensitivity seeds), B15 (tab and slicer clicks), B16 (case-level safeguard) | Agent: tab and slicer capture with the case-level safeguard, then seed loader |
| 2026-10-07 (3) | PR Hefrock/ilara#1 merged; probe captured the dashboard; probe report written; capture now records why each Power BI response was or was not kept | Owner: B15, B16 (plus B04, B05). Agent: seed loader, county tab capture once B15 and B16 are answered |
| 2026-10-07 (2) | Brought in the full package: CLAUDE.md, docs/sources.md, docs/dashboard.md, T1 seeds; registry URLs from sources S1, S2, S8, S9, S10; user agent names the repository (I7); S3 population check in the reference build; tests mirror the code tree | Owner: B12, B05, B13. Agent: seed loader (WP3b), then WP4 release logic |
| 2026-10-07 (1) | WP0 scaffold and guards; WP2 MVC (raw store, capture log, polite HTTP, Playwright capture, alerts, workflows); WP1 builder; WP3e store and views | Bring in the package documents |

## Decisions and ADRs
- Owner decisions 2026-10-07: E01 to E20 accepted; maps Plotly only (E17); sensitivity seeds committed (H6); dashboard capture may click visible tabs and the count-definition slicer within one page load; capture refuses case-level responses.
- `docs/adr/0001-github-free-limits.md`: GitHub Free limits and the in-workflow guards (E18, U23).
- `docs/adr/0002-dashboard-views-and-case-level-safeguard.md`: dashboard views captured per page load and the case-level safeguard (B15, B16).
- Raw manifests sit beside their file as `<name>.manifest.json`, so a JSON capture and its manifest never share a name (E02 detail).
- The dashboard capture saves JSON responses, rendered text, html and a screenshot until the probe picks a path; html and screenshot are kept only alongside a substantive change (8.3 storage rule 1).
