# ADR 0027: a capture day is covered until 06:00 UTC the next morning

Status: accepted (owner, 2026-11-03: "Allow a later window, so a run that starts by about 06:00
UTC the next morning counts"; applied from 2026-11-02 only, not to past weeks).

## Context

HANDOFF 8.1 counted a Monday, Wednesday or Friday as covered only by a good dashboard capture
between 18:00 and 23:59 UTC that day, and Gate G2 needs every such day covered by a scheduled
run. GitHub starts scheduled runs late. After the slots moved earlier (ADR 0025), Monday
2026-11-02's four scheduled runs (19:13, 20:07, 20:53 and 21:47 UTC) all ran and succeeded, but
started 5 to 6 hours late, at 01:32, 02:13, 02:42 and 03:04 UTC on Tuesday. The day was captured,
and by scheduled runs, yet G2 counted it as covered by a dispatched run only.

The midnight cut-off has no data reason. The Department of Health updates the dashboard only on
Monday, Wednesday and Friday afternoons (about 13:00 to 14:20 ET), so a capture made before 06:00
UTC (01:00 or 02:00 ET) the next morning still shows that day's update.

## Decision

1. A capture day is covered by a good dashboard capture finishing from 18:00 UTC that day up to,
   but not including, 06:00 UTC the next day (`schedule.cover_window`). G2, the quality report,
   the dashboard's capture-day list and the weekly release manifest (T4.2) all use it.
2. The 13:17 UTC next-morning slot stays catch-up only. A capture after 06:00 UTC and before
   18:00 UTC the next day is listed as catch-up and does not cover the day.
3. The wider window applies from Monday 2026-11-02 (`schedule.COVER_WIDE_FROM`). Earlier days keep
   the midnight cut-off. Applied to past weeks, the rule would have passed G2 at once (weeks of
   Oct 19 and Oct 26). The owner chose to have G2 earned under the rule as it now stands.

## Consequences

- G2: the week of Nov 2 can count. The earliest pass is the week of Nov 9, once Friday Nov 13's
  window closes (06:00 UTC on Saturday Nov 14).
- A day stays `pending` until 06:00 UTC the next day, so a missed day is reported six hours later
  than before. The backup routine's checks (ADR 0006) are unchanged.
- If scheduled runs start more than about 10 hours late, they miss this window too. Then the
  remaining option is to count the backup routine's automatic runs, which is the owner's decision.
