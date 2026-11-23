"""Application services: search, metadata enrichment chain, full-text pipeline."""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from paper_tools.core.cache import Cache
from paper_tools.core.config import AppConfig
from paper_tools.core.errors import (
    ConfigError,
    FullTextUnavailableError,
    NotFoundError,
    PaperToolsError,
    UpstreamError,
    UsageError,
)
from paper_tools.core.models import (
    SCHEMA_VERSION,
    Artifact,
    ArtifactFormat,
    FullText,
    FullTextCandidate,
    Paper,
    SearchPage,
    is_complete,
    merge_papers,
    paper_slug,
    parse_identifier,
)
from paper_tools.core.plugins import (
    Downloader,
    Extractor,
    Locator,
    MetadataProvider,
    PluginRegistry,
    Searcher,
)
from paper_tools.core.query import Query

logger = logging.getLogger(__name__)

_METADATA_TTL = 7 * 86400
_FILEMAP_TTL = 30 * 86400
_TRUSTED_LOCATORS = {"europepmc", "pmc_oa"}
_PREFERRED_EXTRACTORS = {"xml": "jats", "pdf": "pypdf"}


class SearchService:
    def __init__(
        self, registry: PluginRegistry, config: AppConfig, metadata: MetadataService
    ) -> None:
        self._registry = registry
        self._config = config
        self._metadata = metadata

    def search(
        self,
        query: Query,
        *,
        sources: list[str] | None = None,
        limit: int = 20,
        cursor: str | None = None,
        enrich: bool = False,
    ) -> tuple[SearchPage, list[str]]:
        names = sources or [self._config.general.default_source]
        searchers = [(name, cast(Searcher, self._registry.get("searcher", name))) for name in names]
        if len(searchers) == 1:
            _, searcher = searchers[0]
            page = searcher.search(query, limit=limit, cursor=cursor)
            warnings: list[str] = []
        else:
            page, warnings = self._multi_search(query, searchers, limit, cursor)
        if enrich:
            items = []
            for item in page.items:
                enriched, item_warnings = self._metadata.enrich(item)
                items.append(enriched)
                warnings.extend(item_warnings)
            page = page.model_copy(update={"items": items})
        return page, warnings

    @staticmethod
    def _dedup_key(paper: Paper) -> tuple[str, str] | None:
        """DOI primary key; PMID fallback; normalized-title fingerprint last."""
        if paper.identifiers.get("doi"):
            return ("doi", paper.identifiers["doi"])
        if paper.identifiers.get("pmid"):
            return ("pmid", paper.identifiers["pmid"])
        title = " ".join(paper.title.lower().split())
        return ("title", title) if title else None

    def _multi_search(
        self,
        query: Query,
        searchers: list[tuple[str, Searcher]],
        limit: int,
        cursor: str | None,
    ) -> tuple[SearchPage, list[str]]:
        """Concurrent multi-source search: dedup merge, round-robin interleave.

        The aggregated cursor is a JSON object {source: next_cursor}; sources
        absent from it are exhausted. Dedup is per page (stateless across pages).
        ``total`` is the pre-dedup sum of per-source totals (approximate).
        """
        cursors: dict[str, str] = {}
        if cursor is not None:
            try:
                decoded = json.loads(cursor)
            except ValueError as exc:
                raise UsageError(
                    "Multi-source cursor must be the JSON next_cursor from a previous "
                    "multi-source page."
                ) from exc
            if not isinstance(decoded, dict):
                raise UsageError("Multi-source cursor must be a JSON object.")
            cursors = {str(k): str(v) for k, v in decoded.items()}
        active = [(name, s) for name, s in searchers if cursor is None or name in cursors]
        names = ",".join(name for name, _ in searchers)
        if not active:
            return SearchPage(items=[], total=0, next_cursor=None, source=names), []
        warnings: list[str] = []
        pages: dict[str, SearchPage] = {}
        stalled: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            futures = {
                name: pool.submit(s.search, query, limit=limit, cursor=cursors.get(name))
                for name, s in active
            }
            for name, future in futures.items():
                try:
                    pages[name] = future.result()
                except PaperToolsError as exc:
                    warnings.append(f"{name}: {exc.message}")
                    if name in cursors:
                        stalled[name] = cursors[name]  # keep progress for a later retry
        if not pages:
            raise UpstreamError("All search sources failed")

        merged: list[Paper] = []
        index_by_key: dict[tuple[str, str], int] = {}
        lists = [(name, pages[name].items) for name, _ in active if name in pages]
        for round_index in range(max((len(items) for _, items in lists), default=0)):
            for name, items in lists:
                if round_index >= len(items):
                    continue
                item = items[round_index]
                key = self._dedup_key(item)
                if key is not None and key in index_by_key:
                    position = index_by_key[key]
                    combined, merge_warnings = merge_papers(merged[position], item, source=name)
                    merged[position] = combined
                    warnings.extend(merge_warnings)
                else:
                    contributed = item.model_copy(deep=True)
                    if name not in contributed.sources:
                        contributed.sources.append(name)
                    if key is not None:
                        index_by_key[key] = len(merged)
                    merged.append(contributed)

        next_cursors = {name: page.next_cursor for name, page in pages.items() if page.next_cursor}
        next_cursors.update(stalled)
        total = sum(page.total or 0 for page in pages.values())
        page = SearchPage(
            items=merged[:limit],
            total=total,
            next_cursor=json.dumps(next_cursors, sort_keys=True) if next_cursors else None,
            source=names,
        )
        return page, warnings


class MetadataService:
    """Enrichment chain: route by id_kinds, fill-missing merge, cache results."""

    def __init__(self, registry: PluginRegistry, config: AppConfig, cache: Cache) -> None:
        self._registry = registry
        self._config = config
        self._cache = cache

    def enrich(self, paper: Paper, *, only_source: str | None = None) -> tuple[Paper, list[str]]:
        warnings: list[str] = []
        providers = [
            cast(MetadataProvider, p)
            for p in self._registry.list("metadata")
            if p.id_kinds & paper.identifiers.keys()
        ]
        priority = self._config.metadata.enrich_priority
        providers.sort(
            key=lambda p: (
                priority.index(p.meta.name) if p.meta.name in priority else len(priority),
                p.meta.name,
            )
        )
        if only_source is not None:
            providers = [p for p in providers if p.meta.name == only_source]
            if not providers:
                raise UsageError(
                    f"Metadata source {only_source!r} cannot handle identifiers "
                    f"{sorted(paper.identifiers)}"
                )
        if not providers:
            raise NotFoundError(
                "No metadata source accepts these identifiers",
                identifiers=paper.identifiers,
            )

        cache_key = (
            f"meta:v{SCHEMA_VERSION}:"
            + json.dumps(paper.identifiers, sort_keys=True)
            + f":{only_source}"
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            merged, merge_warnings = merge_papers(paper, Paper.model_validate(cached), source="")
            return merged, warnings + merge_warnings

        current = paper
        failures = 0
        for provider in providers:
            if is_complete(current):
                break
            try:
                incoming = provider.enrich(current)
            except ConfigError:
                raise  # misconfiguration must surface loudly (exit 5), not become a warning
            except PaperToolsError as exc:
                warnings.append(f"{provider.meta.name}: {exc.message}")
                failures += 1
                continue
            current, merge_warnings = merge_papers(current, incoming, source=provider.meta.name)
            warnings.extend(merge_warnings)

        if failures == len(providers):
            raise UpstreamError("All metadata sources failed", identifiers=paper.identifiers)
        if not current.title:
            raise NotFoundError("No metadata found", identifiers=paper.identifiers)
        self._cache.set(cache_key, current.model_dump(mode="json"), ttl=_METADATA_TTL)
        return current, warnings


class FetchService:
    """Full-text pipeline: locate -> rank -> download -> validate -> extract -> store."""

    def __init__(
        self,
        registry: PluginRegistry,
        config: AppConfig,
        cache: Cache,
        metadata: MetadataService,
    ) -> None:
        self._registry = registry
        self._config = config
        self._cache = cache
        self._metadata = metadata

    def fetch(
        self,
        identifier: str,
        *,
        fmt: ArtifactFormat = "pdf",
        out_dir: Path | None = None,
        locators: list[str] | None = None,
        downloader: str | None = None,
        extractor: str | None = None,
    ) -> tuple[FullText, list[str]]:
        ident = parse_identifier(identifier)
        stub = Paper(identifiers={ident.kind: ident.value})
        paper, warnings = self._metadata.enrich(stub)

        candidates = self._collect_candidates(paper, locators, warnings)
        attempts: list[str] = []
        for candidate in self._rank(candidates, fmt):
            if not self._format_compatible(candidate, fmt):
                continue
            artifact = self._cached_artifact(candidate, fmt)
            if artifact is None:
                artifact = self._download(candidate, downloader, attempts)
            if artifact is None:
                continue
            try:
                if artifact.downloader != "cache":
                    # cached artifacts are final products, validated before storing
                    self._validate(artifact)
                result = self._finalize(
                    paper, artifact, candidate, fmt, out_dir, extractor, warnings
                )
            except UpstreamError as exc:
                # validation/extraction failure: fall through to the next candidate.
                # ConfigError/UsageError (e.g. missing extractor) intentionally propagate.
                attempts.append(f"{candidate.url}: {exc.message}")
                continue
            return result, warnings + attempts

        landing_url = next((c.url for c in candidates if c.format == "landing"), None)
        raise FullTextUnavailableError(
            "No open-access full text could be retrieved.",
            oa_status=paper.oa_status,
            publisher_url=paper.publisher_url or landing_url,
            attempts=attempts,
        )

    def _collect_candidates(
        self, paper: Paper, locators: list[str] | None, warnings: list[str]
    ) -> list[FullTextCandidate]:
        names = locators if locators is not None else self._config.fetch.locators
        plugins = (
            [cast(Locator, self._registry.get("locator", name)) for name in names]
            if names
            else [cast(Locator, p) for p in self._registry.list("locator")]
        )
        seen: set[tuple[str, str]] = set()
        candidates: list[FullTextCandidate] = []
        # Links captured at search/enrich time seed the pool; locators still run
        # for fallback diversity (merge, not short-circuit).
        for link in paper.fulltext_links:
            key = (link.url, link.format)
            if key not in seen:
                seen.add(key)
                candidates.append(link)
        for loc in plugins:
            try:
                resolved = loc.resolve(paper)
            except PaperToolsError as exc:
                # includes ConfigError: a misconfigured locator must not block the
                # others (e.g. fetch works without unpaywall email); enrich stays strict.
                warnings.append(f"{loc.meta.name}: {exc.message}")
                continue
            for candidate in resolved:
                key = (candidate.url, candidate.format)
                if key not in seen:
                    seen.add(key)
                    candidates.append(candidate)
        return candidates

    def _rank(
        self, candidates: list[FullTextCandidate], fmt: ArtifactFormat
    ) -> list[FullTextCandidate]:
        def key(c: FullTextCandidate) -> tuple[int, int, int]:
            if fmt == "text":
                format_score = {"xml": 0, "text": 1, "pdf": 2}.get(c.format, 3)
            else:
                format_score = 0 if c.format == fmt else 1
            trust_score = (
                0 if c.locator in _TRUSTED_LOCATORS else 1 if c.locator == "unpaywall" else 2
            )
            license_score = 0 if c.license else 1
            return (format_score, trust_score, license_score)

        return sorted(candidates, key=key)

    @staticmethod
    def _format_compatible(candidate: FullTextCandidate, fmt: ArtifactFormat) -> bool:
        if candidate.format == "landing":
            return False
        if fmt == "text":
            return candidate.format in {"pdf", "xml", "text"}
        return candidate.format == fmt

    def _downloaders_for(
        self, candidate: FullTextCandidate, forced: str | None
    ) -> list[Downloader]:
        if forced is not None:
            dl = cast(Downloader, self._registry.get("downloader", forced))
            if candidate.format not in dl.formats or not dl.supports(candidate):
                raise UsageError(
                    f"Downloader {forced!r} does not support candidate {candidate.url}"
                )
            return [dl]
        downloaders = [
            cast(Downloader, d)
            for d in self._registry.list("downloader")
            if candidate.format in d.formats and d.supports(candidate)
        ]
        # specific downloaders before the generic http_direct fallback
        return sorted(downloaders, key=lambda d: d.meta.name == "http_direct")

    def _cached_artifact(
        self, candidate: FullTextCandidate, fmt: ArtifactFormat
    ) -> Artifact | None:
        mapping = self._cache.get(f"file:{candidate.url}:{fmt}")
        if not isinstance(mapping, dict):
            return None
        path = self._cache.get_file(mapping["sha256"], mapping["ext"])
        if path is None:
            return None
        stored_format = cast(ArtifactFormat, mapping.get("artifact_format", candidate.format))
        return Artifact(
            format=stored_format,
            content=path.read_bytes(),
            source_url=candidate.url,
            downloader="cache",
            license=candidate.license,
        )

    def _download(
        self, candidate: FullTextCandidate, forced: str | None, attempts: list[str]
    ) -> Artifact | None:
        for dl in self._downloaders_for(candidate, forced):
            try:
                return dl.download(candidate)
            except PaperToolsError as exc:
                attempts.append(f"{dl.meta.name}: {exc.message}")
            except Exception as exc:  # a broken plugin must not kill the fallback chain
                logger.exception("downloader %s crashed", dl.meta.name)
                attempts.append(f"{dl.meta.name}: unexpected error: {exc}")
        return None

    @staticmethod
    def _validate(artifact: Artifact) -> None:
        if artifact.format == "pdf" and (
            not artifact.content.startswith(b"%PDF") or len(artifact.content) < 1024
        ):
            raise UpstreamError("Downloaded content is not a valid PDF", url=artifact.source_url)
        elif artifact.format == "xml":
            try:
                # hardened parser: untrusted upstream XML (no entity expansion / XXE)
                root = safe_xml_fromstring(artifact.content)
            except (ET.ParseError, DefusedXmlException) as exc:
                raise UpstreamError(
                    "Downloaded content is not parseable XML", url=artifact.source_url
                ) from exc
            if root.tag.rsplit("}", 1)[-1] != "article":
                raise UpstreamError("XML is not a JATS article", url=artifact.source_url)
        elif artifact.format == "text" and not artifact.content.strip():
            raise UpstreamError("Downloaded text is empty", url=artifact.source_url)

    def _pick_extractor(self, source_format: str, forced: str | None) -> Extractor:
        if forced is not None:
            ext = cast(Extractor, self._registry.get("extractor", forced))
            if source_format not in ext.source_formats:
                raise UsageError(f"Extractor {forced!r} does not support {source_format!r} input")
            return ext
        available = [
            cast(Extractor, e)
            for e in self._registry.list("extractor")
            if source_format in e.source_formats
        ]
        if not available:
            hint = " Install the 'text' extra: uv tool install 'paper-tools[text]'."
            raise ConfigError(f"No extractor available for {source_format!r}.{hint}")
        preferred = _PREFERRED_EXTRACTORS.get(source_format)
        return sorted(available, key=lambda e: e.meta.name != preferred)[0]

    def _finalize(
        self,
        paper: Paper,
        artifact: Artifact,
        candidate: FullTextCandidate,
        fmt: ArtifactFormat,
        out_dir: Path | None,
        extractor_name: str | None,
        warnings: list[str],
    ) -> FullText:
        extractor_used: str | None = None
        extracted_from: ArtifactFormat | None = None
        if artifact.downloader == "cache":
            # stored bytes are already the final product (possibly extracted text);
            # restore provenance from the mapping instead of re-extracting.
            mapping = self._cache.get(f"file:{candidate.url}:{fmt}") or {}
            data = artifact.content
            ext = mapping.get("ext", artifact.format)
            extractor_used = mapping.get("extractor")
            extracted_from = mapping.get("extracted_from")
        elif fmt == "text" and artifact.format in {"pdf", "xml"}:
            extractor = self._pick_extractor(artifact.format, extractor_name)
            text = extractor.extract(artifact.content, source_format=artifact.format)
            data = text.encode("utf-8")
            ext = "txt"
            extractor_used = extractor.meta.name
            extracted_from = artifact.format
            if extractor_used == "pypdf":
                warnings.append("text extracted from PDF by pypdf; quality may be limited")
        else:
            data = artifact.content
            ext = artifact.format

        _, digest = self._cache.store_file(data, ext)
        self._cache.set(
            f"file:{candidate.url}:{fmt}",
            {
                "sha256": digest,
                "ext": ext,
                "artifact_format": fmt,
                "extractor": extractor_used,
                "extracted_from": extracted_from,
            },
            ttl=_FILEMAP_TTL,
        )
        target_dir = out_dir or Path(self._config.fetch.out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / f"{paper_slug(paper)}.{ext}"
        out_path.write_bytes(data)
        return FullText(
            paper=paper,
            format=fmt,
            path=out_path,
            sha256=digest,
            source_url=candidate.url,
            downloader=artifact.downloader,
            license=artifact.license or candidate.license or paper.license,
            extractor=extractor_used,
            extracted_from=extracted_from,
        )


@dataclass
class Services:
    config: AppConfig
    cache: Cache
    registry: PluginRegistry
    metadata: MetadataService = field(init=False)
    search: SearchService = field(init=False)
    fetch: FetchService = field(init=False)

    def __post_init__(self) -> None:
        self.metadata = MetadataService(self.registry, self.config, self.cache)
        self.search = SearchService(self.registry, self.config, self.metadata)
        self.fetch = FetchService(self.registry, self.config, self.cache, self.metadata)
