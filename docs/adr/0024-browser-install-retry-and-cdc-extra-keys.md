# ADR 0024: browser install with a time limit and retries; CDC map file with extra keys

Status: accepted (owner, 2026-10-30: "yes, do the CDC and Chromium fixes in one PR").

## Context

1. On 2026-10-26 the scheduled dashboard capture at 23:16 UTC hung on the "Install browser" step
   (Playwright's Chromium shell and its system packages) until the job's 10-minute limit
   cancelled it. The capture step never ran. That day was covered only by a dispatched run, so
   the week no longer counts toward Gate G2 (two weeks covered by scheduled runs alone).
2. From the capture of 2026-10-30 CDC's map file carries a Spanish date (`lastUpdated_esp`) beside
   `lastUpdated` and `data`. CDC parser 1.1.0 accepted the wrapper only with exactly those two keys
   (ADR 0019), so it raised `PARSE_SCHEMA_CHANGE` (issue 51). The rows are unchanged.

## Decision

1. The browser is installed by `.github/scripts/install-browser.sh` in every workflow that needs it
   (capture-dashboard, probe, ci): up to three attempts of at most three minutes each, under a
   step limit of 11 minutes. Job limits rise to 20 minutes to leave room for the capture after a
   retry. A test checks that no workflow installs the browser any other way.
2. CDC parser 1.2.0 reads the wrapper whenever it has `lastUpdated` and `data`, whatever other keys
   sit beside them. Dating is unchanged: the row takes the CDC page's "As of" date when its totals
   match the map (I6). On 2026-10-30 the page (as of October 29) matches the map: 4,834 cases in 47
   jurisdictions, Pennsylvania 1,411.

## Consequences

- A slow or stuck install now costs at most a few minutes and is retried, instead of losing a
  scheduled capture. A persistent failure still fails the run, and the backup routine still
  covers the day (ADR 0006), but such a day does not count toward G2.
- Scheduled runs starting late is a separate problem this does not fix (ADR 0025). Correction,
  2026-10-31: this ADR first said no scheduled dashboard run started on 2026-10-30; one did, at
  23:07 UTC, after the backup routine's last check.
- A parser that requires an exact set of keys breaks on harmless additions; the CDC parser now
  checks only for what it reads.
