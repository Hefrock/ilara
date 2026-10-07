"""Dashboard probe (WP2a). Captures once through the normal browser path, then writes a
summary that the owner or agent turns into ``docs/probe_report.md``.

Run: ``uv run python -m ingest.capture.probe --out probe-out``
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from ingest import paths, rawstore, registry
from ingest.capture import runner
from ingest.capture_log import CaptureLog

PLATFORMS = {
    "powerbi": ("powerbi.com", "analysis.windows.net", "pbidedicated"),
    "arcgis": ("arcgis.com", "arcgis/rest", "FeatureServer", "MapServer"),
    "tableau": ("tableau", "public.tableau.com"),
    "socrata": ("socrata", "/resource/", "/api/views/"),
}


def guess_platform(urls: list[str]) -> list[str]:
    found: Counter[str] = Counter()
    for u in urls:
        for name, markers in PLATFORMS.items():
            if any(m.lower() in u.lower() for m in markers):
                found[name] += 1
    return [n for n, _ in found.most_common()]


def summarise(root: Path, capture_id: str) -> dict:
    arts: dict[str, dict] = {}
    for mp in rawstore.iter_manifests("doh_dashboard", root):
        m = rawstore.load_manifest(mp)
        if (m.get("extra") or {}).get("capture_id") == capture_id:
            arts[m["capture_key"]] = m
    out: dict = {
        "capture_id": capture_id,
        "artefacts": {k: {"raw_path": v["raw_path"], "bytes": v["bytes"]} for k, v in arts.items()},
    }
    if "responses" in arts:
        bundle = json.loads(rawstore.read_payload(arts["responses"], root))
        urls = [r["url"] for r in bundle["responses"]]
        out["final_url"] = bundle["final_url"]
        out["json_responses"] = len(urls)
        out["json_hosts"] = sorted({urlsplit(u).netloc for u in urls})
        out["json_urls"] = urls[:200]
        out["platform_guess"] = guess_platform(urls + [bundle["final_url"]])
    if "text" in arts:
        text = rawstore.read_payload(arts["text"], root).decode("utf-8", "replace")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        out["text_lines"] = len(lines)
        out["text_head"] = lines[:300]
        out["county_mentions"] = sorted(set(re.findall(r"\b([A-Z][a-z]+) County\b", text)))
        out["update_stamps"] = sorted(
            set(
                re.findall(
                    r"(?i)(?:updated|as of)[:\s]+[A-Za-z]*\.?\s*"
                    r"\d{1,2}[/ ,.-]+\d{1,2}[/ ,.-]+\d{2,4}",
                    text,
                )
            )
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id")
    ap.add_argument("--out", default="probe-out")
    a = ap.parse_args()
    root = paths.repo_root()
    src = registry.load(root)["doh_dashboard"]
    log = CaptureLog(a.run_id, root)
    recs = runner.run([src], log, root)
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {"records": [r.__dict__ for r in recs]}
    if recs and recs[0].outcome in ("changed", "unchanged"):
        summary.update(summarise(root, recs[0].capture_id))
    (outdir / "probe_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ("text_head", "json_urls")},
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
