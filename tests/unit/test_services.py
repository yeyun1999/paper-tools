"""Unit tests: search routing, enrichment chain, full-text pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_search.core.errors import (
    ConfigError,
    FullTextUnavailableError,
    NotFoundError,
    UpstreamError,
    UsageError,
)
from paper_search.core.models import FullTextCandidate, Paper, SearchPage
from paper_search.core.plugins import PluginMeta
from paper_search.core.query import Query
from paper_search.core.services import Services


def test_search_default_source(services: Services) -> None:
    page, _ = services.search.search(Query(text="CRISPR"))
    assert page.source == "fake"
    assert len(page.items) == 2


def test_search_unknown_source(services: Services) -> None:
    with pytest.raises(UsageError):
        services.search.search(Query(text="x"), sources=["nope"])


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


class StubSearcher:
    def __init__(self, name: str, items: list[Paper], next_cursor: str | None = None) -> None:
        self.meta = PluginMeta(name=name, version="0.1.0")
        self._items = items
        self._next = next_cursor
        self.calls: list[str | None] = []

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        self.calls.append(cursor)
        return SearchPage(
            items=self._items[:limit],
            total=len(self._items),
            next_cursor=self._next,
            source=self.meta.name,
        )


class BrokenSearcher:
    def __init__(self, name: str) -> None:
        self.meta = PluginMeta(name=name, version="0.1.0")

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        raise UpstreamError(f"{self.meta.name} down")


def test_multi_source_dedup_merge_and_order(services: Services) -> None:
    sa = StubSearcher(
        "sa",
        [
            Paper(title="A", identifiers={"doi": "10.1000/x", "pmid": "1"}),
            Paper(title="B", identifiers={"doi": "10.1000/y"}),
        ],
    )
    sb = StubSearcher(
        "sb",
        [
            Paper(title="A variant", identifiers={"doi": "10.1000/x", "pmcid": "PMC9"}, year=2024),
            Paper(title="C", identifiers={"doi": "10.1000/z"}),
        ],
    )
    services.registry.register("searcher", sa)
    services.registry.register("searcher", sb)
    page, warnings = services.search.search(Query(text="q"), sources=["sa", "sb"], limit=10)
    assert page.source == "sa,sb"
    assert page.total == 4  # pre-dedup sum
    assert [p.title for p in page.items] == ["A", "B", "C"]  # round-robin, fill-missing
    first = page.items[0]
    assert first.identifiers == {"doi": "10.1000/x", "pmid": "1", "pmcid": "PMC9"}
    assert first.year == 2024
    assert set(first.sources) == {"sa", "sb"}
    assert not warnings


def test_multi_source_title_fingerprint_dedup(services: Services) -> None:
    sa = StubSearcher("sa", [Paper(title="Hello  CRISPR World")])
    sb = StubSearcher("sb", [Paper(title="hello crispr world", year=2020)])
    services.registry.register("searcher", sa)
    services.registry.register("searcher", sb)
    page, _ = services.search.search(Query(text="q"), sources=["sa", "sb"])
    assert len(page.items) == 1
    assert page.items[0].year == 2020


def test_multi_source_limit_truncates(services: Services) -> None:
    sa = StubSearcher(
        "sa", [Paper(title=f"P{i}", identifiers={"doi": f"10.1000/{i}"}) for i in range(5)]
    )
    services.registry.register("searcher", sa)
    services.registry.register("searcher", StubSearcher("sb", []))
    page, _ = services.search.search(Query(text="q"), sources=["sa", "sb"], limit=2)
    assert len(page.items) == 2


def test_multi_source_failure_degrades_to_warning(services: Services) -> None:
    services.registry.register(
        "searcher", StubSearcher("sa", [Paper(title="A", identifiers={"doi": "10.1000/x"})])
    )
    services.registry.register("searcher", BrokenSearcher("sb"))
    page, warnings = services.search.search(Query(text="q"), sources=["sa", "sb"])
    assert len(page.items) == 1
    assert any(w.startswith("sb:") for w in warnings)


def test_multi_source_all_fail_raises(services: Services) -> None:
    services.registry.register("searcher", BrokenSearcher("sb1"))
    services.registry.register("searcher", BrokenSearcher("sb2"))
    with pytest.raises(UpstreamError):
        services.search.search(Query(text="q"), sources=["sb1", "sb2"])


def test_multi_source_cursor_roundtrip(services: Services) -> None:
    sa = StubSearcher("sa", [Paper(title="A", identifiers={"doi": "10.1000/x"})], next_cursor="a1")
    sb = StubSearcher("sb", [Paper(title="B", identifiers={"doi": "10.1000/y"})], next_cursor="b1")
    services.registry.register("searcher", sa)
    services.registry.register("searcher", sb)
    page, _ = services.search.search(Query(text="q"), sources=["sa", "sb"])
    assert page.next_cursor is not None
    assert json.loads(page.next_cursor) == {"sa": "a1", "sb": "b1"}
    services.search.search(Query(text="q"), sources=["sa", "sb"], cursor=page.next_cursor)
    assert sa.calls[-1] == "a1"
    assert sb.calls[-1] == "b1"
    # a source absent from the aggregated cursor is exhausted and not queried
    services.search.search(Query(text="q"), sources=["sa", "sb"], cursor='{"sa": "a2"}')
    assert sa.calls[-1] == "a2"
    assert sb.calls[-1] == "b1"  # unchanged


def test_multi_source_invalid_cursor(services: Services) -> None:
    services.registry.register("searcher", StubSearcher("sa", []))
    services.registry.register("searcher", StubSearcher("sb", []))
    with pytest.raises(UsageError):
        services.search.search(Query(text="q"), sources=["sa", "sb"], cursor="plain-opaque")


def test_single_source_cursor_stays_opaque(services: Services) -> None:
    page, _ = services.search.search(Query(text="q"), sources=["fake"], cursor="c9")
    assert page.next_cursor == "c9"  # FakeSearcher echoes the cursor; no JSON wrapping
    assert page.source == "fake"


def test_fetch_uses_paper_fulltext_links(services: Services, tmp_path: Path) -> None:
    class LinkMetadata:
        meta = PluginMeta(name="linkmeta", version="0.1.0")
        id_kinds = frozenset({"doi"})

        def enrich(self, paper: Paper) -> Paper:
            return Paper(
                title="Seeded",
                abstract="A",
                identifiers=paper.identifiers,
                fulltext_links=[
                    FullTextCandidate(
                        url="https://example.org/seed.pdf", format="pdf", locator="linkmeta"
                    )
                ],
            )

    class EmptyLocator:
        meta = PluginMeta(name="emptyloc", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            return []

    services.registry.register("metadata", LinkMetadata())
    services.registry.register("locator", EmptyLocator())
    # "missing" makes the fake providers pass through, so linkmeta supplies the links
    result, _ = services.fetch.fetch("doi:10.1000/missing", out_dir=tmp_path, locators=["emptyloc"])
    assert result.source_url == "https://example.org/seed.pdf"
    assert result.path.read_bytes().startswith(b"%PDF")
