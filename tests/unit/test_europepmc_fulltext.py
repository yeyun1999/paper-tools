"""Europe PMC Locator (fullTextXML) tests."""

from __future__ import annotations

import httpx
import respx

from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.plugins.europepmc import (
    SEARCH_URL,
    EuropePmcLocator,
    fulltext_xml_url,
)

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
    assert candidates[0].locator == ["europepmc"]
    assert candidates[0].license == "cc-by"


@respx.mock
def test_locator_not_in_epmc(plugin_ctx: PluginContext) -> None:
    mock_search({**RECORD, "inEPMC": "N"})
    assert EuropePmcLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"})) == []


@respx.mock
def test_locator_no_record(plugin_ctx: PluginContext) -> None:
    mock_search(None)
    assert EuropePmcLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"})) == []
