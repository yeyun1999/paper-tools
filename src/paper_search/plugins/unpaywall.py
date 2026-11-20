"""Unpaywall plugin: Locator + MetadataProvider (OA status / license).

Requires an email (official API policy):
``paper-search config set plugins.unpaywall.email you@example.com``
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from paper_search.core.errors import ConfigError
from paper_search.core.models import CandidateFormat, FullTextCandidate, OAStatus, Paper
from paper_search.core.plugins import PluginContext, PluginMeta

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
                "paper-search config set plugins.unpaywall.email you@example.com"
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
        seen: set[str] = set()
        for location in locations:
            for candidate in _location_candidates(location):
                if candidate.url not in seen:
                    seen.add(candidate.url)
                    candidates.append(candidate)
        return candidates


class UnpaywallMetadata(_UnpaywallBase):
    meta = PluginMeta(name="unpaywall", version="0.1.0", description="Unpaywall OA status/license")
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
            oa_status=oa_status,
            license=best.get("license"),
            publisher_url=data.get("doi_url"),
        )
