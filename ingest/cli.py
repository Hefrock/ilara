"""``uv run measles ...`` (HANDOFF 4.4)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ingest import paths


def _root() -> Path:
    return paths.repo_root()


def _report(problems: list[str], ok_msg: str) -> int:
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print(f"FAIL: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(ok_msg)
    return 0


def cmd_capture(a: argparse.Namespace) -> int:
    from ingest import registry
    from ingest.capture import runner
    from ingest.capture_log import CaptureLog

    if a.backfill:
        from ingest.capture import backfill

        if a.dry_run:
            done = backfill.captured_urls(_root())
            for d in backfill.documents(_root()):
                state = "captured" if d["url"] in done else "to fetch"
                print(f"{state:9s} {d['source_id']:12s} {d['url']}")
            return 0
        log = CaptureLog(a.run_id)
        for r in backfill.run(log, _root()):
            print(f"{r.source_id:12s} {r.outcome:9s} {r.http_status} {r.url}")
        return 0
    reg = registry.load()
    if a.source:
        if a.source not in reg:
            print(f"unknown source {a.source}", file=sys.stderr)
            return 2
        sources = [reg[a.source]]
    else:
        sources = [s for s in reg.values() if s.capturable]
        if a.access:
            sources = [s for s in sources if s.access_path == a.access]
    sources = [s for s in sources if s.capturable]
    if a.dry_run:
        for s in sources:
            print(f"would capture {s.source_id} via {s.access_path}: {s.url}")
        return 0
    log = CaptureLog(a.run_id)
    recs = runner.run(sources, log, _root())
    for r in recs:
        print(
            f"{r.source_id:28s} {r.outcome:9s} {r.http_status} {r.raw_path or ''} "
            f"{(r.error or '').splitlines()[0] if r.error else ''}"
        )
    print(f"capture log: {log.path.relative_to(_root())}")
    # Capture problems are reported through the log and alerts, not the exit code,
    # so the workflow still commits what it saved.
    return 0


def cmd_alerts(a: argparse.Namespace) -> int:
    from ingest import alerts, capture_log

    root = _root()
    log_file = Path(a.log_file)
    records = [json.loads(x) for x in log_file.read_text().splitlines() if x.strip()]
    history = capture_log.read_all(root)
    al = alerts.build_alerts(records, history)
    rec = alerts.recovered_sources(records)
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo) or a.dry_run:
        for x in al:
            print(f"--- {x.title}\n{x.body}\n")
        print(f"recovered: {sorted(rec)}")
        return 0
    for act in alerts.GitHubIssues(repo, token).apply(al, rec):
        print(act)
    return 0


def cmd_references(a: argparse.Namespace) -> int:
    from ingest import references
    from ingest.capture.http import PoliteClient

    client = PoliteClient()
    try:
        results = references.fetch_all(references.load(_root()), client)
    finally:
        client.close()
    print(references.report(results))
    ok = all(any(s["outcome"] == "ok" for s in e["sources"].values()) for e in results)
    return 0 if ok else 1


def cmd_verify(a: argparse.Namespace) -> int:
    from ingest.verify import verify_all

    return _report(verify_all(_root()), "verify: OK")


def cmd_guard(a: argparse.Namespace) -> int:
    root = _root()
    if a.name == "paths":
        from ingest.guards import path_guard

        return _report(path_guard.check_range(root, a.range, all_bot=a.bot), "path guard: OK")
    if a.name == "append-only":
        from ingest.guards import append_only

        return _report(append_only.check_range(root, a.base, a.head), "append-only guard: OK")
    if a.name == "size":
        from ingest.guards import size

        rep = size.evaluate(*size.measure(root))
        for w in rep.warnings:
            print(f"WARN SIZE_BUDGET {w}")
        return _report(rep.failures, f"size: OK ({rep.total_bytes / size.MB:.1f} MB)")
    if a.name == "hygiene":
        from ingest.guards import hygiene

        problems = hygiene.scan_tracked(root)
        if a.history:
            problems += hygiene.scan_history_metadata(root)
        return _report(problems, "hygiene: OK")
    if a.name == "boundary":
        from ingest.guards import boundary

        return _report(boundary.check_tree(root / "project"), "boundary: OK")
    if a.name == "outputs":
        from ingest.guards import outputs

        return _report(outputs.check(root), "outputs guard: OK")
    raise AssertionError(a.name)


def cmd_dashboard(a: argparse.Namespace) -> int:
    from project.dashboard.build import write_site

    try:
        path = write_site(_root() / a.out, _root(), public=a.public)
    except FileNotFoundError as e:
        print(f"dashboard: {e}", file=sys.stderr)
        return 1
    print(f"dashboard: wrote {path} ({'public' if a.public else 'private'})")
    return 0


def cmd_release(a: argparse.Namespace) -> int:
    from ingest.release.weekly import ReleaseError, last_closed_week, release
    from ingest.timeutil import utc_now

    week = a.week or last_closed_week(utc_now())
    try:
        path = release(week, _root())
    except ReleaseError as e:
        print(f"release: {e}", file=sys.stderr)
        return 1
    print(f"release: wrote {path.relative_to(_root())}")
    return 0


def cmd_rebuild(a: argparse.Namespace) -> int:
    from ingest.curate.rebuild import rebuild

    return _report(rebuild(_root()), "rebuild: rebuilt tables match the committed tables")


def cmd_quality(a: argparse.Namespace) -> int:
    from ingest.quality.engine import run

    n, out = run(_root())
    print(f"quality: {n} new flag(s); report {out.relative_to(_root())}")
    return 0


def cmd_parse(a: argparse.Namespace) -> int:
    from ingest.parse.runner import run

    rep = run(_root(), a.source)
    for p in rep.parsed:
        print(f"parsed {p}")
    for f in rep.failed:
        print(f"FAILED {f}", file=sys.stderr)
    print(f"rows {rep.rows}; skipped {rep.skipped}; flags {rep.flags}")
    return 0


def cmd_seed(a: argparse.Namespace) -> int:
    from ingest.curate.seed import SeedError, load

    try:
        rep = load(_root())
    except SeedError as e:
        print(f"seed load: {e}", file=sys.stderr)
        return 1
    for f in rep.new_files:
        print(f"seeded {f}")
    for key in sorted(set(rep.loaded) | set(rep.quarantined)):
        print(
            f"  {key:28s} loaded {rep.loaded.get(key, 0):3d}  "
            f"quarantined {rep.quarantined.get(key, 0):3d}"
        )
    print(f"  data quality flags: {rep.flags}")
    return 0


def cmd_reference(a: argparse.Namespace) -> int:
    from ingest.reference.build import ReferenceError, build

    try:
        m = build(_root(), vintage=a.vintage, force=a.force)
    except ReferenceError as e:
        print(f"reference build: {e}", file=sys.stderr)
        return 1
    if m.get("skipped"):
        print("reference build: inputs unchanged, nothing to do")
        return 0
    print(json.dumps({k: m[k] for k in ("vintage", "statewide_population_check")}))
    for name, entry in m["files"].items():
        print(f"  {name:32s} {entry['bytes']:>10d}  {entry['sha256'][:12]}")
    return 0


def _not_yet(wp: str):
    def run(a: argparse.Namespace) -> int:
        print(f"{a.command}: not implemented yet ({wp}); nothing to do")
        return 0

    return run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="measles")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("capture", help="fetch and save raw; never parses")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--source")
    g.add_argument("--all-due", action="store_true")
    g.add_argument(
        "--backfill",
        action="store_true",
        help="fetch each document in data/registry/backfill_urls.yml once",
    )
    c.add_argument("--access", choices=["http", "browser"])
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--run-id")
    c.set_defaults(func=cmd_capture)

    al = sub.add_parser("alerts", help="open, update or close capture issues for one run")
    al.add_argument("--log-file", required=True)
    al.add_argument("--dry-run", action="store_true")
    al.set_defaults(func=cmd_alerts)

    pa = sub.add_parser("parse")
    pa.add_argument("--source")
    pa.add_argument("--since")
    pa.set_defaults(func=cmd_parse)

    sd = sub.add_parser("seed")
    sd.add_argument("action", choices=["load"])
    sd.set_defaults(func=cmd_seed)

    rf = sub.add_parser("reference", help="build data/reference from saved raw Census files")
    rf.add_argument("action", choices=["build"])
    rf.add_argument("--vintage", default="2025")
    rf.add_argument("--force", action="store_true")
    rf.set_defaults(func=cmd_reference)

    sub.add_parser(
        "references", help="print citation records and abstracts for the model's literature"
    ).set_defaults(func=cmd_references)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    sub.add_parser("rebuild").set_defaults(func=cmd_rebuild)
    sub.add_parser("quality").set_defaults(func=cmd_quality)

    r = sub.add_parser("release")
    r.add_argument("--week")
    r.set_defaults(func=cmd_release)

    d = sub.add_parser("dashboard")
    d.add_argument("action", choices=["build"])
    d.add_argument("--public", action="store_true")
    d.add_argument("--out", default="site")
    d.set_defaults(func=cmd_dashboard)

    gd = sub.add_parser("guard", help="repository guards (E18)")
    gd.add_argument(
        "name", choices=["paths", "append-only", "size", "hygiene", "boundary", "outputs"]
    )
    gd.add_argument("--range", default="HEAD~1..HEAD")
    gd.add_argument("--bot", action="store_true", help="treat every commit as a bot commit")
    gd.add_argument("--base", default="HEAD~1")
    gd.add_argument("--head", default="HEAD")
    gd.add_argument("--history", action="store_true", help="also scan commit metadata")
    gd.set_defaults(func=cmd_guard)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    return int(a.func(a) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
