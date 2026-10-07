"""Append-only capture log (E04): one JSONL file per workflow run."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ingest import paths
from ingest.timeutil import utc_now

OUTCOMES = ("changed", "unchanged", "failed", "blocked")


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

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"bad outcome {self.outcome!r}")


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
        self._seq = 0

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
