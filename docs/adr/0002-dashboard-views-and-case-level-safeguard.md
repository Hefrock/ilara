# ADR 0002: dashboard views and the case-level safeguard

Status: accepted (2026-10-07), owner decisions B15 and B16.

## Context

The probe (`docs/probe_report.md`) showed that county counts sit on the "Cases by County" tab,
not the landing page, and that a slicer switches between "Year to date", "January - March"
and "April - Present". The report's published data model is case-level: `PAmeasles2026_Public`
has one row per case (`CaseNo`) and `PAmeasles2026_Public_mmr` one row per vaccination record
(`record_id`). Every visual on the visible pages is an aggregate (counts, sums, minimums,
percentages); hidden pages exist ("Epidemic Curve" by onset date, three duplicates).

## Decision

1. One navigation per capture (I7). Within it the capture clicks, in a fixed order
   (`ingest/capture/browser.py`, `VIEWS`): the three slicer states on Overview, then back to
   "Year to date", then each other visible tab. Tab clicks are restricted to an allowlist of
   visible tab names, so hidden pages are never opened. The capture never builds or replays
   its own queries.
2. Response bodies are kept only from the report's data API host. Static Power BI resources
   (visual code, themes) are listed in `seen` but not stored: they change with Power BI
   releases and carry no outbreak data.
3. Safeguard (`ingest/capture/caseguard.py`): a response is refused, never written to disk,
   when identifier values could be in it, meaning:
   - a data query selects or groups by `CaseNo` or `record_id` outside an aggregation, or
   - a data query has no parseable body, or
   - a result descriptor names a bare identifier column.

   `Count(CaseNo)` is an aggregate and is allowed. Metadata that only lists column names (the
   field list, the report definition) is allowed, because it holds no case data. Each refusal
   is recorded in the capture's `refused` list and its log line, and raises a `data-anomaly`
   issue (a partial capture).
4. Screenshots are kept for the Overview and Cases by County views only, and only alongside
   a substantive change.

## Consequences

- Each capture makes roughly nine in-app view changes, each triggering a few report queries
  to the Power BI service, three times a week plus catch-up windows.
- If DOH renames a tab, that view fails, the rest of the capture is saved, and an anomaly
  issue names the failed view.
- The safeguard cannot detect quasi-identifying combinations (for example a visual grouped
  by date, county and age band with small cells). None of the visible visuals do this today;
  the parse step applies the HANDOFF rule to suppress or merge cells under 5.
