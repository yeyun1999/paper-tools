"""Contract suite: invariants every plugin of a given role must satisfy.

Parametrized over the registry so real plugins (M2+) are covered automatically.
"""

from __future__ import annotations

import pytest

from paper_tools.core.models import FullTextCandidate, Paper
from paper_tools.core.query import Query
from paper_tools.core.services import Services


def test_searcher_contract(services: Services) -> None:
    for plugin in services.registry.list("searcher"):
        page = plugin.search(Query(text="CRISPR"), limit=1)
        assert page.source == plugin.meta.name
        assert len(page.items) <= 1
        for paper in page.items:
            assert paper.title
            assert paper.identifiers


def test_metadata_contract(services: Services) -> None:
    for plugin in services.registry.list("metadata"):
        assert plugin.id_kinds
        stub = Paper(identifiers={"doi": "10.1000/fake1"})
        result = plugin.enrich(stub)
        assert isinstance(result, Paper)


def test_locator_contract(services: Services) -> None:
    paper = Paper(title="T", identifiers={"doi": "10.1000/fake1"})
    for plugin in services.registry.list("locator"):
        for candidate in plugin.resolve(paper):
            assert isinstance(candidate, FullTextCandidate)
            assert candidate.url.startswith(("http://", "https://"))
            assert plugin.meta.name in candidate.locator


def test_downloader_contract(services: Services) -> None:
    for plugin in services.registry.list("downloader"):
        assert plugin.formats
        candidate = FullTextCandidate(
            url="https://example.org/paper.pdf", format="pdf", locator=["fake"]
        )
        if plugin.supports(candidate):
            artifact = plugin.download(candidate)
            assert artifact.format in plugin.formats
            assert artifact.content
            assert artifact.downloader == plugin.meta.name


def test_extractor_contract(services: Services) -> None:
    for plugin in services.registry.list("extractor"):
        assert plugin.source_formats
        for source_format in plugin.source_formats:
            text = plugin.extract(
                b"<article><p>sample text</p></article>", source_format=source_format
            )
            assert isinstance(text, str)
            assert text.strip()


@pytest.mark.parametrize("role", ["searcher", "metadata", "locator", "downloader", "extractor"])
def test_meta_present(services: Services, role: str) -> None:
    for plugin in services.registry.list(role):
        assert plugin.meta.name
        assert plugin.meta.version
