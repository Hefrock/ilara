# Progress

Work packages and gates follow `docs/HANDOFF.md` (E16). Blockers: `docs/BLOCKERS.md`.

## 2026-10-07 session 1

Done:
- WP0 scaffold: layout (3.2), `pyproject.toml` (Python 3.12, uv, `uv.lock`), `Makefile`,
  MIT licence, README with the unofficial notice, `.gitignore` (`project/outputs/`, `local/`).
- CLI (`uv run measles`): `capture`, `verify`, `guard`, `alerts` implemented; `parse`, `seed
  load`, `rebuild`, `quality`, `release`, `dashboard build` stubbed (exit 0, say which WP).
- Guards (`ingest/guards/`): path guard, append-only guard, size budget, hygiene scan, layer
  boundary, outputs gate. ADR 0001 records the GitHub Free limits (E18).
- WP2 minimum viable capture:
  - raw store `ingest/rawstore.py` (E02 layout, sidecar manifest, `content_hash` gating E03,
    exclusive create, gzip over 256 KB);
  - per-run `capture_log` JSONL (E04);
  - polite HTTP client (robots.txt, 5 s per host, blocked vs failed, 2 retries);
  - Playwright dashboard capture saving JSON responses, rendered text, html and a screenshot,
    so no access path (A, B or C) loses data before the probe decides;
  - issue alerts (open, comment on repeat, close on recovery);
  - workflows `capture-dashboard.yml`, `capture-light.yml`, `release.yml` (stub release),
    `probe.yml`, `ci.yml`, with guards before every push and rebase retry.
- Source registry `data/registry/source_registry.yml` (URLs marked `candidate`).

Tests: `make check` green (ruff, mypy, pytest, guards, verify). Covered: T0.2 to T0.6,
T2.1 to T2.9 (T2.9 against a local bare repository), T2.11, T3.10, T6.16. T0.1 holds locally;
confirm on GitHub with the first `ci` run.

Not yet: T2.10 (network probe) needs B3. WP1, WP2c remainder, WP3 onward.

Gate status: G0 pending the first green `ci` run on GitHub. G1 to G5 not started.
