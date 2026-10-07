from __future__ import annotations

from pathlib import Path

from ingest import cli, registry


def test_registry_loads_initial_sources(root: Path) -> None:
    reg = registry.load(root)
    for sid in (
        "doh_dashboard",
        "doh_measles_page",
        "doh_newsroom",
        "doh_han_index",
        "doh_han_pdf",
        "doh_school_imm_county",
        "doh_school_imm_school",
        "census_popest_totals",
        "census_popest_agesex",
        "census_commuting",
        "census_cartographic",
        "cdc_measles_national",
        "cdc_nwss_measles",
        "seed_statewide",
        "seed_t3_county",
        "seed_events",
    ):
        assert sid in reg
    assert reg["doh_dashboard"].access_path == "browser"


def test_dry_run(root: Path, capsys) -> None:
    assert cli.main(["capture", "--all-due", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "doh_dashboard" in out and "doh_han_index" not in out


def test_stub_commands_exit_zero(root: Path) -> None:
    for argv in (
        ["parse"],
        ["quality"],
        ["rebuild"],
        ["seed", "load"],
        ["release", "--week", "2026-W41"],
        ["dashboard", "build", "--public"],
    ):
        assert cli.main(argv) == 0


def test_verify_empty_root(root: Path) -> None:
    assert cli.main(["verify"]) == 0
