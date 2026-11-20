# ADR 0029: plan for model version 2

Status: **proposed** (drafted 2026-11-20 at the owner's request: "yes, draft a plan for model
version 2"). Nothing in the model changes until the owner accepts this plan, and the decisions
listed at the end are the owner's.

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

## Decisions for the owner

- **D1.** Community group the same in every county, or fitted only where the data need it?
  Recommended: the same share everywhere, with coverage and mixing fitted. It infers nothing
  about where communities live.
- **D2.** Whether to fit cross-county community coupling (item 2) in version 2, or leave it for
  later. Recommended: include it; Lancaster's neighbours are where spread would show it.
- **D3.** Whether the existing U19 scenarios are retired once item 1 replaces them, or kept as a
  sensitivity check. Recommended: kept as a sensitivity check, unchanged.
- **D4.** Whether version 1 keeps running after version 2 is frozen. Recommended: yes, until G4
  is decided for version 2.
- **D5.** The freeze date. Recommended: 2026-12-02, or the first Wednesday after the
  synthetic checks pass if that is later.

## Consequences if accepted

- New parameters are recorded in `project/model/params.yml` and
  `project/susceptibility/params.yml` with status ASSUMPTION and their priors.
  `docs/methods.md` sections 2 to 4 are updated.
- The simulator, inputs and calibration change; tests are added for the community group
  (closed community, open community, no community equals version 1).
- G4 for version 2 cannot be decided before early February 2027. Version 1's G4 record stays as
  it is.
