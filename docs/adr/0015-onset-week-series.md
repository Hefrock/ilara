# ADR 0015: cases by onset week from the Epidemic Curve tab

Status: accepted (owner, 2026-10-17, B18 conditions, ADR 0014); parser design by the agent.

## Context

The first captures that opened the Epidemic Curve tab (2026-10-17 16:09 UTC, data as of
2026-10-16; 2026-10-19 19:42 UTC, as of 2026-10-19) show "Measles Cases by Week (Epidemic
Curve)": one aggregate query, `PAmeasles2026_epicurve`, with `casedate` and `Onset Week`, and
52 weekly bars from 2026-01-05 to 2026-12-28 whose counts sum to the year-to-date total. The
case-level safeguard refused nothing. The republished report has no chart by report month any
more, so `report_month` ends with the 2026-10-09 capture.

## Decision

- Parser 1.5.0 stores the curve as `case_demographics` rows with dimension `onset_week`,
  category the Monday that starts the week (`YYYY-MM-DD`), statewide, calendar year.
- Bars for weeks that start after the as-of date are placeholders, not reported zeros (I5), and
  are not stored. The current week is stored as shown; it is incomplete by nature.
- The set must add up to the year-to-date total, else it is flagged
  `DEMOGRAPHIC_SUM_MISMATCH` and not stored, like the other breakdowns.
- Every capture keeps its own copy, so the store holds the revision history of recent weeks
  (between the two captures, the week of 2026-09-28 went from 87 to 93 and the week of
  2026-10-05 from 70 to 69).
- Kept out of the model and the dashboard (ADR 0014 condition 3): the dashboard displays only
  the dimensions it names, the model never reads `case_demographics`, and a test checks both.
- The "report month not found" flag is raised only when neither the report-month chart nor the
  onset curve is present.

## Consequences

- This is the only dated series by onset the project has. I6 is unchanged: we do not infer
  onset dates; these are DOH's published weekly counts.
- Whether and how the model uses it (an onset-based observation model with right truncation
  for recent weeks) is for the owner and agent to review, with a few weeks of revisions in hand
  to measure how much recent weeks move.
