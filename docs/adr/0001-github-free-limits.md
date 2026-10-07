# ADR 0001: GitHub Free limits and how the guards compensate

Status: accepted (2026-10-07). Register item U23 stays open until checked against current
GitHub documentation at Gate G5.

## Context

The repository is private on the GitHub Free plan (D04, D09).

- Branch protection and rulesets are believed to be unavailable for private repositories on
  GitHub Free (U23), so nothing on the server stops a bad push to `main`.
- Pushes made with the workflow `GITHUB_TOKEN` do not trigger other workflows, so `ci.yml`
  never runs on the capture and release bots' commits.
- Pages is unavailable for private repositories, and Actions minutes are limited.

## Decision (E18)

1. The capture, probe and release workflows run the guards themselves after committing and
   before pushing: path guard (`--bot`: every new commit may touch only `data/`), append-only
   guard (no edit or delete under `data/raw`, `data/capture_log`, `data/curated`,
   `data/sensitivity`, `data/seed`, `data/releases`), size budget, and `measles verify`. A guard
   failure stops the job before `git push`.
2. `ci.yml` runs `make check` plus the path and append-only guards over the pushed range on
   every human push and pull request.
3. The guards are plain Python under `ingest/guards/` with unit tests, so they run the same way
   locally (`make check`).
4. The dashboard is a workflow artifact while the repository is private; Pages starts at G5.

## Consequences

- A human can still bypass the guards by pushing directly. The guard re-runs on the next CI
  run over the pushed range and fails visibly; history is never rewritten to fix it (I8), so
  the fix is a new commit.
- Workflow minutes: the dashboard job installs a browser (cached) and must stay under about
  5 minutes; the light job has no browser.
