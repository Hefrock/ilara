"""Immutable raw store (WP2b, E02, E03).

Layout: ``data/raw/<source_id>/<YYYY>/<YYYYMMDDTHHMMSSZ>_<sha12>.<ext>`` plus a sidecar
manifest ``<same name>.manifest.json``. Files are written once and never overwritten.

``sha256`` is the hash of the exact payload bytes as fetched. Text payloads over 256 KB
are stored gzip-compressed (deterministic, mtime 0) with ``.gz`` appended to the name;
the manifest records ``compression`` and ``stored_sha256`` (hash of the bytes on disk).
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ingest import normalize, paths
from ingest.timeutil import iso_et, iso_utc, stamp

COMPRESS_THRESHOLD = 256 * 1024
MANIFEST_SUFFIX = ".manifest.json"


class RawStoreError(Exception):
    pass


@dataclass
class SaveResult:
    outcome: str  # "changed" or "unchanged"
    sha256: str
    content_hash: str
    bytes: int
    raw_path: str | None  # repo-relative; None when unchanged
    manifest: dict[str, Any] = field(default_factory=dict)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def iter_manifests(source_id: str | None = None, root: Path | None = None):
    base = paths.raw_dir(root)
    if source_id:
        base = base / source_id
    if not base.exists():
        return
    yield from sorted(base.rglob(f"*{MANIFEST_SUFFIX}"))


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def latest_manifest(source_id: str, root: Path | None = None, *, key: str | None = None):
    """Most recent manifest for a source (optionally for one ``capture_key``)."""
    best: dict[str, Any] | None = None
    for mpath in iter_manifests(source_id, root):
        m = load_manifest(mpath)
        if key is not None and m.get("capture_key") != key:
            continue
        if best is None or m["fetched_at_utc"] > best["fetched_at_utc"]:
            best = m
    return best


def read_payload(manifest: dict[str, Any], root: Path | None = None) -> bytes:
    """Return the original payload bytes for a manifest (decompressing if needed)."""
    root = root or paths.repo_root()
    data = (root / manifest["raw_path"]).read_bytes()
    if manifest.get("compression") == "gzip":
        data = gzip.decompress(data)
    return data


def save(
    *,
    source_id: str,
    url: str,
    data: bytes,
    ext: str,
    fetched_at: datetime,
    http_status: int | None = 200,
    parser_hint: str | None = None,
    capture_key: str | None = None,
    extra: dict[str, Any] | None = None,
    root: Path | None = None,
    force: bool = False,
) -> SaveResult:
    """Save a payload unless its normalised content equals the latest saved one.

    ``capture_key`` distinguishes several artefacts of one source in one capture (for
    example the dashboard's page text, JSON responses and screenshot); change detection
    compares against the latest artefact with the same key.
    """
    root = root or paths.repo_root()
    ext = ext.lstrip(".").lower()
    norm = normalize.for_source(source_id, ext)
    sha = sha256_hex(data)
    chash = normalize.content_hash(data, norm)

    prev = latest_manifest(source_id, root, key=capture_key)
    if prev is not None and prev.get("content_hash") == chash and not force:
        return SaveResult("unchanged", sha, chash, len(data), None, prev)

    stored = data
    compression = None
    name_ext = ext
    if ext in normalize.TEXT_EXTS and len(data) > COMPRESS_THRESHOLD:
        stored = gzip.compress(data, compresslevel=9, mtime=0)
        compression = "gzip"
        name_ext = f"{ext}.gz"

    ts = stamp(fetched_at)
    dest = paths.raw_dir(root) / source_id / ts[:4] / f"{ts}_{sha[:12]}.{name_ext}"
    mpath = dest.with_name(dest.name + MANIFEST_SUFFIX)
    if dest.exists() or mpath.exists():
        raise RawStoreError(f"refusing to overwrite existing raw file {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "source_id": source_id,
        "url": url,
        "fetched_at_utc": iso_utc(fetched_at),
        "fetched_at_et": iso_et(fetched_at),
        "http_status": http_status,
        "sha256": sha,
        "content_hash": chash,
        "normaliser": f"{norm.name}:{norm.version}",
        "bytes": len(data),
        "ext": ext,
        "compression": compression,
        "stored_sha256": sha256_hex(stored),
        "parser_hint": parser_hint,
        "capture_key": capture_key,
        "raw_path": _rel(dest, root),
    }
    if extra:
        manifest["extra"] = extra

    # Exclusive create: never overwrite, even under a race.
    with open(dest, "xb") as fh:
        fh.write(stored)
    with open(mpath, "x") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return SaveResult("changed", sha, chash, len(data), manifest["raw_path"], manifest)
