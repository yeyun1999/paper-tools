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
    fulltext_xml_url,
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
    "journalInfo": {"journal": {"issn": "0028-0836"}},
    "citedByCount": 42,
    "referenceCount": 2,
    "referenceList": {
        "reference": [
            {
                "title": "Earlier editing work.",
                "doi": "10.1234/REF",
                "pmid": "111",
                "pmcid": "PMC111",
                "authorString": "Zhang S, Li S",
                "pubYear": "2020",
            },
            {"title": "Untitled reference", "pubYear": 2021},
            None,
        ]
    },
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
    assert paper.license == "cc-by"
    assert paper.abstract
    assert len(paper.authors) == 2
    assert paper.issn == "0028-0836"
    assert paper.cited_by_count == 42
    assert paper.references_count == 2
    assert paper.cited_by_papers == []
    assert paper.impact_factor is None
    assert len(paper.reference_papers) == 2
    reference = paper.reference_papers[0]
    assert reference.title == "Earlier editing work"
    assert reference.identifiers == {"doi": "10.1234/ref", "pmid": "111", "pmcid": "PMC111"}
    assert [author.name for author in reference.authors] == ["Zhang S", "Li S"]
    assert reference.year == 2020
    assert paper.reference_papers[1].year == 2021


@respx.mock
def test_malformed_extended_fields_are_ignored(plugin_ctx: PluginContext) -> None:
    record = {
        **RECORD,
        "pubYear": "unknown",
        "journalInfo": {"journal": {"issn": 123}},
        "citedByCount": True,
        "referenceCount": -1,
        "referenceList": "not-a-dict",
    }
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"resultList": {"result": [record]}})
    )
    paper = EuropePmcSearcher(plugin_ctx).search(Query(text="x"), limit=1).items[0]
    assert paper.year is None
    assert paper.issn is None
    assert paper.cited_by_count is None
    assert paper.references_count is None
    assert paper.reference_papers == []


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


@respx.mock
def test_fulltext_links_from_core_record(plugin_ctx: PluginContext) -> None:
    record = {
        **RECORD,
        "inEPMC": "Y",
        "fullTextUrlList": {
            "fullTextUrl": [
                {
                    "url": "https://europepmc.org/articles/PMC1000000?pdf=render",
                    "documentStyle": "pdf",
                    "availabilityCode": "OA",
                },
                {
                    "url": "https://pub.org/closed.pdf",
                    "documentStyle": "pdf",
                    "availabilityCode": "R",  # subscription: must be skipped
                },
            ]
        },
    }
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"resultList": {"result": [record]}})
    )
    page = EuropePmcSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=1)
    links = page.items[0].fulltext_links
    assert {(link.url, link.format) for link in links} == {
        ("https://europepmc.org/articles/PMC1000000?pdf=render", "pdf"),
        (fulltext_xml_url("PMC1000000"), "xml"),
    }
    assert all(link.locator == ["europepmc"] for link in links)
