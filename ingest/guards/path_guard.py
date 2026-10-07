"""Path guard: bot commits may touch only ``data/`` (WP0 task 3, T0.3)."""

from __future__ import annotations

from pathlib import Path

from ingest.guards.gitutil import git

BOT_MARKERS = ("[bot]", "github-actions")
ALLOWED_PREFIX = "data/"


def is_bot(author: str) -> bool:
    return any(m in author for m in BOT_MARKERS)


def check_files(files: list[str]) -> list[str]:
    return [
        f"bot commit touches {f} (only {ALLOWED_PREFIX} allowed)"
        for f in files
        if not f.startswith(ALLOWED_PREFIX)
    ]


def check_range(root: Path, rev_range: str, *, all_bot: bool = False) -> list[str]:
    """Check every commit in ``rev_range``; ``all_bot`` treats every commit as a bot commit."""
    out: list[str] = []
    shas = git(root, "rev-list", rev_range).split()
    for sha in shas:
        author = git(root, "log", "-1", "--format=%an <%ae>", sha).strip()
        if not (all_bot or is_bot(author)):
            continue
        files = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", sha).split("\n")
        out += [f"{sha[:10]}: {v}" for v in check_files([f for f in files if f])]
    return out
