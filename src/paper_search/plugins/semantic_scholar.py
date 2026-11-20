"""Semantic Scholar plugin: Searcher + MetadataProvider via the Graph API.

Without an api_key the shared quota is tight; the client stays at 1 req/s and
retries 429 with backoff. Configure a personal key for heavier use:
``paper-search config set plugins.semantic_scholar.api_key <key>``
"""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

from paper_search.core.errors import UsageError
from paper_search.core.models import (
    Author,
    FullTextCandidate,
    OAStatus,
    Paper,
    SearchPage,
    normalize_doi,
    normalize_pmcid,
)
from paper_search.core.plugins import PluginContext, PluginMeta
from paper_search.core.query import Query

_BASE = "https://api.semanticscholar.org/graph/v1"
SEARCH_URL = f"{_BASE}/paper/search"
PAPER_URL = f"{_BASE}/paper"
FIELDS = "title,abstract,year,authors,externalIds,venue,publicationTypes,openAccessPdf,isOpenAccess"
_SEARCH_TTL = 3600
_METADATA_TTL = 7 * 86400
_OA_STATUSES = {"gold", "green", "hybrid", "bronze", "closed"}


def _paper_to_paper(record: dict[str, Any]) -> Paper:
    ext = record.get("externalIds") or {}
    identifiers: dict[str, str] = {}
    if ext.get("DOI"):
        identifiers["doi"] = normalize_doi(ext["DOI"])
    if ext.get("PubMed"):
        identifiers["pmid"] = str(ext["PubMed"])
    if ext.get("PubMedCentral"):
        identifiers["pmcid"] = normalize_pmcid(str(ext["PubMedCentral"]))
    if ext.get("ArXiv"):
        identifiers["arxiv"] = str(ext["ArXiv"])
    if record.get("paperId"):
        identifiers["s2"] = record["paperId"]

    oa_pdf = record.get("openAccessPdf") or {}
    raw_status: str = str(oa_pdf.get("status") or "").lower()
    oa_status: OAStatus = (
        cast(OAStatus, raw_status)
        if raw_status in _OA_STATUSES
        else ("gold" if record.get("isOpenAccess") else "unknown")
    )
    links: list[FullTextCandidate] = []
    if oa_pdf.get("url"):
        links.append(
            FullTextCandidate(
                url=oa_pdf["url"],
                format="pdf",
                locator="semantic_scholar",
                license=oa_pdf.get("license"),
            )
        )
    return Paper(
        title=record.get("title") or "",
        identifiers=identifiers,
        authors=[Author(name=a["name"]) for a in record.get("authors") or [] if a.get("name")],
        year=record.get("year"),
        journal=record.get("venue") or None,
        abstract=record.get("abstract"),
        publication_type=(record.get("publicationTypes") or [None])[0],
        oa_status=oa_status,
        license=oa_pdf.get("license"),
        publisher_url=(f"https://doi.org/{identifiers['doi']}" if "doi" in identifiers else None),
        fulltext_links=links,
    )


class _S2Base:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._headers: dict[str, str] = {}
        api_key = ctx.config.plugin_config("semantic_scholar").get("api_key")
        if api_key:
            self._headers["x-api-key"] = api_key

    def _get(self, url: str, params: dict[str, Any], ttl: float) -> dict[str, Any]:
        data: dict[str, Any] = self.ctx.http.get_json(
            url, params=params, headers=self._headers or None, cache_ttl=ttl
        )
        return data


class SemanticScholarSearcher(_S2Base):
    meta = PluginMeta(
        name="semantic_scholar", version="0.1.0", description="Semantic Scholar Graph API"
    )

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        if q.raw is not None:
            query = q.raw
        else:
            query = " ".join(p for p in (q.text, q.title, q.author) if p)
        if not query:
            raise UsageError(
                "Semantic Scholar search needs text/title/author (journal-only is unsupported)."
            )
        params: dict[str, Any] = {
            "query": query,
            "fields": FIELDS,
            "limit": limit,
            "offset": int(cursor) if cursor else 0,
        }
        if q.raw is None:
            if q.journal:
                params["venue"] = q.journal
            if q.year_from is not None or q.year_to is not None:
                lo = q.year_from if q.year_from is not None else ""
                hi = q.year_to if q.year_to is not None else ""
                params["year"] = f"{lo}-{hi}"
            if q.open_access:
                params["openAccessPdf"] = "true"
        data = self._get(SEARCH_URL, params, _SEARCH_TTL)
        total = data.get("total")
        next_offset = data.get("next")
        return SearchPage(
            items=[_paper_to_paper(r) for r in data.get("data") or []],
            total=total,
            next_cursor=str(next_offset) if next_offset is not None else None,
            source="semantic_scholar",
        )


class SemanticScholarMetadata(_S2Base):
    meta = PluginMeta(
        name="semantic_scholar", version="0.1.0", description="Semantic Scholar paper metadata"
    )
    id_kinds = frozenset({"doi", "pmid", "pmcid", "s2", "arxiv"})

    def enrich(self, paper: Paper) -> Paper:
        ids = paper.identifiers
        if ids.get("s2"):
            paper_id = ids["s2"]
        elif ids.get("doi"):
            paper_id = f"DOI:{ids['doi']}"
        elif ids.get("pmid"):
            paper_id = f"PMID:{ids['pmid']}"
        elif ids.get("pmcid"):
            paper_id = f"PMCID:{ids['pmcid']}"
        elif ids.get("arxiv"):
            paper_id = f"ARXIV:{ids['arxiv']}"
        else:
            return paper
        url = f"{PAPER_URL}/{quote(paper_id, safe=':')}"
        data = self._get(url, {"fields": FIELDS}, _METADATA_TTL)
        if not data.get("paperId"):
            return paper
        return _paper_to_paper(data)
