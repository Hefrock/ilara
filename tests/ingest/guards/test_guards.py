from __future__ import annotations

from pathlib import Path

from ingest.guards import append_only, boundary, hygiene, outputs, path_guard, size

from conftest import REPO, git


def test_boundary_real_tree_passes() -> None:
    assert boundary.check_tree(REPO / "project") == []


def test_boundary_catches_violations(tmp_path: Path) -> None:  # T0.2
    proj = tmp_path / "project"
    proj.mkdir()
    (proj / "ok.py").write_text("from ingest import access\nimport ingest.access\n")
    assert boundary.check_tree(proj) == []
    (proj / "bad1.py").write_text("import ingest.capture\n")
    (proj / "bad2.py").write_text("from ingest import rawstore\n")
    (proj / "bad3.py").write_text("open('data/raw/doh_dashboard/x.json')\n")
    probs = boundary.check_tree(proj)
    assert len(probs) == 3


def test_path_guard_rejects_bot_commit_outside_data(gitrepo: Path) -> None:  # T0.3
    base = git(gitrepo, "rev-parse", "HEAD").strip()
    (gitrepo / "data").mkdir()
    (gitrepo / "data" / "a.txt").write_text("ok")
    git(gitrepo, "add", ".")
    git(gitrepo, "-c", "user.name=github-actions[bot]", "commit", "-q", "-m", "data: ok")
    assert path_guard.check_range(gitrepo, f"{base}..HEAD") == []
    (gitrepo / "project").mkdir()
    (gitrepo / "project" / "m.py").write_text("x = 1\n")
    git(gitrepo, "add", ".")
    git(gitrepo, "-c", "user.name=github-actions[bot]", "commit", "-q", "-m", "data: sneaky")
    probs = path_guard.check_range(gitrepo, f"{base}..HEAD")
    assert len(probs) == 1 and "project/m.py" in probs[0]
    # human commits are not restricted unless --bot is given
    (gitrepo / "project" / "n.py").write_text("y = 1\n")
    git(gitrepo, "add", ".")
    git(gitrepo, "commit", "-q", "-m", "feat: human")
    assert len(path_guard.check_range(gitrepo, "HEAD~1..HEAD")) == 0
    assert len(path_guard.check_range(gitrepo, "HEAD~1..HEAD", all_bot=True)) == 1


def test_append_only(gitrepo: Path) -> None:  # T2.11
    log = gitrepo / "data" / "capture_log" / "2026-10"
    raw = gitrepo / "data" / "raw" / "s" / "2026"
    log.mkdir(parents=True)
    raw.mkdir(parents=True)
    (log / "r1.jsonl").write_text("{}\n")
    (raw / "a.html").write_text("a")
    (gitrepo / "data" / "exports").mkdir()
    (gitrepo / "data" / "exports" / "t.csv").write_text("1")
    git(gitrepo, "add", ".")
    git(gitrepo, "commit", "-q", "-m", "data: one")
    base = git(gitrepo, "rev-parse", "HEAD").strip()

    (log / "r2.jsonl").write_text("{}\n")  # add: fine
    (gitrepo / "data" / "exports" / "t.csv").write_text("2")  # exports may be rewritten
    git(gitrepo, "add", ".")
    git(gitrepo, "commit", "-q", "-m", "data: two")
    assert append_only.check_range(gitrepo, base) == []

    (log / "r1.jsonl").write_text("{}\n{}\n")  # edit
    (raw / "a.html").unlink()  # delete
    git(gitrepo, "add", "-A")
    git(gitrepo, "commit", "-q", "-m", "data: bad")
    probs = append_only.check_range(gitrepo, base)
    assert any("r1.jsonl" in p for p in probs) and any("a.html" in p for p in probs)


def test_size_thresholds() -> None:  # T0.4
    mb = size.MB
    ok = size.evaluate(100 * mb, {"a": 1 * mb})
    assert not ok.warnings and not ok.failures
    w = size.evaluate(600 * mb, {"big.zip": 60 * mb})
    assert len(w.warnings) == 2 and not w.failures
    f = size.evaluate(950 * mb, {"huge.zip": 96 * mb})
    assert len(f.failures) == 2


def test_size_measure_counts_git(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "pack").write_bytes(b"x" * 1000)
    (tmp_path / "f.txt").write_bytes(b"y" * 10)
    total, files = size.measure(tmp_path)
    assert total == 1010 and files == {"f.txt": 10}


def test_hygiene(gitrepo: Path) -> None:  # T0.5
    personal = "jane.doe" + "@" + "gmail.com"
    noreply = "12345+someone" + "@" + "users.noreply.github.com"
    (gitrepo / "ok.md").write_text(f"contact {noreply}\n")
    git(gitrepo, "add", ".")
    git(gitrepo, "commit", "-q", "-m", "ok")
    assert hygiene.scan_tracked(gitrepo) == []

    raw = gitrepo / "data" / "raw" / "doh" / "2026"
    raw.mkdir(parents=True)
    (raw / "page.html").write_text(f"agency contact {personal}\n")
    git(gitrepo, "add", ".")
    git(gitrepo, "commit", "-q", "-m", "raw")
    assert hygiene.scan_tracked(gitrepo) == []  # data/raw is out of scope

    (gitrepo / "notes.md").write_text(f"mail {personal}\n")
    (gitrepo / "cfg.txt").write_text("token = ghp_" + "a" * 36 + "\n")
    git(gitrepo, "add", ".")
    git(gitrepo, "commit", "-q", "-m", "bad")
    probs = hygiene.scan_tracked(gitrepo)
    assert any("notes.md" in p for p in probs) and any("github token" in p for p in probs)


def test_hygiene_real_tree_passes() -> None:
    assert hygiene.scan_tracked(REPO) == []


def test_outputs_guard(gitrepo: Path) -> None:  # T6.16
    out = gitrepo / "project" / "outputs"
    out.mkdir(parents=True)
    (out / "f.csv").write_text("1")
    git(gitrepo, "add", "-f", ".")
    git(gitrepo, "commit", "-q", "-m", "oops")
    assert outputs.check(gitrepo)
    (gitrepo / "data").mkdir()
    (gitrepo / "data" / "validation_gate.json").write_text('{"status": "pass"}')
    assert outputs.check(gitrepo) == []


def test_gitignore_covers_outputs() -> None:  # T6.16
    text = (REPO / ".gitignore").read_text()
    assert "project/outputs/" in text and "local/" in text
