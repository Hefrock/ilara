"""Append-only guard (T2.11): existing files under protected trees are never edited or deleted."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ingest.guards.gitutil import git

PROTECTED = (
    "data/raw/",
    "data/capture_log/",
    "data/curated/",
    "data/sensitivity/",
    "data/seed/",
    "data/releases/",
)


# Seed manifests may gain entries but never change or lose one (HANDOFF 4.1).
SEED_MANIFESTS = ("data/seed/MANIFEST.json", "data/sensitivity/seed/MANIFEST.json")


def manifest_only_added(old: str, new: str) -> bool:
    try:
        before, after = json.loads(old)["files"], json.loads(new)["files"]
    except (ValueError, KeyError, TypeError):
        return False
    return all(after.get(name) == entry for name, entry in before.items())


def check_name_status(lines: list[str], additive: Callable[[str], bool] | None = None) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        status, files = parts[0], parts[1:]
        if status.startswith("A"):
            continue
        for f in files:
            if (
                status.startswith("M")
                and f in SEED_MANIFESTS
                and additive is not None
                and additive(f)
            ):
                continue
            if f.startswith(PROTECTED):
                out.append(f"{status} {f}: protected path is append-only")
    return out


def check_range(root: Path, base: str, head: str = "HEAD") -> list[str]:
    diff = git(root, "diff", "--name-status", "--no-renames", f"{base}", f"{head}")

    def additive(path: str) -> bool:
        return manifest_only_added(
            git(root, "show", f"{base}:{path}"), git(root, "show", f"{head}:{path}")
        )

    return check_name_status(diff.splitlines(), additive)
