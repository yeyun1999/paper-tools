"""Core domain models. Fields are the JSON contract (schema_version 1.1)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from paper_tools.core.errors import UsageError

IdentifierKind = Literal["doi", "pmid", "pmcid", "openalex", "s2", "arxiv", "url"]
OAStatus = Literal["gold", "green", "hybrid", "bronze", "closed", "unknown"]
ArtifactFormat = Literal["pdf", "xml", "text"]
CandidateFormat = Literal["pdf", "xml", "text", "landing"]

# JSON contract version. Bump on any field change (snapshot gate + CHANGELOG).
# Also keys the metadata cache so contract bumps invalidate stale entries.
SCHEMA_VERSION = "1.1"

_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_ID_PREFIXES = {"doi", "pmid", "pmcid", "openalex", "s2", "arxiv"}
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_doi(value: str) -> str:
    """Lowercase and strip resolver prefixes from a DOI."""
    v = value.strip()
    lower = v.lower()
    for prefix in _DOI_URL_PREFIXES:
        if lower.startswith(prefix):
            v = v[len(prefix) :]
            break
    return v.lower()


def normalize_pmcid(value: str) -> str:
    """Ensure the canonical ``PMC`` prefix (some upstreams report bare digits)."""
    v = value.strip()
    return v if v.upper().startswith("PMC") else f"PMC{v}"


class Identifier(BaseModel):
    kind: IdentifierKind
    value: str


def parse_identifier(raw: str) -> Identifier:
    """Parse ``doi:...`` / ``pmid:...`` prefixed IDs, DOI URLs, or bare DOIs.

    Bare digit strings are treated as PMIDs for convenience.
    """
    text = raw.strip()
    if not text:
        raise UsageError("Empty identifier.")
    lower = text.lower()
    if lower.startswith(("http://", "https://")):
        if "doi.org/" in lower:
            return Identifier(kind="doi", value=normalize_doi(text))
        return Identifier(kind="url", value=text)
    prefix, sep, rest = text.partition(":")
    if sep and prefix.lower() in _ID_PREFIXES:
        kind = cast(IdentifierKind, prefix.lower())
        value = normalize_doi(rest) if kind == "doi" else rest.strip()
        if not value:
            raise UsageError(f"Empty value for identifier {raw!r}.")
        return Identifier(kind=kind, value=value)
    if _DOI_RE.match(text):
        return Identifier(kind="doi", value=normalize_doi(text))
    if text.isdigit():
        return Identifier(kind="pmid", value=text)
    raise UsageError(
        f"Cannot parse identifier {raw!r}; use a doi:/pmid:/pmcid: prefix or a bare DOI."
    )


class Author(BaseModel):
    name: str
    orcid: str | None = None
    affiliation: str | None = None


class FullTextCandidate(BaseModel):
    url: str
    format: CandidateFormat
    locator: str
    license: str | None = None


class Paper(BaseModel):
    title: str = ""
    identifiers: dict[str, str] = Field(default_factory=dict)
    authors: list[Author] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    abstract: str | None = None
    publication_type: str | None = None
    oa_status: OAStatus = "unknown"
    publisher_url: str | None = None
    license: str | None = None
    sources: list[str] = Field(default_factory=list)
    fulltext_links: list[FullTextCandidate] = Field(default_factory=list)


class SearchPage(BaseModel):
    items: list[Paper] = Field(default_factory=list)
    total: int | None = None
    next_cursor: str | None = None
    source: str


class Artifact(BaseModel):
    """Raw downloaded content, before validation/extraction/output placement."""

    format: ArtifactFormat
    content: bytes
    source_url: str
    downloader: str
    license: str | None = None


class FullText(BaseModel):
    paper: Paper
    format: ArtifactFormat
    path: Path
    sha256: str
    source_url: str
    downloader: str
    license: str | None = None
    extractor: str | None = None
    extracted_from: Literal["pdf", "xml"] | None = None


def paper_slug(paper: Paper) -> str:
    """Filesystem-safe slug, preferring DOI."""
    if "doi" in paper.identifiers:
        base = paper.identifiers["doi"]
    elif paper.identifiers:
        kind, value = next(iter(paper.identifiers.items()))
        base = f"{kind}_{value}"
    else:
        base = paper.title or "paper"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "paper"


def is_complete(paper: Paper) -> bool:
    """Early-stop condition for the enrichment chain."""
    return bool(paper.title) and paper.abstract is not None


_MERGE_SCALAR_FIELDS = (
    "title",
    "year",
    "journal",
    "abstract",
    "publication_type",
    "publisher_url",
    "license",
)


def merge_papers(base: Paper, incoming: Paper, *, source: str) -> tuple[Paper, list[str]]:
    """Fill-missing merge: never overwrite existing values; union identifiers.

    Returns the merged paper and human-readable warnings (identifier conflicts).
    ``source`` is recorded in ``sources`` when it contributed anything.
    """
    merged = base.model_copy(deep=True)
    warnings: list[str] = []
    contributed = False

    for field in _MERGE_SCALAR_FIELDS:
        current = getattr(merged, field)
        new = getattr(incoming, field)
        if current in (None, "") and new not in (None, ""):
            setattr(merged, field, new)
            contributed = True

    if not merged.authors and incoming.authors:
        merged.authors = list(incoming.authors)
        contributed = True

    if merged.oa_status == "unknown" and incoming.oa_status != "unknown":
        merged.oa_status = incoming.oa_status
        contributed = True

    for kind, value in incoming.identifiers.items():
        if kind not in merged.identifiers:
            merged.identifiers[kind] = value
            contributed = True
        elif merged.identifiers[kind] != value:
            warnings.append(
                f"identifier conflict from {source}: {kind} kept "
                f"{merged.identifiers[kind]!r}, ignored {value!r}"
            )

    for src in incoming.sources:
        if src not in merged.sources:
            merged.sources.append(src)
    seen_links = {(link.url, link.format) for link in merged.fulltext_links}
    for link in incoming.fulltext_links:
        if (link.url, link.format) not in seen_links:
            merged.fulltext_links.append(link.model_copy(deep=True))
            seen_links.add((link.url, link.format))
            contributed = True
    if contributed and source and source not in merged.sources:
        merged.sources.append(source)
    return merged, warnings
