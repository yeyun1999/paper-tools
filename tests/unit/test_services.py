"""Unit tests: search routing, enrichment chain, full-text pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_search.core.errors import (
    ConfigError,
    FullTextUnavailableError,
    NotFoundError,
    UsageError,
)
from paper_search.core.models import FullTextCandidate, Paper
from paper_search.core.plugins import PluginMeta
from paper_search.core.query import Query
from paper_search.core.services import Services


def test_search_default_source(services: Services) -> None:
    page, _ = services.search.search(Query(text="CRISPR"))
    assert page.source == "fake"
    assert len(page.items) == 2


def test_search_unknown_source(services: Services) -> None:
    with pytest.raises(UsageError):
        services.search.search(Query(text="x"), source="nope")


def test_search_enrich(services: Services) -> None:
    page, _ = services.search.search(Query(text="CRISPR"), enrich=True)
    assert page.items[0].abstract is not None
    assert "fake" in page.items[0].sources


def test_enrich_stub(services: Services) -> None:
    stub = Paper(identifiers={"doi": "10.1000/fake1"})
    paper, warnings = services.metadata.enrich(stub)
    assert paper.title
    assert paper.abstract is not None
    assert paper.identifiers["pmcid"] == "PMC999"
    assert "fake" in paper.sources
    assert warnings == []


def test_enrich_chain_failover(services: Services) -> None:
    stub = Paper(identifiers={"doi": "10.1000/failmeta"})
    paper, warnings = services.metadata.enrich(stub)
    assert paper.abstract == "Abstract from fake2."
    assert any("fake" in w for w in warnings)


def test_enrich_not_found(services: Services) -> None:
    stub = Paper(identifiers={"doi": "10.1000/missing"})
    with pytest.raises(NotFoundError):
        services.metadata.enrich(stub)


def test_enrich_no_provider_for_kind(services: Services) -> None:
    stub = Paper(identifiers={"url": "https://example.org"})
    with pytest.raises(NotFoundError):
        services.metadata.enrich(stub)


def test_enrich_cache(services: Services) -> None:
    stub = Paper(identifiers={"doi": "10.1000/fake1"})
    services.metadata.enrich(stub)
    provider = services.registry.get("metadata", "fake")
    calls_before = provider.calls
    services.metadata.enrich(stub)
    assert provider.calls == calls_before  # served from cache


def test_fetch_pdf(services: Services, tmp_path: Path) -> None:
    result, _ = services.fetch.fetch("doi:10.1000/fake1", out_dir=tmp_path / "out")
    assert result.format == "pdf"
    assert result.path.exists()
    assert result.path.read_bytes().startswith(b"%PDF")
    assert result.downloader == "fake_dl"
    assert result.path.name == "10.1000_fake1.pdf"


def test_fetch_xml(services: Services, tmp_path: Path) -> None:
    result, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="xml", out_dir=tmp_path)
    assert result.format == "xml"
    assert b"<article>" in result.path.read_bytes()


def test_fetch_text_prefers_xml(services: Services, tmp_path: Path) -> None:
    result, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", out_dir=tmp_path)
    assert result.format == "text"
    assert result.extractor == "fake_ext"
    assert result.extracted_from == "xml"
    assert result.path.read_text(encoding="utf-8").startswith("EXTRACTED[xml]")


def test_fetch_bad_pdf_falls_back(services: Services, tmp_path: Path) -> None:
    result, warnings = services.fetch.fetch("doi:10.1000/badpdf", out_dir=tmp_path)
    assert result.source_url.endswith("good.pdf")
    assert any("not a valid PDF" in w for w in warnings)


def test_fetch_closed_raises_unavailable(services: Services, tmp_path: Path) -> None:
    with pytest.raises(FullTextUnavailableError) as exc_info:
        services.fetch.fetch("doi:10.1000/closed", out_dir=tmp_path)
    assert exc_info.value.exit_code == 4
    assert exc_info.value.details["publisher_url"] == "https://doi.org/10.1000/closed"


def test_fetch_forced_downloader_mismatch(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        services.fetch.fetch(
            "doi:10.1000/fake1", fmt="xml", out_dir=tmp_path, downloader="nonexistent"
        )


def test_fetch_file_cache_hit(services: Services, tmp_path: Path) -> None:
    services.fetch.fetch("doi:10.1000/fake1", out_dir=tmp_path)
    downloader = services.registry.get("downloader", "fake_dl")
    calls_before = downloader.calls
    result, _ = services.fetch.fetch("doi:10.1000/fake1", out_dir=tmp_path)
    assert downloader.calls == calls_before
    assert result.downloader == "cache"


def test_fetch_text_cache_hit_keeps_provenance(services: Services, tmp_path: Path) -> None:
    """Regression: cached text must not be re-validated/re-extracted as its source XML."""
    first, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", out_dir=tmp_path)
    downloader = services.registry.get("downloader", "fake_dl")
    calls_before = downloader.calls
    second, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", out_dir=tmp_path)
    assert downloader.calls == calls_before  # no re-download
    assert second.downloader == "cache"
    assert second.extractor == "fake_ext"
    assert second.extracted_from == "xml"
    assert second.path.name.endswith(".txt")
    assert second.path.read_text(encoding="utf-8") == first.path.read_text(encoding="utf-8")


def test_fetch_locator_config_error_becomes_warning(services: Services, tmp_path: Path) -> None:
    class BrokenConfigLocator:
        meta = PluginMeta(name="broken_cfg", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            raise ConfigError("missing email")

    services.registry.register("locator", BrokenConfigLocator())
    result, warnings = services.fetch.fetch("doi:10.1000/fake1", out_dir=tmp_path)
    assert result.source_url == "https://example.org/paper.pdf"
    assert any("broken_cfg: missing email" in w for w in warnings)


def test_enrich_config_error_propagates(services: Services) -> None:
    class BrokenConfigProvider:
        meta = PluginMeta(name="broken_cfg", version="0.1.0")
        id_kinds = frozenset({"doi"})

        def enrich(self, paper: Paper) -> Paper:
            raise ConfigError("missing email")

    services.registry.register("metadata", BrokenConfigProvider())
    with pytest.raises(ConfigError):
        services.metadata.enrich(Paper(identifiers={"doi": "10.1000/fake1"}))


def test_fetch_dedup_keeps_formats_per_url(services: Services, tmp_path: Path) -> None:
    class SameUrlLocator:
        meta = PluginMeta(name="sameurl", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            url = "https://example.org/package.tar.gz"
            return [
                FullTextCandidate(url=url, format="pdf", locator="sameurl"),
                FullTextCandidate(url=url, format="xml", locator="sameurl"),
                FullTextCandidate(url=url, format="xml", locator="sameurl"),  # duplicate
            ]

    services.registry.register("locator", SameUrlLocator())
    result, _ = services.fetch.fetch(
        "doi:10.1000/fake1", fmt="xml", out_dir=tmp_path, locators=["sameurl"]
    )
    assert result.format == "xml"
    assert result.source_url == "https://example.org/package.tar.gz"


class _PdfOnlyLocator:
    meta = PluginMeta(name="pdfonly", version="0.1.0")

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        return [
            FullTextCandidate(url="https://example.org/other.pdf", format="pdf", locator="pdfonly")
        ]


def test_fetch_locators_list_restricts(services: Services, tmp_path: Path) -> None:
    services.registry.register("locator", _PdfOnlyLocator())
    result, _ = services.fetch.fetch(
        "doi:10.1000/fake1", fmt="xml", out_dir=tmp_path, locators=["pdfonly", "fake"]
    )
    assert result.source_url == "https://example.org/paper.xml"
    with pytest.raises(FullTextUnavailableError):
        services.fetch.fetch(
            "doi:10.1000/fake1", fmt="xml", out_dir=tmp_path / "x", locators=["pdfonly"]
        )


def test_fetch_locators_default_from_config(services: Services, tmp_path: Path) -> None:
    class BoomLocator:
        meta = PluginMeta(name="boom", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            raise AssertionError("locator outside fetch.locators must not be consulted")

    services.registry.register("locator", BoomLocator())
    services.config.fetch.locators = ["fake"]
    result, warnings = services.fetch.fetch("doi:10.1000/fake1", out_dir=tmp_path)
    assert result.source_url == "https://example.org/paper.pdf"
    assert not warnings


def test_fetch_unknown_locator_usage_error(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        services.fetch.fetch("doi:10.1000/fake1", out_dir=tmp_path, locators=["nope"])
