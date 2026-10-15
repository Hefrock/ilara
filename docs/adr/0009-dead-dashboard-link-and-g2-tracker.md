# ADR 0009: dead dashboard link, good captures, G2 tracker and stale banners

Status: accepted (agent decision; owner asked for the G2 tracker and stale banner on
2026-10-15).

## Context

From 2026-10-13 19:48 UTC every dashboard capture reached a Power BI placeholder: the data API
answered HTTP 401 `KeyFoundInDeletedResourceKeyCacheException`, the page said "This content isn't
available", and every report tab click timed out. DOH had republished the report under a new
publish-to-web key; the DOH measles page links it from its capture of 2026-10-14 18:48 UTC
(same tenant, key 24efe031...). This is a moved link, not a block or a challenge (I7).

The browser capture logged these as `changed` or `unchanged`, with the view errors in `error`.
So the capture-day rule (HANDOFF 8.1) counted Oct 14 as covered, the backup routine did not
retry, and the only signal was a partial-capture alert.

## Decision

- The registry follows the DOH page's link (`doh_dashboard` URL updated, history in its notes
  and `docs/sources.md` S1).
- A dashboard capture that did not reach the report is `failed` with `report unavailable: ...`:
  a data API error body with HTTP status 400 or more, the placeholder text, or no report tab
  opening. Raw is saved first, as before (I1).
- `capture_log.problem` and `is_good` apply the same test to every record, so the Oct 13 to 15
  records (which cannot be edited, I1) are judged from what they recorded. Capture-day cover,
  freshness, alerts and weekly releases all use `is_good`.
- New parser `doh_measles_page` (flags only): `DASHBOARD_LINK_CHANGED` when the page's dashboard
  link differs from the page captured before. It would have raised the change on Oct 14.
- Capture records carry `trigger` (`schedule`, `workflow_dispatch`, `local`). `access.g2_status`
  counts a week toward Gate G2 only when every capture day in it was covered by a scheduled run;
  days covered only by a dispatch (the backup routine, ADR 0006, or a person) are covered but
  not unattended. Older records show `unknown`. Shown in the quality report and the dashboard.
- The dashboard's stale banners say what the captures show and no more (I5): the source could
  not be captured (why, last good capture); DOH had not published newer figures by a good
  capture after a scheduled update; or an update could not be checked.

## Consequences

- With the new link, captures should recover from the next run; the report layout may have
  changed, in which case the partial-capture alert and the parser's quarantine say so.
- Oct 14 counts as missed. The dashboard keeps no history, so any update DOH published on
  Oct 14 or 15 before the next good capture is lost to this archive.
- G2 starts counting from the first full week with triggers recorded (week of Oct 19 at the
  earliest).
