# ADR 0014: the capture opens the Epidemic Curve tab

Status: accepted (owner, 2026-10-17, B18: "yes, open the Epidemic Curve tab with your
conditions").

## Context

ADR 0002 restricts tab clicks to the visible tabs; when it was written, "Epidemic Curve" was a
hidden page of the report (an epidemic curve by onset date). In the report DOH republished on
2026-10-13 (ADR 0009) it is in the visible tab bar, one of seven pages, and cases by report
month are no longer on the age tab. Captures from 2026-10-14 therefore lack report month, and a
capture day without it cannot be recovered.

## Decision

- `View("epi_curve", "Epidemic Curve")` joins `VIEWS` after the age tab. The allowlist still
  holds only visible tab names; hidden pages (the "Duplicate of" pages) stay closed.
- Conditions set with the owner:
  1. The case-level safeguard (`ingest/capture/caseguard.py`) applies to this tab as to every
     other: any response that could carry case or record identifiers is refused, never saved.
  2. Only the aggregate counts the page shows are stored.
  3. If the tab is by onset date, its counts are stored as their own labelled dimension and are
     kept out of the model and the public dashboard until the owner and agent have reviewed
     them. The parser matches report-month data only by its `reportdate` field, so an
     onset-date query is flagged (`PARSE_SCHEMA_CHANGE`), not stored, until a parser for it is
     written on purpose.
- Records from before this change never tried the new view, so the dead-report rule
  (`capture_log.problem`) ignores views listed in `LATER_CLICK_VIEWS` when it checks whether
  every click view failed.

## Consequences

- From the next capture, the raw files hold the tab's responses; the parser is extended once
  their shape is seen (a re-parse then recovers every capture since).
- I6 is unchanged: we do not infer onset dates. A DOH-published onset curve, if that is what
  the tab shows, is a source figure, labelled as such.
