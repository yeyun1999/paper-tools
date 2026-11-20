"""Semantic Scholar plugin tests with respx replay (offline, deterministic)."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_search.core.errors import UsageError
from paper_search.core.models import Paper
from paper_search.core.plugins import PluginContext
from paper_search.core.query import Query
from paper_search.plugins.semantic_scholar import (
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
    params = route.calls.last.request.url.params
    assert params["limit"] == "5"
    assert "title" in params["fields"]


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
    respx.get(f"{PAPER_URL}/DOI:10.1234/abc").mock(return_value=httpx.Response(200, json=RECORD))
    paper = SemanticScholarMetadata(plugin_ctx).enrich(Paper(identifiers={"doi": "10.1234/abc"}))
    assert paper.title == "CRISPR base editing in vivo"
    assert paper.identifiers["s2"] == "abc123"


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
    assert [(link.url, link.format, link.locator) for link in links] == [
        ("https://pub.org/paper.pdf", "pdf", "semantic_scholar")
    ]
    assert links[0].license == "cc-by"
