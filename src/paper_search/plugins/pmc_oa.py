"""PMC Open Access Subset plugin: Locator (OA web service) + Downloader (tar.gz packages).

Only the official OA subset is served; non-OA PMC records yield no candidates.
"""

from __future__ import annotations

import io
import tarfile
from typing import Any, cast

from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from paper_search.core.errors import UpstreamError
from paper_search.core.models import Artifact, ArtifactFormat, FullTextCandidate, Paper
from paper_search.core.plugins import PluginContext, PluginMeta

OA_SERVICE = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_TTL = 86400


def _https(href: str) -> str:
    """OA service reports ftp:// links; the same paths are served over https."""
    if href.startswith("ftp://"):
        return "https://" + href[len("ftp://") :]
    return href


class _PmcOaBase:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._common: dict[str, Any] = {"tool": "paper-search"}
        if ctx.config.general.mailto:
            self._common["email"] = ctx.config.general.mailto


class PmcOaLocator(_PmcOaBase):
    meta = PluginMeta(name="pmc_oa", version="0.1.0", description="PMC OA Subset locator")

    def _pmcid(self, paper: Paper) -> str | None:
        pmcid = paper.identifiers.get("pmcid")
        if pmcid:
            return pmcid
        ident = paper.identifiers.get("pmid") or paper.identifiers.get("doi")
        if not ident:
            return None
        data = self.ctx.http.get_json(
            IDCONV, params={**self._common, "ids": ident, "format": "json"}, cache_ttl=_TTL
        )
        for record in data.get("records", []):
            if record.get("pmcid"):
                return cast(str, record["pmcid"])
        return None

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        pmcid = self._pmcid(paper)
        if not pmcid:
            return []
        content = self.ctx.http.get_bytes(OA_SERVICE, params={"id": pmcid})
        root = safe_xml_fromstring(content)
        if root.find("error") is not None:
            # e.g. idIsNotOpenAccess: the record exists but is outside the OA subset
            return []
        candidates: list[FullTextCandidate] = []
        for link in root.findall(".//record/link"):
            href = link.get("href")
            if not href:
                continue
            url = _https(href)
            if link.get("format") == "tgz":
                # package holds JATS .nxml and usually a rendered .pdf
                candidates.append(FullTextCandidate(url=url, format="xml", locator="pmc_oa"))
                candidates.append(FullTextCandidate(url=url, format="pdf", locator="pmc_oa"))
            elif link.get("format") == "pdf":
                candidates.append(FullTextCandidate(url=url, format="pdf", locator="pmc_oa"))
        return candidates


class PmcOaDownloader(_PmcOaBase):
    meta = PluginMeta(name="pmc_oa", version="0.1.0", description="PMC OA package downloader")
    formats = frozenset({"pdf", "xml"})

    def supports(self, candidate: FullTextCandidate) -> bool:
        return candidate.locator == "pmc_oa"

    def download(self, candidate: FullTextCandidate) -> Artifact:
        content = self.ctx.http.get_bytes(candidate.url)
        if candidate.url.endswith(".tar.gz"):
            content = self._from_package(content, candidate)
        return Artifact(
            format=cast(ArtifactFormat, candidate.format),
            content=content,
            source_url=candidate.url,
            downloader="pmc_oa",
            license=candidate.license,
        )

    @staticmethod
    def _from_package(data: bytes, candidate: FullTextCandidate) -> bytes:
        suffix = ".nxml" if candidate.format == "xml" else ".pdf"
        # read members in memory only (extractfile) -- never unpack to disk,
        # so tar path traversal is not a concern here.
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.isfile() and member.name.lower().endswith(suffix):
                    extracted = tf.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
        raise UpstreamError(f"No {suffix} file inside PMC OA package", url=candidate.url)
