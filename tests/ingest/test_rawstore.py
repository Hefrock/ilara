from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingest import rawstore
from ingest.verify import verify_raw

T0 = datetime(2026, 10, 7, 18, 0, 5, tzinfo=UTC)
T1 = datetime(2026, 10, 9, 18, 0, 5, tzinfo=UTC)


def _save(root: Path, data: bytes, ts: datetime = T0, ext: str = "html", **kw):
    return rawstore.save(
        source_id="doh_measles_page",
        url="https://example.org/x",
        data=data,
        ext=ext,
        fetched_at=ts,
        root=root,
        **kw,
    )


def test_save_writes_file_and_manifest(root: Path) -> None:  # T2.1
    res = _save(root, b"<html>cases 1004</html>")
    assert res.outcome == "changed"
    sha = hashlib.sha256(b"<html>cases 1004</html>").hexdigest()
    assert res.raw_path == f"data/raw/doh_measles_page/2026/20261007T180005Z_{sha[:12]}.html"
    assert re.fullmatch(r"data/raw/[a-z_]+/\d{4}/\d{8}T\d{6}Z_[0-9a-f]{12}\.html", res.raw_path)
    m = json.loads((root / (res.raw_path + ".manifest.json")).read_text())
    assert m["sha256"] == sha == hashlib.sha256((root / res.raw_path).read_bytes()).hexdigest()
    for k in ("url", "fetched_at_utc", "http_status", "sha256", "content_hash", "parser_hint"):
        assert k in m
    assert m["fetched_at_et"].startswith("2026-10-07T14:00:05-04:00")


def test_unchanged_after_normalisation(root: Path) -> None:  # T2.2 (raw side)
    a = b'<html><input name="__VIEWSTATE" value="abc123"/>cases 1004<script src="x.js?v=111">'
    b = b'<html><input name="__VIEWSTATE" value="zzz999"/>cases 1004<script src="x.js?v=222">'
    assert _save(root, a).outcome == "changed"
    res = _save(root, b, T1)
    assert res.outcome == "unchanged" and res.raw_path is None
    assert len(list((root / "data/raw").rglob("*.html"))) == 1
    assert _save(root, b.replace(b"1004", b"1010"), T1).outcome == "changed"


def test_json_volatile_keys_ignored(root: Path) -> None:
    a = json.dumps({"data": [1, 2], "timestamp": "2026-10-07T18:00:00Z"}).encode()
    b = json.dumps({"timestamp": "2026-10-09T18:00:00Z", "data": [1, 2]}).encode()
    assert _save(root, a, ext="json").outcome == "changed"
    assert _save(root, b, T1, ext="json").outcome == "unchanged"


def test_refuses_overwrite(root: Path) -> None:  # T2.3
    _save(root, b"one")
    with pytest.raises(rawstore.RawStoreError):
        _save(root, b"one", force=True)


def test_large_text_is_gzipped_and_verifies(root: Path) -> None:
    data = b"x" * (rawstore.COMPRESS_THRESHOLD + 10)
    res = _save(root, data)
    assert res.raw_path and res.raw_path.endswith(".html.gz")
    assert gzip.decompress((root / res.raw_path).read_bytes()) == data
    assert rawstore.read_payload(res.manifest, root) == data
    assert verify_raw(root) == []


def test_verify_detects_one_byte_change(root: Path) -> None:  # T3.10
    res = _save(root, b"<html>cases 1004</html>")
    assert verify_raw(root) == []
    p = root / res.raw_path
    p.write_bytes(p.read_bytes().replace(b"1004", b"1005"))
    problems = verify_raw(root)
    assert problems and all("HASH_MISMATCH" in x for x in problems)


def test_verify_flags_orphan_file(root: Path) -> None:
    d = root / "data/raw/doh_measles_page/2026"
    d.mkdir(parents=True)
    (d / "stray.html").write_text("x")
    assert any("without manifest" in x for x in verify_raw(root))
