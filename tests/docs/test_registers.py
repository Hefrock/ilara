"""T0.7: docs/BLOCKERS.md and docs/PROGRESS.md follow their templates."""

from __future__ import annotations

from ingest.guards import hygiene

from conftest import REPO

COLUMNS = [
    "ID",
    "Opened",
    "Type",
    "Blocks",
    "Needed from the owner",
    "Why",
    "Status",
    "Resolved",
    "Resolution",
]


def _rows(text: str) -> list[list[str]]:
    return [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.startswith("|")
    ]


def test_blockers_register() -> None:
    text = (REPO / "docs" / "BLOCKERS.md").read_text()
    rows = _rows(text)
    assert rows[0] == COLUMNS
    entries = [r for r in rows[2:]]
    ids = [r[0] for r in entries]
    assert ids and len(ids) == len(set(ids))
    assert all(i.startswith("B") and i[1:].isdigit() for i in ids)
    for r in entries:
        assert len(r) == len(COLUMNS)
        assert r[2] in ("action", "decision", "info")
        assert r[6] in ("open", "resolved", "withdrawn")
        if r[6] == "resolved":
            assert r[7] and r[8]
    assert hygiene.scan_text("docs/BLOCKERS.md", text) == []


def test_progress_lists_every_package_and_gate() -> None:
    text = (REPO / "docs" / "PROGRESS.md").read_text()
    for wp in range(8):
        assert f"| WP{wp} " in text
    for g in range(6):
        assert f"| G{g} " in text
