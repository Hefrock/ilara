# ADR 0006: backup trigger for dashboard captures

Status: accepted by the owner (2026-10-08).

## Context

The dashboard keeps no public history, so a Monday, Wednesday or Friday update that is not
captured that afternoon is lost (HANDOFF 8.1). GitHub's scheduler has proved unreliable for
this repository: on 2026-10-07 the 14:30 UTC capture-light run started at 20:04 and only one of
the three dashboard windows (18:00, 20:00, 22:00 UTC) ran, at 22:24; on 2026-10-08 neither the
13:00 catch-up nor the 14:30 capture-light run had started by 16:50 UTC. Scheduled runs on
GitHub can be delayed or dropped under load.

## Decision

- A Claude Routine on the owner's account ("Dashboard capture backup (Mon/Wed/Fri)") fires at
  18:40 and 22:40 UTC on Monday, Wednesday and Friday.
- Each firing checks the day's capture-dashboard runs. The day counts as covered only if a run
  finished successfully at or after 18:00 UTC and its committed capture log shows outcome
  `changed` or `unchanged` for `doh_dashboard` (a workflow can succeed while the capture was
  blocked or failed).
- If the day is not covered and no run is queued or in progress, it starts capture-dashboard
  on main with `workflow_dispatch`, once per firing. It never touches other workflows.
- If a capture outcome is `blocked`, it stops and tells the owner (I7): no retry.
- The GitHub schedule stays as it is (8.1); the routine only fills gaps.

## Consequences

- At most two extra dashboard loads on an update day, each one navigation (I7).
- G2 asks for capture "with no manual action". A routine-dispatched run is automated, not
  manual, but its runs show the `workflow_dispatch` event; the capture log records every run,
  so G2 evidence stays checkable.
- The 18:40 firing assumes the 2 p.m. ET update (18:00 UTC in daylight time). After the switch
  to standard time on 2026-11-01 the update lands at 19:00 UTC, so the 18:40 firing may capture
  the previous data; the 22:40 firing still covers the day. Revisit the time in the E05 review.
- capture-light (daily HTTP sources) has no backup: its sources keep their pages, so a late or
  missed run loses nothing irreplaceable.
