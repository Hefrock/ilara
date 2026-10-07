"""Backfill capture (WP3c): fetch each listed one-off document once, through the raw store.

The list lives in ``data/registry/backfill_urls.yml``. A URL is skipped once any raw file
holds a capture of it (``capture_key`` is the URL). Fetching follows the same politeness
rules as every capture (robots.txt, 5 s per host, blocked stops, I7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ingest import paths, rawstore
from ingest.capture.http import PoliteClient
from ingest.capture.runner import _ext_for
from ingest.capture_log import CaptureLog, CaptureRecord, runner_label
from ingest.registry import load as load_registry
from ingest.timeutil import iso_utc, utc_now

LIST = "backfill_urls.yml"


def documents(root: Path) -> list[dict[str, Any]]:
    p = paths.data_dir(root) / "registry" / LIST
    if not p.exists():
        return []
    return yaml.safe_load(p.read_text()).get("documents", [])


def captured_urls(root: Path) -> set[str]:
    out: set[str] = set()
    for mp in rawstore.iter_manifests(None, root):
        m = rawstore.load_manifest(mp)
        if m.get("capture_key"):
            out.add(m["capture_key"])
    return out


def run(log: CaptureLog, root: Path, client: PoliteClient | None = None) -> list[CaptureRecord]:
    reg = load_registry(root)
    done = captured_urls(root)
    todo = [d for d in documents(root) if d["url"] not in done]
    own = client is None
    client = client or PoliteClient()
    records: list[CaptureRecord] = []
    try:
        for d in todo:
            src = reg[d["source_id"]]
            if src.access_path != "backfill":
                raise ValueError(f"{d['source_id']} is not a backfill source")
            started = utc_now()
            res = client.fetch(d["url"])
            common: dict[str, Any] = dict(
                capture_id=log.next_capture_id(src.source_id),
                source_id=src.source_id,
                url=d["url"],
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
            else:
                saved = rawstore.save(
                    source_id=src.source_id,
                    url=d["url"],
                    data=res.body,
                    ext=_ext_for(src, res),
                    fetched_at=started,
                    http_status=res.status,
                    parser_hint=src.source_id,
                    capture_key=d["url"],
                    extra={
                        "purpose": d.get("purpose"),
                        "final_url": res.url,
                        "capture_id": common["capture_id"],
                    },
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
            records.append(rec)
    finally:
        if own:
            client.close()
    return records
