from __future__ import annotations

from typing import Any

import pytest
import yaml

from ingest import schedule

from conftest import REPO

WF = REPO / ".github" / "workflows"
WRITERS = ["capture-dashboard.yml", "capture-light.yml", "release.yml", "probe.yml"]


def load(name: str) -> dict[str, Any]:
    doc = yaml.safe_load((WF / name).read_text())
    doc["on"] = doc.pop(True, doc.get("on"))  # PyYAML reads `on:` as True
    return doc


def crons(doc: dict[str, Any]) -> list[str]:
    return [c["cron"] for c in (doc["on"].get("schedule") or [])]


@pytest.mark.parametrize("name", sorted(p.name for p in WF.glob("*.yml")))
def test_parses_with_required_keys(name: str) -> None:  # T0.6
    doc = load(name)
    assert "concurrency" in doc and "permissions" in doc
    assert set(doc["permissions"]) <= {"contents", "issues"}
    if name in WRITERS:
        assert doc["concurrency"]["cancel-in-progress"] is False
        assert doc["permissions"] == {"contents": "write", "issues": "write"}


@pytest.mark.parametrize("name", WRITERS)
def test_guards_run_before_push(name: str) -> None:  # T0.6, E18
    steps = next(iter(load(name)["jobs"].values()))["steps"]
    names = [s.get("name", "") for s in steps]
    runs = [s.get("run", "") for s in steps]
    push = next(i for i, r in enumerate(runs) if "push-with-retry" in r)
    guards = next(i for i, n in enumerate(names) if n.startswith("Guards"))
    assert guards < push
    g = runs[guards]
    for needle in ("guard paths --bot", "guard append-only", "guard size", "measles verify"):
        assert needle in g


def test_schedules_match_runbook() -> None:  # T2.8
    assert crons(load("capture-dashboard.yml")) == list(schedule.DASHBOARD_CRONS)
    assert crons(load("capture-light.yml")) == list(schedule.LIGHT_CRONS)
    assert crons(load("release.yml")) == list(schedule.RELEASE_CRONS)
    assert schedule.DASHBOARD_CRONS == ("0 18,20,22 * * 1,3,5", "0 13 * * 2,4,6")
    assert schedule.LIGHT_CRONS == ("30 14 * * *",)
    assert schedule.RELEASE_CRONS == ("30 13 * * 1",)


def test_ci_minimal_permissions() -> None:
    assert load("ci.yml")["permissions"] == {"contents": "read"}


def test_parse_step_cannot_block_raw_commit() -> None:  # E19
    steps = load("capture-dashboard.yml")["jobs"]["capture"]["steps"]
    names = [s.get("name", "") for s in steps]
    raw = names.index("Commit raw and capture log")
    parse = next(i for i, n in enumerate(names) if n.startswith("Parse"))
    assert raw < parse and steps[parse].get("continue-on-error") is True


def test_scripts_exist() -> None:
    for s in ("push-with-retry.sh", "commit-data.sh"):
        assert (REPO / ".github" / "scripts" / s).stat().st_mode & 0o111
