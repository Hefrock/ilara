# Ilara: Pennsylvania measles data archive

> **Unofficial independent project.** This is not clinical or public health guidance and is not
> affiliated with or endorsed by any health department or agency. For official information see the
> Pennsylvania Department of Health.

Ilara tracks the 2026 Pennsylvania measles outbreak and is a way to learn Python epidemiological
tooling. It captures public data on a fixed schedule, stores every capture with its provenance,
curates it into typed tables and publishes weekly data releases. A county-level model is planned
once enough data exists.

## Status

Work in progress. See [`docs/PROGRESS.md`](docs/PROGRESS.md) and the build plan in
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
```

## Licence

Code: MIT (see `LICENSE`). Data: each source's own terms apply; only government-sourced data
(Pennsylvania DOH, CDC, US Census Bureau) appears in the public tables.
