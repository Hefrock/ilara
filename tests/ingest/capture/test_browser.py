"""Dashboard browser capture against a fake Power BI report, fully offline.

Runs only when a Chromium binary is available (``MEASLES_CHROMIUM`` or Playwright's own).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from ingest import rawstore, registry
from ingest.capture import browser
from ingest.capture_log import CaptureLog

REPORT = "https://report.test/view?r=fake"
API = "https://wabi-test.analysis.usgovcloudapi.net/public/reports/querydata?synchronous=true"
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

TABS = [
    "Overview",
    "Cases by Age and Time",
    "Hospitalizations",
    "Cases by County",
    "Community Transmission",
    "Measles Vaccine Administered",
]

PAGE = """<!doctype html><html><body>
<h1>2026 Overview: Pennsylvania Measles Cases</h1><div>Last Updated: October 5, 2026</div>
<div id="slicers">
 <div class="ui-role-button-text selected" title="Year to date">Year to date</div>
 <div class="ui-role-button-text" title="January - March">January - March</div>
 <div class="ui-role-button-text" title="April - Present">April - Present</div>
</div>
<div id="content">Total cases 1,004</div>
<div id="tabs">TABS</div>
<script>
const API = "API_URL";
function q(tab, slicer) {
  const sel = tab === "Measles Vaccine Administered" ? "record_id" : "County";
  const body = {queries: [{Query: {Commands: [{SemanticQueryDataShapeCommand: {Query: {
    Select: [{Column: {Property: sel}, Name: "T." + sel}]}}}]}}], tab: tab, slicer: slicer};
  return fetch(API, {method: "POST", body: JSON.stringify(body)}).then(r => r.json());
}
function show(tab) {
  const slicer = document.querySelector("[title].selected").getAttribute("title");
  q(tab, slicer).then(d => {
    document.getElementById("content").innerText = tab + " | " + slicer + " | " + d.text;
  });
}
document.querySelectorAll("#tabs .ui-role-button-text").forEach(
  el => el.addEventListener("click", () => show(el.innerText)));
document.querySelectorAll("#slicers [title]").forEach(el => el.addEventListener("click", () => {
  document.querySelectorAll("#slicers [title]").forEach(x => x.classList.remove("selected"));
  el.classList.add("selected"); show("Overview");
}));
</script></body></html>"""


def _fake_report(page: Any) -> None:
    tabs = "".join(f'<div class="ui-role-button-text">{t}</div>' for t in TABS)
    html = PAGE.replace("TABS", tabs).replace("API_URL", API)

    def handle(route: Any) -> None:
        req = route.request
        if req.url.startswith(REPORT):
            route.fulfill(status=200, content_type="text/html", body=html)
        elif req.url.startswith(API.split("?")[0]):
            q = json.loads(req.post_data)
            text = "Lancaster 391; Mifflin 118" if q["tab"] == "Cases by County" else "ok"
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"text": text, "results": []}),
            )
        else:
            route.abort()

    page.route("**/*", handle)


def _default_browser_works() -> bool:
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    exe = os.environ.get("MEASLES_CHROMIUM") or (CHROMIUM if Path(CHROMIUM).exists() else None)
    if exe:
        monkeypatch.setenv("MEASLES_CHROMIUM", exe)
    elif not _default_browser_works():
        pytest.skip("no Chromium available")
    monkeypatch.setattr(browser, "SETTLE_MS", 200)
    monkeypatch.setattr(browser, "VIEW_SETTLE_MS", 300)
    monkeypatch.setattr(browser, "NAV_TIMEOUT_MS", 15_000)


def _src(root: Path) -> registry.Source:
    return registry.load(root)["doh_dashboard"].model_copy(update={"url": REPORT})


def test_views_captured_and_case_level_refused(root: Path, fast: None) -> None:
    log = CaptureLog("t1", root)
    [rec] = browser.capture_browser(
        _src(root), log, root, robots_allowed=lambda u: True, page_hook=_fake_report
    )
    assert rec.outcome == "changed"
    # The vaccine tab's fake query selects record_id: refused, reported, never saved.
    assert rec.error and "refused by the case-level safeguard" in rec.error
    mans = {
        m["capture_key"]: m
        for m in map(rawstore.load_manifest, rawstore.iter_manifests("doh_dashboard", root))
    }
    assert {"text", "responses", "html", "screenshot_overview_ytd", "screenshot_county"} <= set(
        mans
    )
    text = rawstore.read_payload(mans["text"], root).decode()
    for v in browser.VIEWS:
        assert f"=== view: {v.key} |" in text
    assert "Cases by County | Year to date | Lancaster 391; Mifflin 118" in text
    assert "Overview | April - Present" in text
    bundle = json.loads(rawstore.read_payload(mans["responses"], root))
    assert all(v["ok"] for v in bundle["views"])
    assert [v["slicer_selected"] for v in bundle["views"][:4]] == [
        "Year to date",
        "April - Present",
        "January - March",
        "Year to date",
    ]
    kept_views = {r["view"] for r in bundle["responses"]}
    assert "county" in kept_views and "vaccine" not in kept_views
    assert "record_id" not in json.dumps(bundle["responses"])
    assert any(s["kept"].startswith("refused") for s in bundle["seen"])


def test_unchanged_second_capture_saves_nothing_new(root: Path, fast: None) -> None:
    for run in ("t1", "t2"):
        browser.capture_browser(
            _src(root),
            CaptureLog(run, root),
            root,
            robots_allowed=lambda u: True,
            page_hook=_fake_report,
        )
    log = (root / "data/capture_log").rglob("t2.jsonl")
    [line] = next(log).read_text().splitlines()
    assert json.loads(line)["outcome"] == "unchanged"
    assert len(list(rawstore.iter_manifests("doh_dashboard", root))) == 5


def test_robots_disallow_blocks_before_browser(root: Path) -> None:
    [rec] = browser.capture_browser(
        _src(root), CaptureLog("t3", root), root, robots_allowed=lambda u: False
    )
    assert rec.outcome == "blocked" and rec.raw_path is None


def test_hidden_tab_cannot_be_clicked() -> None:
    with pytest.raises(ValueError):
        browser._click_tab(object(), "Epidemic Curve")
    assert "Epidemic Curve" not in browser.ALLOWED_TABS
