# ADR 0020: superseded county snapshots, fit guards, and the weekly vaccine chart

Status: accepted (owner, 2026-10-28: "yes, run the fit then the vaccine fix").

## Context

1. The first real fit at origin 2026-10-28 (Gate G3 passed with the tenth county snapshot
   date) returned the prior. Two counties have a count that DOH later revised down: Forest
   (42053) showed 2 cases on 2026-10-14 and 16, then 0 from 2026-10-19 (the cases were
   reassigned); Mifflin (42087) showed 194 on 2026-10-19, then 193. Each gives one negative
   increase between snapshots, the distance takes a square root of it, so every distance was
   NaN, no generation was accepted, and the fit ended without an error. The synthetic dry runs
   never had a downward revision.
2. From the capture of 2026-10-28 the "Measles Vaccine Administered" chart reads a new table,
   `MMR_Weekly_Dashboard_File` (`SHC_MMR_Doses` by month). Parser 1.7.0 did not find it.

## Decision

1. **A county count that a later snapshot of the same county is lower than is superseded**:
   the later, lower figure is DOH's own revision of it. Superseded snapshots are left out of the
   fit as gaps; no count is changed (I5). They are listed in the fit's manifest
   (`superseded_snapshots`). On 2026-10-28 that is three snapshots: Forest on Oct 14 and 16,
   Mifflin on Oct 19. The curated store is unchanged; this is the fit's reading of it.
2. **Guards.** A problem whose observed counts still decrease is refused when it is built; a
   distance that is not finite stops the fit; a fit that accepts no generation raises instead of
   returning the prior.
3. **Vaccine chart.** Parser 1.8.0 reads doses from either chart. The new table gives the same
   measure: every month from January to September equals the old chart as of 2026-10-26, and
   October rose from 1,703 to 1,948. Stored as before (`administered_by` `doh_staff`). The
   re-parse on merge stores the 2026-10-28 doses.

## Consequences

- The first real fit's results are in the owner summary, not here (outputs stay private
  before Gate G4).
- If DOH revises down a county's latest count, the earlier snapshots above it drop out until a
  later count matches or exceeds them; a county whose counts fall repeatedly loses information,
  which the manifest list makes visible.
