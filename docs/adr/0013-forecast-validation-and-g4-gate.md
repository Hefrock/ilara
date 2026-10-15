# ADR 0013: forecast validation (6d) and the G4 gate writer, built before G3

Status: accepted (owner, 2026-10-15: "go with your order", which put 6d on synthetic data after
the dry run; design choices by the agent).

## Context

HANDOFF 6d: replay archived snapshots through `as_known_at(T)`, fit at T, forecast 1 to 4 weeks,
score against what was later reported (WIS or CRPS, 50/80/90 percent coverage, per county and
statewide, against persistence) and write `data/validation_gate.json`. G4 needs at least 8
weekly origins with pooled 80 percent coverage between 70 and 90 percent and pooled WIS below
persistence at 1 and 2 weeks. Real fits need G3 (ADR 0011). As with 6c, the code is built and
tested now so that the first origin can be the day G3 passes.

## Decision

- `project/model/validate.py` holds the scoring, the baseline, the gate and `replay`;
  `project/model/pa.py` provides the forecaster; `python -m project.model.run_validation` runs it.
- **Target:** cases newly reported in week h after origin T: the calendar-year cumulative count
  at the snapshot 7h days after T minus the one 7(h-1) days after. Counties with snapshots and
  the dashboard's statewide total. Both snapshots must exist; a missing one leaves the target
  unscored (I5). Outcomes use the latest revision of each snapshot.
- **Origins:** Wednesdays (a publishing day with no 2026 holiday before January), from
  2026-10-28. **Cutoff:** end of the origin day, Eastern time (`pa.cutoff`).
- **Scores:** WIS (Bracher et al. 2021) over the median and the 50, 80 and 90 percent central
  intervals of the forecast samples; coverage of each interval.
- **Baseline:** persistence on the same origins and targets. Median = the last observed weekly
  increase; intervals = that value plus the quantiles of past week-on-week changes in the same
  geography, mirrored to both signs, floored at zero; Poisson around the last value while fewer
  than three past changes exist (the first origins). This follows the forecast hubs' baseline.
- **Gate:** pooled over counties and weeks, as G4 states; statewide rows are scored and
  reported but do not decide. `write_gate` records `pass` only when every criterion holds
  (T6.15), and stores summary metrics and the run reference only, never forecasts (I10).
- **Leak guard (T6.13):** every read made with a cutoff (`calibrate`, `pa`, `inputs`,
  `estimate`) passes through `project/leak.py:check_known`, which raises `LeakError` if any row
  was fetched after the cutoff, so a reader that ignored the cutoff is caught, not trusted.
- **Forecasts:** a fresh ABC fit at each origin (ADR 0011, 0012); 200 posterior draws are
  simulated past T, reported through the observation model, and weekly counts drawn from the
  negative binomial.

## Consequences

- Earliest G4 decision: 8 Wednesday origins from 2026-10-28 is 2026-12-16, and its 2-week
  target is reported 2026-12-30. Forecasts stay withheld until then at the soonest (I11).
- A real validation run costs one fit per origin (about 13 minutes on one core with 300
  particles), so it runs in a session, not in CI.
- Open for the owner: whether origins before G3 may use the statewide release history and
  fewer county snapshots. That would bring G4 forward but changes E12's intent, so it is not
  done without a decision.
- Not yet run: an end-to-end replay on a synthetic outbreak (does the model beat persistence
  when the model is true?). It needs a synthetic curated store and several hours of fitting.
