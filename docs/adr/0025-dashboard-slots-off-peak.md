# ADR 0025: dashboard capture slots earlier and off the hour

Status: accepted (owner, 2026-10-31: "yes, prepare option 1").

## Context

Gate G2 counts an update day only when a scheduled run captures it between 18:00 and 23:59 UTC.
Since the slots were last set (ADR 0010: 19:30, 21:30 and 23:00 UTC on Monday, Wednesday and
Friday, 13:00 UTC catch-up), the scheduled runs on the seven update days from 2026-10-16 to
2026-10-30 started at:

| Update day | Scheduled runs started (UTC) |
|---|---|
| Fri Oct 16 | 22:10, Sat 01:12 |
| Mon Oct 19 | 23:01, Tue 01:39 |
| Wed Oct 21 | 22:37, Thu 01:23 |
| Fri Oct 23 | 22:32, Sat 01:27 |
| Mon Oct 26 | 23:16 (cancelled at the browser install, ADR 0024), Tue 01:56 |
| Wed Oct 28 | 23:26, Thu 02:15 |
| Fri Oct 30 | 23:07, Sat 02:12 |

The 19:30 slot never started. The others started one to three hours late, and the late ones fell
after midnight UTC, outside the day they were meant to cover. The next-morning catch-up started
three to six hours late. Every slot was on the hour or half hour.

## Decision

Four same-day slots at 19:13, 20:07, 20:53 and 21:47 UTC on Monday, Wednesday and Friday, and the
catch-up at 13:17 UTC on Tuesday, Thursday and Saturday. Earlier slots leave room for a late
start to land before midnight; odd minutes avoid the busiest times. A test keeps the slots off
minutes 0 and 30 and inside the cover window.

## Consequences

- On an update day up to four scheduled dashboard loads instead of three, each one navigation
  (I7).
- A slot that starts before DOH's update covers the day with the previous figures; later slots
  and the backup routine (ADR 0006, 0010), which checks freshness, catch the update.
- Whether this helps is measured, not assumed: the G2 tracker shows each day's coverage. If
  scheduled runs still miss days, the next option is for G2 to count runs started by the backup
  routine (the owner's decision; it changes what the gate counts).
