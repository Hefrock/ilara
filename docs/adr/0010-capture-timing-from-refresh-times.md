# ADR 0010: capture timing from the report's refresh times

Status: accepted by the owner (2026-10-15: "do all three timing changes").

## Context

The Power BI responses we capture carry the report's own refresh metadata (`lastRefreshTime`,
`LastRefreshTime`). Observed refreshes: Mon Oct 5 18:19 UTC, Wed Oct 7 17:00, Fri Oct 9 17:02,
Wed Oct 14 17:26; none on Mon Oct 12 (a state holiday is a likely reason, unconfirmed). DOH
therefore publishes about 13:00 to 14:20 ET, by hand: the report's scheduled daily refresh
(13:20 UTC) did not move the data, and from Oct 10 no scheduled refresh is listed.

The dashboard crons ran at 18:00, 20:00 and 22:00 UTC and the backup routine (ADR 0006) at
18:40 and 22:40 UTC. When daylight saving ends on Nov 1, 13:00 to 14:20 ET becomes 18:00 to
19:20 UTC, so the first scheduled capture and the first backup check would usually run before
the update, and an early capture still marks the day covered (HANDOFF 8.1) while holding the
previous figures.

## Decision

1. Dashboard crons: `30 19,21 * * 1,3,5` and `0 23 * * 1,3,5` (plus the next-morning catch-up),
   all after the update in EDT and EST and inside the 18:00 to 23:59 UTC cover window.
2. Backup routine in Eastern time: 15:40 and 18:20 ET Monday, Wednesday, Friday, so it follows
   the clock change and its second check still ends before 23:59 UTC in winter. Two routines,
   since one cron line cannot hold both minutes (`trig_01Pcp2d2L94w2hHoNsdhH9ba` at 15:40,
   `trig_01XMuJrj9ttPnhEk8G3bafAq` at 18:20), both firing into the agent session of ADR 0006.
3. Parser 1.3.0 stores the refresh time with each dashboard snapshot (`case_state`
   `source_refreshed_utc`). The dashboard status line and the quality report show it. The
   backup routine starts one more capture when the newest snapshot was not refreshed that day
   (ET), at most once per firing, which catches updates that land after an early capture.

The cover rule in HANDOFF 8.1 is unchanged.

## Consequences

- Earlier captures no longer predate the update, so the cover rule and the data agree more
  often; a day with no DOH update (a holiday) still shows as covered with older figures, and the
  stale banner says DOH had not published (ADR 0009).
- One more column in `case_state`; re-parsing all dashboard raw files fills it for every
  snapshot (E20). Rows from other sources leave it null.
