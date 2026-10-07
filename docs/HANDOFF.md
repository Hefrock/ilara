# HANDOFF: build plan for the Pennsylvania measles data repository and model

Version 2, 2026-10-07. Supersedes the version 1 handoff (single file, sections 1 to 12). Appendix A lists what the engineering review found and changed; Appendix B traces every version 1 section to its new home.

## 0. How to use this package

| Document | Single purpose | Committed to repo as |
|---|---|---|
| `CLAUDE.md` | How the agent must behave: invariants I1 to I11, commands, session protocol | `CLAUDE.md` |
| `HANDOFF.md` (this file) | What to build and in what order: decisions, architecture, data contracts, work packages, gates, operations | `docs/HANDOFF.md` |
| `SOURCES.md` | Facts about the world: sources, URLs, parameters, known data issues, verification register | `docs/sources.md` |
| `DASHBOARD.md` | The dashboard and GIS specification (work package WP5 detail) | `docs/dashboard.md` |
| `seed/*.csv` | Dated T1 figures and events already collected, ready to load | `data/seed/` |
| `sensitivity_seed/*.csv` | Figures and events not taken from a primary government source (news-derived, secondary) | `data/sensitivity/seed/` |
| `HUMAN_STEPS.md` | Owner-only actions, with blocking status | kept outside the repository |

Rules for reading this package. Each requirement appears in exactly one place. Behaviour rules live in CLAUDE.md, never here. Facts live in SOURCES.md, never here. If two documents disagree, stop and ask (CLAUDE.md, "Stop and ask").

Status labels used throughout: VERIFIED, PARTIAL, UNVERIFIED (see SOURCES.md; each UNVERIFIED item has a register ID `U1` to `U22`).

## 1. Mission and scope

Build a provenance-first, self-contained git repository that captures Pennsylvania measles data on a fixed schedule, curates it into typed tables, publishes weekly releases, renders an executive and epidemiological dashboard with GIS maps, and supports a county-level stochastic metapopulation model with honest forecast validation.

In scope: Pennsylvania, 67 counties, US-only data, 2026 outbreak (first outbreak cluster January 2026, main outbreak from late April 2026) onward.

Out of scope: individual-level inference, transmission-chain reconstruction, estimating generation time, household attack rate or cluster-level effective R from public data (no line list exists), mortality modelling, any case-level data in this repository, other states or diseases (schema allows them; no implementation now).

## 2. Decisions register

### 2.1 Confirmed by the owner (do not reopen)

| ID | Decision |
|---|---|
| D01 | Purpose: portfolio showcase plus methods write-up. Priorities: provenance, reproducibility, honest uncertainty. Unofficial; not clinical or public health guidance. |
| D02 | Pennsylvania measles first. Every table carries `jurisdiction` and `disease` columns (defaults `PA`, `measles`) so other jurisdictions or diseases can be added without migration. |
| D03 | Capture Monday, Wednesday and Friday (the DOH update days); publish a weekly release. Never reduce capture to weekly. |
| D04 | Private GitHub repository (owner Hefrock) with scheduled GitHub Actions. If the dashboard probe shows GitHub-hosted runners are blocked, use a self-hosted runner. Flip public only at Gate G5. |
| D05 | Plain git only: no Git LFS, no cloud object storage, no third-party storage. A clone is a complete, verifiable archive. |
| D06 | One monorepo with `data/` (data layer) and `project/` (project layer) folders. |
| D07 | Observed data public. Forecasts and the watchlist map stay private until validated (Gate G4), then carry a "model output, not official guidance" label. |
| D08 | Capture failures and anomalies open or update a GitHub issue; GitHub email notifies the owner. Every failure is also a `data_quality_flag`. |
| D09 | GitHub Free plan: no Pages for private repos, limited Actions minutes. While private the dashboard is a CI artifact and local build; Pages starts at G5. |
| D10 | Attribution: personal GitHub identity only. No institutional affiliation text anywhere in the repository or commit metadata. README states: unofficial independent project. |
| D11 | Build order: data layer first. Modelling that needs county time series waits for Gate G3. |
| D12 | The owner runs the build locally in Claude Code using this package. |
| D13 | Code under MIT. Data licence defers to each source's terms. Only government-sourced data (DOH, CDC, Census) is in public tables. `T3-derived` rows follow CLAUDE.md I4 and decision E08. |
| D14 | Seed the repository with the dated statewide figures, county figures and events in `seed/` and `sensitivity_seed/` so history does not start empty. |
| D15 | Any request to DOH for case-level data is a parallel human task handled outside this repository (owner step H7). Not a blocker. |
| D16 | Dashboard: a short executive band on top, a detailed epidemiological breakdown below, GIS mapping included (DASHBOARD.md). |
| D17 | Python only; US-only data. |

### 2.2 Engineering decisions made in review (the owner may veto any; the default stands until then)

| ID | Decision | Why |
|---|---|---|
| E01 | Curated tables are Parquet files, append-only, one file per ingest run, never rewritten. No `.duckdb` file is committed; DuckDB reads Parquet by glob. | A committed database or rewritten table adds a new full-size binary blob to git history on every change. |
| E02 | One raw path layout: `data/raw/<source_id>/<YYYY>/<YYYYMMDDTHHMMSSZ>_<sha256 first 12>.<ext>` plus a sidecar `.json` manifest. | v1 had two conflicting layouts. |
| E03 | Raw saving is gated on a `content_hash` computed after stripping source-specific volatile fields (session ids, timestamps). `sha256` of exact bytes is still stored. Unchanged content is logged, not re-committed. | Without it, volatile fields make every capture "new" and bloat history. |
| E04 | Every capture attempt, changed or not, is logged: one file per workflow run, `data/capture_log/<YYYY-MM>/<run_id>.jsonl`, one line per source (append-only, never edited). | A flat count is information about reporting. Text keeps history small; per-run files avoid merge conflicts between concurrent workflows. |
| E05 | The capture schedule is defined once, in section 8.1. Tune the windows from `capture_log` after two weeks. | Scheduled runs drift or are dropped; DST shifts ET by an hour; exact DOH update time is unknown. |
| E06 | Capture workflows use a `concurrency` group with `cancel-in-progress: false`, and commit with `git pull --rebase` and up to 3 retries. | Overlapping runs otherwise race on push. |
| E07 | The weekly release for ISO week W (Monday to Sunday, America/New_York) is built Monday `30 13 * * 1` UTC and tagged `data-YYYY-Www`. | v1 had two release times. One time, after the week closes. |
| E08 | Figures not taken directly from a primary government source (`T3-derived`, T3 events, secondary journal figures) live only under `data/sensitivity/` (seed files in `data/sensitivity/seed/`) as numbers plus source name and URL. Article text is never committed. Because history becomes public at G5, the owner decides H6 before the first commit of those files; if H6 is no, they stay local and gitignored. | Flipping a repository public exposes all history, and history is never rewritten (I8). |
| E09 | CLAUDE.md, HANDOFF.md, SOURCES.md and DASHBOARD.md are sanitised for publication and committed. HUMAN_STEPS.md is not committed. | Consistency with D10 and I10. |
| E10 | Tools: polars (tables), duckdb (SQL views), pydantic v2 (schemas), geopandas (reference and map code only), numba (simulator), pytest, hypothesis, ruff, playwright. | v1 left "polars or pandas" and "DuckDB or parquet" open. |
| E11 | All validation replay reads data only through `as_known_at(T)` (section 4.5). | Prevents look-ahead leakage in forecast evaluation. |
| E12 | Gate G3 (modelling go) requires at least 10 distinct `as_of_date` values with county-level snapshots from the dashboard. | v1 said "four weeks"; this is measurable. |
| E13 | Capture and parse are separate stages. Parsers run only on saved raw files and can be re-run when fixed. | A parser bug must never lose data. |
| E14 | `count_definition` enum is `calendar_year`, `since_april`, `unknown`. | Several source values have an unresolved definition. |
| E15 | Commits use the GitHub noreply address. | Hygiene (I10). |
| E16 | One phase system: work packages WP0 to WP7 and gates G0 to G5. v1 Phases 0 to 7 and D0 to D5 are retired. | v1 had two overlapping phase systems. |
| E17 | Plotly for charts and choropleth maps from simplified GeoJSON; no tile server and no MapLibre. | v1 left it open; keeps the site static and offline-capable. |
| E18 | Guards (path guard, append-only guard, `verify`) run inside the capture and release workflows before any push, and `ci.yml` runs on human pushes. | Pushes made with `GITHUB_TOKEN` do not trigger other workflows, and GitHub Free private repositories are believed to lack branch protection (U23). |
| E19 | In the capture workflows, parse and curate run after the raw commit, as a second step and second `data:` commit. A parse failure never blocks or reverts the raw commit. | Capture and parse stay independent (E13). |
| E20 | One `ingest_run_id` per (raw file, parser version). `current` ties break on later `fetched_at_utc`, then higher `parser_version`. | Makes full rebuild and incremental parsing produce the same files and the same current views. |

## 3. Architecture

### 3.1 Layers and data flow

```
 sources ──► L2 capture ──► data/raw ──► L3 parse+curate ──► data/curated, data/sensitivity
                │  (no parsing)            (no fetching)              │
                ▼                                                     ▼
          capture_log, alerts                        L4 release ──► tag data-YYYY-Www, exports
                                                                      │
 L1 reference data (geometry, crosswalk, population, adjacency) ──────┤
                                                                      ▼
                                            L5 dashboard   and   L6 model (project/)
```

| Layer | Work package | Reads | Writes |
|---|---|---|---|
| L0 Foundation | WP0 | none | repo scaffold, CI, CLI |
| L1 Reference | WP1 | public files | `data/reference/` |
| L2 Capture | WP2 | live sources | `data/raw/`, `data/capture_log/`, issues |
| L3 Parse and curate | WP3 | `data/raw/`, `data/seed/`, `data/reference/` | `data/curated/`, `data/sensitivity/`, quality report |
| L4 Release | WP4 | `data/curated/` | `data/releases/`, exports, tags |
| L5 Dashboard | WP5 | `data/curated/`, `data/reference/` | static site |
| L6 Model | WP6 | `data/curated/`, `data/reference/` via `as_known_at` | `project/` outputs, `data/validation_gate.json` |
| Docs | WP7 | all | README, methods, limitations |

### 3.2 Repository layout

```
measles-pa/
  README.md  LICENSE  CLAUDE.md  Makefile  pyproject.toml  uv.lock  .gitignore
  .github/workflows/  ci.yml  capture-dashboard.yml  capture-light.yml  release.yml
  data/
    seed/            statewide_backfill.csv  county_t3_derived.csv  events.csv
    registry/        source_registry.yml
    raw/             <source_id>/<YYYY>/...        (immutable)
    capture_log/     <YYYY-MM>/<run_id>.jsonl     (append-only, one file per run)
    curated/         <table>/<YYYY-MM>/<ingest_run_id>.parquet   (append-only); quarantine/
    sensitivity/     seed/  <table>/...  quarantine/   (T3-derived, T3 events, secondary figures)
    quality/         quality_report.md
    reference/       geometry, crosswalk, population, adjacency, mobility
    releases/        data-YYYY-Www.json           (release manifests)
    RELEASE_NOTES.md
    exports/         <table>_current.csv          (rewritten at release; small)
    validation_gate.json     (recorded by WP6d)
  ingest/            cli.py  rawstore.py  capture/  parse/  curate/  release/  quality/  access.py
  project/           susceptibility/  model/  calibration/  validation/  dashboard/  notebooks/  outputs/ (gitignored until G4)
  docs/              HANDOFF.md  sources.md  dashboard.md  PROGRESS.md  BLOCKERS.md  schemas.md
                     probe_report.md  backfill_report.md  adr/
  tests/             mirrors ingest/ and project/; tests/fixtures/ (real captured samples)
```

`ingest/access.py` is the only module `project/` may use to read data (I8).

## 4. Data contracts

### 4.1 Conventions
- IDs: `source_id` from the registry (below). `county_fips` is a 5-digit string. `ingest_run_id` is the first 12 hex of sha256(`raw_sha256` + `parser_version`): one id per raw file and parser version, so a full rebuild and an incremental run produce the same ids and no duplicate files.
- Every curated and sensitivity row has the common columns of I3. Seed rows carry `seed_file` and `seed_row` instead of `raw_sha256`.
- Dates ISO 8601. Times UTC with a parallel `*_et` column where the source's "as of" is a local date.
- `date_precision` ∈ `exact`, `approx`, `range`, `to_confirm`. Rows with `to_confirm` never enter the main tables (they go to the quarantine of their store with flag `DATE_TO_CONFIRM`).
- Seed files are immutable once loaded. `data/seed/MANIFEST.json` and `data/sensitivity/seed/MANIFEST.json` record each file's sha256 and `seeded_utc`. For a seed row, `fetched_at_utc` is its file's `seeded_utc`, `raw_sha256` is the file's sha256 and `seed_row` is its `row_id`. Corrections are new rows in a new file, never edits.

### 4.2 Source registry (`data/registry/source_registry.yml`)
Fields: `source_id, name, url, tier, cadence, access_path, robots_checked_utc, terms_note, last_verified_utc, notes`. Initial source ids:
`doh_dashboard`, `doh_measles_page`, `doh_newsroom`, `doh_han_index`, `doh_han_pdf`, `doh_school_imm_county`, `doh_school_imm_school`, `census_popest_totals`, `census_popest_agesex`, `census_commuting`, `census_cartographic`, `cdc_measles_national`, `cdc_nwss_measles`, `local_hd_<name>` (added as located), `seed_statewide`, `seed_t3_county`, `seed_events`.

### 4.3 Tables

Common columns (all curated and sensitivity tables): `jurisdiction, disease, source_id, source_tier, as_of_date, fetched_at_utc, fetched_at_et, ingest_run_id, raw_sha256 or (seed_file, seed_row), parser_version, source_label, source_url, url_status`. The last three are nullable. `event` uses `event_date` in place of `as_of_date`.

| Table (location) | Table-specific columns | Notes |
|---|---|---|
| `case_state` (curated; T3-derived rows in sensitivity) | `cum_cases, counties_with_cases, hospitalizations, deaths, vaccinated_cases, new_since_count, new_since_date, new_7day, count_definition, date_precision, as_of_date_end, is_backfill, notes` | Statewide. |
| `case_county` (same split) | `county_fips, cum_cases, hospitalizations, deaths, community_transmission, new_7day, count_definition, date_precision, as_of_date_end, is_backfill, notes` | Zero reported is a value; absent is absent. |
| `immunization_county` | `school_year, county_fips, grade, enrolled, mmr_up_to_date_pct, med_exempt_pct, relig_exempt_pct, philos_exempt_pct, provisional_pct` | |
| `immunization_school` | `school_year, school_name, county_fips, grade, enrolled, mmr_pct, exempt_pcts, suppressed_flag` | `ND` becomes null with `suppressed_flag = true`, never 0. |
| `event` | `event_id, event_type, event_date, county_scope, title, detail` | `event_type` ∈ `health_alert, intervention, program, school_calendar, exposure, wastewater_detection`. `county_scope` is a `;`-separated list of county names (resolved through the crosswalk) or the tokens `state` or `affected_counties`. Replaces v1's three event tables. |
| `case_demographics` (provisional) | `dimension, category, cases, county_fips (nullable), count_definition` | `dimension` ∈ `age_band, vaccination_status, sex, hospitalized`. Final columns are set from the probe (WP2a); suppress or merge cells under 5. |
| `wastewater_sample` | `sample_id, site_id, county_fips, collection_date, target, result, concentration` | Optional (WP3). |
| `data_quality_flag` | `flag_id, raised_utc, severity, code, ref_raw_sha256, description, status` | Append-only; latest row per `flag_id` wins. |
| `quarantine` | `table, row_json, reason_code, ref` | Rows that failed validation or have `to_confirm` dates. One per store: `data/curated/quarantine/` and `data/sensitivity/quarantine/`. |
| `capture_log` (JSONL, one file per run) | `capture_id, source_id, url, started_utc, finished_utc, http_status, outcome, raw_path, sha256, content_hash, bytes, runner, error` | `outcome` ∈ `changed, unchanged, failed, blocked`. |
| Reference (`data/reference/`) | `geography_county(county_fips, name, land_area_km2, centroid_lat, centroid_lon)` plus GeoPackage and simplified GeoJSON; `county_adjacency(a_fips, b_fips, shared_boundary_m)`; `county_distance(a_fips, b_fips, km)`; `county_crosswalk(variant_normalized, county_fips)`; `population_county(vintage, county_fips, total, age_bands...)`; `mobility_edge(origin, dest, flow, period)` with `EXTERNAL` for out-of-state endpoints | Reference files also follow I1 and I3 (raw first, manifest). |

Natural keys (used by `current`): `case_state` (as_of_date, source_id, count_definition); `case_county` (the same plus county_fips); `immunization_county` (school_year, county_fips, grade); `immunization_school` (school_year, school_name, county_fips, grade); `event` (event_id); `wastewater_sample` (sample_id); `case_demographics` (as_of_date, dimension, category, county_fips); `population_county` (vintage, county_fips).

Data quality flag codes: `PARSE_SCHEMA_CHANGE, COUNTY_COUNT_DROP, CUM_DECREASE, COUNTY_SUM_MISMATCH, IMPLIED_COUNT_BREAK, STALE_SNAPSHOT, BLOCKED, DEFINITION_UNKNOWN, DATE_TO_CONFIRM, SIZE_BUDGET, HASH_MISMATCH, SOURCE_CONFLICT`.

Seed loading rules. The location of a seed file decides its store. Files under `data/seed/` load to `data/curated/` and must contain only tier T1 rows (the loader fails on any other tier). Files under `data/sensitivity/seed/` load to `data/sensitivity/` whatever their tier. `statewide_*.csv` load to `case_state`, `county_*.csv` to `case_county`, `events*.csv` to `event`. Rows with `date_precision = to_confirm` go to the quarantine of their store with flag `DATE_TO_CONFIRM`. Rows with `approx` or `range` load with their precision kept; models and default dashboard views use `exact` rows only. Sensitivity-store figures and events may be used only in labelled sensitivity runs until a T1 source is found (WP3c).

### 4.4 CLI (`uv run measles ...`)

| Command | Behaviour |
|---|---|
| `capture --source <id> \| --all-due [--dry-run]` | Fetch, save raw first, append `capture_log`, never parse. |
| `parse [--source <id>] [--since <date>]` | Raw to curated, offline, deterministic. |
| `seed load` | Seed CSVs to curated, sensitivity, quarantine. |
| `verify` | Recompute raw hashes; check every curated row's raw reference; check append-only rules. Exit non-zero on any mismatch. |
| `rebuild` | Rebuild curated into a temp dir and diff against committed curated (logical rows). |
| `quality` | Write `data/quality/quality_report.md` from data quality flags and checks. |
| `release --week YYYY-Www` | Section WP4. |
| `dashboard build [--public]` | Section WP5. `--public` omits all gated content. |

### 4.5 Views (DuckDB over Parquet, defined in `ingest/access.py`)
- `current(table)`: per natural key and `as_of_date`, the row with the greatest `fetched_at_utc`, then the highest `parser_version`.
- `ingest/access.py` also exposes `capture_status()` (latest capture outcome per source, read from `capture_log`) for the dashboard.
- `as_known_at(table, T)`: `current` computed over only rows with `fetched_at_utc <= T`. The only source for validation replay (E11).

## 5. Work packages

Each package lists purpose, depends on, tasks, outputs and acceptance tests. Tests are numbered `T<package>.<n>`. A package is done only when all its tests pass (CLAUDE.md session protocol).

### WP0 Foundation
Depends on: owner steps H1 to H3 and H8 (repository exists, Actions enabled, noreply identity, decisions confirmed).

Tasks:
1. Scaffold the repository layout (3.2), `pyproject.toml` (Python 3.12, uv, pinned), `Makefile` targets from CLAUDE.md, `.gitignore`, MIT licence, README skeleton with the D01 notice.
2. CLI skeleton (4.4) with stubbed commands.
3. `ci.yml`: ruff, type check, tests, path guard (bot commits may touch only `data/`), size budget and per-file size check (8.3), append-only guard for `data/raw`, `data/capture_log`, `data/curated`. The same guards also run inside the capture and release workflows before any push (E18).
4. `docs/PROGRESS.md`, `docs/BLOCKERS.md`, `docs/adr/`.
5. Hygiene scan: tracked files outside `data/raw/` contain no personal email addresses or secret patterns (the GitHub noreply address is allowed). Raw captures of agency pages may legitimately contain agency contact emails.
6. ADR recording the GitHub Free limits (no branch protection on private repositories, `GITHUB_TOKEN` pushes do not trigger workflows; U23) and how E18 compensates.
7. `.gitignore`: `project/outputs/`, `local/`.

Acceptance:
- T0.1 `make check` passes on a clean clone with no network after `uv sync`.
- T0.2 A fixture module in `project/` that imports `ingest.capture` or opens `data/raw` makes the boundary test fail.
- T0.3 A simulated bot commit touching `project/` is rejected by the path guard.
- T0.4 The size script applies the 8.3 thresholds to `.git` plus working tree on synthetic inputs, and flags a file over 50 MB (warn) or 95 MB (fail).
- T0.5 The hygiene scan fails on a planted personal email address or secret pattern, allows the noreply address, ignores `data/raw/`, and passes on the clean tree.
- T0.6 Workflow files parse and contain required keys (`concurrency`, minimal `permissions`, guard steps before push).

### WP1 Reference data
Depends on: WP0. Can run in parallel with WP2.

Tasks: download and save raw (I1) the Census cartographic boundary county file, Vintage 2025 county totals and age-sex files, and ACS 2016-2020 commuting flows; build PA geography, simplified GeoJSON, adjacency, centroid distances, area, the county crosswalk (all name variants seen in any source, normalised), population table, mobility edges. Resolve register items U5, U6, U7.

Acceptance:
- T1.1 Geometry has exactly 67 Pennsylvania counties, all valid, CRS recorded, simplified GeoJSON keeps all 67.
- T1.2 FIPS set in geometry equals FIPS set in population; all begin with `42`.
- T1.3 County populations sum to the statewide check value in S3.
- T1.4 Crosswalk maps every variant to exactly one FIPS, with no collisions after normalisation.
- T1.5 Adjacency is symmetric; distances symmetric and non-negative.
- T1.6 Commuting edges reference only PA FIPS or `EXTERNAL`; flows non-negative.
- T1.7 `make verify` passes for all downloaded reference files.

### WP2 Capture
Depends on: WP0. This package starts the clock on irreplaceable data; ship its minimum first.

Minimum viable capture (MVC): WP0, plus the raw store (2b), plus the dashboard capture workflow (2d), plus `capture_log` and issue alerts. Everything else in WP2 follows.

2a Probe (decides Gate G1). With Playwright, load the dashboard URL (S1), take a screenshot, list visible fields, and try to capture the report's JSON query responses. Decide the access path:
- Path A: JSON query responses captured (preferred).
- Path B: rendered page text or DOM extraction.
- Path C: scheduled screenshots only, with manual transcription by the owner (H5). Transcriptions are committed as `data/raw/doh_dashboard/<YYYY>/<timestamp>_<sha>.csv` (a human-entered raw artefact with columns matching the `case_county` layout, `manual = true`, and the sha256 of the screenshot it was read from) and parsed like any raw file. Each transcribed update counts toward G3.
Also record: volatile fields to strip for `content_hash`, observed update times, robots.txt and terms notes, whether GitHub-hosted runners can load it. Output `docs/probe_report.md`. Resolves U1, U2, U22. If blocked or challenged: stop (I7) and record in BLOCKERS.

2b Raw store (`ingest/rawstore.py`): `save()` writes file plus manifest (url, fetched_at_utc, http_status, sha256, content_hash, parser_hint), refuses to overwrite, applies E03, appends `capture_log` (E04).

2c Fetchers (HTTP only, polite per I7): DOH measles page, newsroom, HAN index and PDFs, school immunization files (county and school-level), CDC measles page, CDC NWSS (optional; resolves U8), local health department pages once located. Cadence per section 8.

2d Workflows: `capture-dashboard.yml` (browser, E05 schedule, concurrency and rebase retry E06, cached browser install, job under 5 minutes) and `capture-light.yml` (HTTP sources, daily). Permissions: contents write, issues write. Each workflow runs: capture, commit raw and `capture_log` (`data:`), parse and curate and write the quality report, run the guards, commit (`data:`), push with rebase retry. A parse failure never blocks or reverts the raw commit (E19). Bot commits touch only `data/`.

2e Alerts: failure or anomaly opens or updates one issue per failure type (labels `capture-failure`, `data-anomaly`) with run link, capture id and raw hash; duplicates comment on the open issue; issue closes only after a successful capture. Anomalies never block saving raw (save, then flag).

Acceptance:
- T2.1 `save()` writes the file and manifest; manifest sha256 matches; path follows E02.
- T2.2 Identical content after normalisation yields outcome `unchanged`, no new raw file, one `capture_log` line.
- T2.3 `save()` refuses to overwrite an existing path.
- T2.4 Rate limiter enforces at least 5 seconds between requests to the same host (fake clock).
- T2.5 A robots.txt disallow yields outcome `blocked` with no body request.
- T2.6 A 403, 429 or challenge page yields outcome `blocked`, an issue payload, no curated row and no retry. A 5xx or timeout yields `failed` after at most 2 retries with backoff.
- T2.7 One source failing does not stop the other sources in the same run.
- T2.8 Workflow YAML has the section 8.1 cron entries, a `concurrency` group with `cancel-in-progress: false`, and minimal permissions.
- T2.9 A concurrent push simulated against a local bare repository succeeds via rebase retry, and two simultaneous runs write different `capture_log` files.
- T2.10 (network, run once) The probe capture produces raw plus screenshot and `make verify` passes.
- T2.11 The append-only guard (CI and in-workflow) rejects any diff that deletes or edits existing files under `data/capture_log/` or `data/raw/`.

### WP3 Parse and curate
Depends on: WP1 (crosswalk), WP2 (raw files). Parsers for the dashboard depend on Gate G1.

Tasks:
3a Parsers (pure functions, raw to rows, `parser_version` recorded): school immunization county Excel (`xlrd` for `.xls`) and school-level HTML, Census files, commuting flows, DOH release and HAN pages (stats block), dashboard (per probe path), CDC page, NWSS (optional). Record sheet and field layouts in `docs/schemas.md` (U3, U4). Golden fixtures are real captured samples.
3b Seed loader (rules in 4.3).
3c Backfill: fetch (through WP2 raw store) HAN PDFs and DOH releases to resolve U14, U16, U17, find DOH releases for the `T3-derived` statewide rows, locate T1 corroboration for T3 events, find a `source_url` for every T1 event row with `url_status = url_to_find` and set it to `verified`, try the Wayback CDX technique (U11). Output `docs/backfill_report.md` with one outcome per item.
3d Quality engine: checks below, flags, `data/quality/quality_report.md` regenerated each run.
3e `verify`, `rebuild`, and the views of 4.5.

Acceptance:
- T3.1 Every parser has a golden-file test (fixture in, expected rows out).
- T3.2 `rebuild` with the committed parser versions yields `current` views identical (as logical rows) to the committed `current` views, and running it twice gives identical results.
- T3.3 Seed load: all seed files load; the loader rejects a non-T1 row placed in `data/seed/`; `to_confirm` rows are in the quarantine of their store with `DATE_TO_CONFIRM`; nothing from `data/sensitivity/seed/` appears under `data/curated/`.
- T3.4 Every `county_name` and county scope in the seeds resolves through the crosswalk.
- T3.5 Implied-count check: for every statewide row with `new_since_count` and `new_since_date`, the implied earlier cumulative (cumulative minus new) is computed and equals the SOURCES S1 values (460 on Aug 28, 497 on Aug 31, 624 on Sept 9, 903 on Sept 28). Within one store, a row on the implied date must agree, else flag `IMPLIED_COUNT_BREAK`. Comparisons across stores are reported in the quality report, not flagged.
- T3.6 Cumulative counts do not decrease within one `count_definition`; violations flagged `CUM_DECREASE`.
- T3.7 County-sum check: when a snapshot lists every county with cases (rows with cases equal `counties_with_cases`), the county sum equals the statewide count exactly; otherwise the sum is at most the statewide count. Across sources, a difference above 1 case plus 1 percent is flagged `COUNTY_SUM_MISMATCH`.
- T3.8 The quality report lists: the late-July to Aug 21 growth step, the 114 versus 134 July discrepancy, any `unknown` definitions, any non-monotonic series, any implied-count breaks, and the seed conflict between 792 (Sept 21) and 788 (903 minus 115 new in the week).
- T3.9 `as_known_at(T)` returns only rows with `fetched_at_utc <= T` and the latest vintage per key (synthetic revisions test).
- T3.10 Changing one byte of a raw file makes `verify` fail with `HASH_MISMATCH`.
- T3.11 (network, after G1) Parser sanity on the first parsed dashboard snapshot: counts cannot fall below the Oct 5 values (statewide at least 1,004, counties with cases at least 39, Lancaster at least 391, Mifflin at least 118, Chester at least 84).
- T3.12 `docs/backfill_report.md` records an outcome for each of U11, U14, U16, U17.
- T3.13 School county parse reproduces the Lancaster kindergarten MMR rate of about 87.6 percent and the Chester overall kindergarten rate of about 94.5 percent within rounding, or the difference exceeds 0.5 percentage points and is documented in an ADR (S2).
- T3.14 `ND` values become null with `suppressed_flag = true`; none become 0.
- T3.15 A parse that yields fewer counties than the previous snapshot sends its rows to quarantine and raises `COUNTY_COUNT_DROP`; the previous good `current` view is unchanged.

### WP4 Release
Depends on: WP3.

Tasks: `release --week YYYY-Www` builds the weekly rollup for the ISO week (Monday to Sunday, America/New_York): the last `as_known_at` state per source at week end, the list of expected captures (Monday, Wednesday, Friday) that are missing, new rows, flags raised, definition changes. Write `data/releases/data-YYYY-Www.json`, `data/RELEASE_NOTES.md`, `data/exports/*_current.csv`; run `verify`; tag `data-YYYY-Www`; build the dashboard (`dashboard build`, private mode) as a CI artifact in the same workflow. `release.yml` runs Monday at 13:30 UTC (E07).

Acceptance:
- T4.1 Week boundaries are correct across a DST change (fixture week).
- T4.2 A week with an uncovered capture day (8.1) still releases, lists each uncovered day, and contains no interpolated values.
- T4.3 Running `release` twice for the same week is idempotent.
- T4.4 A release fails closed (no tag) if `verify` fails.
- T4.5 CSV exports equal the Parquet current views.
- T4.6 Release manifests record input raw hashes and `data_commit_sha` (the last data commit before the week closed), so re-running yields the same manifest.

### WP5 Dashboard
Depends on: WP0, WP1 (D0, D1); WP3 (D2, D3); WP6 and Gate G4 (D4). Full specification, stages D0 to D5 and tests T5.1 to T5.9 are in DASHBOARD.md. The dashboard is built inside `release.yml` as an artifact (D09). Hard rules: reads only through `ingest/access.py`; no `T3-derived` in default build; gated panels absent from `--public` builds.

### WP6 Susceptibility and model
Depends on: WP1, WP3. 6a and 6b may run on fixtures before G3. 6c and 6d require Gate G3.

6a Susceptibility: per county, effective susceptible fraction = 1 minus (coverage × vaccine effectiveness), with uncertainty. Use school MMR coverage with exemption and suppression handling. Add an explicit under-covered subpopulation parameter (U19) with scenarios. School coverage is a December 2025 baseline; add post-outbreak vaccination as a separate dated adjustment from `event` rows, applying the accounting rule (the early infant dose does not count toward the routine series; an accelerated second dose does, S8). Default inputs are T1 event rows only; T3 events (such as the school opening date) enter only the sensitivity run until a T1 source is found (WP3c).

6b Simulator: stochastic county metapopulation SEIR (chain-binomial or tau-leaping, numba). Coupling terms compared, not assumed: commuting flow, geographic adjacency, long-range community link (S11). External introduction rate, school-calendar covariate, intervention effects from `event`. Seed from observed first-case dates. Hand-written first; compare with `epydemix` only if maintained (U18).

6c Calibration: ABC or a particle method on county cumulative counts, negative binomial observation model with explicit reporting delay, under-ascertainment and day-of-week terms (S1 weekday artifact). The default fit uses T1 data only; a separate labelled sensitivity fit may include `T3-derived`. Priors from S7 with literature confirmation (U12, U13). Before the first capture only the statewide T1 series exists, so the pre-capture period constrains statewide totals only; county-level fitting uses captured snapshots. Report posterior predictive checks, not point fits.

6d Validation: replay archived snapshots through `as_known_at(T)`: fit at T, forecast T plus 1 to 4 weeks, score against what was later reported. Weighted interval score or CRPS and 50, 80 and 90 percent interval coverage, per county and statewide, versus a persistence baseline. Writes `data/validation_gate.json`. Model outputs go to `project/outputs/` (gitignored, never committed) until Gate G4 passes.

6e Extensions (only after 6a to 6d are stable): age-structured version, wastewater covariate check, hospitalization sub-model.

Acceptance:
- T6.1 Susceptible fractions lie in [0,1]; ND and exemption handling is deterministic; the uncertainty draw is reproducible from a seed.
- T6.2 A sensitivity output of final outbreak size versus the under-covered subpopulation parameter is produced.
- T6.3 The post-outbreak vaccination adjustment excludes the early infant dose (unit test).
- T6.4 Population is conserved in every simulation.
- T6.5 Final size never exceeds the susceptible pool.
- T6.6 If effective R is below 1 in all counties, large outbreaks (over 10 percent of susceptibles) occur in under 5 percent of 200 seeds.
- T6.7 A fixed seed gives identical output.
- T6.8 Turning interventions off never lowers expected final size (mean over at least 200 seeds; the difference may not be below minus 1 percent of the mean).
- T6.9 Each coupling term reduces to no coupling when its strength is zero.
- T6.10 Calibration recovers known parameters from synthetic data generated by the simulator: across 20 synthetic datasets the true value lies inside the 90 percent interval for each parameter in at least 80 percent of runs.
- T6.11 Posterior predictive checks are written for every fit.
- T6.12 The default fit fails if any input row has tier `T3-derived`.
- T6.13 Validation replay raises an error if it reads any row with `fetched_at_utc` after T (inject a future row in the test).
- T6.14 Scoring functions reproduce hand-computed values on a small example, and the persistence baseline is computed on the same cutoffs.
- T6.15 The gate writer records `pass` only when the G4 criteria hold.
- T6.16 `project/outputs/` is gitignored, and CI fails if any file under it is tracked while `data/validation_gate.json` is not `pass`.

### WP7 Documentation and write-up
Depends on: all others, finalised last; README and notice from WP0.

Tasks: README (purpose, status, reproduction, limitations, monthly Actions minutes, measured repository growth), `docs/methods.md`, limitations section in plain language, `docs/sources.md` kept current with verified items flipped, data licences list, methods write-up.

Acceptance:
- T7.1 README contains the unofficial notice, "counts are a floor", and "forecasts withheld until validated".
- T7.2 Internal links in `docs/` resolve.
- T7.3 Every figure in the write-up cites a release tag and a run manifest (trace check).
- T7.4 `docs/sources.md` has no UNVERIFIED item that the work packages claim to have closed.

## 6. Gates

| Gate | Condition | Evidence | Unlocks |
|---|---|---|---|
| G0 | Repo exists, Actions enabled, CI green on a clean clone | T0.1 to T0.6 pass | everything |
| G1 | Dashboard access path decided (A, B or C) and runner reachability known | `docs/probe_report.md`, T2.10 | dashboard parser, county content in WP5 |
| G2 | Unattended capture proven: two consecutive full Monday, Wednesday, Friday cycles with no manual action, every capture day covered (8.1) or flagged | `capture_log`, quality report | G3 clock, and the public-flip clock (G5) |
| G3 | Modelling go: at least 10 distinct `as_of_date` values with county-level dashboard snapshots (E12) | `capture_log`, `case_county` | WP6 calibration and validation |
| G4 | Forecast publication: over at least 8 weekly forecast origins, pooled across counties and weeks, the 80 percent interval covers between 70 and 90 percent of held-out values, and pooled weighted interval score is lower than the persistence baseline at the 1-week and 2-week horizons | `data/validation_gate.json` = pass | forecast panels and watchlist map in public builds |
| G5 | Public flip, all required: four consecutive weeks clean (G2 sustained); licence review; secret scan and hygiene scan (scope as T0.5) over full history pass; the H6 decision, made before the first commit of the sensitivity seeds, re-confirmed; README notice present; scheduled-workflow behaviour for public repositories checked against current GitHub documentation (U21) | checklist in `docs/adr/` | repository public, Pages |

## 7. Execution order

1. WP0 (needs H1 to H3).
2. In parallel: WP2a probe, WP1 downloads. Then WP2b, 2d and 2e (the MVC) and switch the schedule on. This starts the irreplaceable-data clock; do it before any parser exists.
3. WP2c, then WP3 (3b seed load first, then parsers, backfill, quality, views). G1 gates the dashboard parser only.
4. WP4 after the first full week of captures. WP5 D0 and D1 can start after WP3b.
5. G2, then WP5 D2 and D3. WP6a and 6b on fixtures any time after WP1 and WP3b.
6. G3, then WP6c and 6d, then WP5 D4 and G4.
7. WP7 throughout; finalise last. G5 only when the owner chooses.

### 7.1 Kickoff prompt for the first Claude Code session
Paste this after placing the package files in the repository root (CLAUDE.md at the root, the other documents under `docs/` as listed in section 0) and completing H1 to H3 and H8:

> Read CLAUDE.md, then docs/HANDOFF.md sections 2 to 8. Work package WP0 first: scaffold the repository and make `make check` pass. Then WP2a (the dashboard probe) and the minimum viable capture, so scheduled capture starts as early as possible. Keep docs/PROGRESS.md current. Stop and list in docs/BLOCKERS.md anything that needs the owner. Do not begin modelling.

## 8. Operations runbook

### 8.1 Schedule

| What | Cron (UTC) | Notes |
|---|---|---|
| Dashboard capture | `0 18,20,22 * * 1,3,5` and `0 13 * * 2,4,6` | Three afternoon windows plus next-morning catch-up. Drop the next-morning window first if Actions minutes run short. Tune after two weeks from `capture_log`. |
| Light HTTP sources (DOH pages, HAN, newsroom, CDC, school and Census files by hash) | `30 14 * * *` | Unchanged content is logged only. |
| Weekly release | `30 13 * * 1` | Builds the prior ISO week (E07). |

A Monday, Wednesday or Friday is **covered** when at least one dashboard capture with outcome `changed` or `unchanged` is logged between 18:00 and 23:59 UTC that day. G2 and T4.2 use this definition. The next-morning window is catch-up only.

### 8.2 Failure handling

| Condition | Detection | Automatic response | Human action |
|---|---|---|---|
| Scheduled run dropped or late | no capture within cadence + 24 h | flag `STALE_SNAPSHOT`, issue | check Actions status |
| Blocked, challenged or disallowed | 403, 429, challenge page, robots | outcome `blocked`, stop, issue, no retry loop | decide; never evade (I7) |
| HTTP error or timeout | status or exception | 2 retries with backoff, then `failed`, issue | none unless repeated |
| Parser schema change | expected fields missing | raw saved, rows quarantined, `PARSE_SCHEMA_CHANGE`, issue | update parser, re-run `parse` on saved raw |
| County count drops | fewer counties than previous snapshot | quarantine, `COUNTY_COUNT_DROP`, previous good view kept | review |
| Push conflict | non-fast-forward | `pull --rebase`, up to 3 retries | none |
| Actions minutes low | usage report | skip next-morning window, issue | consider self-hosted runner |
| Repository size | CI size script | `SIZE_BUDGET`, issue proposing rotation | rotation only by owner decision (section 8.3) |
| Runner IP blocked | probe or capture failures | issue | self-hosted runner (H11) |

### 8.3 Storage rules (plain git, D05)
1. Prefer structured captures (JSON responses, extracted text). Screenshots are a fallback, downscaled WebP.
2. Commit large files (school Excel, Census, boundaries) only when `content_hash` changes.
3. Compress text captures larger than 256 KB (gzip or zstd).
4. Budget: warn 500 MB, fail 900 MB for `.git` plus working tree; warn at 50 MB and fail at 95 MB for any single file (GitHub rejects files over 100 MB). Expected growth about 100 to 500 MB per year; measure after four weeks and report in the README.
5. Rotation if needed, by explicit owner decision: move completed years of `data/raw` to a separate plain git archive repository, leaving a pointer file with the commit hash and per-file SHA-256 list.
6. Never rewrite history on `main` (I8, CLAUDE.md).

### 8.4 Alert content
Each issue states: failure type, source id, capture id, run link, raw hash if any, the last good `as_of_date`, and the next scheduled attempt.

## 9. Risks and fallbacks

| Risk | Impact | Fallback |
|---|---|---|
| Dashboard blocks automated access or GitHub runner IPs | no county data | self-hosted runner; path C screenshots with manual transcription; stop if disallowed |
| DOH changes dashboard layout | parser breaks | raw preserved; re-parse after fix (E13) |
| Count definitions unresolved | wrong comparisons | `count_definition = unknown`, flag, never merge across definitions |
| Public flip exposes history | accidental disclosure | I10, hygiene scan over full history at G5 |
| Actions minutes exhausted | missed captures | reduce next-morning window; self-hosted runner |
| Model weakly identified (no line list) | misleading forecasts | G4 gate; label outputs; report cases where the model does worse than persistence |
| News-derived figures wrong or unattributed | bad calibration | `T3-derived` isolation; default fit uses T1 only |

## 10. Definition of done
- Gates G0 to G3 passed and recorded; G4 either passed or recorded as not passed, in which case forecasts stay withheld and the limitations section says why; G5 decided by the owner.
- `make check`, `make verify` and `make rebuild` pass on a fresh clone with no network.
- Weekly releases tagged for every completed week since capture started, gaps listed.
- Dashboard builds for private and `--public` modes; public mode contains no gated content.
- Every number in any write-up traces to a release tag and a run manifest.
- Limitations are stated in plain language, including cases where the model does worse than persistence.

---

Appendices A (engineering review findings) and B (version 1 coverage trace) are kept in the owner's copy of the handoff package; they record review history only and contain no requirements.
