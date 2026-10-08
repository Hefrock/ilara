"""Fetch citation records and abstracts for the model's literature (B17, U12, U13).

Reads ``docs/references/references.yml`` and asks two official bibliographic APIs, PubMed
E-utilities and Europe PMC, for each record through the polite client (robots.txt, one request
per 5 seconds per host, stop on a block: I7). The result is printed for a person or agent to
read the figures from the source itself. Nothing is written to the repository: abstracts are
publisher text and are never committed (I10).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from ingest import paths
from ingest.capture.http import PoliteClient

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id={}"
EUROPEPMC = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search?resultType=core&format=json"
    "&query=EXT_ID:{}%20AND%20SRC:MED"
)


def load(root: Path | None = None) -> list[dict[str, Any]]:
    path = (root or paths.repo_root()) / "docs" / "references" / "references.yml"
    refs: list[dict[str, Any]] = yaml.safe_load(path.read_text())["references"]
    return refs


def parse_pubmed(xml: bytes) -> dict[str, Any] | None:
    art = ET.fromstring(xml).find(".//PubmedArticle")
    if art is None:
        return None
    abstract = " ".join(
        (f"{a.get('Label')}: " if a.get("Label") else "") + "".join(a.itertext())
        for a in art.findall(".//Abstract/AbstractText")
    )
    title = art.find(".//ArticleTitle")
    doi = next(
        (i.text for i in art.findall(".//ArticleIdList/ArticleId") if i.get("IdType") == "doi"),
        None,
    )
    return {
        "title": "".join(title.itertext()) if title is not None else None,
        "journal": art.findtext(".//Journal/Title"),
        "year": art.findtext(".//JournalIssue/PubDate/Year"),
        "doi": doi,
        "abstract": abstract or None,
    }


def parse_europepmc(body: bytes) -> dict[str, Any] | None:
    results = json.loads(body).get("resultList", {}).get("result", [])
    if not results:
        return None
    r = results[0]
    return {
        "title": r.get("title"),
        "journal": (r.get("journalInfo") or {}).get("journal", {}).get("title"),
        "year": r.get("pubYear"),
        "doi": r.get("doi"),
        "abstract": r.get("abstractText"),
    }


def fetch_all(refs: list[dict[str, Any]], client: PoliteClient) -> list[dict[str, Any]]:
    out = []
    for ref in refs:
        pmid = quote(str(ref["pmid"]))
        entry: dict[str, Any] = {"key": ref["key"], "pmid": ref["pmid"], "sources": {}}
        for name, url, parser in (
            ("pubmed", EFETCH.format(pmid), parse_pubmed),
            ("europepmc", EUROPEPMC.format(pmid), parse_europepmc),
        ):
            res = client.fetch(url)
            if res.outcome != "ok" or res.body is None:
                entry["sources"][name] = {"outcome": res.outcome, "error": res.error}
                continue
            try:
                rec = parser(res.body)
            except (ET.ParseError, ValueError) as e:
                entry["sources"][name] = {"outcome": "failed", "error": f"parse: {e}"}
                continue
            if rec is None:
                entry["sources"][name] = {"outcome": "failed", "error": "no record"}
                continue
            want = (ref.get("doi") or "").lower()
            rec["doi_matches"] = None if not want else (rec.get("doi") or "").lower() == want
            entry["sources"][name] = {"outcome": "ok", **rec}
        out.append(entry)
    return out


def report(results: list[dict[str, Any]]) -> str:
    lines = []
    for e in results:
        lines.append(f"=== {e['key']} (PMID {e['pmid']})")
        for name, s in e["sources"].items():
            if s["outcome"] != "ok":
                lines.append(f"--- {name}: {s['outcome']} ({s.get('error')})")
                continue
            lines.append(
                f"--- {name}: {s.get('title')} | {s.get('journal')} | {s.get('year')} | "
                f"doi {s.get('doi')} (matches: {s.get('doi_matches')})"
            )
            lines.append(s.get("abstract") or "(no abstract)")
    return "\n".join(lines)
