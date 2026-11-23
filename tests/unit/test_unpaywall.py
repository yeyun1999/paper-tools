"""Unpaywall plugin tests with respx replay (offline, deterministic)."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_tools.core.errors import ConfigError
from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.plugins.unpaywall import API_BASE, UnpaywallLocator, UnpaywallMetadata

DOI_URL = API_BASE + "10.1234/abc"

OA_PAYLOAD = {
    "is_oa": True,
    "oa_status": "gold",
    "doi_url": "https://doi.org/10.1234/abc",
    "best_oa_location": {
        "url_for_pdf": "https://pub.org/paper.pdf",
        "url_for_landing_page": "https://pub.org/paper",
        "url": "https://pub.org/paper.pdf",
        "license": "cc-by",
    },
    "oa_locations": [
        {
            "url_for_pdf": "https://pub.org/paper.pdf",
            "url_for_landing_page": "https://pub.org/paper",
            "url": "https://pub.org/paper.pdf",
            "license": "cc-by",
        },
        {"url": "https://repo.org/handle/123", "license": None},
    ],
}


@pytest.fixture
def unpaywall_ctx(plugin_ctx: PluginContext) -> PluginContext:
    plugin_ctx.config.plugins["unpaywall"] = {"email": "test@example.org"}
    return plugin_ctx


@respx.mock
def test_locator_candidates(unpaywall_ctx: PluginContext) -> None:
    respx.get(DOI_URL).mock(return_value=httpx.Response(200, json=OA_PAYLOAD))
    candidates = UnpaywallLocator(unpaywall_ctx).resolve(Paper(identifiers={"doi": "10.1234/abc"}))
    assert candidates[0].url == "https://pub.org/paper.pdf"
    assert candidates[0].format == "pdf"
    assert candidates[0].locator == "unpaywall"
    assert candidates[0].license == "cc-by"
    urls = {(c.url, c.format) for c in candidates}
    assert ("https://pub.org/paper", "landing") in urls
    assert ("https://repo.org/handle/123", "landing") in urls
    # best location is not duplicated
    assert sum(c.url == "https://pub.org/paper.pdf" for c in candidates) == 1


@respx.mock
def test_enrich_oa_status(unpaywall_ctx: PluginContext) -> None:
    respx.get(DOI_URL).mock(return_value=httpx.Response(200, json=OA_PAYLOAD))
    paper = UnpaywallMetadata(unpaywall_ctx).enrich(Paper(identifiers={"doi": "10.1234/abc"}))
    assert paper.oa_status == "gold"
    assert paper.license == "cc-by"
    assert paper.publisher_url == "https://doi.org/10.1234/abc"


@respx.mock
def test_closed_no_candidates(unpaywall_ctx: PluginContext) -> None:
    respx.get(DOI_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "is_oa": False,
                "oa_status": "closed",
                "best_oa_location": None,
                "oa_locations": [],
            },
        )
    )
    stub = Paper(identifiers={"doi": "10.1234/abc"})
    assert UnpaywallLocator(unpaywall_ctx).resolve(stub) == []
    assert UnpaywallMetadata(unpaywall_ctx).enrich(stub).oa_status == "closed"


def test_missing_email_raises_config_error(plugin_ctx: PluginContext) -> None:
    stub = Paper(identifiers={"doi": "10.1234/abc"})
    with pytest.raises(ConfigError) as exc_info:
        UnpaywallLocator(plugin_ctx).resolve(stub)
    assert exc_info.value.exit_code == 5
    with pytest.raises(ConfigError):
        UnpaywallMetadata(plugin_ctx).enrich(stub)


def test_no_doi_returns_empty(plugin_ctx: PluginContext) -> None:
    assert UnpaywallLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "1"})) == []
