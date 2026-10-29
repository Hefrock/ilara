# Ilara: Pennsylvania measles data archive

An unofficial, provenance-first archive and county-level model of the 2026 Pennsylvania measles
outbreak.

> **Unofficial independent project.** This is not clinical or public health guidance and is not
> affiliated with or endorsed by any health department or agency. For official information see the
> Pennsylvania Department of Health.

## What it does

Ilara collects public data about the outbreak on a fixed schedule: the Department of Health
dashboard, CDC case counts and Census reference data. Every capture is saved exactly as received,
with a hash, before anything else happens to it. The captures are then parsed into tables where
each row records where it came from. A data release is tagged each week, and a small static
dashboard shows the latest figures.

A county-level transmission model sits on top of the data. It is fitted to the reported county
counts and makes forecasts one to four weeks ahead. Those forecasts stay private until they have
proven better than a simple baseline.

The project is also a way to learn Python epidemiological tooling.

## Status

Data capture, curation, weekly releases and the dashboard run now. The model was first fitted to
real data on 28 October 2026, once ten county snapshots existed. Its forecasts are being scored
each week from November; they will be shown only if they beat a simple baseline over eight
weekly forecasts, which is no earlier than 30 December 2026.

How the data and model work: [`docs/methods.md`](docs/methods.md). Progress:
[`docs/PROGRESS.md`](docs/PROGRESS.md). Build plan: [`docs/HANDOFF.md`](docs/HANDOFF.md).
Decisions: [`docs/adr/`](docs/adr/). What went wrong and what it taught us:
[`docs/lessons.md`](docs/lessons.md).

## Reading the numbers

- **Counts are a floor.** Reported cases are cases known to and published by public health
  authorities, and are revised. Many infections are never reported.
- **Forecasts withheld until validated.** Model output is not published until it beats a simple
  persistence baseline on held-out data.
- Every figure traces to a raw capture (`data/raw/`) with a SHA-256 hash and a weekly release tag.

## Where things are

`ingest/` captures, parses and checks the data. `project/` holds the model, its validation and the
dashboard. `data/` holds the raw captures, the curated tables and the quality report. `docs/`
holds the methods, sources, decisions and progress log.

## Reproduce

```sh
uv sync --all-extras
make check     # lint, type check, tests, guards (no network)
make verify    # recompute raw hashes and provenance links
make rebuild   # regenerate the curated tables from raw and seed files
make dashboard # build the static site
```

## Licence

Code: MIT (see `LICENSE`). Data: each source's own terms apply; only government-sourced data
(Pennsylvania DOH, CDC, US Census Bureau) appears in the public tables.
