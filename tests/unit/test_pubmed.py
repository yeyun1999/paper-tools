"""PubMed plugin tests with respx replay (offline, deterministic)."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_search.core.errors import UpstreamError
from paper_search.core.models import Paper
from paper_search.core.plugins import PluginContext
from paper_search.core.query import Query
from paper_search.plugins.pubmed import (
    EFETCH,
    ESEARCH,
    ESUMMARY,
    PubMedMetadata,
    PubMedSearcher,
    translate_query,
)

EFETCH_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <Journal>
          <Title>Nature</Title>
          <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>CRISPR base editing in vivo</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Base editors enable precise changes.</AbstractText>
          <AbstractText Label="RESULTS">We demonstrate editing in mice.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Zhang</LastName><ForeName>San</ForeName></Author>
        </AuthorList>
        <PublicationTypeList>
          <PublicationType>Journal Article</PublicationType>
        </PublicationTypeList>
        <ELocationID EIdType="doi">10.1038/s41586-023-00001-1</ELocationID>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345678</ArticleId>
        <ArticleId IdType="pmc">PMC1000000</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_translate_structured() -> None:
    q = Query(text="CRISPR", author="Zhang", year_from=2020, year_to=2025, open_access=True)
    term = translate_query(q)
    assert term == "CRISPR AND Zhang[Author] AND 2020:2025[dp] AND free full text[sb]"


def test_translate_raw_passthrough() -> None:
    assert translate_query(Query(raw="x[Title]")) == "x[Title]"


@respx.mock
def test_search(plugin_ctx: PluginContext) -> None:
    respx.get(ESEARCH).mock(
        return_value=httpx.Response(
            200, json={"esearchresult": {"count": "1", "idlist": ["12345678"]}}
        )
    )
    respx.get(ESUMMARY).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["12345678"],
                    "12345678": {
                        "title": "CRISPR base editing in vivo",
                        "fulljournalname": "Nature",
                        "pubdate": "2023 Jan 15",
                        "authors": [{"name": "Zhang S"}],
                        "articleids": [
                            {"idtype": "doi", "value": "10.1038/ABC"},
                            {"idtype": "pmc", "value": "PMC1000000"},
                        ],
                        "pubtype": ["Journal Article"],
                    },
                }
            },
        )
    )
    page = PubMedSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=5)
    assert page.source == "pubmed"
    assert page.total == 1
    paper = page.items[0]
    assert paper.identifiers == {
        "pmid": "12345678",
        "doi": "10.1038/abc",
        "pmcid": "PMC1000000",
    }
    assert paper.year == 2023
    assert paper.authors[0].name == "Zhang S"


@respx.mock
def test_search_error(plugin_ctx: PluginContext) -> None:
    respx.get(ESEARCH).mock(
        return_value=httpx.Response(200, json={"esearchresult": {"ERROR": "bad term"}})
    )
    with pytest.raises(UpstreamError):
        PubMedSearcher(plugin_ctx).search(Query(text="x"))


@respx.mock
def test_enrich_by_pmid(plugin_ctx: PluginContext) -> None:
    route = respx.get(EFETCH).mock(return_value=httpx.Response(200, content=EFETCH_XML))
    stub = Paper(identifiers={"pmid": "12345678"})
    paper = PubMedMetadata(plugin_ctx).enrich(stub)
    assert route.call_count == 1
    assert paper.title == "CRISPR base editing in vivo"
    assert "BACKGROUND: Base editors" in (paper.abstract or "")
    assert paper.identifiers["doi"] == "10.1038/s41586-023-00001-1"
    assert paper.identifiers["pmcid"] == "PMC1000000"
    assert paper.year == 2023
    assert paper.authors[0].name == "San Zhang"


@respx.mock
def test_enrich_by_doi_resolves_pmid(plugin_ctx: PluginContext) -> None:
    respx.get(ESEARCH).mock(
        return_value=httpx.Response(
            200, json={"esearchresult": {"count": "1", "idlist": ["12345678"]}}
        )
    )
    respx.get(EFETCH).mock(return_value=httpx.Response(200, content=EFETCH_XML))
    stub = Paper(identifiers={"doi": "10.1038/s41586-023-00001-1"})
    paper = PubMedMetadata(plugin_ctx).enrich(stub)
    assert paper.identifiers["pmid"] == "12345678"
    assert paper.abstract


@respx.mock
def test_enrich_not_found_returns_original(plugin_ctx: PluginContext) -> None:
    respx.get(EFETCH).mock(return_value=httpx.Response(200, content=b"<PubmedArticleSet/>"))
    stub = Paper(identifiers={"pmid": "999"})
    assert PubMedMetadata(plugin_ctx).enrich(stub) is stub


def test_api_key_raises_rate_limit(plugin_ctx: PluginContext) -> None:
    plugin_ctx.config.plugins["pubmed"] = {"api_key": "k"}
    PubMedSearcher(plugin_ctx)
    assert plugin_ctx.http._rates["eutils.ncbi.nlm.nih.gov"] == 10.0
