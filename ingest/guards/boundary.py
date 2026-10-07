"""Layer boundary (I8, T0.2): ``project/`` reads data only through ``ingest.access``."""

from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_INGEST = {"ingest.access"}
FORBIDDEN_STRINGS = ("data/raw", "data/capture_log")


def check_tree(project_dir: Path) -> list[str]:
    out: list[str] = []
    for py in sorted(project_dir.rglob("*.py")):
        src = py.read_text()
        name = py.as_posix()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            out.append(f"{name}: syntax error {e}")
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "ingest":
                    mods = [f"ingest.{a.name}" for a in node.names]
                else:
                    mods = [node.module]
            for m in mods:
                if (m == "ingest" or m.startswith("ingest.")) and m not in ALLOWED_INGEST:
                    line = getattr(node, "lineno", 0)
                    out.append(f"{name}:{line}: imports {m} (only ingest.access allowed)")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for s in FORBIDDEN_STRINGS:
                    if s in node.value:
                        out.append(f"{name}:{getattr(node, 'lineno', 0)}: references {s}")
    return out
