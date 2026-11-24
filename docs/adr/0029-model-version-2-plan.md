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

   **Result (2026-11-24).** 120 posterior draws from the 2026-11-18 fit, fresh simulations, no
   refit. Medians of simulated weekly new reported cases over the three weeks to the origin, for
   the 43 counties under 10 cases other than Lancaster, against what was reported:

   | | 15 counties first seen 2026-10-05 | 28 others |
   |---|---|---|
   | Reported | 2, 2, 0 | 2, 4, 6 |
   | Version 1 (5 exposed seeded per county) | 8.6, 7.4, 6.5 | 9.3, 9.2, 9.1 |
   | 1 exposed seeded in these counties | 3.7, 3.8, 3.2 | 2.8, 2.8, 2.9 |
   | Censored counties seeded with the short lead | 14.3, 12.7, 10.5 | 9.0, 9.7, 9.2 |

   The seed size drives the excess; the shared censored lead does not. **Rule for version 2,
   fixed now:** each county is seeded with as many exposed people as the cases known on its
   first known date, at least 1 and at most 5 (version 1 seeds 5 everywhere). This uses only
   what was known on that date.

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

## Recovery rule (fixed 2026-11-24, before the recovery runs)

The two new parameters, `community_scale` and `community_within`, are fitted in version 2 only
if the synthetic recovery test passes for each. The test uses three 67-county synthetic datasets
made from version 2, on the real observation design (ten snapshot dates, statewide release
dates), with these truths and the version 1 dry-run values for all other parameters:

| Dataset | `community_scale` | `community_within` |
|---|---|---|
| A | 0.005 | 0.80 |
| B | 0.02 | 0.65 |
| C | 0.08 | 0.90 |

A parameter passes when, in all three datasets, both hold:

- the 90 percent posterior interval contains the truth;
- the interval is narrower than 0.6 of the prior's width on the prior's own scale (log for
  `community_scale`), so the data and not the prior decide it.

A parameter that fails is fixed at its prior's centre on that scale and varied as a
sensitivity check (ADR 0029 revisions). Cross-county community coupling (D2) is not attempted
unless both pass.

## Recovery result (2026-11-24)

Three 67-county synthetic fits, 300 particles, eight generations, as set out above. Width is
the 90 percent interval as a share of the prior's width on its own scale.

| Dataset | `community_scale` truth, 90% interval, width | `community_within` truth, 90% interval, width |
|---|---|---|
| A | 0.005, 0.0021 to 0.0158, 0.36 | 0.80, 0.52 to 0.93, 0.93 |
| B | 0.02, 0.0045 to 0.0366, 0.37 | 0.65, 0.52 to 0.93, 0.93 |
| C | 0.08, 0.0262 to 0.1451, 0.30 | 0.90, 0.53 to 0.92, 0.87 |

- `community_scale` **passes** in all three: fitted.
- `community_within` **fails** (its posterior is almost the prior): fixed at 0.725, the centre of
  its prior, and varied from 0.5 to 0.95 as a sensitivity check.
- Cross-county community coupling (D2) is therefore **not attempted** in version 2.

Version 2 thus adds one fitted parameter to version 1.

## Diagnostic hindcast result (2026-11-24): version 2 not ready

Version 2 was refitted at origins 2026-10-28, 11-04 and 11-11 as a diagnostic that does not
count towards G4. Outputs stay private before G4 (I10), so only the pattern is recorded:

- In Lancaster and in the counties with few cases, version 2 scores worse than version 1, and
  both lose to persistence there. Lancaster's median forecast is still about zero.
- In the larger counties and statewide, version 2 is close to version 1.
- 80 percent coverage on targets with a case improves and falls inside the 70 to 90 percent band.

A version 2 fit at 2026-11-18 shows why. The fitted community scale is near the bottom of its
prior, so each community is a tiny share of its county, and Lancaster's simulated outbreak
peaks early in the year and dies out. A larger community would sustain Lancaster, but under the
shrunken proxy every county has a community and seeds go into it, so a larger community also
starts outbreaks in small counties that the data reject. Two design choices made here defeat
the mechanism:

1. shrinkage gives every county a community;
2. seeds go into the community.

**Version 2 is not frozen on 2026-12-02.** Proposed next step, for the owner's decision:

- one more round with these two choices changed, fixed before running: seed into the general
  population; a community only where the county's proxy exceeds the statewide value;
- the recovery test and the hindcast again;
- if version 2 still does not beat version 1 on the hindcast, version 2 is paused and version 1
  stays the scored model.

## Round 2 (owner chose option A, 2026-11-24; fixed before any run)

Version 2 has never been frozen or scored, so it is redefined in place; the round 1 definition
is kept in git history. Two changes, and nothing else:

1. **Seeds go into the general population.** Each county's seeded exposures are placed wholly
   in its general patch (round 1: wholly in the community). Vaccination stays split in
   proportion to susceptibles.
2. **A community only above the statewide value.** A county's community share is
   `min(scale * proxy, 0.5)` where its shrunken proxy exceeds the statewide share `p`, and zero
   otherwise. The proxy itself (D1, shrinkage included) is unchanged; a county with no rows
   takes `p` and so has no community.

`community_within` stays fixed at 0.725; the seed-size rule (item 3) and the priors are
unchanged.

**Recovery test, round 2.** As in the recovery rule above, except that the three datasets keep
`community_scale` at 0.005, 0.02 and 0.08 and all use `community_within` = 0.725, since it is no
longer fitted. `community_scale` must again pass in all three (truth inside the 90 percent
interval, width below 0.6 of the prior's log width). If it fails, version 2 is paused.

**Decision rule on the diagnostic hindcast** (origins 2026-10-28, 11-04 and 11-11, the same as
round 1; diagnostic, not counted towards G4). Version 2 is frozen on the next Wednesday only if
all three hold; otherwise it is paused and version 1 stays the scored model:

- lower mean WIS than version 1 in Lancaster at both horizons 1 and 2;
- in each other group (larger counties, remaining counties, state), mean WIS at most 10
  percent above version 1's at both horizons;
- 80 percent coverage on targets with a case inside 70 to 90 percent.

Results are recorded here as a pattern only (outputs stay private before G4, I10).

## Consequences

- New parameters are recorded in `project/model/params.yml` and
  `project/susceptibility/params.yml` with status ASSUMPTION and their priors.
  `docs/methods.md` sections 2 to 4 are updated.
- The simulator, inputs and calibration change; tests are added for the community group
  (closed community, open community, no community equals version 1).
- G4 for version 2 cannot be decided before early February 2027. Version 1's G4 record stays as
  it is.
