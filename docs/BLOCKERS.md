# Blockers and owner actions

Items that need the owner. Newest first. Remove an item only when it is resolved, and note
the resolution in `docs/PROGRESS.md`.

## Open

### B1. Package documents missing from the repository (blocks WP3b and the I1 to I11 rules)
Only `docs/HANDOFF.md` was provided. Still needed, placed as listed in HANDOFF section 0:
- `CLAUDE.md` (repository root): invariants I1 to I11, commands, session protocol. Until it
  arrives, the work follows the invariants as HANDOFF cites them (raw first, provenance
  columns, tier isolation, politeness, append-only history, hygiene).
- `docs/sources.md` (SOURCES.md): source URLs (S1 dashboard URL), check values (S3 statewide
  population for T1.3), register U1 to U23. The source registry URLs are marked `candidate`
  until it arrives.
- `docs/dashboard.md` (DASHBOARD.md): needed for WP5.
- `data/seed/*.csv`: needed for WP3b (seed load) and the T3.5 and T3.8 checks.
- `data/sensitivity/seed/*.csv`: only after decision H6 (B2).

### B2. Decision H6 before any sensitivity seed is committed (E08)
Decide whether the news-derived and secondary figures (numbers, source name and URL only)
may enter history, which becomes public at G5. If no, they stay in `local/` (gitignored).

### B3. Turn on scheduled capture: merge to the default branch and allow workflow writes
- GitHub runs `schedule` triggers only from workflows on the default branch. Capture starts
  once this work is merged into `main`.
- Settings, Actions, General, Workflow permissions: choose "Read and write permissions" so
  the workflows can push `data:` commits and open issues.
- Then run `probe-dashboard` once by hand (Actions tab, Run workflow). It saves the first
  dashboard capture and uploads `probe_summary.json`, which is the input for
  `docs/probe_report.md` and Gate G1.

### B4. The first commit's author address is a personal address (I10, E15, G5)
Commit `460104a` ("Create README") carries a personal email address in its author metadata.
Commits from this point use the GitHub noreply address. Because history is never rewritten
(I8), this commit will fail the full-history hygiene scan at G5 unless the owner decides
otherwise. Options: (a) accept and record it in the G5 checklist; (b) a one-time owner
decision to recreate the repository history before captures begin, while it holds nothing
of value. This is the owner's call; nothing has been changed.

### B5. Live sources are unreachable from the cloud development sandbox
`census.gov`, `pa.gov` and `cdc.gov` are blocked by this environment's network policy, so the
probe (T2.10) and the WP1 downloads run on GitHub-hosted runners through the workflows. This
does not block anything once B3 is done. To run them from a Claude Code cloud session as
well, add those hosts to the environment's allowed domains.
