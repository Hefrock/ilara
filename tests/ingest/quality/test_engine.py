"""Quality engine (WP3d): T3.5 to T3.8, flag idempotency, staleness."""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from ingest import access
from ingest.capture_log import CaptureLog, CaptureRecord
from ingest.curate import seed, store
from ingest.quality import engine

from conftest import REPO

NOW = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)


@pytest.fixture
def seeded(root: Path) -> Path:
    for sub in ("data/seed", "data/sensitivity/seed"):
        shutil.copytree(REPO / sub, root / sub, ignore=shutil.ignore_patterns("MANIFEST.json"))
    seed.load(root, NOW)
    return root


def _dash_state(
    root: Path,
    as_of: date,
    cum: int,
    sha: str,
    fetched: datetime,
    counties: int | None = None,
    source_id: str = "doh_dashboard",
) -> None:
    run_id = store.ingest_run_id(sha, "1.0.0")
    store.write(
        "curated",
        "case_state",
        pl.DataFrame(
            [
                {
                    "jurisdiction": "PA",
                    "disease": "measles",
                    "source_id": source_id,
                    "source_tier": "T1",
                    "as_of_date": as_of,
                    "fetched_at_utc": fetched,
                    "ingest_run_id": run_id,
                    "raw_sha256": sha,
                    "parser_version": "1.0.0",
                    "cum_cases": cum,
                    "counties_with_cases": counties,
                    "count_definition": "calendar_year",
                    "date_precision": "exact",
                }
            ]
        ),
        run_id,
        fetched,
        root,
    )


def _dash_counties(
    root: Path, as_of: date, counts: dict[str, int], sha: str, fetched: datetime
) -> None:
    run_id = store.ingest_run_id(sha, "1.0.0")
    store.write(
        "curated",
        "case_county",
        pl.DataFrame(
            [
                {
                    "jurisdiction": "PA",
                    "disease": "measles",
                    "source_id": "doh_dashboard",
                    "source_tier": "T1",
                    "as_of_date": as_of,
                    "fetched_at_utc": fetched,
                    "ingest_run_id": run_id,
                    "raw_sha256": sha,
                    "parser_version": "1.0.0",
                    "county_fips": f,
                    "cum_cases": n,
                    "count_definition": "calendar_year",
                    "date_precision": "exact",
                }
                for f, n in counts.items()
            ]
        ),
        run_id,
        fetched,
        root,
    )


def test_implied_counts_match_sources(seeded: Path) -> None:  # T3.5
    f = engine.Findings()
    got = {(x["implied_date"], x["implied_cum"]) for x in engine.implied_counts(seeded, f)}
    assert got == {
        (date(2026, 8, 28), 460),
        (date(2026, 8, 31), 497),
        (date(2026, 9, 9), 624),
        (date(2026, 9, 28), 903),
    }
    # 903 agrees with a row in the other store: reported, not flagged
    assert not [x for x in f.flags if x.code == "IMPLIED_COUNT_BREAK"]
    assert any("agrees with sensitivity" in line for line in f.sections["Implied counts"])


def test_implied_count_break_within_store(seeded: Path) -> None:  # T3.5
    _dash_state(seeded, date(2026, 9, 9), 600, "a" * 64, NOW)
    f = engine.Findings()
    engine.implied_counts(seeded, f)
    breaks = [x for x in f.flags if x.code == "IMPLIED_COUNT_BREAK"]
    assert len(breaks) == 1 and "624" in breaks[0].description


def test_cum_decrease_flagged(seeded: Path) -> None:  # T3.6
    _dash_state(seeded, date(2026, 10, 5), 1004, "a" * 64, NOW)
    _dash_state(seeded, date(2026, 10, 7), 1001, "b" * 64, NOW)
    f = engine.Findings()
    engine.monotonic(seeded, f)
    assert [x.code for x in f.flags] == ["CUM_DECREASE"]


def test_cdc_lag_is_not_a_decrease(seeded: Path) -> None:  # S6
    # CDC counts lag DOH, so a CDC value below an earlier DOH value is expected, not a break;
    # a decrease within the CDC series itself is still flagged.
    _dash_state(seeded, date(2026, 10, 5), 1004, "a" * 64, NOW)
    _dash_state(seeded, date(2026, 10, 6), 990, "c" * 64, NOW, source_id="cdc_measles_cases_map")
    f = engine.Findings()
    engine.monotonic(seeded, f)
    assert [x.code for x in f.flags] == []
    _dash_state(seeded, date(2026, 10, 7), 980, "d" * 64, NOW, source_id="cdc_measles_cases_map")
    f = engine.Findings()
    engine.monotonic(seeded, f)
    assert [x.code for x in f.flags] == ["CUM_DECREASE"] and "cross-check" in f.flags[0].description


def test_county_sum_complete_and_partial(seeded: Path) -> None:  # T3.7
    d = date(2026, 10, 9)
    _dash_state(seeded, d, 100, "c" * 64, NOW, counties=2)
    _dash_counties(seeded, d, {"42071": 60, "42087": 39, "42003": 0}, "c" * 64, NOW)
    f = engine.Findings()
    engine.county_sums(seeded, f)
    assert [x.code for x in f.flags] == ["COUNTY_SUM_MISMATCH"]  # complete list, 99 != 100

    d2 = date(2026, 10, 12)
    _dash_state(seeded, d2, 100, "d" * 64, NOW, counties=3)  # list incomplete: sum may be lower
    _dash_counties(seeded, d2, {"42071": 60, "42087": 39}, "d" * 64, NOW)
    f = engine.Findings()
    engine.county_sums(seeded, f)
    assert [x.code for x in f.flags] == ["COUNTY_SUM_MISMATCH"]  # only the Oct 9 one


def test_report_lists_known_issues(seeded: Path) -> None:  # T3.8
    engine.run(seeded, NOW)
    text = (seeded / "data/quality/quality_report.md").read_text()
    assert "134 (2026-07-23" in text and "379 (2026-08-21" in text  # growth step
    assert "## Growth steps" in text
    july = next(line for line in text.splitlines() if line.startswith("- 2026-07:"))
    assert "114" in july and "134" in july
    assert "count_definition `unknown`" in text
    assert "implies 788 on 2026-09-21" in text and "says 792: conflicts" in text
    assert "## Non-monotonic series" in text and "## Implied counts" in text


def test_flags_written_once(seeded: Path) -> None:
    _dash_state(seeded, date(2026, 10, 5), 1004, "a" * 64, NOW)
    _dash_state(seeded, date(2026, 10, 7), 1001, "b" * 64, NOW)
    n1, _ = engine.run(seeded, NOW)
    n2, _ = engine.run(seeded, NOW)
    assert n1 >= 1 and n2 == 0
    codes = access.all_rows("data_quality_flag", root=seeded)["code"].to_list()
    assert codes.count("CUM_DECREASE") == 1


def test_stale_snapshot(seeded: Path) -> None:
    log = CaptureLog("r1", seeded)
    t = "2026-10-01T18:00:05Z"
    log.append(
        CaptureRecord(
            capture_id="x",
            source_id="doh_dashboard",
            url="u",
            started_utc=t,
            finished_utc=t,
            http_status=200,
            outcome="changed",
            raw_path=None,
            sha256=None,
            content_hash=None,
            bytes=None,
            runner="local",
        )
    )
    f = engine.Findings()
    engine.freshness(seeded, NOW, f)
    assert [x.code for x in f.flags] == ["STALE_SNAPSHOT"]
    f = engine.Findings()
    engine.freshness(seeded, datetime(2026, 10, 2, tzinfo=UTC), f)
    assert f.flags == []


def _release_row(root: Path, url: str, counties: int, sha: str, fetched: datetime) -> None:
    run_id = store.ingest_run_id(sha, "1.0.0")
    store.write(
        "curated",
        "case_state",
        pl.DataFrame(
            [
                {
                    "jurisdiction": "PA",
                    "disease": "measles",
                    "source_id": "doh_release",
                    "source_tier": "T1",
                    "as_of_date": date(2026, 8, 25),
                    "fetched_at_utc": fetched,
                    "ingest_run_id": run_id,
                    "raw_sha256": sha,
                    "parser_version": "1.0.0",
                    "source_url": url,
                    "cum_cases": 393,
                    "counties_with_cases": counties,
                    "count_definition": "calendar_year",
                    "date_precision": "exact",
                }
            ]
        ),
        run_id,
        fetched,
        root,
    )


def test_source_conflict_between_documents_not_revisions(seeded: Path) -> None:
    t1, t2 = datetime(2026, 10, 7, 11, 54, tzinfo=UTC), datetime(2026, 10, 7, 11, 55, tzinfo=UTC)
    _release_row(seeded, "https://a.gov/r1", 29, "1" * 64, t1)
    _release_row(seeded, "https://a.gov/r1", 30, "3" * 64, t2)  # revision of r1: not a conflict
    f = engine.Findings()
    engine.source_conflicts(seeded, f)
    assert f.flags == []
    _release_row(seeded, "https://a.gov/r2", 28, "2" * 64, t2)  # a second document disagrees
    f = engine.Findings()
    engine.source_conflicts(seeded, f)
    assert [x.code for x in f.flags] == ["SOURCE_CONFLICT"]
    cur = access.current("case_state", root=seeded).filter(pl.col("source_id") == "doh_release")
    assert cur["raw_sha256"].to_list() == ["3" * 64]  # fixed tie-break on equal fetch time
