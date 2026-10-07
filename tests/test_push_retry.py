"""T2.9: concurrent pushes succeed through rebase retry and never share a log file."""

from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import REPO, git

SCRIPT = REPO / ".github" / "scripts" / "push-with-retry.sh"


def clone(bare: Path, dest: Path) -> Path:
    git(bare.parent, "clone", "-q", str(bare), str(dest))
    git(dest, "config", "user.name", "github-actions[bot]")
    git(dest, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git(dest, "config", "commit.gpgsign", "false")
    git(dest, "config", "pull.rebase", "true")
    return dest


def test_concurrent_push(tmp_path: Path, gitrepo: Path) -> None:
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(gitrepo), str(bare))
    a, b = clone(bare, tmp_path / "a"), clone(bare, tmp_path / "b")
    for repo, run in ((a, "gh-1-1"), (b, "gh-2-1")):
        d = repo / "data" / "capture_log" / "2026-10"
        d.mkdir(parents=True)
        (d / f"{run}.jsonl").write_text('{"x": 1}\n')
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", f"data: {run}")
    subprocess.run([str(SCRIPT), "main"], cwd=a, check=True, capture_output=True)
    r = subprocess.run([str(SCRIPT), "main"], cwd=b, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "rebasing" in r.stdout
    log = git(bare, "ls-tree", "-r", "--name-only", "main")
    assert "data/capture_log/2026-10/gh-1-1.jsonl" in log
    assert "data/capture_log/2026-10/gh-2-1.jsonl" in log
