"""Shared fixtures: five-role fake plugins wired into real services."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_tools.core.cache import Cache
from paper_tools.core.config import AppConfig, GeneralConfig
from paper_tools.core.errors import UpstreamError
from paper_tools.core.http import HttpClient
from paper_tools.core.models import (
    Artifact,
    Author,
    FullTextCandidate,
    Paper,
    SearchPage,
)
from paper_tools.core.plugins import PluginContext, PluginMeta, PluginRegistry
from paper_tools.core.query import Query
from paper_tools.core.services import Services

PDF_BYTES = b"%PDF-1.4\n" + b"x" * 2048
XML_BYTES = b'<?xml version="1.0"?><article><body><p>Hello CRISPR world</p></body></article>'


class FakeSearcher:
    meta = PluginMeta(name="fake", version="0.1.0", description="Fake search source")

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx
        self.calls: list[Query] = []

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        self.calls.append(q)
        items = [
            Paper(
                title="CRISPR base editing review",
                identifiers={"doi": "10.1000/fake1", "pmid": "111"},
            ),
            Paper(title="Another paper", identifiers={"doi": "10.1000/fake2"}),
        ][:limit]
        return SearchPage(items=items, total=2, next_cursor=cursor, source="fake")


class FakeMetadata:
    meta = PluginMeta(name="fake", version="0.1.0", description="Fake metadata source")
    id_kinds = frozenset({"doi", "pmid"})

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx
        self.calls = 0

    def enrich(self, paper: Paper) -> Paper:
        self.calls += 1
        doi = paper.identifiers.get("doi", "")
        if doi == "10.1000/failmeta":
            raise UpstreamError("fake metadata upstream failure")
        if doi == "10.1000/missing":
            return paper
        return Paper(
            title=paper.title or "CRISPR base editing review",
            identifiers={**paper.identifiers, "pmcid": "PMC999"},
            abstract="An abstract about base editing.",
            authors=[Author(name="Zhang San")],
            year=2023,
            journal="Fake Journal",
            oa_status="gold",
            license="cc-by",
            publisher_url=f"https://doi.org/{doi}" if doi else None,
        )


class FakeMetadata2:
    meta = PluginMeta(name="fake2", version="0.1.0", description="Fallback metadata source")
    id_kinds = frozenset({"doi"})

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx

    def enrich(self, paper: Paper) -> Paper:
        if paper.identifiers.get("doi") == "10.1000/missing":
            return paper
        return Paper(
            title=paper.title or "Recovered title",
            identifiers=paper.identifiers,
            abstract="Abstract from fake2.",
            year=2024,
        )


class FakeLocator:
    meta = PluginMeta(name="fake", version="0.1.0", description="Fake OA locator")

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        doi = paper.identifiers.get("doi", "")
        if doi == "10.1000/closed":
            return [
                FullTextCandidate(
                    url="https://example.org/landing", format="landing", locator=["fake"]
                )
            ]
        if doi == "10.1000/badpdf":
            return [
                FullTextCandidate(
                    url="https://example.org/bad.pdf", format="pdf", locator=["fake"]
                ),
                FullTextCandidate(
                    url="https://example.org/good.pdf", format="pdf", locator=["fake"]
                ),
            ]
        return [
            FullTextCandidate(
                url="https://example.org/paper.pdf",
                format="pdf",
                locator=["fake"],
                license="cc-by",
            ),
            FullTextCandidate(url="https://example.org/paper.xml", format="xml", locator=["fake"]),
            FullTextCandidate(
                url="https://example.org/landing", format="landing", locator=["fake"]
            ),
        ]


class FakeDownloader:
    meta = PluginMeta(name="fake_dl", version="0.1.0", description="Fake downloader")
    formats = frozenset({"pdf", "xml"})

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx
        self.calls = 0

    def supports(self, candidate: FullTextCandidate) -> bool:
        return candidate.url.startswith("https://example.org/")

    def download(self, candidate: FullTextCandidate) -> Artifact:
        self.calls += 1
        if "fail" in candidate.url:
            raise UpstreamError("fake download failure")
        if candidate.url.endswith("bad.pdf"):
            return Artifact(
                format="pdf",
                content=b"this is not a pdf",
                source_url=candidate.url,
                downloader="fake_dl",
            )
        content = PDF_BYTES if candidate.format == "pdf" else XML_BYTES
        return Artifact(
            format=candidate.format,  # type: ignore[arg-type]
            content=content,
            source_url=candidate.url,
            downloader="fake_dl",
            license=candidate.license,
        )


class FakeExtractor:
    meta = PluginMeta(name="fake_ext", version="0.1.0", description="Fake extractor")
    source_formats = frozenset({"pdf", "xml"})

    def __init__(self, ctx: PluginContext | None = None) -> None:
        self.ctx = ctx

    def extract(self, data: bytes, *, source_format: str) -> str:
        return f"EXTRACTED[{source_format}] " + data.decode("utf-8", errors="replace")[:80]


def make_services(tmp_path: Path) -> Services:
    config = AppConfig(general=GeneralConfig(default_source="fake"))
    cache = Cache(root=tmp_path / "cache")
    http = HttpClient(cache=cache, sleep=lambda _s: None)
    ctx = PluginContext(config=config, http=http, cache=cache)
    registry = PluginRegistry(ctx)
    registry.register("searcher", FakeSearcher(ctx))
    registry.register("metadata", FakeMetadata(ctx))
    registry.register("metadata", FakeMetadata2(ctx))
    registry.register("locator", FakeLocator(ctx))
    registry.register("downloader", FakeDownloader(ctx))
    registry.register("extractor", FakeExtractor(ctx))
    return Services(config=config, cache=cache, registry=registry)


@pytest.fixture
def services(tmp_path: Path) -> Services:
    return make_services(tmp_path)


@pytest.fixture
def plugin_ctx(services: Services) -> PluginContext:
    return services.registry.ctx
