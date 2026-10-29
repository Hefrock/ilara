# ADR 0022: seed every county with a known case; a calibrated lead for censored counties

Status: accepted (owner, 2026-10-29: "yes, go with option 1").

## Context

After ADR 0021 the real fit at origin 2026-10-28 forecast too few cases, and the fastest-growing
central counties were matched poorly. A diagnostic (posterior draws, fresh simulations, no
refit) showed why:

- Seeding mode `first` seeded only Lancaster; every other county had to be reached through the
  fixed commuting (0.05) and adjacency (0.02) links. Counties with dozens of reported cases were
  reached in few runs: Mifflin (198 cases on Oct 28) in 25 percent, Jefferson (87) in 6,
  Clearfield (49) in 7, Indiana (48) in 12, Centre (41) in 29, Clinton (41) in 10. The median
  statewide count on Oct 28 was 95, against 1,398 reported. The outbreak has several foci.
- With every county seeded at its first known date (mode `all`, already a sensitivity variant),
  every county with cases is reached in every run and the median rises to 446. Still low,
  because 35 of the 45 counties with cases are first known only from the first county snapshot
  (2026-10-05) and held 549 of its 1,004 cases: their outbreaks were under way, start unknown,
  but they were seeded only `lead_days` (7 to 42) before it.

## Decision

1. Seeding mode `all` is the default: every county with a known case is seeded `lead_days`
   before its first known date. `first` stays as a sensitivity variant.
2. A county first known only from the first snapshot (censored, `inputs.first_known`) is seeded
   `censored_lead_days` before that snapshot instead. It is one calibrated parameter shared by
   all censored counties, with a wide prior of 14 to 150 days. Their start dates are not known,
   so none is guessed (I5): the data choose one lead for the group.
3. The coupling strengths stay fixed for now; fitting the commuting strength is a later option.

## Consequences

- One more calibrated parameter (nine in all). The parameter-recovery test (T6.10) and the
  67-county dry run are rerun before the real refit.
- All censored counties share one lead: a county whose outbreak began much earlier or later than
  the others is still matched poorly. That is the next limitation to look at if scoring shows it.
- The start of the model run is unchanged (set by the earliest known case and the `lead_days`
  bound); the latest censored seeding (150 days before 2026-10-05) falls well after it.
