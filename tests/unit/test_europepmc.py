"""Europe PMC plugin tests with respx replay."""

from __future__ import annotations

import httpx
import respx

from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.core.query import Query
from paper_tools.plugins.europepmc import (
    SEARCH_URL,
    EuropePmcMetadata,
    EuropePmcSearcher,
    translate_query,
)

RECORD = {
    "id": "12345678",
    "source": "MED",
    "pmid": "12345678",
    "pmcid": "PMC1000000",
    "doi": "10.1038/ABC",
    "title": "CRISPR base editing in vivo.",
    "authorString": "Zhang S, Li S.",
    "journalTitle": "Nature",
    "pubYear": "2023",
    "abstractText": "Base editors enable precise changes.",
    "isOpenAccess": "Y",
    "license": "cc by",
    "pubTypeList": {"pubType": ["Journal Article"]},
}


def test_translate_structured() -> None:
    q = Query(text="CRISPR", author="Zhang", year_from=2020, year_to=2025, open_access=True)
    assert translate_query(q) == (
        'CRISPR AND AUTH:"Zhang" AND FIRST_PDATE:[2020 TO 2025] AND OPEN_ACCESS:y'
    )


@respx.mock
def test_search(plugin_ctx: PluginContext) -> None:
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={"hitCount": 1, "nextCursorMark": "abc", "resultList": {"result": [RECORD]}},
        )
    )
    page = EuropePmcSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=5)
    assert page.source == "europepmc"
    assert page.total == 1
    assert page.next_cursor == "abc"
    paper = page.items[0]
    assert paper.title == "CRISPR base editing in vivo"
    assert paper.identifiers["doi"] == "10.1038/abc"
    assert paper.oa_status == "gold"
    assert paper.abstract
    assert len(paper.authors) == 2


@respx.mock
def test_enrich_by_doi(plugin_ctx: PluginContext) -> None:
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"resultList": {"result": [RECORD]}})
    )
    stub = Paper(identifiers={"doi": "10.1038/abc"})
    paper = EuropePmcMetadata(plugin_ctx).enrich(stub)
    assert route.calls.last.request.url.params["query"] == 'DOI:"10.1038/abc"'
    assert paper.title
    assert paper.identifiers["pmid"] == "12345678"


@respx.mock
def test_enrich_not_found(plugin_ctx: PluginContext) -> None:
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"resultList": {"result": []}})
    )
    stub = Paper(identifiers={"doi": "10.9999/nope"})
    assert EuropePmcMetadata(plugin_ctx).enrich(stub) is stub
