"""Weekly release (WP4): T4.1 to T4.6."""

from __future__ import annotations

import gzip
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from ingest import rawstore
from ingest.capture_log import CaptureLog, CaptureRecord
from ingest.curate import seed
from ingest.parse import runner
from ingest.release import weekly

from conftest import REPO, git

FIXTURE = REPO / "tests/fixtures/doh_dashboard/2026-10-05_responses.json.gz"
AFTER = datetime(2026, 10, 12, 13, 30, tzinfo=UTC)


def _log(root: Path, run: str, finished: str, outcome: str = "changed") -> None:
    CaptureLog(run, root).append(
        CaptureRecord(
            capture_id=f"{run}:01:doh_dashboard",
            source_id="doh_dashboard",
            url="u",
            started_utc=finished,
            finished_utc=finished,
            http_status=200,
            outcome=outcome,
            raw_path=None,
            sha256=None,
            content_hash=None,
            bytes=None,
            runner="local",
        )
    )


@pytest.fixture
def repo(root: Path) -> Path:
    for sub in ("data/seed", "data/sensitivity/seed"):
        shutil.copytree(REPO / sub, root / sub, ignore=shutil.ignore_patterns("MANIFEST.json"))
    seed.load(root, datetime(2026, 10, 7, 4, tzinfo=UTC))
    rawstore.save(
        source_id="doh_dashboard",
        url="https://report.test",
        data=gzip.decompress(FIXTURE.read_bytes()),
        ext="json",
        capture_key="responses",
        fetched_at=datetime(2026, 10, 7, 18, 5, tzinfo=UTC),
        root=root,
    )
    runner.run(root)
    _log(root, "mon", "2026-10-05T20:01:00Z")
    _log(root, "wed", "2026-10-07T18:05:00Z")
    _log(root, "fri-fail", "2026-10-09T18:05:00Z", "failed")  # Friday not covered
    _log(root, "sat", "2026-10-10T13:02:00Z")  # catch-up window does not cover Friday
    git(root, "init", "-q")
    git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "-c",
        "commit.gpgsign=false",
        "add",
        ".",
    )
    git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "-m",
        "data",
        "--date=2026-10-08T00:00:00Z",
    )
    return root


def test_week_bounds_across_dst() -> None:  # T4.1
    w44 = weekly.Week.parse("2026-W44")  # DST ends Sunday 2026-11-01
    assert w44.start_utc == datetime(2026, 10, 26, 4, tzinfo=UTC)
    assert w44.end_utc == datetime(2026, 11, 2, 5, tzinfo=UTC)
    w45 = weekly.Week.parse("2026-W45")
    assert w45.start_utc == w44.end_utc
    assert [d.isoformat() for d in w44.capture_days] == ["2026-10-26", "2026-10-28", "2026-10-30"]
    assert weekly.last_closed_week(AFTER) == "2026-W41"
    assert weekly.last_closed_week(datetime(2026, 10, 11, 20, tzinfo=UTC)) == "2026-W40"


def test_uncovered_day_listed_no_interpolation(repo: Path) -> None:  # T4.2
    p = weekly.release("2026-W41", repo, now=AFTER)
    m = json.loads(p.read_text())
    assert m["uncovered_days"] == ["2026-10-09"]
    assert m["capture_days"]["2026-10-05"]["covered"] and m["capture_days"]["2026-10-07"]["covered"]
    assert m["interpolated_values"] == 0
    assert m["latest_dashboard"]["calendar_year"]["cum_cases"] == 1004
    assert "missed: 2026-10-09" in (repo / "data/RELEASE_NOTES.md").read_text()


def test_idempotent_even_after_later_data(repo: Path) -> None:  # T4.3, T4.6
    p = weekly.release("2026-W41", repo, now=AFTER)
    first = p.read_bytes()
    _log(repo, "mon2", "2026-10-12T18:05:00Z")  # next week's capture
    rawstore.save(
        source_id="doh_measles_page",
        url="u",
        data=b"later",
        ext="html",
        fetched_at=datetime(2026, 10, 12, 14, 30, tzinfo=UTC),
        root=repo,
    )
    weekly.release("2026-W41", repo, now=datetime(2026, 10, 20, tzinfo=UTC))
    assert p.read_bytes() == first
    m = json.loads(first)
    assert m["data_commit_sha"] and len(m["data_commit_sha"]) == 40
    assert m["inputs"]["raw_files_in_week"] and all(
        len(x["sha256"]) == 64 for x in m["inputs"]["raw_files_in_week"]
    )


def test_fails_closed_when_verify_fails(repo: Path) -> None:  # T4.4
    raw = next(
        p
        for p in (repo / "data/raw").rglob("*")
        if p.is_file() and not p.name.endswith(".manifest.json")
    )
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(weekly.ReleaseError, match="verify failed"):
        weekly.release("2026-W41", repo, now=AFTER)
    assert not (repo / "data/releases").exists()


def test_exports_equal_views(repo: Path) -> None:  # T4.5
    weekly.release("2026-W41", repo, now=AFTER)
    week = weekly.Week.parse("2026-W41")
    for t in weekly.EXPORT_TABLES:
        view = weekly._known(t, week.end_utc, repo)
        csv = pl.read_csv(repo / f"data/exports/{t}_current.csv", schema=view.schema)
        assert csv.equals(view)


def test_open_week_refused(repo: Path) -> None:
    with pytest.raises(weekly.ReleaseError, match="has not ended"):
        weekly.release("2026-W41", repo, now=datetime(2026, 10, 9, tzinfo=UTC))
