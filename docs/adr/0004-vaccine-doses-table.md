# ADR 0004: `vaccine_doses` table for MMR doses given by DOH staff

Status: accepted (2026-10-08).

## Context

WP6a needs post-outbreak vaccination as a dated adjustment (HANDOFF WP6, S8). The dashboard's
"Measles Vaccine Administered" page shows "Total MMR Vaccine Doses Administered by DOH Staff in
2026" and a bar chart of doses by month. The report's own queries return those monthly counts
(no dose number, no county, no age). HANDOFF 4.3 has no table for them.

## Decision

- Add a curated table `vaccine_doses` (`ingest/curate/schema.py`): `period_start`,
  `period_end`, `period_complete`, `doses`, `administered_by` (`doh_staff`), `geography`
  (`state`), plus the common provenance columns. Natural key: `as_of_date`, `source_id`,
  `administered_by`, `geography`, `period_start`. Each snapshot adds a full set of months, so
  late entries show up as revisions (September was 2,866 on Oct 5 and 2,877 on Oct 7).
- The month containing `as_of_date` is partial and marked so. Months after it are empty in the
  report and are not stored (not zeros, I5).
- The dashboard parser becomes 1.1.0 and re-parses every dashboard capture (E20).
- The school and release parsers become 1.0.1: their rows were labelled "DOH measles
  dashboard" by a runner bug, now fixed.
- `measles rebuild` compares quarantine rows for the newest parser version of each raw file,
  since a rebuild runs only the current parsers.

## Consequences

- These are doses given by DOH staff only, statewide. They are a floor on post-outbreak
  vaccination, not a total, and cannot be split into first, second and early infant doses.
  WP6a must treat the split as an explicit scenario parameter (the accounting rule, S8).
