"""Unit tests: identifiers, models, merge policy."""

from __future__ import annotations

import pytest

from paper_tools.core.errors import UsageError
from paper_tools.core.models import (
    Author,
    Paper,
    merge_papers,
    normalize_doi,
    paper_slug,
    parse_identifier,
)


@pytest.mark.parametrize(
    ("raw", "kind", "value"),
    [
        ("doi:10.1038/S41586-020-2649-2", "doi", "10.1038/s41586-020-2649-2"),
        ("10.1038/s41586-020-2649-2", "doi", "10.1038/s41586-020-2649-2"),
        ("https://doi.org/10.1038/abc", "doi", "10.1038/abc"),
        ("pmid:12345678", "pmid", "12345678"),
        ("12345678", "pmid", "12345678"),
        ("pmcid:PMC123", "pmcid", "PMC123"),
        ("s2:abc123", "s2", "abc123"),
        ("https://example.org/paper", "url", "https://example.org/paper"),
    ],
)
def test_parse_identifier(raw: str, kind: str, value: str) -> None:
    ident = parse_identifier(raw)
    assert ident.kind == kind
    assert ident.value == value


@pytest.mark.parametrize("raw", ["", "not-an-id", "doi:", "abc"])
def test_parse_identifier_invalid(raw: str) -> None:
    with pytest.raises(UsageError):
        parse_identifier(raw)


def test_normalize_doi() -> None:
    assert normalize_doi(" HTTPS://DOI.ORG/10.1038/ABC ") == "10.1038/abc"
    assert normalize_doi("doi:10.1038/abc") == "10.1038/abc"


def test_merge_fills_missing_and_never_overwrites() -> None:
    base = Paper(title="Original", identifiers={"doi": "10.1/a"}, year=2020)
    incoming = Paper(
        title="Different",
        identifiers={"doi": "10.1/a", "pmid": "999"},
        abstract="New abstract",
        year=2024,
        authors=[Author(name="Li Si")],
        oa_status="gold",
    )
    merged, warnings = merge_papers(base, incoming, source="prov")
    assert merged.title == "Original"
    assert merged.year == 2020
    assert merged.abstract == "New abstract"
    assert merged.identifiers == {"doi": "10.1/a", "pmid": "999"}
    assert merged.authors[0].name == "Li Si"
    assert merged.oa_status == "gold"
    assert merged.sources == ["prov"]
    assert warnings == []


def test_merge_identifier_conflict_warns() -> None:
    base = Paper(identifiers={"doi": "10.1/a"})
    incoming = Paper(identifiers={"doi": "10.1/b"})
    merged, warnings = merge_papers(base, incoming, source="prov")
    assert merged.identifiers["doi"] == "10.1/a"
    assert len(warnings) == 1
    assert "conflict" in warnings[0]
    assert merged.sources == []  # nothing contributed


def test_merge_unions_sources() -> None:
    base = Paper(title="T", sources=["search"])
    incoming = Paper(abstract="A", sources=["meta1"])
    merged, _ = merge_papers(base, incoming, source="meta2")
    assert merged.sources == ["search", "meta1", "meta2"]


def test_paper_slug() -> None:
    paper = Paper(identifiers={"doi": "10.1038/s41586-020-2649-2"})
    assert paper_slug(paper) == "10.1038_s41586-020-2649-2"
    assert paper_slug(Paper(title="A/B: C")) == "A_B_C"
