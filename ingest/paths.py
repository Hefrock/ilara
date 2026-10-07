"""Repository paths. Every module resolves data locations through here.

``MEASLES_ROOT`` overrides the repository root (tests point it at a temp dir).
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("MEASLES_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def data_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data"


def raw_dir(root: Path | None = None) -> Path:
    return data_dir(root) / "raw"


def capture_log_dir(root: Path | None = None) -> Path:
    return data_dir(root) / "capture_log"


def curated_dir(root: Path | None = None) -> Path:
    return data_dir(root) / "curated"


def sensitivity_dir(root: Path | None = None) -> Path:
    return data_dir(root) / "sensitivity"


def reference_dir(root: Path | None = None) -> Path:
    return data_dir(root) / "reference"


def registry_path(root: Path | None = None) -> Path:
    return data_dir(root) / "registry" / "source_registry.yml"
