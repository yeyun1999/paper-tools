"""bioRxiv plugin tests: respx replay + contract invariants (offline)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from paper_tools.core.cache import Cache
from paper_tools.core.config import AppConfig
from paper_tools.core.http import HttpClient
from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext

from paper_tools_biorxiv.metadata import API_BASE, BiorxivMetadata

DOI = "10.1101/2020.03.09.984229"

RECORD_V1 = {
    "doi": DOI,
    "title": "CRISPR base editing in vivo",
    "authors": "Zhang, San; Li, Si",
    "date": "2020-03-10",
    "version": "1",
    "license": "cc_by",
    "abstract": "First version abstract.",
    "server": "bioRxiv",
}
RECORD_V2 = {**RECORD_V1, "version": "2", "date": "2020-06-01", "abstract": "Latest abstract."}

OK = {"messages": [{"status": "ok"}], "collection": [RECORD_V1, RECORD_V2]}
MISS = {"messages": [{"status": "no posts found"}], "collection": []}


@pytest.fixture
def ctx(tmp_path: Path) -> PluginContext:
    cache = Cache(root=tmp_path / "cache")
    return PluginContext(
        config=AppConfig(), http=HttpClient(cache=cache, sleep=lambda _s: None), cache=cache
    )


@respx.mock
def test_enrich_latest_version(ctx: PluginContext) -> None:
    respx.get(f"{API_BASE}/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=OK))
    result = BiorxivMetadata(ctx).enrich(Paper(identifiers={"doi": DOI}))
    assert result.title == "CRISPR base editing in vivo"
    assert result.abstract == "Latest abstract."
    assert result.year == 2020
    assert [a.name for a in result.authors] == ["San Zhang", "Si Li"]
    assert result.license == "cc-by"
    assert result.oa_status == "green"
    assert result.publication_type == "preprint"
    assert result.publisher_url == f"https://www.biorxiv.org/content/{DOI}v2"
    assert result.identifiers["doi"] == DOI


@respx.mock
def test_medrxiv_fallback(ctx: PluginContext) -> None:
    respx.get(f"{API_BASE}/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=MISS))
    med = {**RECORD_V2, "server": "medRxiv"}
    respx.get(f"{API_BASE}/medrxiv/{DOI}").mock(
        return_value=httpx.Response(200, json={"messages": [{"status": "ok"}], "collection": [med]})
    )
    result = BiorxivMetadata(ctx).enrich(Paper(identifiers={"doi": DOI}))
    assert result.abstract == "Latest abstract."
    assert result.publisher_url == f"https://www.medrxiv.org/content/{DOI}v2"


@respx.mock
def test_both_servers_miss_returns_stub(ctx: PluginContext) -> None:
    respx.get(f"{API_BASE}/biorxiv/{DOI}").mock(return_value=httpx.Response(200, json=MISS))
    respx.get(f"{API_BASE}/medrxiv/{DOI}").mock(return_value=httpx.Response(200, json=MISS))
    stub = Paper(identifiers={"doi": DOI})
    assert BiorxivMetadata(ctx).enrich(stub) is stub


def test_no_doi_returns_stub(ctx: PluginContext) -> None:
    stub = Paper(identifiers={"pmid": "123"})
    assert BiorxivMetadata(ctx).enrich(stub) is stub


@respx.mock
def test_configured_server_first(ctx: PluginContext) -> None:
    ctx.config.plugins["biorxiv"] = {"server": "medrxiv"}
    route = respx.get(f"{API_BASE}/medrxiv/{DOI}").mock(return_value=httpx.Response(200, json=OK))
    BiorxivMetadata(ctx).enrich(Paper(identifiers={"doi": DOI}))
    assert route.called


def test_role_contracts(ctx: PluginContext) -> None:
    plugin = BiorxivMetadata(ctx)
    assert plugin.meta.name == "biorxiv"
    assert plugin.meta.version
    assert plugin.id_kinds == frozenset({"doi"})
    assert isinstance(plugin.enrich(Paper(identifiers={"pmid": "1"})), Paper)
