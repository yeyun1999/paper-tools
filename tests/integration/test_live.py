"""Live smoke tests against real upstream APIs. Run: uv run pytest -m live"""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_tools.core.cache import Cache
from paper_tools.core.config import AppConfig, load_config
from paper_tools.core.errors import PaperToolsError, UpstreamError
from paper_tools.core.http import HttpClient
from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext, PluginRegistry
from paper_tools.core.query import Query
from paper_tools.core.services import Services

pytestmark = pytest.mark.live


@pytest.fixture
def ctx(tmp_path: Path) -> PluginContext:
    config = AppConfig()
    cache = Cache(root=tmp_path / "cache")
    return PluginContext(config=config, http=HttpClient(cache=cache), cache=cache)


@pytest.fixture
def live_services(tmp_path: Path) -> Services:
    config = load_config()
    if not config.plugin_config("unpaywall").get("email"):
        pytest.skip("unpaywall email not configured (config set plugins.unpaywall.email ...)")
    cache = Cache(root=tmp_path / "cache")
    http = HttpClient(cache=cache, mailto=config.general.mailto)
    ctx = PluginContext(config=config, http=http, cache=cache)
    registry = PluginRegistry.discover(ctx)
    return Services(config=config, cache=cache, registry=registry)


def _oa_pmcid(services: Services, *, journal: str | None = None) -> str:
    page, _ = services.search.search(
        Query(text="CRISPR", journal=journal, open_access=True), source="europepmc", limit=10
    )
    pmcid = next((p.identifiers["pmcid"] for p in page.items if p.identifiers.get("pmcid")), None)
    assert pmcid, "no OA PMC paper found in live search"
    return pmcid


def test_builtin_discovery(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    assert {"pubmed", "europepmc", "crossref", "openalex", "semantic_scholar"} <= set(
        registry.names("searcher")
    )
    assert "pubmed" in registry.names("metadata")
    assert {"europepmc", "pmc_oa", "unpaywall", "openalex"} <= set(registry.names("locator"))
    assert {"europepmc", "pmc_oa", "http_direct"} <= set(registry.names("downloader"))
    assert "jats" in registry.names("extractor")


def test_pubmed_search_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    page = registry.get("searcher", "pubmed").search(Query(text="CRISPR base editing"), limit=3)
    assert page.items
    assert all(p.identifiers.get("pmid") for p in page.items)
    assert page.total and page.total > 100


def test_europepmc_search_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    page = registry.get("searcher", "europepmc").search(Query(text="CRISPR base editing"), limit=3)
    assert page.items
    assert any(p.identifiers.get("doi") for p in page.items)


def test_pubmed_enrich_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    page = registry.get("searcher", "pubmed").search(Query(text="CRISPR base editing"), limit=1)
    pmid = page.items[0].identifiers["pmid"]
    paper = registry.get("metadata", "pubmed").enrich(Paper(identifiers={"pmid": pmid}))
    assert paper.title
    assert paper.abstract


def test_fetch_xml_live(live_services: Services, tmp_path: Path) -> None:
    pmcid = _oa_pmcid(live_services)
    result, _ = live_services.fetch.fetch(f"pmcid:{pmcid}", fmt="xml", out_dir=tmp_path / "out")
    assert result.path.exists()
    assert b"article" in result.path.read_bytes()[:500]
    assert result.downloader in {"europepmc", "pmc_oa", "http_direct", "cache"}


def test_fetch_pdf_live(live_services: Services, tmp_path: Path) -> None:
    # PLOS ONE is fully OA and in the PMC OA subset; individual papers may still
    # lack a retrievable PDF, so try a few candidates before failing.
    page, _ = live_services.search.search(
        Query(text="CRISPR", journal="PLoS ONE", open_access=True), source="europepmc", limit=10
    )
    pmcids = [p.identifiers["pmcid"] for p in page.items if p.identifiers.get("pmcid")][:3]
    assert pmcids, "no OA PLOS ONE paper with PMCID found"
    errors: list[str] = []
    for pmcid in pmcids:
        try:
            result, _ = live_services.fetch.fetch(
                f"pmcid:{pmcid}", fmt="pdf", out_dir=tmp_path / "out"
            )
        except PaperToolsError as exc:
            errors.append(f"{pmcid}: {exc.message}")
            continue
        assert result.path.read_bytes().startswith(b"%PDF")
        return
    pytest.fail(f"no OA PDF retrievable from {len(pmcids)} PLOS ONE candidates: {errors}")


def test_fetch_text_live(live_services: Services, tmp_path: Path) -> None:
    pmcid = _oa_pmcid(live_services)
    result, _ = live_services.fetch.fetch(f"pmcid:{pmcid}", fmt="text", out_dir=tmp_path / "out")
    text = result.path.read_text(encoding="utf-8")
    assert len(text) > 500
    assert result.extractor in {"jats", "pypdf"}


def test_unpaywall_enrich_live(live_services: Services) -> None:
    page, _ = live_services.search.search(
        Query(text="CRISPR", journal="PLoS ONE", open_access=True), source="europepmc", limit=1
    )
    doi = page.items[0].identifiers["doi"]
    paper = live_services.registry.get("metadata", "unpaywall").enrich(
        Paper(identifiers={"doi": doi})
    )
    assert paper.oa_status in {"gold", "hybrid", "bronze", "green"}


_NUMPY_DOI = "10.1038/s41586-020-2649-2"  # stable, well-known OA paper


def test_crossref_search_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    page = registry.get("searcher", "crossref").search(Query(text="CRISPR base editing"), limit=3)
    assert page.items
    assert all(p.identifiers.get("doi") for p in page.items)


def test_openalex_search_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    page = registry.get("searcher", "openalex").search(
        Query(text="CRISPR base editing", open_access=True), limit=3
    )
    assert page.items
    assert any(p.identifiers.get("doi") for p in page.items)
    assert all(p.oa_status != "closed" for p in page.items)


def test_semantic_scholar_search_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    try:
        page = registry.get("searcher", "semantic_scholar").search(
            Query(text="CRISPR base editing"), limit=2
        )
    except UpstreamError as exc:
        pytest.skip(
            "Semantic Scholar shared quota unavailable "
            f"(status={exc.details.get('status', 'network')}); "
            "configure plugins.semantic_scholar.api_key for reliable access"
        )
    assert page.items
    assert all(p.identifiers.get("s2") for p in page.items)


def test_cross_source_doi_normalization_live(ctx: PluginContext) -> None:
    registry = PluginRegistry.discover(ctx)
    crossref = registry.get("metadata", "crossref").enrich(Paper(identifiers={"doi": _NUMPY_DOI}))
    openalex = registry.get("metadata", "openalex").enrich(Paper(identifiers={"doi": _NUMPY_DOI}))
    assert crossref.title
    assert openalex.title
    assert crossref.identifiers["doi"] == openalex.identifiers["doi"] == _NUMPY_DOI
    assert openalex.identifiers.get("openalex", "").startswith("W")


def test_mcp_stdio_full_flow_live(tmp_path: Path) -> None:
    """Real `paper-tools mcp` subprocess: search -> get -> fetch over stdio."""
    pytest.importorskip("mcp", reason="mcp extra not installed")
    import asyncio
    import json
    import sys
    from typing import Any

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    def payload(result: Any) -> dict[str, Any]:
        if result.structured_content is not None:
            return dict(result.structured_content)
        return dict(json.loads(result.content[0].text))

    async def flow() -> Path:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from paper_tools.cli.app import main; main()", "mcp"],
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            search = payload(
                await session.call_tool(
                    "search_papers",
                    {"query": "CRISPR base editing", "source": "pubmed", "limit": 2},
                )
            )
            assert "data" in search, search
            pmid = search["data"]["items"][0]["identifiers"]["pmid"]
            got = payload(await session.call_tool("get_paper", {"identifier": f"pmid:{pmid}"}))
            assert got["data"]["title"], got
            fetched = payload(
                await session.call_tool(
                    "fetch_fulltext",
                    {
                        "identifier": "pmcid:PMC13434336",
                        "format": "text",
                        "out_dir": str(tmp_path / "out"),
                    },
                )
            )
            assert "data" in fetched, fetched
            return Path(fetched["data"]["path"])

    path = asyncio.run(asyncio.wait_for(flow(), timeout=180))
    assert len(path.read_text(encoding="utf-8")) > 500
