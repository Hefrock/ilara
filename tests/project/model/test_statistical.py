"""The statistical comparator (ADR 0029 revisions), offline."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from project.model import statistical as st
from project.model import validate

W = date(2026, 11, 18)


def _cum(incs: list[int], end: date = W) -> dict[date, int]:
    out, tot = {end - timedelta(days=7 * len(incs)): 0}, 0
    for i, x in enumerate(incs):
        tot += x
        out[end - timedelta(days=7 * (len(incs) - 1 - i))] = tot
    return out


def test_parameters_level_growth_and_size() -> None:
    level, growth, size = st.parameters([10, 10, 20, 20])
    assert level == 20 and growth == pytest.approx((41 / 21) ** 0.5)
    assert st.parameters([0, 0, 0, 0]) == (0.0, 1.0, st.K_MAX)  # flat zero: Poisson-like
    assert st.parameters([1, 1, 400, 400])[1] == st.GROWTH_MAX  # clipped


def test_forecast_needs_four_known_weeks_and_reads_nothing_after_the_origin() -> None:
    obs = {"state": _cum([10, 10, 20, 20]), "42001": _cum([1, 2])}
    fc = st.forecast(obs, W)
    assert set(fc) == {"state"}  # 42001 has only two weeks: a gap
    later = {"state": {**obs["state"], W + timedelta(days=7): 10**6}}
    assert np.array_equal(st.forecast(later, W)["state"][1], fc["state"][1])
    assert np.median(fc["state"][1]) == pytest.approx(20 * (41 / 21) ** 0.5, rel=0.25)


def test_group_uncertainty_resamples_origins() -> None:
    rows = [
        {
            "origin": W + timedelta(days=7 * i),
            "geography": "state",
            "horizon": 1,
            "wis": 1.0 + i,
            "wis_persistence": 2.0,
        }
        for i in range(4)
    ]
    u = validate.group_uncertainty(pl.DataFrame(rows))
    s = u[1]["state"]
    assert s["origins"] == 4 and s["diff"] == pytest.approx(0.5)
    assert s["low"] <= s["diff"] <= s["high"] and s["low"] >= -1.0 and s["high"] <= 2.0
