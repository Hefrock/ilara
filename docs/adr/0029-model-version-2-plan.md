# ADR 0029: plan for model version 2

Status: **accepted** with the revisions in "Decisions" below (owner, 2026-11-24: "your
recommendations are reasonable. proceed"). Drafted 2026-11-20 at the owner's request. The
revisions come from a review of this plan made on 2026-11-20 (epidemiological and statistical
soundness), and they replace the first draft where the two differ.

## Context

Model version 1 (frozen 2026-10-31, [ADR 0026](0026-release-time-release-backup-model-version.md))
has been scored on three weekly origins (2026-10-28, 11-04 and 11-11) under the G4 rules as
amended by [ADR 0028](0028-scoring-rules-proposed.md) items 1 to 3. Outputs are private before
G4; the pattern, not the values, is what matters here:

- It beats persistence statewide and in the larger counties, most clearly at two weeks.
- It loses badly in Lancaster County: the median forecast is about zero new cases a week in
  every origin while 10 to 31 are reported.
- It over-forecasts the counties with few cases, taken together.
- Its 80 percent intervals hold 94 percent of outcomes even where cases occur, so they are too
  wide.

The [methods review](../methods_review_2026-11.md) (finding 4) explains the Lancaster result:
each county mixes evenly and its susceptible share is 6 to 9 percent, so a county's simulated
epidemic burns out once that share is used up. The outbreak is concentrated in under-vaccinated
communities, where most people are susceptible and mix mostly with each other; that cannot be
represented by an average.

The existing under-covered option (U19, `under_covered` in
`project/susceptibility/params.yml`, off by owner decision) does not fix this. It only lowers
each county's average immunity; the county still mixes evenly. A version 2 needs a group
structure inside counties, not a different average.

## Proposed changes

Each is separate and can be accepted or dropped on its own. Items 1 and 2 address the main
failure; 3 to 5 address the others.

1. **A community group inside each county (main change).** Each county is split into a general
   population and a community group: a share of the population, with its own susceptible
   fraction, that mixes mostly within itself.

   - Parameters, all fitted with wide priors, not assumed:
     - the community's share of the population;
     - the community's vaccination coverage;
     - the share of the community's contacts made within the community.
   - The simulator gains a second compartment set per county, about twice the run time, which
     is still seconds per simulation.
   - No location is inferred: no T1 source says where these communities live (U19). So
     either the share is the same in every county, or it is fitted only where the data
     demand it. That is an owner decision (D1 below).
   - Context, not a parameter: in Ohio's 2014 Amish outbreak, single-dose MMR coverage in
     affected households was 14 percent (Gastañaduy et al. 2016, abstract, already cited
     under U19).

2. **Coupling between communities across counties.** Counties are linked today by commuting
   (workers) and shared borders. Community groups in different counties may be more strongly
   linked to each other than to the general population. Proposed: one fitted strength for
   community-to-community links between adjacent counties. No T1 mobility data exist for this,
   so it stays a single fitted number, labelled an assumption.

3. **Check why small counties are over-forecast before changing anything.** Two candidate
   causes, neither verified:

   - every county with a case is seeded with its own introduction;
   - the 35 counties first seen on 2026-10-05 share one fitted start lead
     ([ADR 0022](0022-seed-every-county-censored-lead.md)).

   A diagnostic run (posterior draws, no refit) will show which drives the excess. The fix
   follows the evidence: for example, fewer seeded cases where only one case is known, or a
   start lead that varies with county size.

4. **Tighter fit.** The ABC fit stops at a loose match (methods review, finding 5).

   - Proposed: more particles and generations, and a stopping rule on the tolerance rather
     than a fixed number of generations.
   - Measured on synthetic data first, as in [ADR 0011](0011-calibration-abc-smc.md).

5. **Reporting effects kept out of the model unless the data force them in.** The 2026-11-11
   holiday showed up as a low week followed by a high one. A holiday effect is not proposed
   now, since one holiday is too little to fit. Thanksgiving week will show whether it is
   needed.

## How version 2 is built and judged

Built:

- Built and tested on synthetic data first: parameter recovery (as T6.10) with the community
  group switched on, then a 67-county dry run.
- A diagnostic hindcast on origins already seen (2026-10-28 to 2026-11-25), clearly labelled
  as diagnostic. It does not count towards G4: these origins were seen before the model was
  designed ([lesson 12](../lessons.md)).

Judged:

- Frozen as `MODEL_VERSION = "2"` before its first scored origin, with the freeze date
  recorded here.
- Scored only on origins after the freeze ([ADR 0026](0026-release-time-release-backup-model-version.md)).
- Version 1 keeps running beside it on the same origins, so the two are compared on equal
  terms.
- G4 counts version 2's own origins: eight from the freeze.
- The weekly check-in runs both versions and reports both.

Timeline, if accepted by 2026-11-24:

| Step | Target |
|---|---|
| Diagnostics (item 3) and design | 2026-11-24 to 11-26 |
| Simulator and calibration changes, synthetic tests | by 2026-12-01 |
| Diagnostic hindcast, owner review | 2026-12-02 |
| Freeze version 2; first scored origin | Wednesday 2026-12-02 |
| Eighth origin; earliest G4 decision for version 2 | origin 2027-01-20, decided once its two-week target is in (2027-02-03) |

## Decisions (accepted 2026-11-24)

- **D1. Where the community group is: guided by school coverage data.** A uniform share would
  give every county a self-sustaining pocket and worsen the small-county over-forecast. Each
  county's community size is instead a fitted scale times a county proxy, fixed now, before its
  relation to case counts is examined:

  > **Proxy:** the share of the county's kindergarten and grade 7 enrolment, in schools listed
  > in the DOH school-level immunization file for 2025-2026 (`immunization_school`, T1), that is
  > in schools reporting MMR coverage below 90 percent. Suppressed school rows are left out of
  > both numerator and denominator.

  Two rules, also fixed now:

  - **Small counties are shrunk toward the statewide value.** The proxy is computed as
    (low + 500 p) / (enrolled + 500), where p is the statewide share, so a county with few listed
    pupils is not ranked on a handful of schools.
  - **A county with no unsuppressed rows takes the statewide value.**

  Computed on 2026-11-24 before any comparison with cases: 66 of 67 counties have rows.
  Unshrunk, the values run from 0 to 0.58, with a median of 0.09; the two highest are counties
  with 65 and 298 listed pupils, which is why shrinkage is needed.

  The file omits many small private and one-room schools (U19), so the proxy is imperfect. It
  only orders counties and sets relative sizes. If it proves uninformative in the synthetic and
  diagnostic checks, the fallback is partial pooling: county sizes vary around a common value.

- **D2. Cross-county community coupling only if it can be estimated.** It is included only if
  the synthetic recovery test recovers it; otherwise it stays out of version 2.

- **D3.** The U19 scenarios are kept unchanged, as a sensitivity check.

- **D4.** Version 1 keeps running beside version 2 until G4 is decided for version 2.

- **D5.** Freeze on Wednesday 2026-12-02, or the first Wednesday after the synthetic checks pass
  if that is later.

**Revisions from the review, also accepted:**

- **Fewer parameters.** Community share and coverage enter through one combined quantity, the
  effective community size (the fitted scale above), with coverage held at the U19 `mid`
  scenario value. The share of the community's contacts made within it is a second fitted
  parameter. Any parameter the recovery test does not recover is fixed and varied as a
  sensitivity check instead of fitted.
- **A statistical comparator.** A simple county growth-rate model (negative binomial counts,
  with a growth rate estimated from recent weeks) is frozen on the same day as version 2 and
  scored the same way, to test whether the mechanism adds forecasting value.
- **Uncertainty in the reports.** Group comparisons in the weekly report carry a range from
  resampling origins. The gate rule itself is unchanged.

## Consequences

- New parameters are recorded in `project/model/params.yml` and
  `project/susceptibility/params.yml` with status ASSUMPTION and their priors.
  `docs/methods.md` sections 2 to 4 are updated.
- The simulator, inputs and calibration change; tests are added for the community group
  (closed community, open community, no community equals version 1).
- G4 for version 2 cannot be decided before early February 2027. Version 1's G4 record stays as
  it is.
