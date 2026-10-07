"""Backfill capture (WP3c): each listed document is fetched once, politely."""

from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from ingest import rawstore
from ingest.capture import backfill
from ingest.capture.http import PoliteClient, RateLimiter
from ingest.capture_log import CaptureLog


def _client(calls: list[str]) -> PoliteClient:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if "blocked" in req.url.path:
            return httpx.Response(403)
        return httpx.Response(
            200, text=f"<html>{req.url.path}</html>", headers={"content-type": "text/html"}
        )

    lim = RateLimiter(min_interval=0.0, sleep=lambda s: None)
    return PoliteClient(transport=httpx.MockTransport(handler), limiter=lim, sleep=lambda s: None)


def _list(root: Path, urls: list[tuple[str, str]]) -> None:
    (root / "data/registry/backfill_urls.yml").write_text(
        yaml.safe_dump(
            {"documents": [{"source_id": s, "url": u, "purpose": "test"} for s, u in urls]}
        )
    )


def test_fetch_once_then_skip(root: Path) -> None:
    _list(
        root, [("doh_release", "https://a.gov/news/one"), ("doh_release", "https://a.gov/news/two")]
    )
    calls: list[str] = []
    recs = backfill.run(CaptureLog("r1", root), root, _client(calls))
    assert [r.outcome for r in recs] == ["changed", "changed"]
    mans = [rawstore.load_manifest(p) for p in rawstore.iter_manifests("doh_release", root)]
    assert {m["capture_key"] for m in mans} == {"https://a.gov/news/one", "https://a.gov/news/two"}
    calls.clear()
    assert backfill.run(CaptureLog("r2", root), root, _client(calls)) == []
    assert calls == []  # nothing fetched the second time


def test_blocked_is_logged_and_retried_next_run_only(root: Path) -> None:
    _list(root, [("doh_release", "https://a.gov/blocked/x")])
    calls: list[str] = []
    [rec] = backfill.run(CaptureLog("r1", root), root, _client(calls))
    assert rec.outcome == "blocked" and rec.raw_path is None
    assert sum(1 for c in calls if "blocked" in c) == 1  # no retry loop


def test_shared_run_log_keeps_capture_ids_unique(root: Path) -> None:
    _list(root, [("doh_release", "https://a.gov/news/one")])
    first = CaptureLog("same", root)
    first.append(
        backfill.CaptureRecord(
            capture_id=first.next_capture_id("doh_release"),
            source_id="doh_release",
            url="u",
            started_utc="t",
            finished_utc="t",
            http_status=200,
            outcome="unchanged",
            raw_path=None,
            sha256=None,
            content_hash=None,
            bytes=None,
            runner="local",
        )
    )
    [rec] = backfill.run(CaptureLog("same", root), root, _client([]))
    assert rec.capture_id == "same:02:doh_release"


def test_real_list_is_valid(root: Path) -> None:
    from ingest.registry import load

    from conftest import REPO

    reg = load(REPO)
    docs = backfill.documents(REPO)
    assert docs and len({d["url"] for d in docs}) == len(docs)
    assert all(reg[d["source_id"]].access_path == "backfill" for d in docs)
