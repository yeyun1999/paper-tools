"""PMC Article Datasets plugin: ID conversion and AWS full-text location."""

from __future__ import annotations

from typing import Any, cast

from paper_tools.core.models import FullTextCandidate, Paper
from paper_tools.core.plugins import PluginContext, PluginMeta

S3_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
_TTL = 86400
_S3_PREFIX = "s3://pmc-oa-opendata/"


def _https_url(href: str) -> str:
    if href.startswith(_S3_PREFIX):
        return f"{S3_BASE}/{href[len(_S3_PREFIX) :]}"
    return href


class _PmcOaBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._common: dict[str, Any] = {"tool": "paper-tools"}
        if ctx.config.general.mailto:
            self._common["email"] = ctx.config.general.mailto
        ctx.http.set_rate_limit("pmc-oa-opendata.s3.amazonaws.com", 3.0)


class PmcOaLocator(_PmcOaBase):
    meta = PluginMeta(name="pmc_oa", version="0.1.0", description="PMC Article Datasets locator")

    def _current_version(self, paper: Paper) -> str | None:
        ident = (
            paper.identifiers.get("pmcid")
            or paper.identifiers.get("pmid")
            or paper.identifiers.get("doi")
        )
        if not ident:
            return None
        data = self.ctx.http.get_json(
            IDCONV,
            params={**self._common, "ids": ident, "format": "json", "versions": "yes"},
            cache_ttl=_TTL,
        )
        for record in data.get("records", []):
            if record.get("live") is False:
                continue
            versions = record.get("versions") or []
            current = next(
                (version for version in versions if version.get("current") is True), None
            )
            version = current or record
            versioned_pmcid = version.get("pmcid")
            if not versioned_pmcid:
                continue
            version_id = cast(str, versioned_pmcid)
            return version_id if "." in version_id else f"{version_id}.1"
        return None

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        version = self._current_version(paper)
        if not version:
            return []
        metadata = self.ctx.http.get_json(f"{S3_BASE}/{version}/{version}.json", cache_ttl=_TTL)
        candidates: list[FullTextCandidate] = []
        for key, fmt in (("pdf_url", "pdf"), ("xml_url", "xml")):
            href = metadata.get(key)
            if href:
                candidates.append(
                    FullTextCandidate(
                        url=_https_url(href),
                        format=fmt,
                        locator=["pmc_oa"],
                        license=metadata.get("license_code"),
                    )
                )
        return candidates


def resolve_pmc_candidates(pmcid: str, ctx: PluginContext) -> list[FullTextCandidate]:
    return PmcOaLocator(ctx).resolve(Paper(identifiers={"pmcid": pmcid}))
