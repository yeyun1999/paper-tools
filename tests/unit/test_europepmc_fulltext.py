"""Europe PMC Locator + Downloader (fullTextXML) tests."""

from __future__ import annotations

import httpx
import respx

from paper_search.core.models import FullTextCandidate, Paper
from paper_search.core.plugins import PluginContext
from paper_search.plugins.europepmc import (
    SEARCH_URL,
    EuropePmcDownloader,
    EuropePmcLocator,
    fulltext_xml_url,
)
from tests.conftest import XML_BYTES

RECORD = {
    "pmcid": "PMC123",
    "pmid": "999",
    "doi": "10.1234/abc",
    "inEPMC": "Y",
    "isOpenAccess": "Y",
    "license": "cc-by",
    "title": "A paper.",
}


def mock_search(record: dict[str, object] | None) -> None:
    results = [record] if record else []
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"resultList": {"result": results}})
    )


@respx.mock
def test_locator_in_epmc(plugin_ctx: PluginContext) -> None:
    mock_search(RECORD)
    candidates = EuropePmcLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"}))
    assert len(candidates) == 1
    assert candidates[0].url == fulltext_xml_url("PMC123")
    assert candidates[0].format == "xml"
    assert candidates[0].locator == "europepmc"
    assert candidates[0].license == "cc-by"


@respx.mock
def test_locator_not_in_epmc(plugin_ctx: PluginContext) -> None:
    mock_search({**RECORD, "inEPMC": "N"})
    assert EuropePmcLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"})) == []


@respx.mock
def test_locator_no_record(plugin_ctx: PluginContext) -> None:
    mock_search(None)
    assert EuropePmcLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"})) == []


@respx.mock
def test_downloader_fulltext_xml(plugin_ctx: PluginContext) -> None:
    url = fulltext_xml_url("PMC123")
    respx.get(url).mock(return_value=httpx.Response(200, content=XML_BYTES))
    candidate = FullTextCandidate(url=url, format="xml", locator="europepmc", license="cc-by")
    artifact = EuropePmcDownloader(plugin_ctx).download(candidate)
    assert artifact.format == "xml"
    assert artifact.content == XML_BYTES
    assert artifact.downloader == "europepmc"
    assert artifact.license == "cc-by"


def test_downloader_supports(plugin_ctx: PluginContext) -> None:
    dl = EuropePmcDownloader(plugin_ctx)
    assert dl.supports(
        FullTextCandidate(url=fulltext_xml_url("PMC1"), format="xml", locator="europepmc")
    )
    assert not dl.supports(
        FullTextCandidate(url="https://example.org/a.xml", format="xml", locator="europepmc")
    )
