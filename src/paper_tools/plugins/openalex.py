"""OpenAlex plugin: Searcher + MetadataProvider + Locator (best_oa_location)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from paper_tools.core.models import (
    Author,
    FullTextCandidate,
    OAStatus,
    Paper,
    SearchPage,
    normalize_doi,
    normalize_pmcid,
)
from paper_tools.core.plugins import PluginContext, PluginMeta
from paper_tools.core.query import Query

WORKS_URL = "https://api.openalex.org/works"
_SEARCH_TTL = 3600
_METADATA_TTL = 7 * 86400
_OA_STATUSES = {"gold", "green", "hybrid", "bronze", "closed"}


def _short_id(url: str) -> str:
    """https://openalex.org/W123 -> W123 (canonical short form)."""
    return url.rstrip("/").rsplit("/", 1)[-1]


def _abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """Reconstruct plain text from OpenAlex's inverted-index abstract."""
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, indexes in inverted.items():
        for index in indexes:
            positions[index] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def _work_to_paper(work: dict[str, Any]) -> Paper:
    ids = work.get("ids") or {}
    identifiers: dict[str, str] = {}
    if ids.get("doi"):
        identifiers["doi"] = normalize_doi(ids["doi"])
    if work.get("id"):
        identifiers["openalex"] = _short_id(work["id"])
    if ids.get("pmid"):
        identifiers["pmid"] = _short_id(ids["pmid"])
    if ids.get("pmcid"):
        identifiers["pmcid"] = normalize_pmcid(_short_id(ids["pmcid"]))

    oa = work.get("open_access") or {}
    raw_status = oa.get("oa_status")
    oa_status: OAStatus = (
        raw_status if raw_status in _OA_STATUSES else ("gold" if oa.get("is_oa") else "unknown")
    )
    best = work.get("best_oa_location") or {}
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    authors = [
        Author(name=a["author"]["display_name"])
        for a in work.get("authorships") or []
        if (a.get("author") or {}).get("display_name")
    ]
    links: list[FullTextCandidate] = []
    if best.get("pdf_url"):
        links.append(
            FullTextCandidate(
                url=best["pdf_url"], format="pdf", locator="openalex", license=best.get("license")
            )
        )
    if best.get("landing_page_url"):
        links.append(
            FullTextCandidate(
                url=best["landing_page_url"],
                format="landing",
                locator="openalex",
                license=best.get("license"),
            )
        )
    return Paper(
        title=work.get("display_name") or "",
        identifiers=identifiers,
        authors=authors,
        year=work.get("publication_year"),
        journal=source.get("display_name"),
        abstract=_abstract(work.get("abstract_inverted_index")),
        publication_type=work.get("type"),
        oa_status=oa_status,
        license=best.get("license") or primary.get("license"),
        publisher_url=primary.get("landing_page_url"),
        fulltext_links=links,
    )


def _query_params(q: Query) -> dict[str, Any]:
    if q.raw is not None:
        return {"search": q.raw}
    params: dict[str, Any] = {}
    if q.text:
        params["search"] = q.text
    filters: list[str] = []
    if q.title:
        filters.append(f"title.search:{q.title}")
    if q.author:
        filters.append(f"raw_author_name.search:{q.author}")
    if q.journal:
        filters.append(f"primary_location.source.display_name.search:{q.journal}")
    if q.year_from is not None:
        filters.append(f"from_publication_date:{q.year_from}-01-01")
    if q.year_to is not None:
        filters.append(f"until_publication_date:{q.year_to}-12-31")
    if q.open_access:
        filters.append("is_oa:true")
    if filters:
        params["filter"] = ",".join(filters)
    return params


class _OpenAlexBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._common: dict[str, Any] = {}
        if ctx.config.general.mailto:
            self._common["mailto"] = ctx.config.general.mailto
        api_key = str(ctx.config.plugin_config("openalex").get("api_key") or "")
        self._headers: dict[str, str] | None = None
        if api_key:
            self._headers = {"Authorization": f"Bearer {api_key}"}
            ctx.http.set_rate_limit("api.openalex.org", 10.0)

    def _find_work(self, paper: Paper) -> dict[str, Any] | None:
        ids = paper.identifiers
        if ids.get("doi"):
            url = f"{WORKS_URL}/doi:{quote(ids['doi'], safe='/')}"
            data = self.ctx.http.get_json(
                url, params=self._common, headers=self._headers, cache_ttl=_METADATA_TTL
            )
            return data if data.get("id") else None
        if ids.get("openalex"):
            url = f"{WORKS_URL}/{quote(_short_id(ids['openalex']), safe='')}"
            data = self.ctx.http.get_json(
                url, params=self._common, headers=self._headers, cache_ttl=_METADATA_TTL
            )
            return data if data.get("id") else None
        for kind in ("pmid", "pmcid"):
            if ids.get(kind):
                data = self.ctx.http.get_json(
                    WORKS_URL,
                    params={
                        **self._common,
                        "filter": f"{kind}:{ids[kind]}",
                        "per-page": 1,
                    },
                    headers=self._headers,
                    cache_ttl=_METADATA_TTL,
                )
                results: list[dict[str, Any]] = data.get("results") or []
                return results[0] if results else None
        return None


class OpenAlexSearcher(_OpenAlexBase):
    meta = PluginMeta(name="openalex", version="0.1.0", description="OpenAlex works REST API")

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        params: dict[str, Any] = {
            **self._common,
            **_query_params(q),
            "per-page": limit,
            "cursor": cursor or "*",
        }
        data = self.ctx.http.get_json(
            WORKS_URL, params=params, headers=self._headers, cache_ttl=_SEARCH_TTL
        )
        meta = data.get("meta", {})
        return SearchPage(
            items=[_work_to_paper(w) for w in data.get("results") or []],
            total=meta.get("count"),
            next_cursor=meta.get("next_cursor"),
            source="openalex",
        )


class OpenAlexMetadata(_OpenAlexBase):
    meta = PluginMeta(name="openalex", version="0.1.0", description="OpenAlex metadata")
    id_kinds = frozenset({"doi", "openalex", "pmid", "pmcid"})

    def enrich(self, paper: Paper) -> Paper:
        work = self._find_work(paper)
        if work is None:
            return paper
        return _work_to_paper(work)


class OpenAlexLocator(_OpenAlexBase):
    meta = PluginMeta(name="openalex", version="0.1.0", description="OpenAlex best_oa_location")

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        work = self._find_work(paper)
        if work is None:
            return []
        best = work.get("best_oa_location") or {}
        candidates: list[FullTextCandidate] = []
        if best.get("pdf_url"):
            candidates.append(
                FullTextCandidate(
                    url=best["pdf_url"],
                    format="pdf",
                    locator="openalex",
                    license=best.get("license"),
                )
            )
        if best.get("landing_page_url"):
            candidates.append(
                FullTextCandidate(
                    url=best["landing_page_url"],
                    format="landing",
                    locator="openalex",
                    license=best.get("license"),
                )
            )
        return candidates
