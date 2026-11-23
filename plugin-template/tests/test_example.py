"""Template plugin tests: respx replay + role contract invariants.

派生插件时保留契约不变量测试，替换回放夹具为你的真实 API 响应。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from paper_tools.core.cache import Cache
from paper_tools.core.config import AppConfig
from paper_tools.core.http import HttpClient
from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.core.query import Query

from paper_tools_example.metadata import ExampleMetadata
from paper_tools_example.searcher import BASE_URL, ExampleSearcher

ROW = {
    "doi": "10.1234/ABC",
    "pmid": "123",
    "title": "CRISPR base editing in vivo",
    "authors": [{"name": "San Zhang"}],
    "year": 2023,
    "journal": "Example Journal",
    "abstract": "An abstract.",
    "oa_status": "gold",
    "license": "cc-by",
    "url": "https://pub.example.org/paper",
}


@pytest.fixture
def ctx(tmp_path: Path) -> PluginContext:
    cache = Cache(root=tmp_path / "cache")
    return PluginContext(
        config=AppConfig(), http=HttpClient(cache=cache, sleep=lambda _s: None), cache=cache
    )


def test_query_translation(ctx: PluginContext) -> None:
    params = ExampleSearcher(ctx)._query_params(
        Query(text="CRISPR", author="Zhang", year_from=2020, open_access=True), 5, None
    )
    assert params == {
        "page_size": 5,
        "query": "CRISPR",
        "author": "Zhang",
        "year_from": 2020,
        "is_oa": "true",
    }
    assert ExampleSearcher(ctx)._query_params(Query(raw="native"), 5, "c1") == {
        "page_size": 5,
        "cursor": "c1",
        "q": "native",
    }


@respx.mock
def test_search_replay(ctx: PluginContext) -> None:
    route = respx.get(f"{BASE_URL}/works").mock(
        return_value=httpx.Response(200, json={"total": 9, "next_cursor": "c2", "items": [ROW]})
    )
    page = ExampleSearcher(ctx).search(Query(text="CRISPR"), limit=1, cursor="c1")
    assert route.called
    assert page.source == "example"
    assert page.total == 9
    assert page.next_cursor == "c2"
    assert len(page.items) == 1
    paper = page.items[0]
    assert paper.identifiers["doi"] == "10.1234/abc"  # normalize_doi 小写化
    assert paper.title


@respx.mock
def test_enrich_replay(ctx: PluginContext) -> None:
    respx.get(f"{BASE_URL}/works/10.1234/abc").mock(return_value=httpx.Response(200, json=ROW))
    result = ExampleMetadata(ctx).enrich(Paper(identifiers={"doi": "10.1234/abc"}))
    assert isinstance(result, Paper)
    assert result.abstract == "An abstract."
    assert result.year == 2023


@respx.mock
def test_enrich_404_returns_stub(ctx: PluginContext) -> None:
    respx.get(f"{BASE_URL}/works/10.1234/missing").mock(return_value=httpx.Response(404))
    stub = Paper(identifiers={"doi": "10.1234/missing"})
    assert ExampleMetadata(ctx).enrich(stub) is stub


def test_enrich_without_doi_returns_stub(ctx: PluginContext) -> None:
    stub = Paper(identifiers={"pmid": "123"})
    assert ExampleMetadata(ctx).enrich(stub) is stub


def test_role_contracts(ctx: PluginContext) -> None:
    """契约不变量：与主仓库 tests/contract/test_plugin_contract.py 对齐。"""
    searcher = ExampleSearcher(ctx)
    assert searcher.meta.name and searcher.meta.version
    metadata = ExampleMetadata(ctx)
    assert metadata.id_kinds
    assert metadata.meta.name and metadata.meta.version
