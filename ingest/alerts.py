"""Issue alerts (WP2e, HANDOFF 8.4).

One open issue per (label, source, failure type). A repeat failure comments on the open
issue; a later successful capture of that source closes it.

Data-quality flags that mean the parse could not trust a capture (ALERT_FLAG_CODES) also open
an issue, keyed by source and flag code, so a problem that is logged is never silent
(ADR 0016). Those issues close when no open flag with that code remains for the source, not
when the next capture succeeds.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from ingest import capture_log, schedule
from ingest.timeutil import parse_utc, utc_now

LABEL_FAILURE = "capture-failure"
LABEL_ANOMALY = "data-anomaly"
ALERT_FLAG_CODES = (
    "PARSE_SCHEMA_CHANGE",
    "COUNTY_COUNT_DROP",
    "COUNTY_SUM_MISMATCH",
    "DEMOGRAPHIC_SUM_MISMATCH",
    "DEFINITION_UNKNOWN",
)


@dataclass
class Alert:
    label: str
    title: str
    body: str
    source_id: str


def run_link() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run = os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run}" if repo and run else "(local run)"


def _crons_for(source_id: str) -> tuple[str, ...]:
    return schedule.DASHBOARD_CRONS if source_id == "doh_dashboard" else schedule.LIGHT_CRONS


def build_alerts(records: list[dict[str, Any]], history: list[dict[str, Any]]) -> list[Alert]:
    alerts: list[Alert] = []
    for r in records:
        if r["outcome"] in ("changed", "unchanged") and r.get("error"):
            alerts.append(_partial_alert(r))
            continue
        if r["outcome"] not in ("failed", "blocked"):
            continue
        last_good = max(
            (
                h["finished_utc"]
                for h in history
                if h["source_id"] == r["source_id"] and capture_log.is_good(h)
            ),
            default="none recorded",
        )
        nxt = schedule.next_run(_crons_for(r["source_id"]), parse_utc(r["finished_utc"]))
        body = "\n".join(
            [
                f"**Failure type:** {r['outcome']}",
                f"**Source:** `{r['source_id']}` ({r['url']})",
                f"**Capture id:** `{r['capture_id']}`",
                f"**Run:** {run_link()}",
                f"**HTTP status:** {r.get('http_status')}",
                f"**Raw hash:** {r.get('sha256') or 'none (nothing saved)'}",
                f"**Last good capture:** {last_good}",
                f"**Next scheduled attempt:** {nxt.strftime('%Y-%m-%d %H:%M UTC')}",
                "",
                "```",
                (r.get("error") or "")[:1500],
                "```",
                "",
                "Blocked sources are not retried in a loop and are never worked around (I7).",
            ]
        )
        alerts.append(
            Alert(
                LABEL_FAILURE,
                f"[{LABEL_FAILURE}] {r['source_id']}: {r['outcome']}",
                body,
                r["source_id"],
            )
        )
    return alerts


def _partial_alert(r: dict[str, Any]) -> Alert:
    body = "\n".join(
        [
            "**Anomaly:** capture saved, but part of it did not complete",
            f"**Source:** `{r['source_id']}` ({r['url']})",
            f"**Capture id:** `{r['capture_id']}`",
            f"**Run:** {run_link()}",
            f"**Raw hash (text):** {r.get('sha256')}",
            "",
            "```",
            (r.get("error") or "")[:1500],
            "```",
            "",
            "Raw was saved first (I1); the parse step decides what the partial capture supports.",
        ]
    )
    return Alert(
        LABEL_ANOMALY, f"[{LABEL_ANOMALY}] {r['source_id']}: partial capture", body, r["source_id"]
    )


def _flag_key(source_id: str, code: str) -> str:
    return f"{source_id}/{code}"


def flag_alerts(
    records: list[dict[str, Any]], flags: list[dict[str, Any]], source_of: dict[str, str]
) -> list[Alert]:
    """One alert per (source, code) for open parser flags raised in this run: flags on raw
    files fetched at or after the run's first capture of that source. ``source_of`` maps a
    raw sha256 to its source."""
    started: dict[str, str] = {}
    for r in records:
        started[r["source_id"]] = min(r["started_utc"], started.get(r["source_id"], "~"))
    groups: dict[str, list[dict[str, Any]]] = {}
    for fl in flags:
        src = source_of.get(fl.get("ref_raw_sha256") or "")
        if fl["code"] not in ALERT_FLAG_CODES or src not in started:
            continue
        when = fl["fetched_at_utc"]
        stamp = when if isinstance(when, str) else when.strftime("%Y-%m-%dT%H:%M:%SZ")
        if stamp >= started[src]:
            groups.setdefault(_flag_key(src, fl["code"]), []).append(fl)
    out = []
    for key, fls in sorted(groups.items()):
        src, code = key.split("/", 1)
        lines = sorted({f"- {fl['description']}" for fl in fls})
        body = "\n".join(
            [
                f"**Flag:** `{code}` raised while parsing `{src}`",
                f"**Run:** {run_link()}",
                "",
                *lines[:20],
                "",
                "Raw was saved first (I1); flagged rows are held back or labelled, never "
                "guessed (I5). This issue closes when the newest capture of the source parses "
                "without this flag.",
            ]
        )
        out.append(Alert(LABEL_ANOMALY, f"[{LABEL_ANOMALY}] {key}: data-quality flag", body, key))
    return out


def cleared_flag_keys(
    sources: set[str],
    flags: list[dict[str, Any]],
    source_of: dict[str, str],
    newest: set[str],
) -> set[str]:
    """Flag-alert keys whose source's newest capture carries no open flag with that code.
    ``newest`` holds the raw sha256s of each source's newest capture. Older flags that stay
    open by design (a dead capture, a chart a capture lacked) no longer keep an issue open
    once the source parses cleanly again (ADR 0019, amending ADR 0016)."""
    still = {
        _flag_key(source_of.get(fl.get("ref_raw_sha256") or "", ""), fl["code"])
        for fl in flags
        if fl.get("ref_raw_sha256") in newest
    }
    return {_flag_key(s, c) for s in sources for c in ALERT_FLAG_CODES} - still


def newest_capture(manifests: list[dict[str, Any]]) -> set[str]:
    """Raw sha256s of each source's newest capture (all files saved at its newest time)."""
    last: dict[str, str] = {}
    for m in manifests:
        last[m["source_id"]] = max(m["fetched_at_utc"], last.get(m["source_id"], ""))
    return {m["sha256"] for m in manifests if m["fetched_at_utc"] == last[m["source_id"]]}


def recovered_sources(records: list[dict[str, Any]]) -> set[str]:
    return {
        r["source_id"]
        for r in records
        if r["outcome"] in ("changed", "unchanged") and not r.get("error")
    }


class GitHubIssues:
    def __init__(self, repo: str, token: str, transport: httpx.BaseTransport | None = None):
        self.repo = repo
        self.http = httpx.Client(
            base_url="https://api.github.com",
            transport=transport,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def open_issues(self, label: str) -> list[dict[str, Any]]:
        r = self.http.get(
            f"/repos/{self.repo}/issues", params={"labels": label, "state": "open", "per_page": 100}
        )
        r.raise_for_status()
        return [i for i in r.json() if "pull_request" not in i]

    def apply(self, alerts: list[Alert], recovered: set[str]) -> list[str]:
        actions: list[str] = []
        open_ = self.open_issues(LABEL_FAILURE) + self.open_issues(LABEL_ANOMALY)
        by_title = {i["title"]: i for i in open_}
        for a in alerts:
            if a.title in by_title:
                n = by_title[a.title]["number"]
                self.http.post(
                    f"/repos/{self.repo}/issues/{n}/comments", json={"body": a.body}
                ).raise_for_status()
                actions.append(f"commented #{n}")
            else:
                r = self.http.post(
                    f"/repos/{self.repo}/issues",
                    json={"title": a.title, "body": a.body, "labels": [a.label]},
                )
                r.raise_for_status()
                actions.append(f"opened #{r.json()['number']}")
        failing_now = {a.source_id for a in alerts}
        for issue in open_:
            src = issue["title"].split("] ", 1)[-1].split(":", 1)[0]
            if src in recovered and src not in failing_now:
                n = issue["number"]
                self.http.post(
                    f"/repos/{self.repo}/issues/{n}/comments",
                    json={
                        "body": f"Recovered: successful capture at {utc_now():%Y-%m-%d %H:%M} UTC "
                        f"({run_link()})."
                    },
                ).raise_for_status()
                self.http.patch(
                    f"/repos/{self.repo}/issues/{n}",
                    json={"state": "closed", "state_reason": "completed"},
                ).raise_for_status()
                actions.append(f"closed #{n}")
        return actions
