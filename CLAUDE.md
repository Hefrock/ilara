# measles-pa: instructions for Claude Code

Unofficial, independent project: a provenance-first data repository and county-level model of the 2026 Pennsylvania measles outbreak. Python 3.12. Read `docs/PROGRESS.md` first in every session, then `docs/HANDOFF.md` for the work package you are on.

## Invariants (never break; if a task seems to require it, stop and ask)

- I1 Raw is immutable and saved first. Every fetch outcome is logged in `data/capture_log/`; every fetch whose content changed is written to `data/raw/` with a manifest before anything else happens to it (unchanged content is logged with its hash). Never edit or delete raw files. Parsing or validation failure never prevents saving raw.
- I2 Curated is regenerable and append-only. `data/curated/` can be rebuilt from `data/raw/` plus `data/seed/` with one command, and rebuilding twice gives identical content. Never hand-edit curated files. Revisions are new rows, never overwrites.
- I3 Provenance on every row: `source_id`, `source_tier`, `as_of_date`, `fetched_at_utc`, `raw_sha256` (or `seed_file` and `seed_row`), `parser_version`, `jurisdiction`, `disease`.
- I4 Source tiers. T1 official primary (PA DOH, CDC, Census, official local health departments). T2 peer-reviewed or MMWR. T3 news or Wikipedia: for locating sources and sanity checks only. `T3-derived` is the single exception: dated figures that a news article attributes to the DOH dashboard, which keeps no public history. The same holds for T3 events and secondary journal figures. They live only under `data/sensitivity/` (seeds in `data/sensitivity/seed/`), are excluded from default calibration, charts and the public dashboard, and appear only in a labelled sensitivity run. Never merge them silently with T1.
- I5 No fabrication. Never interpolate, forward-fill or guess counts or dates. A gap stays a gap. "Unknown" and "to_confirm" are valid values. Zero reported is different from not reported.
- I6 Dates. `as_of_date` is the date the source says the data reflect (local ET date). `fetched_at_utc` is when we got it. Store UTC and also ET. Do not infer onset dates: the only dated series is by report date. Never treat dashboard deltas as daily incidence.
- I7 Be polite to servers. Descriptive user agent that names the repository URL (never a personal email), at most 1 request per 5 seconds per host, respect robots.txt and site terms. One navigation per browser capture. If a request is blocked, challenged or disallowed: stop, record outcome `blocked`, raise an alert, and do not work around it.
- I8 Layer boundaries. Capture does not parse. Parse does not fetch. Code under `project/` reads only `data/curated/` and `data/reference/` through the data-access module (`ingest/access.py`, which also exposes capture status), never `data/raw/`. The capture bot commits only under `data/`.
- I9 Determinism. Pinned dependencies (`uv.lock`), seeded randomness, every model run writes a manifest (git SHA, data release tag, seeds, parameters).
- I10 Publication hygiene. Assume every committed byte becomes public, including history. Never commit: personal email addresses, institutional affiliation text, secrets or tokens, full article text, any case-level or line-list data, or model outputs before Gate G4 (`project/outputs/` is gitignored). Commit identity is the GitHub noreply address.
- I11 Observed and modelled are always labelled and styled differently. Forecasts and the watchlist map are withheld from public output until `data/validation_gate.json` records a pass.

## Commands

`uv sync` install. `make check` lint, type check, tests (offline). `make verify` recompute raw hashes and check every curated row's raw reference. `make rebuild` regenerate curated from raw plus seed. `make dashboard` build the static site. CLI: `uv run measles <capture|parse|seed|verify|rebuild|quality|release|dashboard>` (HANDOFF.md section 4.4).

## Conventions

- Tools: uv, polars, duckdb, pydantic v2 (schemas), ruff, pytest, hypothesis, playwright, geopandas (reference and map code only), numba (simulator).
- Tests are offline. Network tests are marked `@pytest.mark.network` and are not part of `make check`.
- Commit prefixes: `data:` (bot only), `ingest:`, `project:`, `docs:`, `ci:`. Branch per work package for human-directed work; never force-push or rewrite history on `main`.
- Code in `ingest/` and `project/`; tests mirror the tree under `tests/`.
- Dates ISO 8601. County keys are 5-digit FIPS strings. Names are normalised only through the crosswalk.

## Session protocol

1. Read `docs/PROGRESS.md`, then the work package you are on.
2. Plan before coding. For parsers, write golden-file tests from real captured fixtures first.
3. Work one task at a time; commit after each green `make check`.
4. Do not claim done until the work package's acceptance tests pass and you have run them.
5. Update `docs/PROGRESS.md` (status, evidence, next step) using the format in that file. Record non-obvious decisions as `docs/adr/NNN-title.md`.
6. Flip UNVERIFIED items to VERIFIED in `docs/sources.md` only after observing them directly, and cite what you observed.

## Stop and ask the human when

- A source blocks, challenges or disallows access (I7).
- Anything needs credentials, repository settings, secrets, a self-hosted runner, or a request to any agency. Add a row to `docs/BLOCKERS.md` (format in that file: neutral wording, exactly what you need, which work package it blocks) and continue with unblocked work.
- Two documents disagree, or a decision in HANDOFF.md section 2 would have to change.
- An action is irreversible or could expose data publicly.

Do not ask about anything already decided in HANDOFF.md section 2.
