from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated repository root with the real source registry."""
    (tmp_path / "data" / "registry").mkdir(parents=True)
    shutil.copy(
        REPO / "data" / "registry" / "source_registry.yml",
        tmp_path / "data" / "registry" / "source_registry.yml",
    )
    monkeypatch.setenv("MEASLES_ROOT", str(tmp_path))
    return tmp_path


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def gitrepo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Human")
    git(repo, "config", "user.email", "1+human@users.noreply.github.com")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("x\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo
