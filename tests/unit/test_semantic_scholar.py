"""Semantic Scholar plugin tests with respx replay (offline, deterministic)."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_tools.core.errors import UsageError
from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.core.query import Query
from paper_tools.plugins.semantic_scholar import (
    PAPER_URL,
    SEARCH_URL,
    SemanticScholarMetadata,
    SemanticScholarSearcher,
)

RECORD = {
    "paperId": "abc123",
    "externalIds": {
        "DOI": "10.1234/ABC",
        "PubMed": "999",
        "PubMedCentral": "777",
        "ArXiv": "2101.00001",
    },
    "title": "CRISPR base editing in vivo",
    "abstract": "An abstract.",
    "year": 2023,
    "authors": [{"name": "San Zhang"}],
    "venue": "Nature",
    "publicationTypes": ["JournalArticle"],
    "openAccessPdf": {"url": "https://pub.org/paper.pdf", "status": "HYBRID", "license": "cc-by"},
    "isOpenAccess": True,
    "citationCount": 42,
    "referenceCount": 2,
    "citations": [
        {
            "citingPaper": {
                "paperId": "citing1",
                "title": "Later editing work",
                "year": 2024,
                "authors": [{"name": "Li San"}],
                "externalIds": {"DOI": "10.1234/CITING", "PubMed": "111"},
                "citations": [{"citingPaper": {"paperId": "must-not-recurse"}}],
            }
        },
        {"citingPaper": None},
    ],
    "references": [
        {
            "citedPaper": {
                "paperId": "ref1",
                "title": "Earlier editing work",
                "year": 2020,
                "authors": [{"name": "Zhang San"}],
                "externalIds": {"PubMedCentral": "PMC777"},
                "references": [{"citedPaper": {"paperId": "must-not-recurse"}}],
            }
        },
        None,
    ],
}


@respx.mock
def test_search_and_normalization(plugin_ctx: PluginContext) -> None:
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"total": 1, "offset": 0, "data": [RECORD]})
    )
    page = SemanticScholarSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=5)
    assert page.source == "semantic_scholar"
    assert page.total == 1
    paper = page.items[0]
    assert paper.identifiers == {
        "doi": "10.1234/abc",
        "pmid": "999",
        "pmcid": "PMC777",
        "arxiv": "2101.00001",
        "s2": "abc123",
    }
    assert paper.oa_status == "hybrid"
    assert paper.license == "cc-by"
    assert paper.publisher_url == "https://doi.org/10.1234/abc"
    assert paper.cited_by_count == 42
    assert paper.references_count == 2
    assert paper.impact_factor is None
    assert len(paper.cited_by_papers) == 1
    citing = paper.cited_by_papers[0]
    assert citing.identifiers == {"doi": "10.1234/citing", "pmid": "111", "s2": "citing1"}
    assert citing.title == "Later editing work"
    assert citing.authors[0].name == "Li San"
    assert citing.year == 2024
    assert len(paper.reference_papers) == 1
    reference = paper.reference_papers[0]
    assert reference.identifiers == {"pmcid": "PMC777", "s2": "ref1"}
    assert reference.title == "Earlier editing work"
    assert reference.authors[0].name == "Zhang San"
    assert reference.year == 2020
    params = route.calls.last.request.url.params
    assert params["limit"] == "5"
    assert "title" in params["fields"]
    assert "citationCount" in params["fields"]
    assert "referenceCount" in params["fields"]
    assert "citations.paperId" not in params["fields"]
    assert "references.externalIds" not in params["fields"]
    assert route.call_count == 1


@respx.mock
def test_malformed_extended_fields_are_ignored(plugin_ctx: PluginContext) -> None:
    record = {
        **RECORD,
        "citationCount": True,
        "referenceCount": -1,
        "citations": "not-a-list",
        "references": [{"citedPaper": {"paperId": 123, "authors": [None]}}],
    }
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json={"data": [record]}))
    paper = SemanticScholarSearcher(plugin_ctx).search(Query(text="x"), limit=1).items[0]
    assert paper.cited_by_count is None
    assert paper.references_count is None
    assert paper.cited_by_papers == []
    assert paper.reference_papers == []


@respx.mock
def test_search_year_and_oa_params(plugin_ctx: PluginContext) -> None:
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"total": 0, "data": []})
    )
    q = Query(text="CRISPR", year_from=2020, year_to=2025, open_access=True, journal="Nature")
    SemanticScholarSearcher(plugin_ctx).search(q)
    params = route.calls.last.request.url.params
    assert params["year"] == "2020-2025"
    assert params["openAccessPdf"] == "true"
    assert params["venue"] == "Nature"


def test_journal_only_query_rejected(plugin_ctx: PluginContext) -> None:
    with pytest.raises(UsageError):
        SemanticScholarSearcher(plugin_ctx).search(Query(journal="Nature"))


@respx.mock
def test_enrich_by_doi(plugin_ctx: PluginContext) -> None:
    route = respx.get(f"{PAPER_URL}/DOI:10.1234/abc").mock(
        return_value=httpx.Response(200, json=RECORD)
    )
    paper = SemanticScholarMetadata(plugin_ctx).enrich(Paper(identifiers={"doi": "10.1234/abc"}))
    assert paper.title == "CRISPR base editing in vivo"
    assert paper.identifiers["s2"] == "abc123"
    assert paper.cited_by_count == 42
    assert paper.cited_by_papers[0].title == "Later editing work"
    assert paper.reference_papers[0].title == "Earlier editing work"
    params = route.calls.last.request.url.params["fields"]
    assert "citations.paperId" in params
    assert "references.externalIds" in params
    assert "citations.citations" not in params


@respx.mock
def test_enrich_by_s2_id(plugin_ctx: PluginContext) -> None:
    respx.get(f"{PAPER_URL}/abc123").mock(return_value=httpx.Response(200, json=RECORD))
    paper = SemanticScholarMetadata(plugin_ctx).enrich(Paper(identifiers={"s2": "abc123"}))
    assert paper.abstract == "An abstract."


@respx.mock
def test_api_key_header(plugin_ctx: PluginContext) -> None:
    plugin_ctx.config.plugins["semantic_scholar"] = {"api_key": "test-key"}
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"total": 0, "data": []})
    )
    SemanticScholarSearcher(plugin_ctx).search(Query(text="x"))
    assert route.calls.last.request.headers["x-api-key"] == "test-key"


@respx.mock
def test_search_captures_oa_pdf_link(plugin_ctx: PluginContext) -> None:
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"total": 1, "offset": 0, "data": [RECORD]})
    )
    page = SemanticScholarSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=1)
    links = page.items[0].fulltext_links
    assert [(link.url, link.format, tuple(link.locator)) for link in links] == [
        ("https://pub.org/paper.pdf", "pdf", ("semantic_scholar",))
    ]
    assert links[0].license == "cc-by"
