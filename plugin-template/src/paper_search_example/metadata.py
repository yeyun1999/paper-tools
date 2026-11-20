"""Template MetadataProvider.

Demonstrates: id_kinds routing, fill-missing contract (return a Paper with
whatever you can fill; the service merges without overwriting), 404 tolerance,
metadata caching (7d).
"""

from __future__ import annotations

from urllib.parse import quote

from paper_search.core.errors import UpstreamError
from paper_search.core.models import Paper
from paper_search.core.plugins import PluginContext, PluginMeta

from paper_search_example.mapping import row_to_paper
from paper_search_example.searcher import BASE_URL

_META_TTL = 7 * 86400  # 补全结果缓存 7d（与内置源一致）


class ExampleMetadata:
    meta = PluginMeta(
        name="example",
        version="0.1.0",
        description="Template metadata source (replace with your API)",
    )
    id_kinds = frozenset({"doi"})  # 声明能处理的标识符类型，服务据此路由

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enrich(self, paper: Paper) -> Paper:
        doi = paper.identifiers.get("doi")
        if not doi:
            return paper
        try:
            row = self.ctx.http.get_json(
                f"{BASE_URL}/works/{quote(doi, safe='/')}", cache_ttl=_META_TTL
            )
        except UpstreamError as exc:
            if exc.details.get("status") == 404:
                return paper  # 本源没有该文献：交回补全链继续
            raise
        return row_to_paper(row)
