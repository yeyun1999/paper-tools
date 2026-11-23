"""Crossref plugin tests with respx replay (offline, deterministic)."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_tools.core.errors import UsageError
from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.core.query import Query
from paper_tools.plugins.crossref import (
    WORKS_URL,
    CrossrefMetadata,
    CrossrefSearcher,
    _query_params,
)

ITEM = {
    "DOI": "10.1234/ABC",
    "title": ["CRISPR base editing in vivo"],
    "author": [{"given": "San", "family": "Zhang"}],
    "issued": {"date-parts": [[2023, 1, 15]]},
    "container-title": ["Nature"],
    "abstract": (
        "&lt;jats:p&gt;Hello &lt;jats:italic&gt;CRISPR&lt;/jats:italic&gt; world&lt;/jats:p&gt;"
    ),
    "type": "journal-article",
    "license": [{"URL": "http://creativecommons.org/licenses/by/4.0"}],
    "resource": {"primary": {"URL": "https://pub.org/paper"}},
}


def test_query_translation() -> None:
    q = Query(text="CRISPR", author="Zhang", year_from=2020, year_to=2025)
    params = _query_params(q)
    assert params["query"] == "CRISPR"
    assert params["query.author"] == "Zhang"
    assert params["filter"] == "from-pub-date:2020,until-pub-date:2025"


def test_raw_passthrough() -> None:
    assert _query_params(Query(raw="custom")) == {"query": "custom"}


def test_oa_only_unsupported() -> None:
    with pytest.raises(UsageError):
        _query_params(Query(text="x", open_access=True))


@respx.mock
def test_search(plugin_ctx: PluginContext) -> None:
    route = respx.get(WORKS_URL).mock(
        return_value=httpx.Response(200, json={"message": {"total-results": 1, "items": [ITEM]}})
    )
    page = CrossrefSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=5)
    assert page.source == "crossref"
    assert page.total == 1
    assert page.next_cursor is None
    paper = page.items[0]
    assert paper.identifiers["doi"] == "10.1234/abc"
    assert paper.authors[0].name == "San Zhang"
    assert paper.year == 2023
    assert paper.abstract == "Hello CRISPR world"
    assert paper.journal == "Nature"
    assert paper.license == "http://creativecommons.org/licenses/by/4.0"
    assert route.calls.last.request.url.params["rows"] == "5"


@respx.mock
def test_search_pagination(plugin_ctx: PluginContext) -> None:
    respx.get(WORKS_URL).mock(
        return_value=httpx.Response(200, json={"message": {"total-results": 50, "items": [ITEM]}})
    )
    page = CrossrefSearcher(plugin_ctx).search(Query(text="CRISPR"), limit=20)
    assert page.next_cursor == "20"


@respx.mock
def test_enrich_by_doi(plugin_ctx: PluginContext) -> None:
    respx.get(f"{WORKS_URL}/10.1234/abc").mock(
        return_value=httpx.Response(200, json={"message": ITEM})
    )
    paper = CrossrefMetadata(plugin_ctx).enrich(Paper(identifiers={"doi": "10.1234/abc"}))
    assert paper.title == "CRISPR base editing in vivo"
    assert paper.abstract == "Hello CRISPR world"


@respx.mock
def test_mailto_polite_pool(plugin_ctx: PluginContext) -> None:
    plugin_ctx.config.general.mailto = "test@example.org"
    route = respx.get(WORKS_URL).mock(
        return_value=httpx.Response(200, json={"message": {"total-results": 0, "items": []}})
    )
    CrossrefSearcher(plugin_ctx).search(Query(text="x"))
    assert route.calls.last.request.url.params["mailto"] == "test@example.org"
