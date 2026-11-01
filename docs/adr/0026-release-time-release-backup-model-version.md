# ADR 0026: release off the half hour, a backup check for releases, and a frozen model version

Status: accepted (owner, 2026-10-31: "yes, do all three").

## Context

Only captures are time-critical: a dashboard update that is not captured is lost, but a weekly
release or a forecast can be made later from the archive, using only what was known at the time
(`as_known_at`). Still:

- The weekly release, scheduled for Monday 13:30 UTC (E07), was tagged 6 to 8 hours late every
  week: W41 at 21:49, W42 at 19:25, W43 at 19:29 UTC. Late, but never missed.
- Forecasts can be replayed at any past origin, which makes it easy to change the model after
  seeing scores and present the result as a forecast.

## Decision

1. **Release time.** The release runs at 13:23 UTC on Mondays (E07 updated with the owner's
   approval), off the half hour like the capture slots (ADR 0025). The week it releases is the
   ISO week that just closed, so its content does not depend on when the run starts.
2. **Release backup.** The Monday 18:20 ET backup routine (ADR 0006, 0010) also checks that the
   tag for the week that just closed (`data-YYYY-Www`) exists. If it does not and no release run
   is queued or in progress, it starts the release once.
3. **Model version.** `pa.MODEL_VERSION` names the model forecasts are scored with: "1" is the
   model after ADR 0020 to 0022. It is recorded in every real fit's manifest and in every
   validation score row. From the 2026-11-04 scoring on, any change to the model, its handling of
   inputs or its priors is a new version, scored only on origins after it is introduced. A new
   version may be replayed on earlier origins for comparison, but those scores are labelled as
   replays and never replace the scores the earlier version earned.
4. **Weekly check-in.** On Thursdays, after Wednesday's capture, the agent fits at the new origin
   and scores the earlier origins whose first forecast week has been reported, then reports to the
   owner. Outputs stay under `project/outputs/` (gitignored, private before Gate G4).

## Consequences

- A late or dropped release is noticed and redone the same day.
- Scores always say which model made them, so Gate G4 is judged on forecasts made in advance.
- Bumping the model version is a deliberate act, recorded in an ADR with the reason.
