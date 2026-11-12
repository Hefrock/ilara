# ADR 0028: scoring rules that survive skipped updates and quiet counties

Status: **proposed** (drafted 2026-11-11 at the owner's request; not accepted, nothing in the
code changes until the owner decides each item).

## Context

The [methods review](../methods_review_2026-11.md) found four problems in how forecasts are scored
(ADR 0013), none of them in the model:

1. A target needs snapshots dated exactly seven days apart. The department skipped its update on
   2026-11-11, so several targets and one whole origin cannot be scored, and Gate G4's earliest
   date (2026-12-30) no longer holds.
2. G4's coverage band (80 percent intervals holding 70 to 90 percent of outcomes, pooled over 67
   counties) is exceeded by any sound forecast, because counties with no new cases are covered
   automatically.
3. The pooled mean score against persistence is decided by counties where nothing happens
   (persistence scores exactly zero) and by one or two large counties.
4. Outcomes are read as the latest revision, so past scores change when a count is revised.

## Proposed decision

Each item is separate; the owner may accept, change or reject any of them.

1. **Targets by what had been published.** The outcome for the week ending on day D is the
   increase in the cumulative count between what the dashboard showed on D minus 7 and on D, each
   read from a good dashboard capture (`capture_log.is_good`) fetched inside that day's cover
   window (ADR 0027). If the department published nothing new, the captured total is unchanged
   and the week's increase is what it is. If there is no good capture in the window, the target
   stays unscored.

   This is not forward-filling under I5: no count is carried to a date without evidence. The
   capture is the evidence that the published total on that day was unchanged, and it keeps its
   own fetch time and raw hash. Curated rows keep the department's own as-of date; only the
   scoring reads by capture day. The owner should confirm this reading of I5.

   Consequence: a skipped update gives a low week followed by a high one. The model has no
   holiday effect and will score worse in such weeks; persistence faces the same targets.

2. **Coverage where there is something to cover.** The G4 coverage band is computed over targets
   where the outcome, or the forecast's upper 80 percent bound, is at least 1. Coverage over all
   targets is still reported.

3. **A fairer comparison with persistence.** G4 compares the model and persistence on four
   groups, each scored on its own weekly total: Lancaster County; the other counties fitted on
   their own (10 or more cases at the origin); the remaining counties as one group; and the state.
   The model must have the lower mean score in at least three of the four at both the one-week and
   two-week horizons. The pooled per-county mean is still reported.

   Open: the number of groups and the three-of-four rule are choices. An alternative is one
   scaled score (each target's score divided by the persistence score plus one).

4. **Frozen outcomes.** Each outcome is read as known 14 days after its target day and recorded
   with that date; later revisions do not change a score. Open: the length of the lag.

5. **Applied to every origin.** The rules apply to all origins from 2026-10-28, with model version
   1 unchanged. They are set after one scored week has been seen (one origin, one horizon); that
   is recorded here so a reader can weigh it ([lesson 12](../lessons.md)).

## Consequences if accepted

- HANDOFF section 6 (Gate G4) and ADR 0013 are amended; `validate.py` and `run_validation.py`
  change; tests are added for a skipped update, for the coverage subset, for the groups and for
  the frozen outcome.
- All origins from 2026-10-28 stay scoreable, and the earliest G4 decision returns to 2026-12-30.
- `data/validation_gate.json` records which rules produced it.
