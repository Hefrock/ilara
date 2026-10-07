"""T6.16: nothing under ``project/outputs/`` is tracked unless the validation gate passed."""

from __future__ import annotations

import json
from pathlib import Path

from ingest.guards.gitutil import git


def gate_passed(root: Path) -> bool:
    p = root / "data" / "validation_gate.json"
    if not p.exists():
        return False
    return json.loads(p.read_text()).get("status") == "pass"


def check(root: Path) -> list[str]:
    tracked = [f for f in git(root, "ls-files", "project/outputs").splitlines() if f]
    if tracked and not gate_passed(root):
        return [f"{f} is tracked but data/validation_gate.json is not pass" for f in tracked]
    return []
