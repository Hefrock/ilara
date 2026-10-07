"""Browser capture of the DOH dashboard (WP2a/2d).

One navigation per capture (I7). Until the probe decides the access path, every capture
saves all candidate artefacts so that no access path loses data:

- ``responses``: JSON bodies of the report's query responses, sorted by URL (path A)
- ``text``: rendered text of the page and all frames (path B)
- ``html`` and ``screenshot`` (full-page JPEG, path C fallback): saved only when ``text`` or
  ``responses`` changed, or none exists yet, because both carry render noise that would
  otherwise add a file on every capture

robots.txt is checked through the polite HTTP client before the browser starts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ingest import rawstore
from ingest.capture.http import PoliteClient, looks_like_challenge
from ingest.capture_log import CaptureLog, CaptureRecord, runner_label
from ingest.registry import Source
from ingest.timeutil import iso_utc, utc_now

NAV_TIMEOUT_MS = 90_000
SETTLE_MS = 12_000
MAX_RESPONSE_BYTES = 5_000_000


def _record(log: CaptureLog, src: Source, started: str, **kw: Any) -> CaptureRecord:
    rec = CaptureRecord(
        capture_id=kw.pop("capture_id", None) or log.next_capture_id(src.source_id),
        source_id=src.source_id,
        url=src.url or "",
        started_utc=started,
        finished_utc=iso_utc(utc_now()),
        runner=runner_label(),
        **kw,
    )
    log.append(rec)
    return rec


def capture_browser(src: Source, log: CaptureLog, root: Path) -> list[CaptureRecord]:
    assert src.url
    started_dt = utc_now()
    started = iso_utc(started_dt)

    client = PoliteClient()
    try:
        allowed = client.allowed(src.url)
    finally:
        client.close()
    if allowed is False:
        return [
            _record(
                log,
                src,
                started,
                http_status=None,
                outcome="blocked",
                raw_path=None,
                sha256=None,
                content_hash=None,
                bytes=None,
                error="disallowed by robots.txt",
            )
        ]
    if allowed is None:
        return [
            _record(
                log,
                src,
                started,
                http_status=None,
                outcome="failed",
                raw_path=None,
                sha256=None,
                content_hash=None,
                bytes=None,
                error="robots.txt unreachable",
            )
        ]

    from playwright.sync_api import sync_playwright

    responses: list[dict[str, Any]] = []
    cid = log.next_capture_id(src.source_id)

    def on_response(resp: Any) -> None:
        try:
            ctype = (resp.headers or {}).get("content-type", "")
            if "json" not in ctype:
                return
            body = resp.body()
            if len(body) > MAX_RESPONSE_BYTES:
                return
            try:
                parsed: Any = json.loads(body)
            except ValueError:
                parsed = body.decode("utf-8", "replace")
            req = resp.request
            responses.append(
                {
                    "url": resp.url,
                    "status": resp.status,
                    "method": req.method,
                    "post_data": req.post_data,
                    "body": parsed,
                }
            )
        except Exception:  # noqa: BLE001 - a lost response must not abort the capture
            return

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1200}, user_agent=None)
            page.on("response", on_response)
            nav = page.goto(src.url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            status = nav.status if nav else None
            page.wait_for_timeout(SETTLE_MS)
            final_url = page.url
            html = page.content().encode()
            texts = []
            for i, frame in enumerate(page.frames):
                try:
                    t = frame.inner_text("body", timeout=5000)
                except Exception:  # noqa: BLE001
                    t = ""
                texts.append(f"=== frame {i}: {frame.url}\n{t}\n")
            text = "".join(texts).encode()
            if status in (403, 429) or looks_like_challenge(html):
                return [
                    _record(
                        log,
                        src,
                        started,
                        capture_id=cid,
                        http_status=status,
                        outcome="blocked",
                        raw_path=None,
                        sha256=None,
                        content_hash=None,
                        bytes=None,
                        error=f"HTTP {status} or challenge page",
                    )
                ]
            shot = page.screenshot(full_page=True, type="jpeg", quality=60)
        finally:
            browser.close()

    responses.sort(key=lambda r: (r["url"], r["method"], str(r["post_data"])))
    bundle = json.dumps(
        {"final_url": final_url, "responses": responses}, indent=1, sort_keys=True
    ).encode()
    extra = {"capture_id": cid, "final_url": final_url}
    common = dict(
        source_id=src.source_id,
        url=final_url,
        fetched_at=started_dt,
        http_status=status,
        parser_hint="doh_dashboard",
        extra=extra,
        root=root,
    )

    r_text = rawstore.save(data=text, ext="txt", capture_key="text", **common)  # type: ignore[arg-type]
    r_resp = rawstore.save(data=bundle, ext="json", capture_key="responses", **common)  # type: ignore[arg-type]
    changed = "changed" in (r_text.outcome, r_resp.outcome)
    # html and screenshot carry render noise; keep them only alongside a substantive change.
    for key, data, ext in (("html", html, "html"), ("screenshot", shot, "jpg")):
        if changed or rawstore.latest_manifest(src.source_id, root, key=key) is None:
            rawstore.save(data=data, ext=ext, capture_key=key, force=True, **common)  # type: ignore[arg-type]

    return [
        _record(
            log,
            src,
            started,
            capture_id=cid,
            http_status=status,
            outcome="changed" if changed else "unchanged",
            raw_path=r_text.raw_path,
            sha256=r_text.sha256,
            content_hash=r_text.content_hash,
            bytes=r_text.bytes,
            error=None,
        )
    ]
