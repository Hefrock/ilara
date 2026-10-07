"""``measles verify`` (HANDOFF 4.4): recompute raw hashes and check provenance links."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

from ingest import paths, rawstore


def verify_raw(root: Path) -> list[str]:
    problems: list[str] = []
    base = paths.raw_dir(root)
    if not base.exists():
        return problems
    manifests = set()
    for mpath in rawstore.iter_manifests(None, root):
        m = rawstore.load_manifest(mpath)
        data_path = root / m["raw_path"]
        manifests.add(data_path.resolve())
        if data_path.name + rawstore.MANIFEST_SUFFIX != mpath.name:
            problems.append(f"HASH_MISMATCH {mpath}: manifest does not sit beside its file")
        if not data_path.exists():
            problems.append(f"HASH_MISMATCH {m['raw_path']}: file missing")
            continue
        stored = data_path.read_bytes()
        if hashlib.sha256(stored).hexdigest() != m["stored_sha256"]:
            problems.append(f"HASH_MISMATCH {m['raw_path']}: stored bytes changed")
            continue
        payload = gzip.decompress(stored) if m.get("compression") == "gzip" else stored
        if hashlib.sha256(payload).hexdigest() != m["sha256"]:
            problems.append(f"HASH_MISMATCH {m['raw_path']}: payload hash differs from manifest")
        if not data_path.name.split("_", 1)[-1].startswith(m["sha256"][:12]):
            problems.append(f"HASH_MISMATCH {m['raw_path']}: name does not carry sha256 prefix")
    for f in base.rglob("*"):
        if (
            f.is_file()
            and not f.name.endswith(rawstore.MANIFEST_SUFFIX)
            and f.name != ".gitkeep"
            and f.resolve() not in manifests
        ):
            problems.append(f"{f.relative_to(root)}: raw file without manifest")
    return problems


def verify_curated(root: Path) -> list[str]:
    """Every curated or sensitivity row must reference a raw file or a seed file that exists."""
    import polars as pl

    problems: list[str] = []
    known_raw = {rawstore.load_manifest(m)["sha256"] for m in rawstore.iter_manifests(None, root)}
    known_seed = _seed_hashes(root)
    for store in (paths.curated_dir(root), paths.sensitivity_dir(root)):
        for pq in sorted(store.rglob("*.parquet")):
            df = pl.read_parquet(pq)
            if "raw_sha256" not in df.columns:
                problems.append(f"{pq.relative_to(root)}: no raw_sha256 column")
                continue
            for sha in df["raw_sha256"].unique().to_list():
                if sha not in known_raw and sha not in known_seed:
                    problems.append(f"{pq.relative_to(root)}: unknown raw_sha256 {sha}")
    return problems


def _seed_hashes(root: Path) -> set[str]:
    import json

    out: set[str] = set()
    for mf in (
        paths.data_dir(root) / "seed" / "MANIFEST.json",
        paths.sensitivity_dir(root) / "seed" / "MANIFEST.json",
        paths.reference_dir(root) / "MANIFEST.json",
    ):
        if mf.exists():
            for entry in json.loads(mf.read_text()).get("files", {}).values():
                out.add(entry["sha256"])
    return out


def verify_all(root: Path | None = None) -> list[str]:
    root = root or paths.repo_root()
    return verify_raw(root) + verify_curated(root)
