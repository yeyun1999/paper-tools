"""Crossref plugin: Searcher + MetadataProvider via the /works REST API."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote

from paper_tools.core.errors import UsageError
from paper_tools.core.models import Author, Paper, SearchPage, normalize_doi
from paper_tools.core.plugins import PluginContext, PluginMeta
from paper_tools.core.query import Query

WORKS_URL = "https://api.crossref.org/works"
_SEARCH_TTL = 3600
_METADATA_TTL = 7 * 86400


def _clean_abstract(raw: str | None) -> str | None:
    """Crossref abstracts are HTML-escaped JATS fragments; strip to plain text."""
    if not raw:
        return None
    text = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(raw)).split())
    return text or None


def _year(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            return int(parts[0][0])
    return None


def _item_to_paper(item: dict[str, Any]) -> Paper:
    identifiers: dict[str, str] = {}
    if item.get("DOI"):
        identifiers["doi"] = normalize_doi(item["DOI"])
    titles = item.get("title") or []
    authors = [
        Author(name=f"{a.get('given', '')} {a.get('family', '')}".strip())
        for a in item.get("author", [])
        if a.get("family") or a.get("given")
    ]
    licenses = item.get("license") or []
    primary = (item.get("resource") or {}).get("primary") or {}
    return Paper(
        title=titles[0] if titles else "",
        identifiers=identifiers,
        authors=authors,
        year=_year(item),
        journal=(item.get("container-title") or [None])[0],
        abstract=_clean_abstract(item.get("abstract")),
        publication_type=item.get("type"),
        license=licenses[0].get("URL") if licenses else None,
        publisher_url=primary.get("URL"),
    )


def _query_params(q: Query) -> dict[str, Any]:
    if q.raw is not None:
        return {"query": q.raw}
    if q.open_access:
        raise UsageError(
            "Crossref has no reliable OA filter; use --source pubmed/europepmc/openalex "
            "for --oa-only searches."
        )
    params: dict[str, Any] = {}
    if q.text:
        params["query"] = q.text
    if q.title:
        params["query.title"] = q.title
    if q.author:
        params["query.author"] = q.author
    if q.journal:
        params["query.container-title"] = q.journal
    filters: list[str] = []
    if q.year_from is not None:
        filters.append(f"from-pub-date:{q.year_from}")
    if q.year_to is not None:
        filters.append(f"until-pub-date:{q.year_to}")
    if filters:
        params["filter"] = ",".join(filters)
    return params


class _CrossrefBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._common: dict[str, Any] = {}
        if ctx.config.general.mailto:
            self._common["mailto"] = ctx.config.general.mailto


class CrossrefSearcher(_CrossrefBase):
    meta = PluginMeta(name="crossref", version="0.1.0", description="Crossref /works REST API")

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        offset = int(cursor) if cursor else 0
        params: dict[str, Any] = {
            **self._common,
            **_query_params(q),
            "rows": limit,
            "offset": offset,
        }
        data = self.ctx.http.get_json(WORKS_URL, params=params, cache_ttl=_SEARCH_TTL)
        message = data.get("message", {})
        items = message.get("items", [])
        total = message.get("total-results")
        next_cursor = str(offset + limit) if total and offset + len(items) < total else None
        return SearchPage(
            items=[_item_to_paper(i) for i in items],
            total=total,
            next_cursor=next_cursor,
            source="crossref",
        )


class CrossrefMetadata(_CrossrefBase):
    meta = PluginMeta(name="crossref", version="0.1.0", description="Crossref DOI metadata")
    id_kinds = frozenset({"doi"})

    def enrich(self, paper: Paper) -> Paper:
        doi = paper.identifiers.get("doi")
        if not doi:
            return paper
        url = f"{WORKS_URL}/{quote(doi, safe='/')}"
        data = self.ctx.http.get_json(url, params=self._common, cache_ttl=_METADATA_TTL)
        item = data.get("message")
        if not item:
            return paper
        return _item_to_paper(item)
