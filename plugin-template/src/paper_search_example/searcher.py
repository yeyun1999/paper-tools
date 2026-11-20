"""Template Searcher.

Demonstrates: query translation table, pagination cursor, response caching,
identifier normalization. The example API is fictional — replace BASE_URL and
the parameter/response mapping with your real source, and add respx replay
tests for every endpoint you call.
"""

from __future__ import annotations

from typing import Any

from paper_search.core.models import SearchPage
from paper_search.core.plugins import PluginContext, PluginMeta
from paper_search.core.query import Query

from paper_search_example.mapping import row_to_paper

BASE_URL = "https://api.example.org/v1"
_SEARCH_TTL = 3600  # 搜索结果缓存 1h（与内置源一致）


class ExampleSearcher:
    meta = PluginMeta(
        name="example",
        version="0.1.0",
        description="Template search source (replace with your API)",
    )

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def _query_params(self, q: Query, limit: int, cursor: str | None) -> dict[str, Any]:
        """查询翻译表：统一 Query -> 上游原生参数。raw 直通，结构化字段逐项映射。"""
        params: dict[str, Any] = {"page_size": limit}
        if cursor:
            params["cursor"] = cursor
        if q.raw is not None:
            params["q"] = q.raw
            return params
        if q.text:
            params["query"] = q.text
        if q.title:
            params["title"] = q.title
        if q.author:
            params["author"] = q.author
        if q.journal:
            params["journal"] = q.journal
        if q.year_from is not None:
            params["year_from"] = q.year_from
        if q.year_to is not None:
            params["year_to"] = q.year_to
        if q.open_access:
            params["is_oa"] = "true"
        return params

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        data = self.ctx.http.get_json(
            f"{BASE_URL}/works",
            params=self._query_params(q, limit, cursor),
            cache_ttl=_SEARCH_TTL,
        )
        items = [row_to_paper(row) for row in data.get("items", [])]
        return SearchPage(
            items=items,
            total=int(data.get("total", len(items))),
            next_cursor=data.get("next_cursor"),
            source=self.meta.name,
        )
