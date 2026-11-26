"""Crossref plugin: Searcher + MetadataProvider via the /works REST API."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import quote

from paper_tools.core.errors import UsageError
from paper_tools.core.models import Author, Paper, PaperSummary, SearchPage, normalize_doi
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
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if (
            isinstance(parts, list)
            and parts
            and isinstance(parts[0], list)
            and parts[0]
            and isinstance(parts[0][0], int)
            and not isinstance(parts[0][0], bool)
        ):
            return parts[0][0]
    year = item.get("year")
    if isinstance(year, int) and not isinstance(year, bool):
        return year
    if isinstance(year, str) and year.isdigit():
        return int(year)
    return None


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _authors(items: Any) -> list[Author]:
    if not isinstance(items, list):
        return []
    authors: list[Author] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        given = item.get("given")
        family = item.get("family")
        name = (
            f"{given if isinstance(given, str) else ''} {family if isinstance(family, str) else ''}"
        )
        name = name.strip()
        if name:
            orcid = item.get("ORCID")
            authors.append(Author(name=name, orcid=orcid if isinstance(orcid, str) else None))
    return authors


def _reference_to_summary(item: Any) -> PaperSummary | None:
    if not isinstance(item, dict):
        return None
    identifiers: dict[str, str] = {}
    doi = item.get("DOI")
    if isinstance(doi, str) and doi.strip():
        identifiers["doi"] = normalize_doi(doi)
    title = item.get("article-title")
    if isinstance(title, list):
        title = title[0] if title else None
    authors = _authors(item.get("author"))
    year = _year(item)
    if not isinstance(title, str):
        title = ""
    if not (title or identifiers or authors or year is not None):
        return None
    return PaperSummary(title=title, identifiers=identifiers, authors=authors, year=year)


def _item_to_paper(item: dict[str, Any]) -> Paper:
    identifiers: dict[str, str] = {}
    doi = item.get("DOI")
    if isinstance(doi, str) and doi:
        identifiers["doi"] = normalize_doi(doi)
    titles = item.get("title")
    title = ""
    if isinstance(titles, list) and titles and isinstance(titles[0], str):
        title = titles[0]
    authors = _authors(item.get("author"))
    licenses = item.get("license")
    licenses = licenses if isinstance(licenses, list) else []
    primary_resource = item.get("resource")
    primary = primary_resource.get("primary") if isinstance(primary_resource, dict) else None
    primary = primary if isinstance(primary, dict) else {}
    issns = item.get("ISSN")
    issn = None
    if isinstance(issns, list):
        issn = next((value for value in issns if isinstance(value, str) and value), None)
    references = item.get("reference")
    return Paper(
        title=title,
        identifiers=identifiers,
        authors=authors,
        year=_year(item),
        journal=(item.get("container-title") or [None])[0],
        abstract=_clean_abstract(item.get("abstract")),
        publication_type=item.get("type"),
        license=licenses[0].get("URL") if licenses and isinstance(licenses[0], dict) else None,
        publisher_url=primary.get("URL"),
        issn=issn,
        cited_by_count=_count(item.get("is-referenced-by-count")),
        references_count=_count(item.get("reference-count")),
        reference_papers=[
            summary
            for reference in references
            if (summary := _reference_to_summary(reference)) is not None
        ]
        if isinstance(references, list)
        else [],
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
