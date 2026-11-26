"""PubMed plugin: Searcher + MetadataProvider via NCBI E-utilities."""

from __future__ import annotations

import re
from typing import Any

from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from paper_tools.core.errors import UpstreamError
from paper_tools.core.models import Author, Paper, PaperSummary, SearchPage, normalize_pmcid
from paper_tools.core.plugins import PluginContext, PluginMeta
from paper_tools.core.query import Query

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH = f"{_BASE}/esearch.fcgi"
ESUMMARY = f"{_BASE}/esummary.fcgi"
EFETCH = f"{_BASE}/efetch.fcgi"
_HOST = "eutils.ncbi.nlm.nih.gov"

_SEARCH_TTL = 3600
_METADATA_TTL = 7 * 86400


def translate_query(q: Query) -> str:
    """Unified Query -> PubMed term syntax."""
    if q.raw is not None:
        return q.raw
    parts: list[str] = []
    if q.text:
        parts.append(q.text)
    if q.title:
        parts.append(f"{q.title}[Title]")
    if q.author:
        parts.append(f"{q.author}[Author]")
    if q.journal:
        parts.append(f"{q.journal}[Journal]")
    if q.year_from is not None or q.year_to is not None:
        lo = q.year_from if q.year_from is not None else 1900
        hi = q.year_to if q.year_to is not None else 3000
        parts.append(f"{lo}:{hi}[dp]")
    if q.open_access:
        parts.append("free full text[sb]")
    return " AND ".join(parts)


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _year_from(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"\d{4}", text)
    return int(match.group()) if match else None


class _PubMedBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        plugin_cfg = ctx.config.plugin_config("pubmed")
        self._common: dict[str, Any] = {"tool": "paper-tools"}
        if ctx.config.general.mailto:
            self._common["email"] = ctx.config.general.mailto
        api_key = plugin_cfg.get("api_key")
        if api_key:
            self._common["api_key"] = api_key
            ctx.http.set_rate_limit(_HOST, 10.0)

    def _esearch_pmids(self, term: str) -> list[str]:
        data = self.ctx.http.get_json(
            ESEARCH,
            params={**self._common, "db": "pubmed", "term": term, "retmax": 1, "retmode": "json"},
            cache_ttl=_SEARCH_TTL,
        )
        result = data.get("esearchresult", {})
        if "ERROR" in result:
            raise UpstreamError(f"PubMed esearch error: {result['ERROR']}", source="pubmed")
        return list(result.get("idlist", []))


class PubMedSearcher(_PubMedBase):
    meta = PluginMeta(name="pubmed", version="0.1.0", description="PubMed via NCBI E-utilities")

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
        retstart = int(cursor) if cursor else 0
        data = self.ctx.http.get_json(
            ESEARCH,
            params={
                **self._common,
                "db": "pubmed",
                "term": translate_query(q),
                "retmax": limit,
                "retstart": retstart,
                "retmode": "json",
                "sort": "relevance",
            },
            cache_ttl=_SEARCH_TTL,
        )
        result = data.get("esearchresult", {})
        if "ERROR" in result:
            raise UpstreamError(f"PubMed esearch error: {result['ERROR']}", source="pubmed")
        idlist = list(result.get("idlist", []))
        total = int(result.get("count", 0))
        items = self._summarize(idlist) if idlist else []
        next_cursor = str(retstart + limit) if retstart + len(idlist) < total else None
        return SearchPage(items=items, total=total, next_cursor=next_cursor, source="pubmed")

    def _summarize(self, pmids: list[str]) -> list[Paper]:
        data = self.ctx.http.get_json(
            ESUMMARY,
            params={**self._common, "db": "pubmed", "id": ",".join(pmids), "retmode": "json"},
            cache_ttl=_SEARCH_TTL,
        )
        result = data.get("result", {})
        papers: list[Paper] = []
        for pmid in result.get("uids", pmids):
            record = result.get(pmid, {})
            if not record:
                continue
            identifiers = {"pmid": pmid}
            for article_id in record.get("articleids", []):
                idtype = article_id.get("idtype")
                value = article_id.get("value")
                if idtype == "doi" and value:
                    identifiers["doi"] = value.lower()
                elif idtype == "pmc" and value:
                    identifiers["pmcid"] = value
            papers.append(
                Paper(
                    title=_strip_tags(record.get("title", "")),
                    identifiers=identifiers,
                    authors=[
                        Author(name=a["name"]) for a in record.get("authors", []) if a.get("name")
                    ],
                    year=_year_from(record.get("pubdate")),
                    journal=record.get("fulljournalname") or record.get("source"),
                    publication_type=(record.get("pubtype") or [None])[0],
                    issn=record.get("issn") if isinstance(record.get("issn"), str) else None,
                )
            )
        return papers


class PubMedMetadata(_PubMedBase):
    meta = PluginMeta(name="pubmed", version="0.1.0", description="PubMed article metadata")
    id_kinds = frozenset({"pmid", "doi", "pmcid"})

    def enrich(self, paper: Paper) -> Paper:
        pmid = paper.identifiers.get("pmid")
        if not pmid:
            doi = paper.identifiers.get("doi")
            pmcid = paper.identifiers.get("pmcid")
            if doi:
                term = f"{doi}[AID]"
            elif pmcid:
                term = f"{pmcid}[PMCID]"
            else:
                return paper
            pmids = self._esearch_pmids(term)
            if not pmids:
                return paper
            pmid = pmids[0]
        response = self.ctx.http.request(
            "GET",
            EFETCH,
            params={
                **self._common,
                "db": "pubmed",
                "id": pmid,
                "rettype": "abstract",
                "retmode": "xml",
            },
            cache_ttl=_METADATA_TTL,
        )
        return _parse_efetch(response.content, paper)


def _text(element: Any) -> str:
    return "".join(element.itertext()).strip() if element is not None else ""


def _citation_title(citation: str) -> str:
    if not citation:
        return ""
    without_year = re.sub(r"\b(?:19|20)\d{2}\b.*$", "", citation).strip()
    without_year = without_year.rstrip(".;, ") or citation
    parts = [part.strip() for part in re.split(r"\.\s+", without_year) if part.strip()]
    if not parts:
        return ""
    if len(parts) > 1 and ("," in parts[0] or re.search(r"\b[A-Z](?:[ -][A-Z])*[.]?$", parts[0])):
        return parts[1]
    return parts[0]


def _reference_to_summary(reference: Any) -> PaperSummary | None:
    citation = _text(reference.find("Citation"))
    identifiers: dict[str, str] = {}
    for article_id in reference.findall("ArticleIdList/ArticleId"):
        id_type = article_id.get("IdType")
        value = _text(article_id)
        if not value:
            continue
        if id_type == "doi":
            identifiers["doi"] = value.lower()
        elif id_type == "pubmed":
            identifiers["pmid"] = value
        elif id_type == "pmc":
            identifiers["pmcid"] = normalize_pmcid(value)
    if not identifiers:
        doi = re.search(r"\b10\.\d{4,9}/\S+", citation)
        pmid = re.search(r"\bPMID:\s*(\d+)", citation, re.IGNORECASE)
        pmcid = re.search(r"\bPMC(?:ID)?:?\s*(?:PMC)?(\d+)", citation, re.IGNORECASE)
        if doi:
            identifiers["doi"] = doi.group(1).rstrip(".").lower()
        if pmid:
            identifiers["pmid"] = pmid.group(1)
        if pmcid:
            identifiers["pmcid"] = normalize_pmcid(pmcid.group(1))
    year = _year_from(citation)
    title = _citation_title(citation)
    if not (title or identifiers or year is not None):
        return None
    return PaperSummary(title=title, identifiers=identifiers, year=year)


def _parse_efetch(content: bytes, original: Paper) -> Paper:
    root = safe_xml_fromstring(content)
    article = root.find(".//PubmedArticle")
    if article is None:
        return original
    medline = article.find("MedlineCitation")
    art = article.find("MedlineCitation/Article")
    if medline is None or art is None:
        return original

    identifiers = dict(original.identifiers)
    pmid = medline.findtext("PMID")
    if pmid:
        identifiers["pmid"] = pmid
    for eloc in art.findall("ELocationID"):
        if eloc.get("EIdType") == "doi" and eloc.text:
            identifiers["doi"] = eloc.text.strip().lower()
    for aid in article.findall("PubmedData/ArticleIdList/ArticleId"):
        id_type = aid.get("IdType")
        if id_type == "doi" and aid.text:
            identifiers.setdefault("doi", aid.text.strip().lower())
        elif id_type == "pmc" and aid.text:
            identifiers["pmcid"] = aid.text.strip()

    abstract_parts: list[str] = []
    for abstract in art.findall("Abstract/AbstractText"):
        text = _text(abstract)
        label = abstract.get("Label")
        abstract_parts.append(f"{label}: {text}" if label else text)

    authors: list[Author] = []
    for author in art.findall("AuthorList/Author"):
        last = author.findtext("LastName")
        fore = author.findtext("ForeName")
        collective = author.findtext("CollectiveName")
        name = f"{fore} {last}".strip() if last else (collective or "")
        if name:
            authors.append(Author(name=name))

    pub_date = art.find("Journal/JournalIssue/PubDate")
    year = None
    if pub_date is not None:
        year = _year_from(pub_date.findtext("Year") or pub_date.findtext("MedlineDate"))

    pub_types = [_text(pt) for pt in art.findall("PublicationTypeList/PublicationType")]

    journal = art.find("Journal")
    issns = journal.findall("ISSN") if journal is not None else []
    issn = next(
        (_text(value) for value in issns if value.get("ISSNType") == "Print" and _text(value)),
        None,
    )
    if issn is None:
        issn = next((_text(value) for value in issns if _text(value)), None)
    reference_list = art.find("ReferenceList")
    references = reference_list.findall("Reference") if reference_list is not None else []

    return Paper(
        title=_text(art.find("ArticleTitle")),
        identifiers=identifiers,
        authors=authors,
        year=year,
        journal=art.findtext("Journal/Title"),
        abstract="\n".join(abstract_parts) if abstract_parts else None,
        publication_type=pub_types[0] if pub_types else None,
        issn=issn,
        references_count=len(references) if reference_list is not None else None,
        reference_papers=[
            summary
            for reference in references
            if (summary := _reference_to_summary(reference)) is not None
        ],
    )
