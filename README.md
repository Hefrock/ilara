# Ilara: Pennsylvania measles data archive

> **Unofficial independent project.** This is not clinical or public health guidance and is not
> affiliated with or endorsed by any health department or agency. For official information see the
> Pennsylvania Department of Health.

Ilara tracks the 2026 Pennsylvania measles outbreak and is a way to learn Python epidemiological
tooling. It captures public data on a fixed schedule, stores every capture with its provenance,
curates it into typed tables and publishes weekly data releases. A county-level transmission model
is built and tested on synthetic data; it is fitted to real data only once enough county snapshots
exist, and its forecasts are published only if they pass validation.

## Status

Work in progress. Data capture, curation, weekly releases and the dashboard run now. The model
waits on two gates: ten county snapshot dates before any real fit (Gate G3, expected late October
2026), and forecasts that beat a simple baseline over eight weekly origins before any forecast is
shown (Gate G4, no earlier than 30 December 2026). How the data and model work:
[`docs/methods.md`](docs/methods.md). Progress: [`docs/PROGRESS.md`](docs/PROGRESS.md). Build plan:
[`docs/HANDOFF.md`](docs/HANDOFF.md).

## Reading the numbers

- **Counts are a floor.** Reported cases are cases known to and published by public health
  authorities, and are revised. Many infections are never reported.
- **Forecasts withheld until validated.** Model output is not published until it beats a simple
  persistence baseline on held-out data (Gate G4 in the build plan).
- Every figure traces to a raw capture (`data/raw/`) with a SHA-256 hash and a weekly release tag.

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
