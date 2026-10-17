"""Append-only capture log (E04): one JSONL file per workflow run."""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ingest import paths
from ingest.timeutil import utc_now

OUTCOMES = ("changed", "unchanged", "failed", "blocked")
GOOD_OUTCOMES = ("changed", "unchanged")

# Dashboard views reached by a click (all but the first, which shows on load). Keys match
# ``ingest.capture.browser.VIEWS`` (tested). A dashboard capture whose error names every one of
# them, or says the report is unavailable, did not capture the report.
DASHBOARD_CLICK_VIEWS = (
    "overview_april",
    "overview_janmar",
    "overview_reset",
    "age_time",
    "epi_curve",
    "hospitalizations",
    "county",
    "community_transmission",
    "vaccine",
)
# Views added after captures began. Records from before never tried them, so a dead report is
# one whose error names every click view except these (a dead report fails all of them anyway).
LATER_CLICK_VIEWS = frozenset({"epi_curve"})  # added 2026-10-17 (B18)
UNAVAILABLE_MARKER = "report unavailable"
_VIEW_AT = re.compile(r"(?:^|; )(\w+): ")


def problem(r: dict[str, Any]) -> str | None:
    """Why a capture did not save the source's content (``report unavailable``, ``failed`` or
    ``blocked``), or None for a good capture."""
    if r["source_id"] == "doh_dashboard" and r["outcome"] != "blocked":
        err = r.get("error") or ""
        if UNAVAILABLE_MARKER in err or set(DASHBOARD_CLICK_VIEWS) - LATER_CLICK_VIEWS <= set(
            _VIEW_AT.findall(err)
        ):
            return UNAVAILABLE_MARKER
    if r["outcome"] not in GOOD_OUTCOMES:
        return str(r["outcome"])
    return None


def is_good(r: dict[str, Any]) -> bool:
    """A capture that saved the source's content: outcome changed or unchanged, and for the
    dashboard, the report itself was reached. Logs from before this check (2026-10-13 to
    2026-10-15) recorded captures of a deleted report as changed or unchanged; they are judged
    here from what they recorded, without editing the log (I1)."""
    return problem(r) is None


def current_trigger() -> str:
    """What started this run: the GitHub event (``schedule``, ``workflow_dispatch``) or
    ``local``."""
    return os.environ.get("GITHUB_EVENT_NAME") or "local"


@dataclass
class CaptureRecord:
    capture_id: str
    source_id: str
    url: str
    started_utc: str
    finished_utc: str
    http_status: int | None
    outcome: str
    raw_path: str | None
    sha256: str | None
    content_hash: str | None
    bytes: int | None
    runner: str
    error: str | None = None
    trigger: str | None = None  # absent in records written before 2026-10-15

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"bad outcome {self.outcome!r}")
        if self.trigger is None:
            self.trigger = current_trigger()


def default_run_id() -> str:
    gh = os.environ.get("GITHUB_RUN_ID")
    if gh:
        return f"gh-{gh}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    return f"local-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


def runner_label() -> str:
    if os.environ.get("GITHUB_ACTIONS"):
        return f"github-{os.environ.get('RUNNER_ENVIRONMENT', 'hosted')}"
    return "local"


class CaptureLog:
    def __init__(self, run_id: str | None = None, root: Path | None = None) -> None:
        self.run_id = run_id or default_run_id()
        self.root = root or paths.repo_root()
        now = utc_now()
        self.path = (
            paths.capture_log_dir(self.root) / now.strftime("%Y-%m") / f"{self.run_id}.jsonl"
        )
        self.records: list[CaptureRecord] = []
        # Continue numbering when a later step of the same run appends to the same file.
        self._seq = len(self.path.read_text().splitlines()) if self.path.exists() else 0

    def next_capture_id(self, source_id: str) -> str:
        self._seq += 1
        return f"{self.run_id}:{self._seq:02d}:{source_id}"

    def append(self, rec: CaptureRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(asdict(rec), sort_keys=True) + "\n")
        self.records.append(rec)


def read_all(root: Path | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base = paths.capture_log_dir(root)
    if not base.exists():
        return out
    for f in sorted(base.rglob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out
