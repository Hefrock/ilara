"""Reference fetcher (B17): offline, with a mock transport and synthetic records."""

from __future__ import annotations

import json

import httpx

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
    assert {r["key"] for r in refs} == {"guerra2017", "vink2014", "klinkenberg2011"}
    assert all(r["pmid"] and r["citation"] and r["for"] for r in refs)


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
    pm, ep = e["sources"]["pubmed"], e["sources"]["europepmc"]
    assert pm["title"] == "A test title" and pm["year"] == "2017"
    assert pm["abstract"] == "FINDINGS: R0 was 9 to 10." and pm["doi_matches"] is True
    assert ep["doi_matches"] is False  # a record for another paper is visibly marked
    text = references.report([e])
    assert "matches: True" in text and "matches: False" in text


def test_robots_disallow_is_reported_not_worked_around() -> None:  # I7
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("must not fetch a disallowed URL")

    [e] = references.fetch_all([{"key": "k", "pmid": "1", "doi": None}], _client(handler))
    assert {s["outcome"] for s in e["sources"].values()} == {"blocked"}
