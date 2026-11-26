"""Unit tests: nested field paths, projection shape, and completeness."""

from __future__ import annotations

import pytest

from paper_tools.core.errors import UsageError
from paper_tools.core.fields import (
    all_field_names,
    field_is_present,
    parse_field_path,
    project_field_paths,
)
from paper_tools.core.models import Author, FullTextCandidate, Paper, PaperSummary


def test_object_projection_preserves_nesting() -> None:
    data = Paper(identifiers={"doi": "10.1/a", "pmid": "123"}).model_dump(mode="json")
    assert project_field_paths(data, ["identifiers.doi"]) == {"identifiers": {"doi": "10.1/a"}}
    assert project_field_paths(data, ["doi"]) == {}


def test_array_projection_preserves_positions_and_containers() -> None:
    data = Paper(
        authors=[Author(name="A", orcid="0000-1"), Author(name="B")],
        fulltext_links=[
            FullTextCandidate(
                url="https://example.org/a.pdf",
                format="pdf",
                locator=["openalex"],
                downloaders=["http_direct"],
            ),
            FullTextCandidate(url="https://example.org/b.pdf", format="pdf", locator=["crossref"]),
        ],
    ).model_dump(mode="json")
    assert project_field_paths(data, ["authors[].name"]) == {
        "authors": [{"name": "A"}, {"name": "B"}]
    }
    assert project_field_paths(data, ["authors[].orcid"]) == {"authors": [{"orcid": "0000-1"}, {}]}
    assert project_field_paths(data, ["fulltext_links[].downloaders[]"]) == {
        "fulltext_links": [{"downloaders": ["http_direct"]}, {"downloaders": []}]
    }


def test_multiple_paths_merge_under_the_same_container() -> None:
    data = Paper(identifiers={"doi": "10.1/a"}, year=2024, cited_by_count=0).model_dump(mode="json")
    assert project_field_paths(
        data, ["identifiers.doi", "identifiers.pmid", "year", "cited_by_count"]
    ) == {"identifiers": {"doi": "10.1/a"}, "year": 2024, "cited_by_count": 0}


@pytest.mark.parametrize(
    "raw",
    [
        "",
        ".doi",
        "identifiers.",
        "identifiers..doi",
        "identifiers[doi]",
        "authors[0].name",
        "authors{}",
        "identifiers.{doi}",
        "authors[].name.",
    ],
)
def test_malformed_field_paths_raise_usage(raw: str) -> None:
    with pytest.raises(UsageError, match="Invalid field path"):
        parse_field_path(raw)


@pytest.mark.parametrize("raw", ["authors.name", "identifiers[]", "year.name"])
def test_container_type_mismatch_raises_usage(raw: str) -> None:
    data = Paper().model_dump(mode="json")
    with pytest.raises(UsageError, match="expects an"):
        project_field_paths(data, [raw])


def test_field_presence_distinguishes_missing_from_zero_and_unknown() -> None:
    data = Paper(
        identifiers={"doi": "10.1/a"},
        cited_by_count=0,
        authors=[Author(name="A"), Author(name="B")],
        cited_by_papers=[PaperSummary(title="Citing paper")],
    ).model_dump(mode="json")
    assert field_is_present(data, "identifiers.doi")
    assert field_is_present(data, "cited_by_count")
    assert field_is_present(data, "authors[].name")
    assert field_is_present(data, "cited_by_papers")
    assert not field_is_present(data, "identifiers.pmid")
    assert not field_is_present(data, "authors[].orcid")
    assert not field_is_present(data, "oa_status")
    assert not field_is_present(data, "reference_papers")


def test_all_field_names_match_paper_contract() -> None:
    assert all_field_names() == list(Paper.model_fields)
    assert "identifiers" in all_field_names()
    assert "impact_factor" in all_field_names()
