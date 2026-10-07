"""Hygiene scan (T0.5): no personal email addresses or secrets in tracked files.

Scope: tracked files outside ``data/raw/`` (agency pages may contain agency contact emails).
Allowed: GitHub noreply addresses, and agency or documentation addresses on allowlisted domains.
"""

from __future__ import annotations

import re
from pathlib import Path

from ingest.guards.gitutil import git

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL = re.compile(
    r"(@users\.noreply\.github\.com$|^noreply@|^no-reply@|@example\.(com|org|net)$"
    r"|@pa\.gov$|@cdc\.gov$|@census\.gov$)",
    re.IGNORECASE,
)
SECRETS = {
    "github token": re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "aws access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "anthropic key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "openai key": re.compile(r"\bsk-[A-Za-z0-9]{40,}\b"),
    "google api key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}
EXCLUDED_PREFIXES = ("data/raw/",)
BINARY_EXTS = {".parquet", ".zip", ".gz", ".xls", ".xlsx", ".pdf", ".jpg", ".png", ".webp", ".gpkg"}


def scan_text(name: str, text: str) -> list[str]:
    out: list[str] = []
    for m in EMAIL.finditer(text):
        addr = m.group(0)
        if not ALLOWED_EMAIL.search(addr):
            out.append(f"{name}: email address {addr}")
    for label, pat in SECRETS.items():
        if pat.search(text):
            out.append(f"{name}: possible {label}")
    return out


def scan_files(root: Path, files: list[str]) -> list[str]:
    out: list[str] = []
    for f in files:
        if f.startswith(EXCLUDED_PREFIXES) or Path(f).suffix.lower() in BINARY_EXTS:
            continue
        p = root / f
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        out += scan_text(f, text)
    return out


def scan_tracked(root: Path) -> list[str]:
    files = [f for f in git(root, "ls-files").splitlines() if f]
    return scan_files(root, files)


def scan_history_metadata(root: Path) -> list[str]:
    """Author and committer addresses across history (used at Gate G5)."""
    out: list[str] = []
    for line in git(root, "log", "--all", "--format=%H %ae %ce").splitlines():
        sha, *addrs = line.split()
        for a in addrs:
            if not ALLOWED_EMAIL.search(a):
                out.append(f"{sha[:10]}: commit metadata address {a}")
    return out
