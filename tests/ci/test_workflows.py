from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from ingest import schedule

from conftest import REPO

WF = REPO / ".github" / "workflows"
WRITERS = ["capture-dashboard.yml", "capture-light.yml", "release.yml", "probe.yml", "reparse.yml"]


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
    assert schedule.DASHBOARD_CRONS == (
        "13 19 * * 1,3,5",
        "7 20 * * 1,3,5",
        "53 20 * * 1,3,5",
        "47 21 * * 1,3,5",
        "17 13 * * 2,4,6",
    )
    assert schedule.LIGHT_CRONS == ("30 14 * * *",)
    assert schedule.RELEASE_CRONS == ("23 13 * * 1",)


def test_ci_minimal_permissions() -> None:
    assert load("ci.yml")["permissions"] == {"contents": "read"}


def test_parse_step_cannot_block_raw_commit() -> None:  # E19
    steps = load("capture-dashboard.yml")["jobs"]["capture"]["steps"]
    names = [s.get("name", "") for s in steps]
    raw = names.index("Commit raw and capture log")
    parse = next(i for i, n in enumerate(names) if n.startswith("Parse"))
    assert raw < parse and steps[parse].get("continue-on-error") is True


def test_scripts_exist() -> None:
    for s in ("push-with-retry.sh", "commit-data.sh", "install-browser.sh"):
        assert (REPO / ".github" / "scripts" / s).stat().st_mode & 0o111


def test_reparse_follows_parser_changes_and_never_overlaps_a_dashboard_capture() -> None:
    doc = load("reparse.yml")  # ADR 0016
    paths = doc["on"]["push"]["paths"]
    assert doc["on"]["push"]["branches"] == ["main"]
    assert "ingest/parse/**" in paths and "ingest/curate/**" in paths
    assert doc["concurrency"]["group"] == load("capture-dashboard.yml")["concurrency"]["group"]
    steps = doc["jobs"]["reparse"]["steps"]
    guards = next(s["run"] for s in steps if s.get("name", "").startswith("Guards"))
    assert "measles rebuild" in guards  # never pushes a store that does not rebuild


@pytest.mark.parametrize("name", sorted(p.name for p in WF.glob("*.yml")))
def test_browser_install_has_a_time_limit_and_retries(name: str) -> None:  # ADR 0024
    # A hung install once cost a scheduled dashboard capture (2026-10-26).
    for job in load(name)["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            if "playwright install" in run:
                raise AssertionError(f"{name}: install the browser through install-browser.sh")
            if "install-browser.sh" in run:
                assert step.get("timeout-minutes", 0) * 60 >= _install_budget_s(), name
                assert job["timeout-minutes"] >= step["timeout-minutes"] + 5, name


def _install_budget_s() -> int:
    """Worst case of install-browser.sh with its defaults: every attempt times out and every
    wait between attempts runs to its limit."""
    text = (WF.parent / "scripts/install-browser.sh").read_text()
    v = {k: int(n) for k, n in re.findall(r"^(\w+)=\$\{\w+:-(\d+)\}", text, flags=re.M)}
    gaps = v["ATTEMPTS"] - 1
    return v["ATTEMPTS"] * v["ATTEMPT_LIMIT"] + gaps * (v["LOCK_WAIT"] + v["PAUSE"])


def test_browser_install_waits_for_a_leftover_package_install(tmp_path: Path) -> None:
    # 2026-11-04: a timed-out attempt left apt-get running as root with the package lock, and
    # the retries failed at once. The script must wait for it before trying again (ADR 0024).
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls"
    apt_left = tmp_path / "apt_left"
    apt_left.write_text("2")  # the leftover apt-get is seen on two polls, then finishes
    (bin_ / "timeout").write_text('#!/usr/bin/env bash\nshift\n"$@"\n')
    (bin_ / "uv").write_text(
        "#!/usr/bin/env bash\n"
        f"n=$(cat {calls} 2>/dev/null || echo 0); n=$((n + 1)); echo $n > {calls}\n"
        f'[ $n -ge 2 ] && [ "$(cat {apt_left})" -eq 0 ]\n'  # retry works once apt is done
    )
    (bin_ / "pgrep").write_text(
        "#!/usr/bin/env bash\n"
        f"[ \"$1 $2\" = '-x apt-get' ] || exit 1\n"
        f"n=$(cat {apt_left}); [ $n -gt 0 ] || exit 1; echo $((n - 1)) > {apt_left}\n"
    )
    (bin_ / "sleep").write_text("#!/usr/bin/env bash\nexit 0\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "POLL": "1", "LOCK_WAIT": "10"}
    out = subprocess.run(
        ["bash", str(WF.parent / "scripts/install-browser.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert calls.read_text().strip() == "2"  # one failed attempt, then success after the wait
    assert "waited 2 s for a leftover package install" in out.stderr
    assert apt_left.read_text().strip() == "0"


def test_dashboard_slots_are_off_peak_and_inside_the_cover_window() -> None:  # ADR 0025, 0026
    for line in schedule.RELEASE_CRONS:
        assert int(line.split()[0]) not in (0, 30), line
    for line in schedule.DASHBOARD_CRONS:
        minute, hour, _dom, _mon, dow = line.split()
        assert int(minute) not in (0, 30), line  # the busiest minutes for the scheduler
        if dow == "1,3,5":  # update days: inside the cover window, after DOH's usual update
            assert schedule.COVER_START_HOUR_UTC <= int(hour) <= 22, line
