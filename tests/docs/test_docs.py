"""WP7 documentation checks: T7.1, T7.2 and T7.4 (T7.3 needs the write-up's figures)."""

from __future__ import annotations

import re
from pathlib import Path

from conftest import REPO

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _docs() -> list[Path]:
    return [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md"))]


def test_readme_notices() -> None:  # T7.1
    text = (REPO / "README.md").read_text().lower()
    for phrase in ("unofficial", "counts are a floor", "forecasts withheld until validated"):
        assert phrase in text, phrase


def test_internal_links_resolve() -> None:  # T7.2
    broken = []
    for doc in _docs():
        for target in LINK.findall(doc.read_text()):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue  # external links and in-page anchors
            path = (doc.parent / target.split("#")[0]).resolve()
            if not path.exists():
                broken.append(f"{doc.relative_to(REPO)} -> {target}")
    assert not broken, broken


def _done_packages() -> set[str]:
    rows = (REPO / "docs" / "PROGRESS.md").read_text().splitlines()
    return {m.group(1) for line in rows if (m := re.match(r"\| (WP\d) [^|]*\| done \|", line))}


def test_no_open_register_item_under_a_done_package() -> None:  # T7.4
    done = _done_packages()
    bad = []
    for line in (REPO / "docs" / "sources.md").read_text().splitlines():
        if not re.match(r"\| U\d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        owners = set(re.findall(r"WP\d", cells[2]))
        status = cells[-1]
        closed = "VERIFIED" in status and "UNVERIFIED" not in status and "PARTIAL" not in status
        if owners & done and not closed and "deferred to" not in status.lower():
            bad.append(cells[0])
    assert not bad, f"register items open under a done work package: {bad}"
