# ADR 0012: the 67-county calibration problem, and two ABC fixes

Status: accepted (owner, 2026-10-15: "starting on #1 makes sense now. Waiting on #2 when at G3
also seems prudent"; design choices by the agent).

## Context

ADR 0011 built and tested the calibration method on a three-county synthetic outbreak. The real
fit needs the full model: 67 counties, susceptibility uncertainty, seeding from the first known
cases, intervention effects and post-outbreak vaccination, with the seeding and intervention
parameters calibrated. Gate G3 (ten county snapshot dates, about 2026-10-28) still blocks real
county fits; validation and scoring (6d) wait for G3 as the owner decided.

## Decision

- `project/model/pa.py` assembles the problem from curated and reference data through
  `ingest.access` and the WP6 modules (I8):
  - counties, populations and coupling from `sensitivity.build`;
  - 200 seeded susceptible-fraction draws (6a, default under-covered scenario); simulation
    seed `s` uses draw `s mod 200`, so susceptibility uncertainty enters every fit;
  - seeding (`inputs.seeding`, default: the earliest county) and intervention multipliers
    (`inputs.intervention_mult`) rebuilt for each candidate's `lead_days` and `factor_<type>`;
  - run start = earliest known case minus the largest `lead_days` (42) minus 7 days.
- Calibrated: R0, `lead_days` (7 to 42), `factor_intervention` (0.25 to 1),
  `factor_health_alert` (0.5 to 1), plus the four observation parameters of ADR 0011.
- **Vaccination allocation (an assumption).** DOH reports doses statewide, not by county. Each
  dose period's immunity gained (6a `dose_adjustment`, `post_outbreak` default scenario) is
  spread evenly over its days and, on each day, over the counties with a known case by then in
  proportion to population. Doses on days before any county is known are not modelled. If
  county-level dose counts appear, they replace this.
- `curated_problem` uses `observations_from_curated`, so it refuses before G3 (`GateError`) and
  on T3-derived rows (`TierError`).
- `python -m project.model.pa` runs a dry run on synthetic data: the model at a fixed truth on
  ten Monday/Wednesday/Friday snapshots from 2026-10-05, using the first simulation seed whose
  statewide count over the window reaches 500 (an outbreak the size of the real one, not a
  fade-out; the real data are conditioned on a large outbreak too). Output and manifest go to
  `project/outputs/calibration_pa/` (gitignored).
- Two fixes to `calibrate.fit`, found by the first dry run:
  1. Every simulated fade-out reports nothing, so all fade-outs have the same distance. When
     more than half the particles were fade-outs the tolerance sat on that value for every
     generation and the posterior stayed at the prior. Now, when several previous distances
     equal the tolerance, a proposal must be strictly below it.
  2. Proposals outside the prior cube were counted against the acceptance budget though they
     cost no simulation, so with eight parameters the fit stopped after generation 0. The
     budget and the reported acceptance now count simulations only.

## Consequences

- Dry run (2026-10-15; 300 particles, seed 20261015, data seed 20261021): the tolerance fell
  3.49, 3.11, 2.50, 2.13, 1.91, 1.76 and stopped after six generations, when acceptance reached
  2.5 percent. It used 41,716 simulations in 13 minutes on one core. Every 90 percent interval
  covered the truth: R0 13.8 to 17.9 (truth 15; prior 9.9 to 18.1), `factor_health_alert` 0.71
  to 0.99 (0.9), `factor_intervention` 0.34 to 0.97 (0.8), `lead_days` 9.9 to 40.7 (21), `rho`
  0.23 to 0.94 (0.7), `report_delay` 1.6 to 9.2 (3), `weekend` 0.24 to 0.94 (0.6), `k` 4.7 to
  161 (20). Posterior predictive coverage was 100 percent, so the intervals are conservative.
- With ten snapshots over three weeks, only R0 and the health-alert factor narrow much. Seeding
  time, ascertainment and the reporting delay are weakly identified. Expect the same in the
  real fit at G3, unless more dated history is added (for example a weekly statewide series).
- T6.10 (three-county recovery) is unchanged after the fixes: R0 20/20, rho 20/20,
  report_delay 18, weekend 18, k 16 out of 20.
- Still to do at G3: run `curated_problem` on real data, then 6d validation and scoring.

## Addendum (2026-10-15): the real observation design

The first dry run gave the synthetic statewide series weekly for 60 days before the first
snapshot. The real fit has statewide counts on 16 dates from 2026-01-30 to 2026-10-02 (DOH
releases and one seed count), so the dry run now uses those dates (`statewide_dates`; counts
simulated). Result (data seed 20261018, 41,424 simulations, 12 minutes): every 90 percent
interval again covered the truth; R0 12.9 to 17.9, `factor_health_alert` 0.73 to 0.98,
`lead_days` 8.1 to 40.4, `rho` 0.23 to 0.93, `report_delay` 1.5 to 9.7. The longer statewide
history did not narrow seeding time, ascertainment or reporting delay. With counts only,
ascertainment trades off against susceptibility and R0, so more count history will not pin it;
informative priors from the literature or a line-list summary would. (One dataset per design,
so the two runs are not a like-for-like comparison of precision.)

Also: a missing county count in the curated store is now left out of the fit instead of being
read as zero (I5).
