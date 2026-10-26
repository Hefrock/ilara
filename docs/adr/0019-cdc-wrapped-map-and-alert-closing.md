# ADR 0019: CDC map file wrapped with lastUpdated; flag issues close on the newest capture

Status: accepted (owner, 2026-10-26: "yes, close #41 and do both fixes").

## Context

1. From the capture of 2026-10-23, CDC's jurisdiction map file (`cdc_measles_cases_map`) is
   an object, `{"lastUpdated": "October 22, 2026", "data": [rows]}`, instead of a bare list
   of rows. The rows are unchanged. Parser 1.0.0 raised `PARSE_SCHEMA_CHANGE` (issue 40).
2. ADR 0016 closes a flag alert issue when no open flag with that code remains for the
   source. Some flags stay open by design: they describe captures that really lacked data
   (dead captures on 2026-10-07, 13 and 14; captures before the Epidemic Curve tab was
   opened). So a dashboard `PARSE_SCHEMA_CHANGE` issue could never close (issue 41, closed by
   hand on 2026-10-26).

## Decision

1. CDC parser 1.1.0 reads both shapes. The row is still dated from the CDC cases page whose
   totals match the map (I6). `lastUpdated` goes into the notes only: CDC's "updated" and
   "data as of" dates have differed by a day before (page of 2026-10-07: updated October 2,
   data as of October 1). On 2026-10-23 the page (as of October 22) matches the map: 4,570
   cases in 47 jurisdictions, Pennsylvania 1,327.
2. A flag alert issue closes when the source's newest capture (every raw file saved at its
   newest fetch time) carries no open flag with that code, checked in each capture run of
   that source. Old flags stay open in the quality report; they no longer hold an issue open.
   This amends ADR 0016, decision 5.

## Consequences

- On merge, the re-parse workflow stores the 2026-10-23 CDC row and resolves its flag;
  issue 40 closes at the next capture run that includes the CDC map.
- A flag issue on a source that is no longer captured never closes by itself; none exists.
