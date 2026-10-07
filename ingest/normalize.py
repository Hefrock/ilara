"""Content normalisers for change detection (E03).

A normaliser strips fields that change on every request (session ids, render timestamps,
cache-busting tokens) so that ``content_hash`` changes only when the substance changes.
The exact bytes are always stored and hashed separately (``sha256``).

Normalisers are registered per source id. Unregistered sources use the generic text
normaliser for text payloads and the identity for binary payloads. When a normaliser
changes, bump its version: the version is part of the content hash, so the next capture
after a change is saved once more rather than being wrongly reported as unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Normaliser:
    name: str
    version: int
    fn: Callable[[bytes], bytes]


_TEXT_PATTERNS = [
    # ASP.NET / Drupal / generic CSRF and session tokens
    re.compile(
        rb'(name="(?:__VIEWSTATE|__EVENTVALIDATION|__REQUESTVERIFICATIONTOKEN|form_build_id|csrf[-_]?token)"[^>]*value=")[^"]*'
    ),
    re.compile(rb'((?:nonce|data-nonce)=")[^"]*'),
    # cache-busting query strings on static assets
    re.compile(rb"([?&](?:v|ver|version|_|cb|t|ts)=)[0-9A-Za-z._-]+"),
    # common rendered-at stamps
    re.compile(rb"(<!--\s*(?:generated|rendered|page generated)[^>]*?)\d[\d:T .Z+-]*"),
]

_JSON_VOLATILE_KEYS = frozenset(
    {
        "timestamp",
        "requestid",
        "request_id",
        "activityid",
        "sessionid",
        "session_id",
        "servertime",
        "server_time",
        "generatedat",
        "generated_at",
        "traceid",
        "trace_id",
        "x-ms-request-id",
        "rid",
        "jobid",
        "job_id",
        "ts",
    }
)


def _generic_text(data: bytes) -> bytes:
    out = data.replace(b"\r\n", b"\n")
    for pat in _TEXT_PATTERNS:
        out = pat.sub(rb"\1", out)
    return out


def _strip_json(obj: object) -> object:
    if isinstance(obj, dict):
        return {
            k: _strip_json(v)
            for k, v in sorted(obj.items())
            if k.lower() not in _JSON_VOLATILE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_json(v) for v in obj]
    return obj


def _json(data: bytes) -> bytes:
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return _generic_text(data)
    return json.dumps(_strip_json(obj), sort_keys=True, separators=(",", ":")).encode()


def _identity(data: bytes) -> bytes:
    return data


IDENTITY = Normaliser("identity", 1, _identity)
GENERIC_TEXT = Normaliser("generic_text", 1, _generic_text)
JSON = Normaliser("json", 1, _json)

TEXT_EXTS = frozenset({"html", "htm", "txt", "csv", "json", "xml", "md"})

# Per-source overrides. Filled from the probe report (WP2a) as volatile fields are found.
_BY_SOURCE: dict[str, Normaliser] = {}


def register(source_id: str, normaliser: Normaliser) -> None:
    _BY_SOURCE[source_id] = normaliser


def for_source(source_id: str, ext: str) -> Normaliser:
    if source_id in _BY_SOURCE:
        return _BY_SOURCE[source_id]
    ext = ext.lower()
    if ext == "json":
        return JSON
    if ext in TEXT_EXTS:
        return GENERIC_TEXT
    return IDENTITY


def content_hash(data: bytes, normaliser: Normaliser) -> str:
    h = hashlib.sha256()
    h.update(f"{normaliser.name}:{normaliser.version}\n".encode())
    h.update(normaliser.fn(data))
    return h.hexdigest()
