# ADR 0018: county map table v3, hospitalizations by age group, and mixed loads

Status: accepted (owner, 2026-10-26: "yes, write the parser fix").

## Context

From the capture of 2026-10-23 (data as of 2026-10-23), the DOH report changed two queries:

- The "Cases by County" table reads a new table, `PAmeasles2026_map_Publicv3` (the community
  transmission map still reads v2). It now lists all 67 counties, with explicit zeros.
- The Hospitalizations tab has no "X of Y" cards any more. It shows one table
  (`PAmeasles2026_Public_hosp`): hospitalized cases and all cases by age group (0-4, 5-9,
  10-17, 18-24, 25-49, 50+; the age tab's groups end 50-64, 65+).

Parser 1.6.0 found neither and stored no county or hospitalization rows for the Oct 23
captures (issue 41). The raw files hold everything (I1).

The capture of 2026-10-26 19:41 UTC (DOH refresh 18:20 UTC) was a mixed load: the overview,
age and onset charts showed the 2026-10-16 snapshot (1,260 cases, "October 16, 2026"), the
county table summed to 1,360, and the hospitalizations table to 1,317 (the 2026-10-21 total).

## Decision

- Parser 1.7.0 reads the county table, map and "counties with cases" card from any
  `PAmeasles2026_map_Public*` version. Same checks as before (T3.15; the county table must
  match the year-to-date total to be `calendar_year`).
- Hospitalizations by age group are stored in `case_demographics` as `cases_hosp_age_group`
  and `hospitalized_age_group`, in the tab's own groups (never merged with the age tab's
  groups). Stored only if every group is present, each hospitalized count is within its
  group, all cases add up to the year-to-date total and hospitalized cases to the
  hospitalized card; else flagged `DEMOGRAPHIC_SUM_MISMATCH`. The old bands
  (`age_band`, `hospitalized_age_band`) end with the 2026-10-21 captures. The dashboard shows
  whichever the latest snapshot has.
- A mixed load needs no new rule: each chart is checked against the overview total of the
  same capture. On 2026-10-26 the county table is labelled `unknown` (`DEFINITION_UNKNOWN`,
  kept out of fits and G3) and the hospitalizations are not stored. The overview rows carry
  the date the report states (2026-10-16), duplicating that day's values.

## Consequences

- The re-parse workflow recovers the Oct 23 county snapshot (8 of 10 for G3) and its
  hospitalizations on merge.
- The `unknown` county rows of 2026-10-26 sit under as-of 2026-10-16, the date the report
  stated, though they are not that day's counts. Nothing reads `unknown` county rows. A later
  capture with a consistent load stores the day properly.
