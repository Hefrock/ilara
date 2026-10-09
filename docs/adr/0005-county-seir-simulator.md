# ADR 0005: county SEIR simulator design

Status: accepted (2026-10-08).

## Context

WP6b asks for a stochastic county metapopulation SEIR (chain-binomial or tau-leaping, numba,
E10) that compares coupling terms rather than assuming one (S11), with interventions, a school
calendar covariate and external introductions.

## Decision

- Daily chain-binomial steps over 67 counties, compiled with numba (`project/model/simulator.py`).
  One seed drives every random draw.
- Daily leaving probabilities are `1 / period` (latent 1/8, infectious 1/8), so a stay is
  geometric with mean exactly the stated period and an infectious person causes R0 expected
  infections in a fully susceptible population. Tests check the final-size relation
  `z = 1 - exp(-R z)` and the early growth rate of the linear daily map; `1 - exp(-1/period)`
  failed both, inflating R by about 6 percent.
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

## Amendment 2026-10-08: staged periods

Geometric single-stage stays gave a mean generation time of 16 days against 11 to 12 in the
literature (Klinkenberg and Nishiura 2011, https://doi.org/10.1016/j.jtbi.2011.06.015; Vink et
al. 2014, https://doi.org/10.1093/aje/kwu209; both in `docs/references/`). Latent and infectious periods are now Erlang: each
split into stages left with probability stages / days per day, which keeps the mean stays and
R0 unchanged but concentrates infectiousness. 7-day latent and 8-day infectious periods with 4
stages each give a mean generation time of 12.0 days. `generation_time` computes it from the
same daily transitions; tests tie it to the simulator's growth rate (Euler-Lotka) and check it
against the literature band. One stage remains the default of `simulate`.

## Consequences

- About 0.5 ms per simulated year after compilation, fast enough for calibration (6c).
- `epydemix` is not compared yet (U18).
- Seeding from observed first-case dates waits for more county snapshots (Gate G3).
