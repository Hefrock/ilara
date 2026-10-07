"""Issue alerts (WP2e, HANDOFF 8.4).

One open issue per (label, source, failure type). A repeat failure comments on the open
issue; a later successful capture of that source closes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from ingest import schedule
from ingest.timeutil import parse_utc, utc_now

LABEL_FAILURE = "capture-failure"
LABEL_ANOMALY = "data-anomaly"


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
                if h["source_id"] == r["source_id"] and h["outcome"] in ("changed", "unchanged")
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
