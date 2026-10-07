"""Run captures for a set of sources. One failing source never stops the others (T2.7)."""

from __future__ import annotations

import traceback
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from ingest import rawstore
from ingest.capture.http import FetchResult, PoliteClient
from ingest.capture_log import CaptureLog, CaptureRecord, runner_label
from ingest.registry import Source
from ingest.timeutil import iso_utc, utc_now

BrowserCapture = Callable[[Source, CaptureLog, Path], list[CaptureRecord]]

_EXT_BY_CTYPE = {
    "application/pdf": "pdf",
    "application/json": "json",
    "text/csv": "csv",
    "text/html": "html",
    "application/zip": "zip",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


def _ext_for(source: Source, res: FetchResult) -> str:
    if res.content_type:
        base = res.content_type.split(";")[0].strip().lower()
        if base in _EXT_BY_CTYPE and source.ext in ("html", "json", "csv", "pdf"):
            return _EXT_BY_CTYPE[base]
    return source.ext


def capture_http(
    source: Source, client: PoliteClient, log: CaptureLog, root: Path
) -> CaptureRecord:
    assert source.url
    started = utc_now()
    res = client.fetch(source.url)
    cid = log.next_capture_id(source.source_id)
    common: dict[str, Any] = dict(
        capture_id=cid,
        source_id=source.source_id,
        url=source.url,
        started_utc=iso_utc(started),
        http_status=res.status,
        runner=runner_label(),
    )
    if res.outcome != "ok" or res.body is None:
        rec = CaptureRecord(
            **common,
            finished_utc=iso_utc(utc_now()),
            outcome=res.outcome,
            raw_path=None,
            sha256=None,
            content_hash=None,
            bytes=None,
            error=res.error,
        )
        log.append(rec)
        return rec
    saved = rawstore.save(
        source_id=source.source_id,
        url=res.url,
        data=res.body,
        ext=_ext_for(source, res),
        fetched_at=started,
        http_status=res.status,
        parser_hint=source.source_id,
        extra={"content_type": res.content_type, "capture_id": cid},
        root=root,
    )
    rec = CaptureRecord(
        **common,
        finished_utc=iso_utc(utc_now()),
        outcome=saved.outcome,
        raw_path=saved.raw_path,
        sha256=saved.sha256,
        content_hash=saved.content_hash,
        bytes=saved.bytes,
    )
    log.append(rec)
    return rec


def run(
    sources: Iterable[Source],
    log: CaptureLog,
    root: Path,
    client: PoliteClient | None = None,
    browser_capture: BrowserCapture | None = None,
) -> list[CaptureRecord]:
    records: list[CaptureRecord] = []
    own_client = client is None
    client = client or PoliteClient()
    try:
        for src in sources:
            try:
                if src.access_path == "browser":
                    if browser_capture is None:
                        from ingest.capture.browser import capture_browser

                        browser_capture = capture_browser
                    records.extend(browser_capture(src, log, root))
                elif src.access_path == "http":
                    records.append(capture_http(src, client, log, root))
            except Exception as e:  # noqa: BLE001 - isolate each source
                rec = CaptureRecord(
                    capture_id=log.next_capture_id(src.source_id),
                    source_id=src.source_id,
                    url=src.url or "",
                    started_utc=iso_utc(utc_now()),
                    finished_utc=iso_utc(utc_now()),
                    http_status=None,
                    outcome="failed",
                    raw_path=None,
                    sha256=None,
                    content_hash=None,
                    bytes=None,
                    runner=runner_label(),
                    error=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}",
                )
                log.append(rec)
                records.append(rec)
    finally:
        if own_client:
            client.close()
    return records
