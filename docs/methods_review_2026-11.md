# Methods review, November 2026

A review of [methods.md](methods.md) against the code, the model inputs and the data, made on
2026-11-11 after the first scored forecast week. It lists what does not hold up, most serious
first, and what does. Forecast values and scores are private before Gate G4 and are not given
here; fit diagnostics are given where they explain a finding. Proposed scoring rules are in
[ADR 0028](adr/0028-scoring-rules-proposed.md), which is a proposal awaiting the owner.

## Findings

### 1. Scoring needs a snapshot dated exactly on each Wednesday

A forecast week is scored only when snapshots dated exactly seven days apart both exist
(`validate.weekly_increase`). On Wednesday 2026-11-11, a state holiday, two good captures (one
scheduled) found the dashboard unchanged since its 2026-11-09 refresh, so no snapshot is dated
2026-11-11. With the code as it stands:

- the 2026-10-28 origin cannot be scored at two weeks;
- the 2026-11-04 origin cannot be scored at one or two weeks;
- the 2026-11-11 origin cannot be scored at all, because the baseline needs the week ending on
  the origin.

Gate G4 needs eight scored origins, so its earliest date of 2026-12-30 no longer holds, and
further holiday Wednesdays may add gaps. This is a gap in the scoring design, not in the data:
the captures show what the department had published by that day.

### 2. The coverage test in Gate G4 cannot be passed as written

G4 asks that 80 percent intervals hold 70 to 90 percent of outcomes, pooled over all 67 counties.
Most counties report no new case in a week, and any interval that includes zero holds those
outcomes. Pooled coverage in the one scored week was 94 percent, mostly from such counties. A
well-calibrated model would still exceed 90 percent and fail.

### 3. The comparison with persistence is dominated by quiet counties and one large county

Where a county reports nothing week after week, persistence scores exactly zero and no forecast
with any uncertainty can score lower. The pooled mean of an unscaled score is also driven by the
few counties with many cases. The statewide forecast is scored but does not enter the gate.

### 4. Susceptibility is nearly uniform, so the fitted R0 is a growth rate

County susceptible fractions (200 draws) average 6.0 to 9.0 percent across the 67 counties, and
each county mixes evenly. At the low end of the R0 prior (9.9) no county can sustain spread; at
the high end (18.1) all 67 can. The fit places the state just above the threshold. The outbreak
is concentrated in under-vaccinated communities, which this structure cannot represent; the
under-covered subpopulation scenarios (U19) exist but are off by owner decision. The fitted R0
should not be read as an estimate of the basic reproduction number of measles here.

### 5. The fit stops at a loose match

At the 2026-11-04 origin the final ABC tolerance was 1.92 on a distance where counting noise alone
gives about 0.5, acceptance fell to 2 percent and the fit stopped after seven of eight
generations. A loose match gives wide posteriors and wide forecast intervals, consistent with
finding 2.

### 6. Scores are not frozen

Outcomes are read as the latest revision (`pa.observed_series`). If the department revises a
count, re-running validation changes the scores of past origins.

### 7. methods.md was out of date

It said it covered parts settled by 2026-10-15 and that checks were on synthetic data only; it
described seeding from the earliest county; it did not mention the backup routine or the cover
window; and it gave the start of the series without the dashboard's launch date. Corrected with
this review.

### 8. Smaller points

- The fit reads data fetched by midnight ET on the origin day, but a capture covers the day until
  06:00 UTC, an hour later in winter. A day captured only in that hour would be missing from its
  own origin's fit.
- Commuting and adjacency strengths are fixed, not fitted, and introductions from other states
  are set to zero.
- The pre-flight's count of scoreable origins starts at the origin passed to it, which misleads.

## What holds up

- Provenance on every row, gaps kept as gaps, and the leak guard on every cutoff read work as
  described.
- Forecasts continue the accepted trajectories (ADR 0021).
- The weighted interval score and the persistence baseline are implemented correctly.
- Every score records the model version that made it (ADR 0026).

## Recommended order

1. Scoring rules for findings 1, 2, 3 and 6, applied to every origin from 2026-10-28
   ([ADR 0028](adr/0028-scoring-rules-proposed.md), proposed). These do not change the model, so
   model version 1 stays frozen.
2. After three or four weeks scored under those rules, decide on a model version 2 for findings 4
   and 5.
