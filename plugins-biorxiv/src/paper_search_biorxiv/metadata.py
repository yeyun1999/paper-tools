"""bioRxiv/medRxiv MetadataProvider via the official details API.

API: https://api.biorxiv.org/details/{server}/{doi} — open, no key required.
Returns all versions of a preprint; we take the latest.

Scope note: this plugin only fills metadata. Full text of bioRxiv preprints is
retrieved through the built-in Europe PMC (PPR records) / Unpaywall locators;
www.biorxiv.org itself blocks non-browser clients (Cloudflare), and bypassing
that is out of scope by the project's compliance rules.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from paper_search.core.models import Author, Paper, normalize_doi
from paper_search.core.plugins import PluginContext, PluginMeta

API_BASE = "https://api.biorxiv.org/details"
_META_TTL = 7 * 86400
_SERVERS = ("biorxiv", "medrxiv")
_HOSTS = {"biorxiv": "www.biorxiv.org", "medrxiv": "www.medrxiv.org"}


def _parse_authors(raw: str) -> list[Author]:
    """'Hanmer, J. M.; D'Antonio, F.' -> [Author('J. M. Hanmer'), ...]"""
    authors: list[Author] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            family, given = (s.strip() for s in part.split(",", 1))
            part = f"{given} {family}".strip()
        authors.append(Author(name=part))
    return authors


def _record_to_paper(record: dict[str, Any], server: str) -> Paper:
    doi = normalize_doi(str(record.get("doi") or ""))
    date = str(record.get("date") or "")
    year = int(date[:4]) if date[:4].isdigit() else None
    license_raw = str(record.get("license") or "").strip()
    version = str(record.get("version") or "1")
    host = _HOSTS.get(server, _HOSTS["biorxiv"])
    return Paper(
        title=str(record.get("title") or ""),
        identifiers={"doi": doi} if doi else {},
        authors=_parse_authors(str(record.get("authors") or "")),
        year=year,
        abstract=str(record.get("abstract") or "") or None,
        publication_type="preprint",
        oa_status="green",
        license=license_raw.replace("_", "-") or None,
        publisher_url=f"https://{host}/content/{doi}v{version}" if doi else None,
    )


class BiorxivMetadata:
    meta = PluginMeta(
        name="biorxiv",
        version="0.1.0",
        description="bioRxiv/medRxiv preprint metadata (official details API)",
    )
    id_kinds = frozenset({"doi"})

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def _servers(self) -> tuple[str, ...]:
        configured = str(self.ctx.config.plugin_config("biorxiv").get("server") or "biorxiv")
        if configured not in _SERVERS:
            configured = "biorxiv"
        rest = tuple(s for s in _SERVERS if s != configured)
        return (configured, *rest)

    def enrich(self, paper: Paper) -> Paper:
        doi = paper.identifiers.get("doi")
        if not doi:
            return paper
        doi = normalize_doi(doi)
        for server in self._servers():
            data = self.ctx.http.get_json(
                f"{API_BASE}/{server}/{quote(doi, safe='/')}", cache_ttl=_META_TTL
            )
            messages = data.get("messages") or [{}]
            collection = data.get("collection") or []
            if messages[0].get("status") == "ok" and collection:
                return _record_to_paper(collection[-1], server)
        return paper
