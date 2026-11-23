"""Unit tests: unified query validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from paper_tools.core.query import Query


def test_structured_query() -> None:
    q = Query(text="CRISPR", author="Zhang", year_from=2020, year_to=2025)
    assert q.text == "CRISPR"


def test_raw_query() -> None:
    q = Query(raw="CRISPR[Title] AND 2020:2025[dp]")
    assert q.raw is not None


def test_raw_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Query(text="CRISPR", raw="CRISPR[Title]")


def test_empty_query_rejected() -> None:
    with pytest.raises(ValidationError, match="empty query"):
        Query()


def test_year_range_validated() -> None:
    with pytest.raises(ValidationError, match="year_from"):
        Query(text="x", year_from=2025, year_to=2020)
