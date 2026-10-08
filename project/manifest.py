"""Run manifests for model runs (I9): git commit, data release tag, seed, parameters, inputs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def inputs_digest(raw_refs: list[str]) -> str:
    """One hash over the sorted raw references a run read, so two runs on the same data agree."""
    return hashlib.sha256("\n".join(sorted(set(raw_refs))).encode()).hexdigest()


def write(
    out_dir: Path,
    kind: str,
    seed: int,
    params: dict[str, Any],
    inputs: dict[str, list[str]],
    extra: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "kind": kind,
        "created_utc": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "data_release": _git("describe", "--tags", "--match", "data-*", "--abbrev=0"),
        "seed": seed,
        "params": params,
        "inputs": {
            t: {"raw_files": len(set(r)), "digest": inputs_digest(r)} for t, r in inputs.items()
        },
        **(extra or {}),
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True, default=str) + "\n")
    return path
