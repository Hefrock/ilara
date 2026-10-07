"""Size budget (HANDOFF 8.3 rule 4, T0.4)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MB = 1024 * 1024
TOTAL_WARN = 500 * MB
TOTAL_FAIL = 900 * MB
FILE_WARN = 50 * MB
FILE_FAIL = 95 * MB
CACHES = {".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__"}


@dataclass
class SizeReport:
    total_bytes: int
    warnings: list[str]
    failures: list[str]


def evaluate(total_bytes: int, file_sizes: dict[str, int]) -> SizeReport:
    warns: list[str] = []
    fails: list[str] = []
    if total_bytes > TOTAL_FAIL:
        fails.append(f"repository {total_bytes / MB:.1f} MB exceeds {TOTAL_FAIL // MB} MB")
    elif total_bytes > TOTAL_WARN:
        warns.append(f"repository {total_bytes / MB:.1f} MB exceeds {TOTAL_WARN // MB} MB")
    for name, size in sorted(file_sizes.items()):
        if size > FILE_FAIL:
            fails.append(f"{name} is {size / MB:.1f} MB (limit {FILE_FAIL // MB} MB)")
        elif size > FILE_WARN:
            warns.append(f"{name} is {size / MB:.1f} MB (warn at {FILE_WARN // MB} MB)")
    return SizeReport(total_bytes, warns, fails)


def measure(root: Path) -> tuple[int, dict[str, int]]:
    total = 0
    files: dict[str, int] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir.parts[:1] in ((".venv",), ("node_modules",)) or set(rel_dir.parts) & CACHES:
            dirnames[:] = []
            continue
        for fn in filenames:
            p = Path(dirpath) / fn
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            total += sz
            if rel_dir.parts[:1] != (".git",):
                files[(rel_dir / fn).as_posix()] = sz
    return total, files
