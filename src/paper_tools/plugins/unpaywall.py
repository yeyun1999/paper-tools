"""Unpaywall plugin: Locator + MetadataProvider (OA status / license).

Requires an email (official API policy):
``paper-tools config set plugins.unpaywall.email you@example.com``
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from paper_tools.core.errors import ConfigError, PaperToolsError
from paper_tools.core.models import Author, CandidateFormat, FullTextCandidate, OAStatus, Paper
from paper_tools.core.plugins import PluginContext, PluginMeta
from paper_tools.plugins.pmc_oa import resolve_pmc_candidates

logger = logging.getLogger(__name__)

API_BASE = "https://api.unpaywall.org/v2/"
_TTL = 86400  # OA locations change slowly; refresh daily
_OA_STATUSES = {"gold", "green", "hybrid", "bronze", "closed"}


class _UnpaywallBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._email = ctx.config.plugin_config("unpaywall").get("email")

    def _fetch(self, doi: str) -> dict[str, Any]:
        if not self._email:
            raise ConfigError(
                "Unpaywall requires an email. Set it with: "
                "paper-tools config set plugins.unpaywall.email you@example.com"
            )
        url = API_BASE + quote(doi, safe="/")
        data: dict[str, Any] = self.ctx.http.get_json(
            url, params={"email": self._email}, cache_ttl=_TTL
        )
        return data


def _location_candidates(location: dict[str, Any]) -> list[FullTextCandidate]:
    candidates: list[FullTextCandidate] = []
    license_ = location.get("license")

    def add(url: str | None, fmt: CandidateFormat) -> None:
        if url:
            candidates.append(
                FullTextCandidate(
                    url=url,
                    format=fmt,
                    locator="unpaywall",
                    license=license_,
                )
            )

    pdf_url = location.get("url_for_pdf")
    add(pdf_url, "pdf")
    url = location.get("url")
    if url and url != pdf_url:
        lower = url.lower()
        fmt: CandidateFormat = (
            "pdf" if lower.endswith(".pdf") else "xml" if lower.endswith(".xml") else "landing"
        )
        add(url, fmt)
    add(location.get("url_for_landing_page"), "landing")
    return candidates


def _pmcid_from_location(location: dict[str, Any]) -> str | None:
    pmh_id = location.get("pmh_id")
    prefix = "oai:pubmedcentral.nih.gov:"
    if isinstance(pmh_id, str) and pmh_id.startswith(prefix):
        accession = pmh_id[len(prefix) :]
        if accession.isdigit():
            return f"PMC{accession}"
    return None


class UnpaywallLocator(_UnpaywallBase):
    meta = PluginMeta(name="unpaywall", version="0.1.0", description="Unpaywall OA location lookup")

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        doi = paper.identifiers.get("doi")
        if not doi:
            return []
        data = self._fetch(doi)
        locations: list[dict[str, Any]] = []
        best = data.get("best_oa_location")
        if best:
            locations.append(best)
        locations.extend(data.get("oa_locations") or [])
        candidates: list[FullTextCandidate] = []
        seen: set[tuple[str, str]] = set()
        for location in locations:
            for candidate in _location_candidates(location):
                key = (candidate.url, candidate.format)
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)
            pmcid = _pmcid_from_location(location)
            if not pmcid:
                continue
            try:
                pmc_candidates = resolve_pmc_candidates(pmcid, self.ctx)
            except PaperToolsError as exc:
                logger.warning("PMC lookup for Unpaywall location failed: %s", exc.message)
                continue
            for candidate in pmc_candidates:
                key = (candidate.url, candidate.format)
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)
        return candidates


class UnpaywallMetadata(_UnpaywallBase):
    meta = PluginMeta(
        name="unpaywall", version="0.1.0", description="Unpaywall metadata and OA locations"
    )
    id_kinds = frozenset({"doi"})

    def enrich(self, paper: Paper) -> Paper:
        doi = paper.identifiers.get("doi")
        if not doi:
            return paper
        data = self._fetch(doi)
        raw_status = data.get("oa_status")
        oa_status: OAStatus = raw_status if raw_status in _OA_STATUSES else "unknown"
        best = data.get("best_oa_location") or {}
        return Paper(
            identifiers=dict(paper.identifiers),
            title=data.get("title") or "",
            authors=[
                Author(name=author["raw_author_name"])
                for author in data.get("z_authors") or []
                if author.get("raw_author_name")
            ],
            year=data.get("year"),
            journal=data.get("journal_name"),
            publication_type=data.get("genre"),
            oa_status=oa_status,
            license=best.get("license"),
            publisher_url=data.get("doi_url"),
        )
