"""Stochastic county metapopulation SEIR (WP6b, HANDOFF WP6, T6.4 to T6.9).

Daily chain-binomial steps, compiled with numba (E10). Each county ``i`` has compartments
S, E, I, R and population N. On day ``t``, from the start-of-day state:

- force of infection ``lambda_i = beta x mult[t, i] x sum_j K[i, j] x I_j / N_j``;
- new exposures ``Binomial(S_i, 1 - exp(-lambda_i))`` plus ``Poisson(imports[t, i])``
  external exposures (capped by the susceptibles left);
- commuting coupling is directed: residents of ``i`` meet the infectious of the counties they
  commute to;
- vaccination moves ``Binomial(S_left, vacc[t, i] / S_left)`` susceptibles to R;
- E and I are each split into stages (Erlang stays): from each of ``k`` latent stages
  ``Binomial(E_ik, k/latent)`` move on, likewise for infectious stages, so mean stays equal
  the stated periods in days and an infectious person still causes R0 infections on average.
  With one stage the stay is geometric and the mean generation time is about latent +
  infectious; with more stages infectiousness is less spread out and the generation time
  approaches latent + infectious / 2 (``generation_time``, checked against the literature).

``K`` is the contact coupling between counties (``coupling_matrix``): the identity plus, for
each link type, its strength times a row-normalised link matrix, with the same share taken
off the county's own contacts. A strength of zero leaves that link out exactly (T6.9).
``mult`` carries interventions and the school calendar as factors on transmission.

Everything random comes from one seed, so a run is reproducible (T6.7).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numba
import numpy as np
import yaml

PARAMS = Path(__file__).with_name("params.yml")


def load_params(path: Path = PARAMS) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


@dataclass
class Result:
    incidence: np.ndarray  # (days, counties) new infections per day, imports included
    vaccinated: np.ndarray  # (days, counties) susceptibles moved to R by vaccination
    state: np.ndarray  # (days + 1, counties, 4) S, E, I, R at the start of each day and at the end

    @property
    def final_size(self) -> np.ndarray:
        """New infections per county over the run (initial E and I not counted)."""
        return self.incidence.sum(axis=0)


@numba.njit(cache=True)
def _run(
    n: np.ndarray,
    s0: np.ndarray,
    e0: np.ndarray,
    i0: np.ndarray,
    rec0: np.ndarray,
    beta: float,
    p_ei: float,
    p_ir: float,
    ke: int,
    ki: int,
    k: np.ndarray,
    mult: np.ndarray,
    imports: np.ndarray,
    vacc: np.ndarray,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    np.random.seed(seed)
    days, c = mult.shape
    state = np.zeros((days + 1, c, 4), dtype=np.int64)
    inc = np.zeros((days, c), dtype=np.int64)
    vac = np.zeros((days, c), dtype=np.int64)
    s = s0.copy()
    r = rec0.copy()
    # Stage counts; initial exposed and infectious start in the first stage.
    e = np.zeros((ke, c), dtype=np.int64)
    i = np.zeros((ki, c), dtype=np.int64)
    e[0] = e0
    i[0] = i0
    prev = np.zeros(c)
    for j in range(c):
        state[0, j, 0] = s[j]
        state[0, j, 1] = e[:, j].sum()
        state[0, j, 2] = i[:, j].sum()
        state[0, j, 3] = r[j]
    move_e = np.zeros((ke, c), dtype=np.int64)
    move_i = np.zeros((ki, c), dtype=np.int64)
    for t in range(days):
        for j in range(c):
            prev[j] = i[:, j].sum() / n[j] if n[j] > 0 else 0.0
        new_e = np.zeros(c, dtype=np.int64)
        new_v = np.zeros(c, dtype=np.int64)
        for a in range(c):
            lam = 0.0
            for b in range(c):
                lam += k[a, b] * prev[b]
            lam *= beta * mult[t, a]
            inf = np.random.binomial(s[a], 1.0 - np.exp(-lam)) if lam > 0 else 0
            if imports[t, a] > 0:
                imp = np.random.poisson(imports[t, a])
                inf += min(imp, s[a] - inf)
            left = s[a] - inf
            v = 0
            if vacc[t, a] > 0 and left > 0:
                v = np.random.binomial(left, min(1.0, vacc[t, a] / left))
            new_e[a] = inf
            new_v[a] = v
            for q in range(ke):
                move_e[q, a] = np.random.binomial(e[q, a], p_ei)
            for q in range(ki):
                move_i[q, a] = np.random.binomial(i[q, a], p_ir)
        for a in range(c):
            s[a] -= new_e[a] + new_v[a]
            e[0, a] += new_e[a]
            for q in range(ke):
                e[q, a] -= move_e[q, a]
                if q + 1 < ke:
                    e[q + 1, a] += move_e[q, a]
            i[0, a] += move_e[ke - 1, a]
            for q in range(ki):
                i[q, a] -= move_i[q, a]
                if q + 1 < ki:
                    i[q + 1, a] += move_i[q, a]
            r[a] += move_i[ki - 1, a] + new_v[a]
            inc[t, a] = new_e[a]
            vac[t, a] = new_v[a]
            state[t + 1, a, 0] = s[a]
            state[t + 1, a, 1] = e[:, a].sum()
            state[t + 1, a, 2] = i[:, a].sum()
            state[t + 1, a, 3] = r[a]
    return inc, vac, state


def simulate(
    population: np.ndarray,
    susceptible: np.ndarray,
    exposed: np.ndarray,
    infectious: np.ndarray,
    *,
    r0: float,
    latent_days: float,
    infectious_days: float,
    coupling: np.ndarray,
    days: int,
    seed: int,
    latent_stages: int = 1,
    infectious_stages: int = 1,
    mult: np.ndarray | None = None,
    imports: np.ndarray | None = None,
    vaccination: np.ndarray | None = None,
) -> Result:
    """Run once. ``susceptible``, ``exposed`` and ``infectious`` are counts per county; the
    rest of the population starts immune (R)."""
    n = np.asarray(population, dtype=np.int64)
    s = np.asarray(susceptible, dtype=np.int64)
    e = np.asarray(exposed, dtype=np.int64)
    i = np.asarray(infectious, dtype=np.int64)
    c = n.size
    if (s < 0).any() or (e < 0).any() or (i < 0).any() or (s + e + i > n).any():
        raise ValueError("compartments must be non-negative and fit within the population")
    k = np.asarray(coupling, dtype=np.float64)
    if k.shape != (c, c) or (k < 0).any() or not np.allclose(k.sum(axis=1), 1.0):
        raise ValueError("coupling must be a non-negative row-stochastic county matrix")
    m = np.ones((days, c)) if mult is None else np.asarray(mult, dtype=np.float64)
    imp = np.zeros((days, c)) if imports is None else np.asarray(imports, dtype=np.float64)
    vac = np.zeros((days, c)) if vaccination is None else np.asarray(vaccination, dtype=np.float64)
    for name, arr in (("mult", m), ("imports", imp), ("vaccination", vac)):
        if arr.shape != (days, c) or (arr < 0).any():
            raise ValueError(f"{name} must be a non-negative (days, counties) array")
    _check_stages(latent_days, infectious_days, latent_stages, infectious_stages)
    # Daily leaving probabilities k/D per stage give k geometric stays with mean exactly D days
    # in all, so an infectious person contributes R0 / D x D = R0 expected infections
    # (validated against the final-size relation in tests). 1 - exp(-k/D) would lengthen stays
    # and inflate R.
    gamma = 1.0 / infectious_days
    inc, vacd, state = _run(
        n,
        s,
        e,
        i,
        n - s - e - i,
        r0 * gamma,
        latent_stages / latent_days,
        infectious_stages * gamma,
        latent_stages,
        infectious_stages,
        k,
        m,
        imp,
        vac,
        seed,
    )
    return Result(inc, vacd, state)


def _check_stages(
    latent_days: float, infectious_days: float, latent_stages: int, infectious_stages: int
) -> None:
    if latent_stages < 1 or infectious_stages < 1:
        raise ValueError("each period needs at least one stage")
    # Daily steps: each stage lasts at least a day, so a stage's leaving probability k/D <= 1.
    if latent_days < latent_stages or infectious_days < infectious_stages:
        raise ValueError("a period must be at least one day per stage (daily steps)")


def generation_time(
    latent_days: float,
    infectious_days: float,
    latent_stages: int = 1,
    infectious_stages: int = 1,
    horizon: int = 1000,
) -> float:
    """Mean days from a person's infection to the infections they cause, in the simulator.

    Follows one person exposed on day 0 through the same daily stage transitions as
    ``simulate``: their infectiousness on day ``t`` is the chance of being infectious at the
    start of that day, and the generation time is the mean of ``t`` weighted by it."""
    _check_stages(latent_days, infectious_days, latent_stages, infectious_stages)
    ke, ki = latent_stages, infectious_stages
    pe, pi = ke / latent_days, ki / infectious_days
    x = np.zeros(ke + ki)
    x[0] = 1.0
    num = den = 0.0
    for t in range(1, horizon):
        w = x[ke:].sum()
        num += t * w
        den += w
        moved = x * np.where(np.arange(ke + ki) < ke, pe, pi)
        x = x - moved
        x[1:] += moved[:-1]
    return num / den


def _row_normalise(m: np.ndarray) -> np.ndarray:
    tot = m.sum(axis=1, keepdims=True)
    return np.divide(m, tot, out=np.zeros_like(m), where=tot > 0)


def coupling_matrix(
    fips: list[str],
    *,
    commuting: Sequence[tuple[str, str, float]] = (),
    adjacency: Sequence[tuple[str, str, float]] = (),
    long_range: Sequence[Sequence[str]] = (),
    strengths: dict[str, float],
) -> np.ndarray:
    """Identity plus ``strength x (link matrix - own contacts)`` for each link type.

    - commuting: (origin, destination, flow); directed, own-county flow ignored.
    - adjacency: (a, b, shared boundary length); symmetric.
    - long_range: groups of counties linked to each other with equal weight.
    A county with no link of a type keeps that share of contacts at home."""
    idx = {f: n for n, f in enumerate(fips)}
    c = len(fips)
    mats: dict[str, np.ndarray] = {}
    m = np.zeros((c, c))
    for a, b, w in commuting:
        if a in idx and b in idx and a != b:
            m[idx[a], idx[b]] += w
    mats["commuting"] = m
    m = np.zeros((c, c))
    for a, b, w in adjacency:
        if a in idx and b in idx and a != b:
            m[idx[a], idx[b]] += w
            m[idx[b], idx[a]] += w
    mats["adjacency"] = m
    m = np.zeros((c, c))
    for group in long_range:
        members = [idx[f] for f in group if f in idx]
        for x in members:
            for y in members:
                if x != y:
                    m[x, y] = 1.0
    mats["long_range"] = m
    unknown = set(strengths) - set(mats)
    if unknown:
        raise ValueError(f"unknown coupling terms {sorted(unknown)}")
    if any(w < 0 for w in strengths.values()) or sum(strengths.values()) > 1:
        raise ValueError("coupling strengths must be non-negative and sum to at most 1")
    k = np.eye(c)
    for name, w in strengths.items():
        if w == 0:
            continue
        link = _row_normalise(mats[name])
        has = link.sum(axis=1) > 0
        k += w * link
        own = np.flatnonzero(has)
        k[own, own] -= w
    return k


def intervention_mult(
    days: int, counties: int, windows: list[tuple[int, int, list[int] | None, float]]
) -> np.ndarray:
    """Transmission factors from (start_day, end_day, county indices or None for all, factor).
    Interventions only reduce transmission, so each factor must lie in [0, 1]."""
    m = np.ones((days, counties))
    for start, end, where, factor in windows:
        if not 0 <= factor <= 1:
            raise ValueError("an intervention factor must lie in [0, 1]")
        cols = slice(None) if where is None else where
        m[max(start, 0) : max(min(end, days), 0), cols] *= factor
    return m
