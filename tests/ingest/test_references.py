"""Reference fetcher (B17): offline, with a mock transport and synthetic records."""

from __future__ import annotations

import json
import re

import httpx
import yaml

from ingest import references
from ingest.capture.http import PoliteClient, RateLimiter

from conftest import REPO

XML = b"""<?xml version="1.0"?><PubmedArticleSet><PubmedArticle><MedlineCitation><Article>
<Journal><JournalIssue><PubDate><Year>2017</Year></PubDate></JournalIssue>
<Title>Lancet Infect Dis</Title></Journal><ArticleTitle>A <i>test</i> title</ArticleTitle>
<Abstract><AbstractText Label="FINDINGS">R0 was 9 to 10.</AbstractText></Abstract>
</Article></MedlineCitation><PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1016/S1473-3099(17)30307-9</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""


def _client(handler) -> PoliteClient:  # type: ignore[no-untyped-def]
    lim = RateLimiter(min_interval=0.0, sleep=lambda s: None)
    return PoliteClient(transport=httpx.MockTransport(handler), limiter=lim, sleep=lambda s: None)


def test_reference_list_is_readable() -> None:
    refs = references.load(REPO)
    used = {r["key"] for r in refs if r["status"] == "used"}
    assert used == {"guerra2017", "vink2014", "klinkenberg2011"}
    assert {r["status"] for r in refs} <= {"used", "context", "to_read"}
    assert all(r["citation"] and r["for"] for r in refs)


def test_every_reference_has_a_doi_cited_where_used() -> None:
    # A DOI identifies each reference (PMIDs proved unreliable: a wrong one was caught), and every
    # document citing a reference by key gives its DOI so a reader can resolve it.
    refs = references.load(REPO)
    readme = (REPO / "docs/references/README.md").read_text()
    params = (REPO / "project/model/params.yml").read_text()
    for r in refs:
        doi = str(r["doi"] or "")
        assert re.fullmatch(r"10\.\d{4,9}/\S+", doi), r["key"]
        assert f"(https://doi.org/{doi})" in readme, r["key"]
        if r["key"] in params:
            assert f"doi:{doi}" in params, r["key"]


def test_fetch_parses_both_sources_and_checks_the_doi() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if req.url.host == "eutils.ncbi.nlm.nih.gov":
            return httpx.Response(200, content=XML)
        body = {
            "resultList": {
                "result": [
                    {"title": "T", "doi": "10.9/other", "pubYear": "2017", "abstractText": "abc"}
                ]
            }
        }
        return httpx.Response(200, content=json.dumps(body).encode())

    ref = {"key": "guerra2017", "pmid": "28757186", "doi": "10.1016/S1473-3099(17)30307-9"}
    [e] = references.fetch_all([ref], _client(handler))
    assert set(e["sources"]) == {"europepmc"}  # PubMed is disallowed by robots.txt
    ep = e["sources"]["europepmc"]
    assert ep["doi_matches"] is False  # a record for another paper is visibly marked
    assert "matches: False" in references.report([e])
    pm = references.parse_pubmed(XML)  # kept for records saved by hand
    assert pm is not None and pm["title"] == "A test title" and pm["year"] == "2017"
    assert pm["abstract"] == "FINDINGS: R0 was 9 to 10."


def test_lookup_is_by_doi_when_known() -> None:
    q = references.europepmc_query({"pmid": "1", "doi": "10.1093/aje/kwu209"})
    assert "DOI" in q and "kwu209" in q and "EXT_ID" not in q
    assert "EXT_ID" in references.europepmc_query({"pmid": "21704640", "doi": None})


def test_robots_disallow_is_reported_not_worked_around() -> None:  # I7
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("must not fetch a disallowed URL")

    [e] = references.fetch_all([{"key": "k", "pmid": "1", "doi": None}], _client(handler))
    assert {s["outcome"] for s in e["sources"].values()} == {"blocked"}


def test_every_used_figure_has_provenance() -> None:
    # A figure in the model config must trace to an evidence entry saying where it appears in the
    # source, what was read and how it was obtained; candidates not yet read are never cited.
    from datetime import date

    refs = references.load(REPO)
    params = (REPO / "project/model/params.yml").read_text()
    values: set[str] = set()
    for r in refs:
        ev = r.get("evidence") or []
        if r["status"] == "used":
            assert ev, r["key"]
        if r["status"] == "to_read":
            assert not ev and r["key"] not in params, r["key"]
        for e in ev:
            assert set(e) == {"quantity", "value", "where", "read", "via", "date"}, r["key"]
            assert e["read"] in {"abstract", "full_text", "abstract_and_introduction"}
            assert e["via"] and e["where"] and isinstance(e["date"], date)
            values.add(str(e["value"]))
    disease = yaml.safe_load(params)["disease"]
    for v in (
        disease["r0"]["low"],
        disease["r0"]["high"],
        f"{disease['generation_time_days']['low']:g}-{disease['generation_time_days']['high']:g}",
        11.7,
    ):
        assert str(v) in values, v
