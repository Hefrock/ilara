"""Append-only guard (T2.11): existing files under protected trees are never edited or deleted."""

from __future__ import annotations

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


def check_name_status(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        status, files = parts[0], parts[1:]
        if status.startswith("A"):
            continue
        for f in files:
            if f.startswith(PROTECTED):
                out.append(f"{status} {f}: protected path is append-only")
    return out


def check_range(root: Path, base: str, head: str = "HEAD") -> list[str]:
    diff = git(root, "diff", "--name-status", "--no-renames", f"{base}", f"{head}")
    return check_name_status(diff.splitlines())
