# Dashboard probe report (WP2a)

Probe run: `probe-dashboard` workflow run 37562037581, 2026-10-07 02:27 UTC, GitHub-hosted
runner. Raw artefacts (all under `data/raw/doh_dashboard/2026/`, capture id
`gh-37562037581-1:01:doh_dashboard`, `make verify` passes):

| Artefact | File | Notes |
|---|---|---|
| Rendered text (path B) | `20261007T022732Z_cd27423fdd9a.txt` | 742 bytes, page 1 only |
| JSON responses (path A) | `20261007T022732Z_f326ab94771c.json.gz` | 8 responses, no data queries (below) |
| HTML | `20261007T022732Z_fbd283509929.html.gz` | |
| Screenshot (path C) | `20261007T022732Z_6fc0d5dfa3e3.jpg` | page 1, legible |

## Findings

| Register | Question | Observation | Status |
|---|---|---|---|
| U22 | Can GitHub-hosted runners load the dashboard? | Yes. HTTP 200, report rendered, no challenge page. | VERIFIED |
| (I7) | robots.txt on `app.powerbigov.us` | Allowed the report URL for our user agent (the capture would otherwise have been `blocked`). | VERIFIED |
| U2 | Fields shown | Page 1 "Overview": title "2026 Overview: Pennsylvania Measles Cases"; "Last Updated: October 5, 2026"; "Updated at 2 p.m. on Monday, Wednesday, and Friday"; tiles Total cases 1,004; New cases (Last 7 days) 106; Fully Vaccinated <1%; Hospitalized 198; Under 18 Years Old 32%; Measles-associated Deaths 5. | VERIFIED |
| U2 | Report pages | Six visible tabs: Overview, Cases by Age and Time, Hospitalizations, Cases by County, Community Transmission, Measles Vaccine Administered. The report definition also lists hidden pages (Epidemic Curve and three "Duplicate of" pages). County counts are on "Cases by County", not on the landing page. | VERIFIED |
| U17 (going forward) | Count definition | A slicer on page 1 offers "Year to date" (selected by default), "January - March" and "April - Present". The default 1,004 is therefore a year-to-date (calendar-year) figure. | VERIFIED |
| U2 | History or export | No history or export control is visible on page 1. The model has a weekly series (`Week Ending`) used by "Cases by Age and Time". | PARTIAL |
| U1 | Data query responses capturable | Yes. The first probe missed them because Power BI serves `querydata` as `text/plain`, not JSON. The multi-view capture (run 37567917285, 2026-10-07 03:42 UTC) kept 44 `querydata` responses, refused none, and parses them. robots.txt allows the report URL; the capture only records responses to the report's own requests (no queries of ours). | VERIFIED |
| (data refresh) | When the data change | `LastRefreshTime` 2026-10-05T18:19:30 (UTC per Power BI convention, 2:19 p.m. EDT), matching "2 p.m." | VERIFIED |

## Safety finding: the published data model is case-level

The field list shows tables keyed by case (`PAmeasles2026_Public`: `CaseNo`, `County`, `agegrp`,
`hosp`, `fully_vaxed`, `Report Date`, ...) and by vaccination record
(`PAmeasles2026_Public_mmr`: `record_id`, `Vaccination Date`, `county`, `agegrp`). The visible
pages show aggregates, but any query response that returns rows at the level of `CaseNo` or
`record_id` would be case-level data, which I10 forbids committing. The capture must never
query hidden pages or build its own queries, and must refuse to save any response that carries
case-level keys. Only column names (not data) are in the committed raw files.

## Decision for G1: path A (2026-10-07)

- The capture clicks the visible tabs and slicer states within one page load (owner decision
  B15, ADR 0002) and keeps the report's `querydata` responses.
- `ingest/parse/doh_dashboard.py` parses them (golden test on the real capture,
  `tests/fixtures/doh_dashboard/`): statewide headline figures for "Year to date"
  (`calendar_year`) and "April - Present" (`since_april`), all 67 counties (zeros included,
  from the county map), and the community transmission list.
- First county snapshot: as of 2026-10-05, 1,004 cases in 39 counties; Lancaster 391, Mifflin
  118, Chester 84 (T3.11 sanity values met). January - March is 12, so 992 + 12 = 1,004.
- The rendered text (path B) and screenshots (path C) are still saved as fallbacks.

## Schedule note

"Updated at 2 p.m." ET is 18:00 UTC during daylight time and 19:00 UTC after Nov 1. The 18:00
UTC window may run before the update; 20:00 and 22:00 UTC cover both. Tune after two weeks
(E05).
