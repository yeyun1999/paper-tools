"""OpenAlex plugin tests with respx replay (offline, deterministic)."""

from __future__ import annotations

import httpx
import respx

from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.core.query import Query
from paper_tools.plugins.openalex import (
    WORKS_URL,
    OpenAlexLocator,
    OpenAlexMetadata,
    OpenAlexSearcher,
    _query_params,
)

WORK = {
    "id": "https://openalex.org/W123",
    "ids": {
        "doi": "https://doi.org/10.1234/ABC",
        "openalex": "https://openalex.org/W123",
        "pmid": "https://pubmed.ncbi.nlm.nih.gov/999",
        "pmcid": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC777",
    },
    "display_name": "CRISPR base editing in vivo",
    "publication_year": 2023,
    "authorships": [{"author": {"display_name": "San Zhang"}}],
    "primary_location": {
        "source": {"display_name": "Nature"},
        "landing_page_url": "https://pub.org/paper",
        "license": "cc-by",
    },
    "open_access": {"is_oa": True, "oa_status": "gold"},
    "best_oa_location": {
        "pdf_url": "https://pub.org/paper.pdf",
        "landing_page_url": "https://pub.org/paper",
        "license": "cc-by",
    },
    "abstract_inverted_index": {"Hello": [0], "CRISPR": [1], "world": [2]},
    "type": "article",
}


def test_query_translation() -> None:
    q = Query(
        text="CRISPR",
        title="editing",
        author="Zhang",
        journal="Nature",
        year_from=2020,
        year_to=2025,
        open_access=True,
    )
    params = _query_params(q)
    assert params["search"] == "CRISPR"
    for fragment in (
        "title.search:editing",
        "raw_author_name.search:Zhang",
        "primary_location.source.display_name.search:Nature",
        "from_publication_date:2020-01-01",
        "until_publication_date:2025-12-31",
        "is_oa:true",
    ):
        assert fragment in params["filter"]


@respx.mock
def test_search_and_normalization(plugin_ctx: PluginContext) -> None:
    route = respx.get(WORKS_URL).mock(
        return_value=httpx.Response(
            200, json={"meta": {"count": 1, "next_cursor": "cur2"}, "results": [WORK]}
        )
    )
    page = OpenAlexSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=5)
    assert page.source == "openalex"
    assert page.total == 1
    assert page.next_cursor == "cur2"
    paper = page.items[0]
    assert paper.identifiers == {
        "doi": "10.1234/abc",
        "openalex": "W123",
        "pmid": "999",
        "pmcid": "PMC777",
    }
    assert paper.abstract == "Hello CRISPR world"
    assert paper.oa_status == "gold"
    assert paper.authors[0].name == "San Zhang"
    assert route.calls.last.request.url.params["cursor"] == "*"


@respx.mock
def test_enrich_by_doi(plugin_ctx: PluginContext) -> None:
    respx.get(f"{WORKS_URL}/doi:10.1234/abc").mock(return_value=httpx.Response(200, json=WORK))
    paper = OpenAlexMetadata(plugin_ctx).enrich(Paper(identifiers={"doi": "10.1234/abc"}))
    assert paper.title == "CRISPR base editing in vivo"
    assert paper.identifiers["openalex"] == "W123"


@respx.mock
def test_enrich_by_pmid(plugin_ctx: PluginContext) -> None:
    route = respx.get(WORKS_URL).mock(return_value=httpx.Response(200, json={"results": [WORK]}))
    paper = OpenAlexMetadata(plugin_ctx).enrich(Paper(identifiers={"pmid": "999"}))
    assert paper.title
    assert route.calls.last.request.url.params["filter"] == "pmid:999"


@respx.mock
def test_locator_best_oa_location(plugin_ctx: PluginContext) -> None:
    respx.get(f"{WORKS_URL}/doi:10.1234/abc").mock(return_value=httpx.Response(200, json=WORK))
    candidates = OpenAlexLocator(plugin_ctx).resolve(Paper(identifiers={"doi": "10.1234/abc"}))
    assert {(c.url, c.format) for c in candidates} == {
        ("https://pub.org/paper.pdf", "pdf"),
        ("https://pub.org/paper", "landing"),
    }
    assert all(c.locator == "openalex" and c.license == "cc-by" for c in candidates)


@respx.mock
def test_locator_closed(plugin_ctx: PluginContext) -> None:
    closed = {**WORK, "open_access": {"is_oa": False}, "best_oa_location": None}
    respx.get(f"{WORKS_URL}/doi:10.1234/abc").mock(return_value=httpx.Response(200, json=closed))
    assert OpenAlexLocator(plugin_ctx).resolve(Paper(identifiers={"doi": "10.1234/abc"})) == []


@respx.mock
def test_api_key_header_on_search(plugin_ctx: PluginContext) -> None:
    plugin_ctx.config.plugins["openalex"] = {"api_key": "test-key"}
    route = respx.get(WORKS_URL).mock(
        return_value=httpx.Response(200, json={"meta": {}, "results": []})
    )
    OpenAlexSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=1)
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"
    assert plugin_ctx.http._rates["api.openalex.org"] == 10.0


@respx.mock
def test_api_key_header_on_enrich_and_locator(plugin_ctx: PluginContext) -> None:
    plugin_ctx.config.plugins["openalex"] = {"api_key": "test-key"}
    route = respx.get(f"{WORKS_URL}/doi:10.1234/abc").mock(
        return_value=httpx.Response(200, json=WORK)
    )
    paper = Paper(identifiers={"doi": "10.1234/abc"})
    OpenAlexMetadata(plugin_ctx).enrich(paper)
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"
    OpenAlexLocator(plugin_ctx).resolve(paper)
    assert route.calls.last.request.headers["authorization"] == "Bearer test-key"


@respx.mock
def test_no_api_key_no_auth_header(plugin_ctx: PluginContext) -> None:
    route = respx.get(WORKS_URL).mock(
        return_value=httpx.Response(200, json={"meta": {}, "results": [WORK]})
    )
    OpenAlexSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=1)
    assert "authorization" not in route.calls.last.request.headers
