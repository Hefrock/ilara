# ADR 0005: county SEIR simulator design

Status: accepted (2026-10-08).

## Context

WP6b asks for a stochastic county metapopulation SEIR (chain-binomial or tau-leaping, numba,
E10) that compares coupling terms rather than assuming one (S11), with interventions, a school
calendar covariate and external introductions.

## Decision

- Daily chain-binomial steps over 67 counties, compiled with numba (`project/model/simulator.py`).
  One seed drives every random draw.
- Frequency-dependent transmission, `beta = R0 / infectious period`. Contacts between counties
  go through a coupling matrix: the identity plus `strength x (link matrix - own contacts)` for
  each link type. Commuting (directed, ACS flows; out-of-state flows ignored), adjacency (shared
  boundary length) and long-range community links (groups of counties) each have their own
  strength. A strength of zero leaves the term out exactly (T6.9); strengths may sum to at most 1.
- Interventions and the school calendar enter as per-day, per-county factors on transmission.
  Intervention factors must lie in [0, 1] (T6.8). External introductions are Poisson exposures;
  vaccination moves susceptibles to R and is never counted as infection.
- Parameters are in `project/model/params.yml`. R0 12 to 18 and the latent period stay
  UNVERIFIED (U12, U13) until the literature is read; long-range links are off by default
  because no T1 source names the linked communities.
- `project/model/sensitivity.py` produces T6.2 (final size by U19 scenario). It is
  uncalibrated and seeded illustratively in Lancaster; its outputs stay in `project/outputs/`.

## Consequences

- About 0.5 ms per simulated year after compilation, fast enough for calibration (6c).
- `epydemix` is not compared yet (U18).
- Seeding from observed first-case dates waits for more county snapshots (Gate G3).
