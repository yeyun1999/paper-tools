"""Unit tests: identifiers, models, merge policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_tools.core.errors import UsageError
from paper_tools.core.models import (
    Artifact,
    Author,
    DownloadedFullText,
    FullText,
    FullTextCandidate,
    Paper,
    PaperSummary,
    merge_papers,
    normalize_doi,
    normalize_license,
    parse_identifier,
)


def test_merge_unions_fulltext_links() -> None:
    base = Paper(
        title="T",
        fulltext_links=[FullTextCandidate(url="https://a.org/p.pdf", format="pdf", locator=["x"])],
    )
    incoming = Paper(
        fulltext_links=[
            FullTextCandidate(url="https://a.org/p.pdf", format="pdf", locator=["y"]),  # dup
            FullTextCandidate(url="https://a.org/p.xml", format="xml", locator=["y"]),
        ]
    )
    merged, warnings = merge_papers(base, incoming, source="y")
    assert {(link.url, link.format) for link in merged.fulltext_links} == {
        ("https://a.org/p.pdf", "pdf"),
        ("https://a.org/p.xml", "xml"),
    }
    assert merged.fulltext_links[0].locator == ["x", "y"]
    assert "y" in merged.sources
    assert not warnings


def test_merge_unions_candidate_locators_and_downloaders() -> None:
    base = Paper(
        fulltext_links=[
            FullTextCandidate(
                url="https://a.org/p.pdf",
                format="pdf",
                locator=["x"],
                downloaders=["first", "shared"],
            )
        ]
    )
    incoming = Paper(
        fulltext_links=[
            FullTextCandidate(
                url="https://a.org/p.pdf",
                format="pdf",
                locator=["y", "x"],
                downloaders=["second", "shared"],
                license="cc-by",
            )
        ]
    )
    merged, _ = merge_papers(base, incoming, source="y")
    candidate = merged.fulltext_links[0]
    assert candidate.locator == ["x", "y"]
    assert candidate.downloaders == ["first", "shared", "second"]
    assert candidate.license == "cc-by"


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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CC BY", "cc-by"),
        (" cc by ", "cc-by"),
        ("cc_by", "cc-by"),
        ("CC-BY-NC-ND", "cc-by-nc-nd"),
        ("CC BY-SA 4.0", "cc-by-sa-4.0"),
        ("CC BY-NC-SA 4.0", "cc-by-nc-sa-4.0"),
        ("CC0 1.0", "cc0-1.0"),
        ("http://creativecommons.org/licenses/by/4.0", "cc-by-4.0"),
        ("https://creativecommons.org/licenses/by-nc-nd/3.0/deed.en", "cc-by-nc-nd-3.0"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "cc0-1.0"),
        ("", None),
        (" \t\n", None),
        (None, None),
        ("Custom License", "Custom License"),
        ("https://example.org/license", "https://example.org/license"),
        (
            "https://creativecommons.org/licenses/unknown/1.0/",
            "https://creativecommons.org/licenses/unknown/1.0/",
        ),
    ],
)
def test_normalize_license(raw: str | None, expected: str | None) -> None:
    assert normalize_license(raw) == expected


def test_license_normalization_applies_to_output_models() -> None:
    candidate = FullTextCandidate(
        url="https://example.org/paper.pdf", format="pdf", locator=["test"], license=" CC BY "
    )
    assert candidate.license == "cc-by"
    assert Paper(license="cc_by").license == "cc-by"
    assert (
        Artifact(format="pdf", content=b"pdf", source_url=candidate.url, downloader="test").license
        is None
    )
    assert (
        Artifact(
            format="pdf",
            content=b"pdf",
            source_url=candidate.url,
            downloader="test",
            license="CC BY",
        ).license
        == "cc-by"
    )
    assert (
        DownloadedFullText(
            source_url=candidate.url,
            format="pdf",
            path=Path("paper.pdf"),
            sha256="hash",
            downloader="test",
            license="CC BY",
        ).license
        == "cc-by"
    )
    assert (
        FullText(
            paper=Paper(),
            format="pdf",
            path=Path("paper.pdf"),
            sha256="hash",
            source_url=candidate.url,
            downloader="test",
            license="CC BY",
        ).license
        == "cc-by"
    )


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


def test_merge_fills_bibliographic_fields_and_unions_related_papers() -> None:
    base = Paper(
        cited_by_count=0,
        cited_by_papers=[PaperSummary(title="Citing A", identifiers={"doi": "10.1/citing-a"})],
    )
    incoming = Paper(
        issn="1234-5678",
        impact_factor=5.2,
        cited_by_count=9,
        references_count=12,
        cited_by_papers=[
            PaperSummary(title="Citing A", identifiers={"doi": "10.1/citing-a"}),
            PaperSummary(title="Citing B", identifiers={"doi": "10.1/citing-b"}),
        ],
        reference_papers=[PaperSummary(title="Reference", year=2020)],
    )
    merged, _ = merge_papers(base, incoming, source="provider")
    assert merged.cited_by_count == 0
    assert merged.issn == "1234-5678"
    assert merged.impact_factor == 5.2
    assert merged.references_count == 12
    assert [paper.title for paper in merged.cited_by_papers] == ["Citing A", "Citing B"]
    assert merged.reference_papers[0].title == "Reference"
    assert "provider" in merged.sources


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
