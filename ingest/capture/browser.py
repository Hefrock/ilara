"""Browser capture of the DOH dashboard (WP2a/2d).

One navigation per capture (I7). Within that single page load the capture clicks the visible
report tabs and the count-definition slicer (owner decision B15), in the fixed order of
``VIEWS``, and records each view. It never opens hidden pages and never builds its own queries;
``caseguard`` refuses any response that could hold case-level data (owner decision B16, I10).

Artefacts saved through the raw store (all share one ``capture_id``):

- ``text``: rendered text of every view, in ``VIEWS`` order (path B)
- ``responses``: JSON bodies from the report's data API, each tagged with its view (path A),
  plus ``seen``: every Power BI response with the reason its body was or was not kept
- ``html`` and ``screenshot_<view>``: saved only when ``text`` or ``responses`` changed, or none
  exists yet, because both carry render noise (8.3 storage rule 1)

robots.txt is checked through the polite HTTP client before the browser starts.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ingest import rawstore
from ingest.capture.caseguard import refusal_reason
from ingest.capture.http import UA_TOKEN, PoliteClient, looks_like_challenge
from ingest.capture_log import CaptureLog, CaptureRecord, runner_label
from ingest.registry import Source
from ingest.timeutil import iso_utc, utc_now

NAV_TIMEOUT_MS = 90_000
SETTLE_MS = 12_000
VIEW_SETTLE_MS = 6_000
CLICK_TIMEOUT_MS = 15_000
MAX_RESPONSE_BYTES = 5_000_000

# Bodies are kept only from the report's data API; static Power BI resources (visual code,
# themes) change with every Power BI release and carry no outbreak data.
DATA_API_MARKERS = ("analysis.usgovcloudapi.net", "analysis.windows.net")
SEEN_MARKERS = ("powerbi", "analysis.usgovcloudapi", "analysis.windows.net")

SLICER_DEFAULT = "Year to date"


@dataclass(frozen=True)
class View:
    key: str
    tab: str
    slicer: str | None = None  # slicer button to select on this view, if any


# Visible tabs only (docs/probe_report.md). Order matters: the Overview slicer is reset to its
# default before leaving the Overview tab so later tabs show their default definition.
VIEWS: tuple[View, ...] = (
    View("overview_ytd", "Overview"),
    View("overview_april", "Overview", "April - Present"),
    View("overview_janmar", "Overview", "January - March"),
    View("overview_reset", "Overview", SLICER_DEFAULT),
    View("age_time", "Cases by Age and Time"),
    View("hospitalizations", "Hospitalizations"),
    View("county", "Cases by County"),
    View("community_transmission", "Community Transmission"),
    View("vaccine", "Measles Vaccine Administered"),
)
ALLOWED_TABS = frozenset(v.tab for v in VIEWS)
SCREENSHOT_VIEWS = ("overview_ytd", "county")

Allowed = Callable[[str], bool | None]
PageHook = Callable[[Any], None]


def _robots_allowed(url: str) -> bool | None:
    client = PoliteClient()
    try:
        return client.allowed(url)
    finally:
        client.close()


def _launch_kwargs() -> dict[str, Any]:
    exe = os.environ.get("MEASLES_CHROMIUM")
    return {"executable_path": exe} if exe else {}


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


def _view_text(page: Any) -> str:
    parts = []
    for i, frame in enumerate(page.frames):
        try:
            t = frame.inner_text("body", timeout=5000)
        except Exception:  # noqa: BLE001
            t = ""
        parts.append(f"--- frame {i}\n{t}\n")
    return "".join(parts)


def _selected_slicer(page: Any) -> str | None:
    try:
        el = page.locator("[title].selected").first
        return el.get_attribute("title", timeout=2000) if el.count() else None
    except Exception:  # noqa: BLE001
        return None


def _click_tab(page: Any, tab: str) -> None:
    if tab not in ALLOWED_TABS:  # never reach hidden pages
        raise ValueError(f"tab {tab!r} is not an allowed visible tab")
    exact = re.compile(rf"^\s*{re.escape(tab)}\s*$")
    page.locator(".ui-role-button-text").filter(has_text=exact).first.click(
        timeout=CLICK_TIMEOUT_MS
    )


def _click_slicer(page: Any, label: str) -> None:
    page.locator(f'[title="{label}"]').first.click(timeout=CLICK_TIMEOUT_MS)


def capture_browser(
    src: Source,
    log: CaptureLog,
    root: Path,
    *,
    robots_allowed: Allowed = _robots_allowed,
    page_hook: PageHook | None = None,
) -> list[CaptureRecord]:
    """``page_hook`` lets offline tests route requests to a fake report; never set in use."""
    assert src.url
    started_dt = utc_now()
    started = iso_utc(started_dt)

    allowed = robots_allowed(src.url)
    none = dict(raw_path=None, sha256=None, content_hash=None, bytes=None)
    if allowed is False:
        return [
            _record(
                log,
                src,
                started,
                http_status=None,
                outcome="blocked",
                **none,
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
                **none,
                error="robots.txt unreachable",
            )
        ]

    from playwright.sync_api import sync_playwright

    cid = log.next_capture_id(src.source_id)
    responses: list[dict[str, Any]] = []
    seen: list[dict[str, Any]] = []
    refused: list[str] = []
    current = {"view": "load"}
    view_log: list[dict[str, Any]] = []
    texts: list[str] = []
    shots: dict[str, bytes] = {}

    def on_response(resp: Any) -> None:
        url = resp.url
        entry: dict[str, Any] = {"url": url, "status": resp.status, "view": current["view"]}
        try:
            req = resp.request
            entry["method"] = req.method
            ctype = (resp.headers or {}).get("content-type", "")
            entry["content_type"] = ctype
            if not any(m in url for m in DATA_API_MARKERS):
                entry["kept"] = "not data API"
                return
            body = resp.body()
            if len(body) > MAX_RESPONSE_BYTES:
                entry["kept"] = f"too large ({len(body)} bytes)"
                return
            try:
                parsed: Any = json.loads(body)
            except ValueError:
                entry["kept"] = "not json"
                return
            reason = refusal_reason(url, req.post_data, parsed)
            if reason:
                entry["kept"] = f"refused: {reason}"
                refused.append(f"{current['view']}: {reason}")
                return
            responses.append(
                {
                    "url": url,
                    "status": resp.status,
                    "method": req.method,
                    "post_data": req.post_data,
                    "view": current["view"],
                    "body": parsed,
                }
            )
            entry["kept"] = "yes"
        except Exception as e:  # noqa: BLE001 - a lost response must not abort the capture
            entry["kept"] = f"error: {type(e).__name__}: {str(e)[:200]}"
        finally:
            if any(m in url for m in SEEN_MARKERS):
                seen.append(entry)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**_launch_kwargs())
        try:
            # I7: identify the archive; keep the browser's own UA so the page renders normally.
            probe_page = browser.new_page()
            base_ua = probe_page.evaluate("navigator.userAgent")
            probe_page.close()
            page = browser.new_page(
                viewport={"width": 1600, "height": 1200}, user_agent=f"{base_ua} {UA_TOKEN}"
            )
            page.on("response", on_response)
            if page_hook is not None:
                page_hook(page)
            nav = page.goto(src.url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            status = nav.status if nav else None
            page.wait_for_timeout(SETTLE_MS)
            final_url = page.url
            html = page.content().encode()
            if status in (403, 429) or looks_like_challenge(html):
                return [
                    _record(
                        log,
                        src,
                        started,
                        capture_id=cid,
                        http_status=status,
                        outcome="blocked",
                        **none,
                        error=f"HTTP {status} or challenge page",
                    )
                ]
            on_tab = "Overview"
            for view in VIEWS:
                current["view"] = view.key
                entry: dict[str, Any] = {
                    "view": view.key,
                    "tab": view.tab,
                    "slicer_requested": view.slicer,
                }
                try:
                    if view.tab != on_tab:
                        _click_tab(page, view.tab)
                        on_tab = view.tab
                    if view.slicer:
                        _click_slicer(page, view.slicer)
                    page.wait_for_timeout(VIEW_SETTLE_MS)
                    entry["slicer_selected"] = _selected_slicer(page)
                    entry["ok"] = True
                except Exception as e:  # noqa: BLE001 - record and continue with the next view
                    entry["ok"] = False
                    entry["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                view_log.append(entry)
                header = (
                    f"=== view: {view.key} | tab: {view.tab} | slicer: "
                    f"{entry.get('slicer_selected')} | ok: {entry['ok']}\n"
                )
                texts.append(header + (_view_text(page) if entry["ok"] else ""))
                if entry["ok"] and view.key in SCREENSHOT_VIEWS:
                    shots[view.key] = page.screenshot(full_page=True, type="jpeg", quality=55)
        finally:
            browser.close()

    responses.sort(key=lambda r: (r["view"], r["url"], r["method"], str(r["post_data"])))
    seen.sort(key=lambda e: (e["view"], e["url"], e.get("method", "")))
    bundle = json.dumps(
        {
            "final_url": final_url,
            "views": view_log,
            "responses": responses,
            "seen": seen,
            "refused": refused,
        },
        indent=1,
        sort_keys=True,
    ).encode()
    text = "".join(texts).encode()
    extra = {
        "capture_id": cid,
        "final_url": final_url,
        "views_ok": sum(1 for v in view_log if v["ok"]),
        "views_total": len(VIEWS),
    }
    common: dict[str, Any] = dict(
        source_id=src.source_id,
        url=final_url,
        fetched_at=started_dt,
        http_status=status,
        parser_hint="doh_dashboard",
        extra=extra,
        root=root,
    )

    r_text = rawstore.save(data=text, ext="txt", capture_key="text", **common)
    r_resp = rawstore.save(data=bundle, ext="json", capture_key="responses", **common)
    changed = "changed" in (r_text.outcome, r_resp.outcome)
    keep = [("html", html, "html")] + [(f"screenshot_{k}", v, "jpg") for k, v in shots.items()]
    for key, data, ext in keep:
        if changed or rawstore.latest_manifest(src.source_id, root, key=key) is None:
            rawstore.save(data=data, ext=ext, capture_key=key, force=True, **common)

    problems = [f"{v['view']}: {v['error']}" for v in view_log if not v["ok"]]
    if refused:
        problems.append(f"{len(refused)} response(s) refused by the case-level safeguard")
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
            error="; ".join(problems) or None,
        )
    ]
