"""Model version 2: a community group inside each county (ADR 0029).

Each county is split into a general population and a community group that keeps a share of
its contacts within itself. The existing simulator runs unchanged on 2c "patches": patch ``i``
is county ``i``'s general population and patch ``c + i`` its community.

Mixing, with ``K`` the county coupling matrix (row-stochastic) and ``w[j, n]`` the population
share of group ``n`` in county ``j``:

- general row (i, g): ``K[i, j] * w[j, n]`` for every county j and group n (proportionate
  mixing, as in version 1);
- community row (i, m): ``(1 - a) * K[i, j] * w[j, n] + a * [j == i and n == m]``, where ``a``
  is the share of community contacts made within the community (fitted).

Every row sums to 1, so R0 keeps the meaning it has in version 1. With no community anywhere
the run is delegated to version 1's path, so version 2 with a zero scale *is* version 1.

Community size: ``share_i = min(scale * proxy_i, MAX_SHARE)``, with ``scale`` fitted and
``proxy_i`` the share of kindergarten and grade 7 enrolment in schools reporting MMR below 90
percent, shrunk toward the statewide value (ADR 0029, D1). Only counties whose proxy exceeds the
statewide value have a community (round 2); elsewhere the proxy is set to zero. Seeds go into
the general population (round 2). The community's susceptible
fraction uses the coverage of the ``under_covered`` scenario named in ``params.yml``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import polars as pl

MAX_SHARE = 0.5  # a community is never more than half a county


def school_proxy(
    schools: pl.DataFrame,
    fips: Sequence[str],
    *,
    grades: Sequence[str],
    threshold_pct: float,
    prior_weight: float,
    above_state_only: bool = False,
) -> np.ndarray:
    """The county proxy fixed in ADR 0029 (D1): share of ``grades`` enrolment in schools
    reporting MMR coverage below ``threshold_pct``, shrunk toward the statewide share with
    ``prior_weight`` pupils; a county with no usable row takes the statewide share. Suppressed
    rows are left out of numerator and denominator. With ``above_state_only``, counties at or
    below the statewide share get zero (ADR 0029, round 2)."""
    if schools.height == 0:
        raise ValueError("no school immunization rows: the proxy cannot be computed")
    use = schools.filter(
        pl.col("grade").is_in(list(grades))
        & ~pl.col("suppressed_flag").fill_null(True)
        & pl.col("mmr_pct").is_not_null()
        & pl.col("enrolled").is_not_null()
    )
    by = use.group_by("county_fips").agg(
        pl.col("enrolled").sum().alias("enrolled"),
        pl.col("enrolled").filter(pl.col("mmr_pct") < threshold_pct).sum().alias("low"),
    )
    tot_enr = float(by["enrolled"].sum())
    if tot_enr <= 0:
        raise ValueError("no enrolment in usable school rows: the proxy cannot be computed")
    p = float(by["low"].sum()) / tot_enr
    vals = {f: (float(lo) + prior_weight * p) / (float(e) + prior_weight) for f, e, lo in by.rows()}
    out = np.array([vals.get(f, p) for f in fips])
    return np.where(out > p, out, 0.0) if above_state_only else out


def shares(proxy: np.ndarray, scale: float) -> np.ndarray:
    if scale < 0:
        raise ValueError("community scale must be non-negative")
    return np.minimum(scale * np.asarray(proxy, dtype=float), MAX_SHARE)


def community_susceptible(params: dict[str, Any], susceptibility: dict[str, Any]) -> float:
    """Susceptible fraction in the community: one minus coverage x two-dose effectiveness, with
    coverage from the named ``under_covered`` scenario (held fixed, ADR 0029 revisions)."""
    scen = params["community"]["coverage_scenario"]
    cov = float(susceptibility["under_covered"]["scenarios"][scen]["coverage"])
    ve2 = float(susceptibility["vaccine_effectiveness"]["two_dose"]["mean"])
    return 1.0 - cov * ve2


def patch_coupling(
    k: np.ndarray, pop_g: np.ndarray, pop_m: np.ndarray, within: float
) -> np.ndarray:
    """The 2c x 2c mixing matrix described in the module docstring."""
    if not 0 <= within <= 1:
        raise ValueError("within-community share must lie in [0, 1]")
    k = np.asarray(k, dtype=float)
    c = k.shape[0]
    tot = pop_g + pop_m
    w_g = np.divide(pop_g, tot, out=np.ones(c), where=tot > 0)
    w_m = np.divide(pop_m, tot, out=np.zeros(c), where=tot > 0)
    prop = np.hstack([k * w_g[None, :], k * w_m[None, :]])  # (c, 2c) proportionate rows
    out = np.vstack([prop, (1 - within) * prop])
    out[np.arange(c, 2 * c), np.arange(c, 2 * c)] += within
    return out


def split(
    population: np.ndarray, frac_general: np.ndarray, share: np.ndarray, s_community: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Population and susceptibles of the general and community patches, as integers."""
    n = np.asarray(population, dtype=np.int64)
    n_m = np.round(n * share).astype(np.int64)
    n_g = n - n_m
    s_g = np.round(n_g * np.asarray(frac_general)).astype(np.int64)
    s_m = np.round(n_m * s_community).astype(np.int64)
    return n_g, n_m, s_g, s_m


INTO = ("general", "community", "susceptible")


def to_patches(arr: np.ndarray, s_g: np.ndarray, s_m: np.ndarray, *, into: str) -> np.ndarray:
    """Spread a (days, c) array over the 2c patches: wholly into each county's general
    population (seeds, round 2), wholly into its community when it has susceptible members
    (seeds, round 1), or in proportion to susceptibles (vaccination)."""
    if into not in INTO:
        raise ValueError(f"into must be one of {INTO}")
    arr = np.asarray(arr)
    c = arr.shape[1]
    out = np.zeros((arr.shape[0], 2 * c), dtype=arr.dtype)
    if into == "general":
        out[:, :c] = arr
        return out
    if into == "community":
        has = s_m > 0
        out[:, :c] = np.where(has[None, :], 0, arr)
        out[:, c:] = np.where(has[None, :], arr, 0)
        return out
    tot = (s_g + s_m).astype(float)
    f_m = np.divide(s_m, tot, out=np.zeros(c), where=tot > 0)
    out[:, :c] = arr * (1 - f_m)[None, :]
    out[:, c:] = arr * f_m[None, :]
    return out
