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
| WP1 Reference data | in progress | T1.1 to T1.7 on synthetic Census-shaped inputs | `ingest/reference/`, `tests/ingest/reference/test_build.py` | B12 (real files arrive with the first `capture-light` run; then U5, U6, U7) |
| WP2 Capture | in progress | T2.1 to T2.11 | MVC live on `main` (merge 310f47f); probe run 37562037581, `docs/probe_report.md` | |
| WP3 Parse and curate | in progress | T3.1 (dashboard), T3.3, T3.4, T3.9, T3.10, T3.11, T3.15 | Seed loader `ingest/curate/seed.py`; dashboard parser `ingest/parse/`; first seed load and Oct 5 snapshot in `data/curated/` | |
| WP4 Release | not started | | Workflow skeleton only (`release.yml`) | |
| WP5 Dashboard | not started | | | |
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
