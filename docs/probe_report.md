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
| U1 | Data query responses capturable | Not yet. The report definition (`modelsAndExploration`) and the field list (`conceptualschema`) were captured, but no `querydata` responses, although the tiles rendered. The capture now records every Power BI response and why its body was or was not kept, so the next scheduled run shows the cause. | open |
| (data refresh) | When the data change | `LastRefreshTime` 2026-10-05T18:19:30 (UTC per Power BI convention, 2:19 p.m. EDT), matching "2 p.m." | VERIFIED |

## Safety finding: the published data model is case-level

The field list shows tables keyed by case (`PAmeasles2026_Public`: `CaseNo`, `County`, `agegrp`,
`hosp`, `fully_vaxed`, `Report Date`, ...) and by vaccination record
(`PAmeasles2026_Public_mmr`: `record_id`, `Vaccination Date`, `county`, `agegrp`). The visible
pages show aggregates, but any query response that returns rows at the level of `CaseNo` or
`record_id` would be case-level data, which I10 forbids committing. The capture must never
query hidden pages or build its own queries, and must refuse to save any response that carries
case-level keys. Only column names (not data) are in the committed raw files.

## Decision for G1 (pending owner answers, see BLOCKERS)

- Path B (rendered text) works today for page 1 headline figures and is what the scheduled
  capture records now.
- County data need the "Cases by County" page. Reaching it within one page load means clicking
  report tabs (in-app interaction, no new page navigation).
- Path A (query responses) is preferred for county parsing once the cause above is known.

G1 stays open until the county page access is agreed and one county snapshot is captured.

## Schedule note

"Updated at 2 p.m." ET is 18:00 UTC during daylight time and 19:00 UTC after Nov 1. The 18:00
UTC window may run before the update; 20:00 and 22:00 UTC cover both. Tune after two weeks
(E05).
