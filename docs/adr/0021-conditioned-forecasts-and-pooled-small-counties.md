# ADR 0021: forecasts continue the accepted trajectories; small counties are fitted as one group

Status: accepted (owner, 2026-10-29: "yes, do both forecast fixes").

## Context

The first converged real fit (origin 2026-10-28, after ADR 0020) gave a statewide forecast whose
median was 0 new cases a week, against about 85 observed, with a 90 percent upper bound near
3,000. Two causes:

1. **Forecasts re-simulated the epidemic.** For each posterior draw, `forecast_samples` ran a
   fresh stochastic simulation with a new seed. The simulator is stochastic, and ABC accepted a
   parameter set together with the particular realisation that matched the data; a fresh
   realisation at the same parameters can fade out or take off at another time. 56 percent of
   the fresh runs had no cases in the first forecast week.
2. **Every county weighed the same in the distance.** About 40 counties with few or no cases
   matched trivially and outweighed the counties driving the outbreak: two of the fastest-growing
   had 0 and 22 percent of their counts inside the 90 percent predictive intervals, while the
   overall coverage (92 percent) looked fine.

## Decision

1. **Conditioned forecasts.** The fit keeps each particle's simulation seed (`Fit.seeds`).
   A forecast resamples particles and continues each one's own accepted trajectory (same
   parameters, same seed, the model run extended past the origin), then draws weekly reported
   counts with negative binomial noise. A fit without seeds can only make unconditioned
   forecasts, which must be asked for (`conditioned=False`). Posterior predictive checks keep
   fresh simulations, so they still test the model rather than the accepted realisations.
2. **Small counties pooled.** Counties whose latest count at the origin is below 10
   (`pa.POOL_BELOW`) are fitted as one "rest" geography: the sum of their counts on the snapshot
   days they all report (a missing count is a gap, I5). Pooling happens before superseded
   snapshots are dropped (ADR 0020), so a revision inside the group removes that day only if the
   group's sum falls. Counties at or above the threshold, and the statewide series, are fitted
   as before.
3. **Forecasts for every county.** Forecasts are made for all 67 counties and the state from the
   same trajectories, pooled or not, so validation (ADR 0013) scores the same targets as before.
4. **Synthetic check before the real refit.** The dry run pools the synthetic data the same way,
   forecasts four weeks past its last snapshot both ways, and scores them against what the
   synthetic truth went on to report (`forecast_check` in the manifest).

## Consequences

- Forecast uncertainty now reflects parameter uncertainty and reporting noise along epidemics
  that matched the data, not the spread of every epidemic the parameters allow.
- The threshold of 10 is a choice, not fitted; changing it changes which counties are fitted
  alone. It is set before any forecast is scored (first scoring: data for 2026-11-04), so it is
  not tuned to scores.
- Conditioning on accepted trajectories can make forecasts overconfident if the accepted set is
  small or the tolerance loose. The validation gate (ADR 0013) measures exactly that.
