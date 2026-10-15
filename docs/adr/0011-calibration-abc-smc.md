# ADR 0011: calibration by ABC-SMC, built before Gate G3 on synthetic data

Status: accepted (owner, 2026-10-15: "then start calibration"; method chosen by the agent).

## Context

HANDOFF 6c asks for ABC or a particle method on county cumulative counts, with a negative
binomial observation model, reporting delay, under-ascertainment and day-of-week terms, and
posterior predictive checks. HANDOFF WP6 says 6c needs Gate G3 (ten county snapshot dates, E12);
on 2026-10-15 there were four. The owner asked to start calibration now.

A tempered SMC sampler with pseudo-marginal likelihoods (one simulator run per evaluation) was
built first and rejected: at fixed parameters the log-likelihood varied from about -2950 to -160
across simulator runs, because the outbreak's random timing and early fade-outs dominate. Fits
collapsed onto lucky runs (R0 interval 16.75 to 17.1 around a true 15.1). A particle filter over
time would fix this but costs tens of minutes per fit.

## Decision

- Building and testing 6c on synthetic data before G3 is allowed. Fitting real county data is
  not: `observations_from_curated` raises `GateError` with fewer than ten county snapshot dates,
  and `TierError` on any `T3-derived` row (T6.12).
- Method: ABC population Monte Carlo (Beaumont et al. 2009) in the unit cube of uniform or
  log-uniform priors. Each candidate simulates a full dataset: the stochastic epidemic, then
  reports with probability `rho`, a gamma delay from infection to report (mean 11.5 days to rash
  plus `report_delay`, sd 3 days), weekend reporting scaled by `weekend`, and negative binomial
  counts with size `k` on the increase between consecutive snapshots of each geography (first
  snapshot as baseline). Distance: RMS difference of Anscombe-transformed increments plus the
  difference in log roughness of those increments; the second term stops the distance favouring
  low-noise simulations, which biased `k` upward in trials.
- Statewide totals before the first county snapshot enter as one more geography, as HANDOFF 6c
  describes for the pre-capture period.
- Every fit writes its posterior, posterior predictive checks (T6.11) and a run manifest (I9) to
  `project/outputs/` (gitignored until G4).
- T6.10 runs 20 synthetic datasets (parameters drawn from the priors) in parallel and needs each
  parameter's 90 percent interval to cover the truth in at least 16. It takes minutes, so it is
  marked `slow`: `make calibration-check` and its own CI step, outside `make check`.

## Consequences

- T6.10 result (2026-10-15): 90 percent intervals covered the truth in 20 of 20 datasets for R0
  and `rho`, 18 for `report_delay` and `weekend`, 16 for `k`. `k` is at the threshold and is the
  parameter to watch if the observation model changes.
- ABC with a tolerance gives intervals somewhat wider than the exact posterior, so coverage
  errs high. In trials the R0 interval was about a quarter to a third of the prior range; the
  reporting delay is barely identified from snapshots alone (it trades off against seeding time).
- When G3 passes, the real fit needs: the 67-county simulator inputs (WP6b), seeding and
  intervention parameters added to the priors, and the curated observations. Validation (6d)
  follows.
