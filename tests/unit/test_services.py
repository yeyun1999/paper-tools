"""Unit tests: search routing, enrichment chain, full-text pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_tools.core.errors import (
    ConfigError,
    FullTextUnavailableError,
    NotFoundError,
    UpstreamError,
    UsageError,
)
from paper_tools.core.models import Artifact, ArtifactFormat, FullTextCandidate, Paper, SearchPage
from paper_tools.core.plugins import PluginMeta
from paper_tools.core.query import Query
from paper_tools.core.services import Services
from tests.conftest import PDF_BYTES, XML_BYTES


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
    output = tmp_path / "custom.pdf"
    result, _ = services.fetch.fetch("doi:10.1000/fake1", output=output)
    assert result.format == "pdf"
    assert result.path == output
    assert result.path.read_bytes().startswith(b"%PDF")
    assert result.downloader == "fake_dl"


def test_fetch_xml(services: Services, tmp_path: Path) -> None:
    output = tmp_path / "paper.xml"
    result, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="xml", output=output)
    assert result.format == "xml"
    assert result.path == output
    assert b"<article>" in result.path.read_bytes()


def test_fetch_text_prefers_xml(services: Services, tmp_path: Path) -> None:
    output = tmp_path / "paper.txt"
    result, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", output=output)
    assert result.format == "text"
    assert result.extractor == "fake_ext"
    assert result.extracted_from == "xml"
    assert result.path == output
    assert result.path.read_text(encoding="utf-8").startswith("EXTRACTED[xml]")


def test_fetch_default_output(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result, _ = services.fetch.fetch("doi:10.1000/fake1")
    assert result.path == Path("CRISPR_base_editing_review.pdf")
    assert result.path.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize(
    ("title", "filename"),
    [
        ("A/B: C?", "A_B_C.pdf"),
        ("中文 标题", "中文_标题.pdf"),
        ("CON", "_CON.pdf"),
    ],
)
def test_fetch_default_output_sanitizes_title(
    services: Services,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    title: str,
    filename: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        services.metadata,
        "enrich",
        lambda paper: (Paper(title=title, identifiers=paper.identifiers, abstract="A"), []),
    )
    result, _ = services.fetch.fetch("doi:10.1000/fake1")
    assert result.path == Path(filename)
    assert result.path.exists()


def test_fetch_default_output_uses_format_extension(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text")
    assert result.path == Path("CRISPR_base_editing_review.txt")


def test_fetch_default_output_appends_id_on_collision(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("Same_title.pdf").write_bytes(b"existing")
    monkeypatch.setattr(
        services.metadata,
        "enrich",
        lambda paper: (Paper(title="Same title", identifiers=paper.identifiers, abstract="A"), []),
    )
    result, _ = services.fetch.fetch("doi:10.1000/fake1")
    assert result.path == Path("Same_title_10.1000_fake1.pdf")
    repeated, _ = services.fetch.fetch("doi:10.1000/fake1")
    assert repeated.path == result.path
    other, _ = services.fetch.fetch("doi:10.1000/fake2")
    assert other.path == Path("Same_title_10.1000_fake2.pdf")


def test_fetch_default_output_appends_pmid(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("Same_title.pdf").write_bytes(b"existing")
    monkeypatch.setattr(
        services.metadata,
        "enrich",
        lambda paper: (Paper(title="Same title", identifiers=paper.identifiers, abstract="A"), []),
    )
    result, _ = services.fetch.fetch("pmid:111")
    assert result.path == Path("Same_title_111.pdf")


def test_fetch_configured_output_overrides_title_default(
    services: Services, tmp_path: Path
) -> None:
    output = tmp_path / "configured.pdf"
    services.config.fetch.output = str(output)
    result, _ = services.fetch.fetch("doi:10.1000/fake1")
    assert result.path == output


@pytest.mark.parametrize(
    ("filename", "expected_format"),
    [("paper.pdf", "pdf"), ("paper.xml", "xml"), ("paper.txt", "text")],
)
def test_fetch_infers_format_from_output(
    services: Services, tmp_path: Path, filename: str, expected_format: str
) -> None:
    output = tmp_path / filename
    result, _ = services.fetch.fetch("doi:10.1000/fake1", output=output)
    assert result.format == expected_format
    assert result.path == output


def test_fetch_appends_missing_extension(services: Services, tmp_path: Path) -> None:
    result, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", output=tmp_path / "paper")
    assert result.path == tmp_path / "paper.txt"


def test_fetch_defaults_to_pdf_without_extension(services: Services, tmp_path: Path) -> None:
    result, _ = services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "paper")
    assert result.format == "pdf"
    assert result.path == tmp_path / "paper.pdf"


@pytest.mark.parametrize(("fmt", "filename"), [("pdf", "paper.xml"), ("text", "paper.pdf")])
def test_fetch_rejects_format_extension_mismatch(
    services: Services, tmp_path: Path, fmt: ArtifactFormat, filename: str
) -> None:
    with pytest.raises(UsageError, match="implies format"):
        services.fetch.fetch("doi:10.1000/fake1", fmt=fmt, output=tmp_path / filename)


def test_fetch_rejects_unsupported_extension(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="Unsupported output extension"):
        services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "paper.docx")


def test_fetch_rejects_output_directory(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="Output path is a directory"):
        services.fetch.fetch("doi:10.1000/fake1", output=tmp_path)


def test_fetch_bad_pdf_falls_back(services: Services, tmp_path: Path) -> None:
    result, warnings = services.fetch.fetch("doi:10.1000/badpdf", output=tmp_path / "paper.pdf")
    assert result.source_url.endswith("good.pdf")
    assert any("not a valid PDF" in w for w in warnings)


def test_fetch_closed_raises_unavailable(services: Services, tmp_path: Path) -> None:
    with pytest.raises(FullTextUnavailableError) as exc_info:
        services.fetch.fetch("doi:10.1000/closed", output=tmp_path / "paper.pdf")
    assert exc_info.value.exit_code == 4
    assert exc_info.value.details["publisher_url"] == "https://doi.org/10.1000/closed"


def test_fetch_forced_downloader_mismatch(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        services.fetch.fetch(
            "doi:10.1000/fake1",
            fmt="xml",
            output=tmp_path / "paper.xml",
            downloader="nonexistent",
        )


def test_fetch_file_cache_hit(services: Services, tmp_path: Path) -> None:
    services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "first.pdf")
    downloader = services.registry.get("downloader", "fake_dl")
    calls_before = downloader.calls
    output = tmp_path / "second.pdf"
    result, _ = services.fetch.fetch("doi:10.1000/fake1", output=output)
    assert downloader.calls == calls_before
    assert result.downloader == "cache"
    assert result.path == output


def test_fetch_text_cache_hit_keeps_provenance(services: Services, tmp_path: Path) -> None:
    """Regression: cached text must not be re-validated/re-extracted as its source XML."""
    first, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", output=tmp_path / "first.txt")
    downloader = services.registry.get("downloader", "fake_dl")
    calls_before = downloader.calls
    output = tmp_path / "second.txt"
    second, _ = services.fetch.fetch("doi:10.1000/fake1", fmt="text", output=output)
    assert downloader.calls == calls_before  # no re-download
    assert second.downloader == "cache"
    assert second.extractor == "fake_ext"
    assert second.extracted_from == "xml"
    assert second.path == output
    assert second.path.read_text(encoding="utf-8") == first.path.read_text(encoding="utf-8")


def test_fetch_locator_config_error_becomes_warning(services: Services, tmp_path: Path) -> None:
    class BrokenConfigLocator:
        meta = PluginMeta(name="broken_cfg", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            raise ConfigError("missing email")

    services.registry.register("locator", BrokenConfigLocator())
    result, warnings = services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "paper.pdf")
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
                FullTextCandidate(url=url, format="pdf", locator=["sameurl"]),
                FullTextCandidate(url=url, format="xml", locator=["sameurl"]),
                FullTextCandidate(url=url, format="xml", locator=["sameurl"]),  # duplicate
            ]

    services.registry.register("locator", SameUrlLocator())
    result, _ = services.fetch.fetch(
        "doi:10.1000/fake1", fmt="xml", output=tmp_path / "paper.xml", locators=["sameurl"]
    )
    assert result.format == "xml"
    assert result.source_url == "https://example.org/package.tar.gz"


class _PdfOnlyLocator:
    meta = PluginMeta(name="pdfonly", version="0.1.0")

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        return [
            FullTextCandidate(
                url="https://example.org/other.pdf", format="pdf", locator=["pdfonly"]
            )
        ]


def test_fetch_locators_list_restricts(services: Services, tmp_path: Path) -> None:
    services.registry.register("locator", _PdfOnlyLocator())
    result, _ = services.fetch.fetch(
        "doi:10.1000/fake1", fmt="xml", output=tmp_path / "paper.xml", locators=["pdfonly", "fake"]
    )
    assert result.source_url == "https://example.org/paper.xml"
    with pytest.raises(FullTextUnavailableError):
        services.fetch.fetch(
            "doi:10.1000/fake1",
            fmt="xml",
            output=tmp_path / "missing" / "paper.xml",
            locators=["pdfonly"],
        )


def test_fetch_locators_default_from_config(services: Services, tmp_path: Path) -> None:
    class BoomLocator:
        meta = PluginMeta(name="boom", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            raise AssertionError("locator outside fetch.locators must not be consulted")

    services.registry.register("locator", BoomLocator())
    services.config.fetch.locators = ["fake"]
    result, warnings = services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "paper.pdf")
    assert result.source_url == "https://example.org/paper.pdf"
    assert not warnings


def test_fetch_unknown_locator_usage_error(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "paper.pdf", locators=["nope"])


def test_locate_returns_ranked_candidates(services: Services) -> None:
    result, warnings = services.fetch.locate("doi:10.1000/fake1")
    assert warnings == []
    assert result.paper.title == "CRISPR base editing review"
    assert [candidate.format for candidate in result.candidates] == ["pdf", "xml", "landing"]
    assert result.candidates[0].url == "https://example.org/paper.pdf"
    assert result.candidates[0].locator == ["fake"]
    assert result.candidates[0].downloaders == ["fake_dl"]
    assert result.candidates[2].downloaders == []


def test_locate_merges_locators_for_same_url(services: Services) -> None:
    class FirstLocator:
        meta = PluginMeta(name="first", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            return [
                FullTextCandidate(
                    url="https://example.org/shared.pdf",
                    format="pdf",
                    locator=["first"],
                )
            ]

    class SecondLocator:
        meta = PluginMeta(name="second", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            return [
                FullTextCandidate(
                    url="https://example.org/shared.pdf",
                    format="pdf",
                    locator=["second"],
                    license="cc-by",
                )
            ]

    services.registry.register("locator", FirstLocator())
    services.registry.register("locator", SecondLocator())
    result, _ = services.fetch.locate("doi:10.1000/fake1", locators=["first", "second"])
    candidate = next(c for c in result.candidates if c.url.endswith("shared.pdf"))
    assert candidate.locator == ["first", "second"]
    assert candidate.downloaders == ["fake_dl"]
    assert candidate.license == "cc-by"


def test_fetch_uses_candidate_downloader_order(services: Services, tmp_path: Path) -> None:
    calls: list[str] = []

    class FirstDownloader:
        meta = PluginMeta(name="first", version="0.1.0")
        formats = frozenset({"pdf"})

        def supports(self, candidate: FullTextCandidate) -> bool:
            return True

        def download(self, candidate: FullTextCandidate) -> Artifact:
            calls.append("first")
            raise UpstreamError("first failed")

    class SecondDownloader:
        meta = PluginMeta(name="second", version="0.1.0")
        formats = frozenset({"pdf"})

        def supports(self, candidate: FullTextCandidate) -> bool:
            return True

        def download(self, candidate: FullTextCandidate) -> Artifact:
            calls.append("second")
            return Artifact(
                format="pdf",
                content=PDF_BYTES,
                source_url=candidate.url,
                downloader="second",
            )

    class OrderedLocator:
        meta = PluginMeta(name="ordered", version="0.1.0")

        def resolve(self, paper: Paper) -> list[FullTextCandidate]:
            return [
                FullTextCandidate(
                    url="https://example.org/ordered.pdf",
                    format="pdf",
                    locator=["ordered"],
                    downloaders=["first", "second"],
                )
            ]

    services.registry.register("downloader", FirstDownloader())
    services.registry.register("downloader", SecondDownloader())
    services.registry.register("locator", OrderedLocator())
    result, warnings = services.fetch.fetch(
        "doi:10.1000/fake1",
        output=tmp_path / "ordered.pdf",
        locators=["ordered"],
    )
    assert calls == ["first", "second"]
    assert result.downloader == "second"
    assert "first: first failed" in warnings


def test_locate_filters_formats(services: Services) -> None:
    xml, _ = services.fetch.locate("doi:10.1000/fake1", fmt="xml")
    assert [candidate.format for candidate in xml.candidates] == ["xml"]
    text, _ = services.fetch.locate("doi:10.1000/fake1", fmt="text")
    assert [candidate.format for candidate in text.candidates] == ["xml", "pdf"]


def test_locate_closed_keeps_landing_page(services: Services) -> None:
    result, _ = services.fetch.locate("doi:10.1000/closed")
    assert [candidate.format for candidate in result.candidates] == ["landing"]
    filtered, _ = services.fetch.locate("doi:10.1000/closed", fmt="pdf")
    assert filtered.candidates == []


def test_download_pdf(services: Services, tmp_path: Path) -> None:
    output = tmp_path / "paper.pdf"
    result, warnings = services.fetch.download("https://example.org/paper.pdf", output=output)
    assert warnings == []
    assert result.format == "pdf"
    assert result.path == output
    assert result.source_url == "https://example.org/paper.pdf"
    assert result.downloader == "fake_dl"
    assert output.read_bytes() == PDF_BYTES


def test_download_infers_format_from_output(services: Services, tmp_path: Path) -> None:
    output = tmp_path / "paper.xml"
    result, _ = services.fetch.download("https://example.org/fulltext", output=output)
    assert result.format == "xml"
    assert output.read_bytes() == XML_BYTES


def test_download_default_output(
    services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result, _ = services.fetch.download("https://example.org/papers/paper.pdf?token=abc")
    assert result.path == Path("paper.pdf")
    assert result.path.exists()


def test_download_requires_format_for_unknown_extension(services: Services) -> None:
    with pytest.raises(UsageError, match="Cannot infer"):
        services.fetch.download("https://example.org/fulltext")


def test_download_rejects_non_http_url(services: Services) -> None:
    with pytest.raises(UsageError, match="HTTP"):
        services.fetch.download("file:///tmp/paper.pdf")


def test_download_failure_reports_attempts(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UpstreamError) as exc_info:
        services.fetch.download("https://example.org/fail.xml", output=tmp_path / "paper.xml")
    assert exc_info.value.details["attempts"] == ["fake_dl: fake download failure"]


def test_download_populates_fetch_cache(services: Services, tmp_path: Path) -> None:
    services.fetch.download("https://example.org/paper.pdf", output=tmp_path / "raw.pdf")
    downloader = services.registry.get("downloader", "fake_dl")
    calls_before = downloader.calls
    result, _ = services.fetch.fetch("doi:10.1000/fake1", output=tmp_path / "fetched.pdf")
    assert downloader.calls == calls_before
    assert result.downloader == "cache"


def test_extract_xml_default_output(services: Services, tmp_path: Path) -> None:
    source = tmp_path / "paper.xml"
    source.write_bytes(XML_BYTES)
    result, warnings = services.fetch.extract(source)
    assert warnings == []
    assert result.source_path == source
    assert result.source_format == "xml"
    assert result.format == "text"
    assert result.extractor == "fake_ext"
    assert result.path == source.with_suffix(".txt")
    assert result.path.read_text(encoding="utf-8").startswith("EXTRACTED[xml]")


def test_extract_pdf_with_forced_extractor(services: Services, tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    output = tmp_path / "paper"
    source.write_bytes(PDF_BYTES)
    result, _ = services.fetch.extract(source, output=output, extractor="fake_ext")
    assert result.source_format == "pdf"
    assert result.path == output.with_suffix(".txt")
    assert result.path.read_text(encoding="utf-8").startswith("EXTRACTED[pdf]")


def test_extract_rejects_missing_input(services: Services, tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="Input file not found"):
        services.fetch.extract(tmp_path / "missing.xml")


def test_extract_rejects_unsupported_input(services: Services, tmp_path: Path) -> None:
    source = tmp_path / "paper.txt"
    source.write_text("already text", encoding="utf-8")
    with pytest.raises(UsageError, match="Unsupported input extension"):
        services.fetch.extract(source)


def test_extract_rejects_non_text_output(services: Services, tmp_path: Path) -> None:
    source = tmp_path / "paper.xml"
    source.write_bytes(XML_BYTES)
    with pytest.raises(UsageError, match="implies format"):
        services.fetch.extract(source, output=tmp_path / "paper.pdf")


def test_extract_rejects_invalid_xml(services: Services, tmp_path: Path) -> None:
    source = tmp_path / "paper.xml"
    source.write_bytes(b"<article>")
    with pytest.raises(UpstreamError, match="not parseable XML"):
        services.fetch.extract(source)


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


def test_multi_source_limit_is_per_source(services: Services) -> None:
    sa = StubSearcher(
        "sa", [Paper(title=f"P{i}", identifiers={"doi": f"10.1000/{i}"}) for i in range(5)]
    )
    sb = StubSearcher(
        "sb", [Paper(title=f"Q{i}", identifiers={"doi": f"10.2000/{i}"}) for i in range(5)]
    )
    services.registry.register("searcher", sa)
    services.registry.register("searcher", sb)
    page, _ = services.search.search(Query(text="q"), sources=["sa", "sb"], limit=2)
    assert len(page.items) == 4  # 2 per source; the deduped merge is not truncated


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
    assert page.next_cursor == "ms1.sa:a1,sb:b1"
    services.search.search(Query(text="q"), sources=["sa", "sb"], cursor=page.next_cursor)
    assert sa.calls[-1] == "a1"
    assert sb.calls[-1] == "b1"
    # a source absent from the aggregated cursor is exhausted and not queried
    services.search.search(Query(text="q"), sources=["sa", "sb"], cursor="ms1.sa:a2")
    assert sa.calls[-1] == "a2"
    assert sb.calls[-1] == "b1"  # unchanged
    # legacy JSON object cursors are still accepted
    services.search.search(Query(text="q"), sources=["sa", "sb"], cursor='{"sa": "a3"}')
    assert sa.calls[-1] == "a3"
    assert sb.calls[-1] == "b1"


def test_multi_source_cursor_escapes_separators(services: Services) -> None:
    nasty = "we:ir,cu%3A%rsor"  # contains every reserved char plus a fake escape
    sa = StubSearcher("sa", [Paper(title="A", identifiers={"doi": "10.1000/x"})], next_cursor=nasty)
    services.registry.register("searcher", sa)
    services.registry.register("searcher", StubSearcher("sb", []))
    page, _ = services.search.search(Query(text="q"), sources=["sa", "sb"])
    assert page.next_cursor == "ms1.sa:we%3Air%2Ccu%253A%25rsor"  # sb has no cursor -> absent
    services.search.search(Query(text="q"), sources=["sa", "sb"], cursor=page.next_cursor)
    assert sa.calls[-1] == nasty  # decoded back to the upstream opaque string


def test_multi_source_invalid_cursor(services: Services) -> None:
    services.registry.register("searcher", StubSearcher("sa", []))
    services.registry.register("searcher", StubSearcher("sb", []))
    for bad in ("plain-opaque", "ms1.", "ms1.nocolon", "ms1.:x", "ms1.sa:", "[1,2]"):
        with pytest.raises(UsageError):
            services.search.search(Query(text="q"), sources=["sa", "sb"], cursor=bad)


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
                        url="https://example.org/seed.pdf", format="pdf", locator=["linkmeta"]
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
    result, _ = services.fetch.fetch(
        "doi:10.1000/missing", output=tmp_path / "paper.pdf", locators=["emptyloc"]
    )
    assert result.source_url == "https://example.org/seed.pdf"
    assert result.path.read_bytes().startswith(b"%PDF")
