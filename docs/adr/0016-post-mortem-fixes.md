# ADR 0016: fixes from the 2026-10-13 to 10-21 post-mortem

Status: accepted (owner, 2026-10-22: "yes, go ahead with all five").

## Context

The week after DOH republished its dashboard (ADR 0009, 0014, 0015) showed five weaknesses:
problems that were logged but alerted nobody, a county check that held back a genuine DOH
revision, quality flags that stayed open after their cause was fixed, false staleness flags for
one-time sources, and a red rebuild check on `main` each time a parser change merged while
captures ran. No data was lost: raw was saved first every time (I1).

## Decision

1. **Re-parse workflow** (`reparse.yml`). On a push to `main` that touches `ingest/parse/**`
   or `ingest/curate/**`, re-run `seed load`, `parse` and `quality`, commit only under `data/`,
   run the capture guards plus `measles rebuild`, and push with the rebase retry. It shares the
   `capture-dashboard` concurrency group, so it never runs alongside a dashboard capture.
2. **T3.15 narrowed.** A county parse is quarantined (`COUNTY_COUNT_DROP`) when, against the
   previous snapshot of the same source, it has fewer county rows or a lower county sum: a
   broken load. A single county revised down while the total holds (2026-10-19: Forest 2 to 0)
   is stored and flagged `CUM_DECREASE` by the quality engine (T3.6). A load that no longer
   matches the statewide total is also labelled `unknown` by the parser and kept out of fits.
   Parser 1.6.0 re-parses everything; the 2026-10-19 county snapshot is released.
3. **Parser flags close when settled.** An open parser flag is resolved (a new row, I2) when its
   raw file is now read by a newer parser version that raises no flag with the same code and
   description for that file. `DASHBOARD_LINK_CHANGED` resolves once the registry points at the
   new link. Identical flags from several captures are listed once in the report. Flags that
   still hold (captures of the deleted report, captures from before the Epidemic Curve tab was
   opened) stay open.
4. **One-time sources** (registry `cadence: once`) are not checked for staleness.
5. **Alert on trust-breaking flags.** `PARSE_SCHEMA_CHANGE`, `COUNTY_COUNT_DROP`,
   `COUNTY_SUM_MISMATCH`, `DEMOGRAPHIC_SUM_MISMATCH` and `DEFINITION_UNKNOWN` raised in a run
   open one `data-anomaly` issue per source and code (HANDOFF section 8.4 already called for an
   issue on a parser schema change; it had not been built). The issue closes when no open flag
   with that code remains, not when the next capture succeeds.

## Consequences

- G3 count rises to 7 county snapshot dates (Oct 19 released); with Oct 23, 26 and 28 it passes
  on 2026-10-28.
- The quality report and the dashboard trust section show only flags that still hold.
- The county check no longer catches a partial load that keeps every county row and the county
  sum; the parser's sum check against the statewide total covers that case.
- Re-parse commits by the bot, like capture commits, do not trigger CI (`GITHUB_TOKEN`); the
  workflow runs `measles rebuild` itself before pushing.
