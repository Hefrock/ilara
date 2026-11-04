# ADR 0023: plan for the end of the outbreak

Status: accepted in outline (owner, 2026-10-29: capture until the Department of Health declares
the outbreak over plus a margin; light captures continue after that). Item 6 added (owner,
2026-11-04: "yes, add it to ADR 0023"). Items marked open are decided when the time comes.

## Context

The dashboard keeps no public history (ADR 0006), so a capture or modelling step that is skipped
at the end cannot be done later. The outbreak may end before Gate G5, so the plan cannot wait for
it. The archive is also meant for teaching ([lessons](../lessons.md)), which needs a clean final
state.

## Decision

1. **When dashboard capture stops.** The browser capture of the dashboard runs on its schedule
   until the Department of Health declares the outbreak over, then for a further margin of eight
   weeks for late revisions (counts have been revised weeks after first publication, ADR 0020).
   The declaration counts only as a captured source: a DOH page or release in `data/raw/`, recorded
   as an event. No end date is inferred from falling counts (I5). A standard measles end-of-outbreak
   criterion is cited here only once verified against a source. For the start, CDC defines a
   measles outbreak as 3 or more related cases (CDC measles data page, captured 2026-10-30,
   `raw_sha256` 007f7e614e78); no archived DOH release formally declares one.
2. **Light captures continue.** After the dashboard capture stops, the daily HTTP captures (DOH
   measles page and newsroom, CDC pages) continue for a further period, so that a resurgence, a new
   dashboard or a late revision is still recorded. Open: the length of that period.
3. **Final release.** A final weekly release is tagged when dashboard capture stops, with a closing
   note in `docs/` listing the known gaps: days not captured, mixed or partial captures, open
   quality flags, counties whose start dates are censored, and the parser and model versions in use.
4. **Final modelling.** While capture runs, forecasts continue weekly and Gate G4 is decided on its
   own schedule (ADR 0013). At the end:
   - a final hindcast of every model version on the same forecast origins, each using only what
     was known at its origin, so versions are compared fairly;
   - a retrospective of final county counts against the susceptibility estimates and the fitted
     parameters.
   Both stay private unless Gate G4 has passed; publishing them is the owner's decision.
5. **Winding down.** When capture stops: the dashboard says capture has ended and shows the last
   capture date; the scheduled dashboard workflow is turned off in code; the owner removes the
   backup routines (they belong to the owner's account). Open: whether the static dashboard stays
   online and for how long.

6. **A data request to DOH after the end.** The dashboard launched on 2026-07-14 (DOH release
   of that date, captured 2026-10-07; event ev-007) and was updated Monday, Wednesday and Friday,
   but our first capture was 2026-10-05: about 36 updates were never archived, and the Internet
   Archive cannot hold them because the dashboard renders in the browser. This gap blocks two
   things already planned: replacing the shared start date for the 35 counties first seen on
   2026-10-05 (ADR 0022), and the full-outbreak retrospective in item 4. Once DOH declares the
   outbreak over, the owner decides whether to send one request, asking for aggregate counts only
   (no case-level data, I10), in this order:
   1. final case counts by county and week of report, from the first case to the end;
   2. final case counts by week of onset, statewide or by county (the reporting delay behind
      [lesson 8](../lessons.md));
   3. the dashboard figures as published on each update date from 2026-07-14 to 2026-10-02.

   Nothing is sent during the outbreak. Contacting DOH is the owner's decision (CLAUDE.md). What
   comes back is stored as received, as its own source in `data/raw/` with the request and reply,
   dated when it was received. It is never merged into the captured series as if it had been
   captured at the time, and a file with different case definitions is labelled, not adjusted.

## Open decisions

- Length of the light-capture period after dashboard capture stops (item 2).
- What happens if the department stops updating without declaring the outbreak over. Proposed: the
  owner decides after four weeks without new figures.
- Whether the static dashboard stays online after capture ends (item 5).
- Whether and where the final release is archived with a DOI (Gate G5 checklist, ADR 0017).
- Whether to send the data request in item 6, and through which channel, once the outbreak is over.

## Consequences

- Nothing changes now; this records the plan so the end is handled deliberately.
- The final hindcast needs every model version to stay runnable: model versions are recorded in
  each run manifest, and old versions are run from their git commit.
