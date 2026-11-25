"""Europe PMC plugin: Searcher + MetadataProvider + Locator (REST API)."""

from __future__ import annotations

from typing import Any

from paper_tools.core.models import Author, FullTextCandidate, Paper, SearchPage
from paper_tools.core.plugins import PluginContext, PluginMeta
from paper_tools.core.query import Query

_REST_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
SEARCH_URL = f"{_REST_BASE}/search"
_SEARCH_TTL = 3600
_METADATA_TTL = 7 * 86400


def fulltext_xml_url(pmcid: str) -> str:
    return f"{_REST_BASE}/{pmcid}/fullTextXML"


def translate_query(q: Query) -> str:
    """Unified Query -> Europe PMC query DSL."""
    if q.raw is not None:
        return q.raw
    parts: list[str] = []
    if q.text:
        parts.append(q.text)
    if q.title:
        parts.append(f'TITLE:"{q.title}"')
    if q.author:
        parts.append(f'AUTH:"{q.author}"')
    if q.journal:
        parts.append(f'JOURNAL:"{q.journal}"')
    if q.year_from is not None or q.year_to is not None:
        lo = q.year_from if q.year_from is not None else 1900
        hi = q.year_to if q.year_to is not None else 3000
        parts.append(f"FIRST_PDATE:[{lo} TO {hi}]")
    if q.open_access:
        parts.append("OPEN_ACCESS:y")
    return " AND ".join(parts)


def _fulltext_links(record: dict[str, Any]) -> list[FullTextCandidate]:
    """OA full-text URLs present in core search/enrich responses."""
    links: list[FullTextCandidate] = []
    entries = (record.get("fullTextUrlList") or {}).get("fullTextUrl") or []
    for entry in entries:
        url = entry.get("url")
        style = entry.get("documentStyle")
        if not url or entry.get("availabilityCode") != "OA":
            continue
        if style in ("pdf", "xml"):
            links.append(FullTextCandidate(url=url, format=style, locator=["europepmc"]))
    pmcid = record.get("pmcid")
    if pmcid and record.get("inEPMC") == "Y":
        links.append(
            FullTextCandidate(url=fulltext_xml_url(pmcid), format="xml", locator=["europepmc"])
        )
    return links


def _record_to_paper(record: dict[str, Any]) -> Paper:
    identifiers: dict[str, str] = {}
    if record.get("doi"):
        identifiers["doi"] = record["doi"].lower()
    if record.get("pmid"):
        identifiers["pmid"] = str(record["pmid"])
    if record.get("pmcid"):
        identifiers["pmcid"] = record["pmcid"]
    authors = [
        Author(name=a.get("fullName", ""))
        for a in record.get("authorList", {}).get("author", [])
        if a.get("fullName")
    ]
    if not authors and record.get("authorString"):
        authors = [Author(name=name.strip()) for name in record["authorString"].split(",")]
    oa_status = "unknown"
    if record.get("isOpenAccess") == "Y":
        oa_status = "gold"
    year = record.get("pubYear")
    return Paper(
        title=record.get("title", "").rstrip("."),
        identifiers=identifiers,
        authors=authors,
        year=int(year) if year else None,
        journal=record.get("journalTitle"),
        abstract=record.get("abstractText"),
        publication_type=(record.get("pubTypeList", {}).get("pubType") or [None])[0],
        oa_status=oa_status,
        license=record.get("license"),
        fulltext_links=_fulltext_links(record),
    )


class _EuropePmcBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def _search(self, query: str, *, page_size: int, cursor: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "query": query,
            "format": "json",
            "pageSize": page_size,
            "resultType": "core",
        }
        if cursor:
            params["cursorMark"] = cursor
        data: dict[str, Any] = self.ctx.http.get_json(
            SEARCH_URL, params=params, cache_ttl=_SEARCH_TTL
        )
        return data

    def _find_record(self, paper: Paper) -> dict[str, Any] | None:
        if paper.identifiers.get("doi"):
            query = f'DOI:"{paper.identifiers["doi"]}"'
        elif paper.identifiers.get("pmid"):
            query = f"EXT_ID:{paper.identifiers['pmid']} AND SRC:MED"
        elif paper.identifiers.get("pmcid"):
            query = f"PMCID:{paper.identifiers['pmcid']}"
        else:
            return None
        data = self.ctx.http.get_json(
            SEARCH_URL,
            params={"query": query, "format": "json", "pageSize": 1, "resultType": "core"},
            cache_ttl=_METADATA_TTL,
        )
        records: list[dict[str, Any]] = data.get("resultList", {}).get("result", [])
        return records[0] if records else None


class EuropePmcSearcher(_EuropePmcBase):
    meta = PluginMeta(name="europepmc", version="0.1.0", description="Europe PMC REST API")

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        data = self._search(translate_query(q), page_size=limit, cursor=cursor)
        records = data.get("resultList", {}).get("result", [])
        next_cursor = data.get("nextCursorMark")
        return SearchPage(
            items=[_record_to_paper(r) for r in records],
            total=data.get("hitCount"),
            next_cursor=next_cursor if next_cursor and next_cursor != cursor else None,
            source="europepmc",
        )


class EuropePmcMetadata(_EuropePmcBase):
    meta = PluginMeta(name="europepmc", version="0.1.0", description="Europe PMC metadata")
    id_kinds = frozenset({"doi", "pmid", "pmcid"})

    def enrich(self, paper: Paper) -> Paper:
        record = self._find_record(paper)
        if record is None:
            return paper
        return _record_to_paper(record)


class EuropePmcLocator(_EuropePmcBase):
    meta = PluginMeta(
        name="europepmc", version="0.1.0", description="Europe PMC OA full-text locator"
    )

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        record = self._find_record(paper)
        if record is None:
            return []
        pmcid = record.get("pmcid")
        if not pmcid or record.get("inEPMC") != "Y":
            return []
        return [
            FullTextCandidate(
                url=fulltext_xml_url(pmcid),
                format="xml",
                locator=["europepmc"],
                license=record.get("license"),
            )
        ]
