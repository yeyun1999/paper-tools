"""Application services: search, metadata enrichment chain, full-text pipeline."""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

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
    DownloadedFullText,
    ExtractedFullText,
    FullText,
    FullTextCandidate,
    FullTextLinks,
    Paper,
    SearchPage,
    is_complete,
    merge_candidate,
    merge_papers,
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
_METADATA_CACHE_VERSION = 2
_FILEMAP_TTL = 30 * 86400
_TRUSTED_LOCATORS = {"europepmc", "pmc_oa"}
_PREFERRED_EXTRACTORS = {"xml": "jats", "pdf": "pypdf"}
_OUTPUT_EXTENSIONS: dict[str, ArtifactFormat] = {
    ".pdf": "pdf",
    ".xml": "xml",
    ".txt": "text",
}
_FORMAT_EXTENSIONS: dict[ArtifactFormat, str] = {"pdf": ".pdf", "xml": ".xml", "text": ".txt"}
_ID_OUTPUT_PRIORITY = ("doi", "pmid", "pmcid", "openalex", "s2", "arxiv", "url")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _filename_slug(value: str, *, max_bytes: int = 160) -> str:
    """Convert text into a portable filename component.

    Args:
        value: Text to sanitize, typically a paper title or identifier.
        max_bytes: Maximum UTF-8 byte length before extension appending.

    Returns:
        A non-empty, Windows-safe slug without path separators.
    """
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip(" ._-") or "paper"
    value = value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore").rstrip(" ._-")
    value = value or "paper"
    if value.partition(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        value = f"_{value}"
    return value


_MULTI_CURSOR_PREFIX = "ms1."
# Percent-style escaping is applied to the cursor values only; the order
# matters (escape % first, unescape % last) so literal "%3A" survives round-trips.
_CURSOR_ESCAPES = (("%", "%25"), (":", "%3A"), (",", "%2C"))


def _escape_cursor(value: str) -> str:
    """Escape cursor separators for use in a multi-source cursor token.

    Args:
        value: Raw source cursor value.

    Returns:
        The value with percent, colon, and comma characters escaped.
    """
    for raw, encoded in _CURSOR_ESCAPES:
        value = value.replace(raw, encoded)
    return value


def _unescape_cursor(value: str) -> str:
    """Reverse escaping of a multi-source cursor value.

    Args:
        value: Escaped source cursor value.

    Returns:
        The original cursor value.
    """
    for raw, encoded in reversed(_CURSOR_ESCAPES):
        value = value.replace(encoded, raw)
    return value


def encode_multi_cursor(cursors: dict[str, str]) -> str:
    """Aggregated cursor wire format: ``ms1.name:cursor,name:cursor`` (sorted).

    Shell-safe by construction: plugin names are registry-validated and
    cursor values are escaped, so the token never needs nested quoting.

    Args:
        cursors: Mapping of source names to their opaque next-page cursors.

    Returns:
        An encoded multi-source cursor token.
    """
    body = ",".join(f"{name}:{_escape_cursor(value)}" for name, value in sorted(cursors.items()))
    return _MULTI_CURSOR_PREFIX + body


def decode_multi_cursor(cursor: str) -> dict[str, str]:
    """Parse an ``ms1.`` token; legacy JSON ``{source: cursor}`` objects still work.

    Args:
        cursor: Encoded multi-source cursor or legacy JSON object string.

    Returns:
        Mapping of source names to decoded opaque cursors.

    Raises:
        UsageError: If the token is malformed or is not a JSON object.
    """
    if cursor.startswith(_MULTI_CURSOR_PREFIX):
        body = cursor[len(_MULTI_CURSOR_PREFIX) :]
        if not body:
            raise UsageError("Multi-source cursor has no entries after the 'ms1.' prefix.")
        cursors: dict[str, str] = {}
        for segment in body.split(","):
            name, sep, value = segment.partition(":")
            if not sep or not name or not value:
                raise UsageError(f"Malformed multi-source cursor segment: {segment!r}.")
            cursors[name] = _unescape_cursor(value)
        return cursors
    try:
        decoded = json.loads(cursor)
    except ValueError as exc:
        raise UsageError(
            "Multi-source cursor must be the 'ms1.' next_cursor from a previous "
            "multi-source page (a legacy JSON object is also accepted)."
        ) from exc
    if not isinstance(decoded, dict):
        raise UsageError("Multi-source cursor must be an 'ms1.' token or a JSON object.")
    return {str(k): str(v) for k, v in decoded.items()}


class SearchService:
    def __init__(
        self, registry: PluginRegistry, config: AppConfig, metadata: MetadataService
    ) -> None:
        """Initialize the search service.

        Args:
            registry: Registry used to resolve searcher plugins.
            config: Application configuration, including the default source.
            metadata: Service used for optional result enrichment.
        """
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
        """Search one or more sources and optionally enrich the results.

        Args:
            query: Parsed literature search query.
            sources: Searcher plugin names; defaults to the configured source.
            limit: Maximum results requested from each source.
            cursor: Opaque next-page cursor from a previous response.
            enrich: Whether to fill missing metadata through ``MetadataService``.

        Returns:
            A tuple containing the search page and non-fatal warning messages.

        Raises:
            UsageError: If a requested plugin is unavailable.
            UpstreamError: If every source in a multi-source search fails.
        """
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
                enriched, item_warnings = self._metadata.enrich(item, cache_result=False)
                items.append(enriched)
                warnings.extend(item_warnings)
            page = page.model_copy(update={"items": items})
        return page, warnings

    @staticmethod
    def _dedup_key(paper: Paper) -> tuple[str, str] | None:
        """Build the best available key for deduplicating a paper.

        Args:
            paper: Paper to identify.

        Returns:
            A DOI, PMID, or normalized-title key, or ``None`` if none is usable.
        """
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

        ``limit`` caps each source's request only; the deduped merge is
        returned in full (a page may exceed ``limit``).

        The aggregated cursor is an escape-free ``ms1.name:cursor,...`` token;
        sources absent from it are exhausted. Dedup is per page (stateless
        across pages). ``total`` is the pre-dedup sum of per-source totals
        (approximate).

        Args:
            query: Parsed literature search query.
            searchers: Source names paired with their searcher plugins.
            limit: Maximum results requested from each active source.
            cursor: Aggregated cursor selecting sources that remain active.

        Returns:
            A deduplicated, interleaved page and non-fatal warnings.

        Raises:
            UsageError: If the aggregated cursor is malformed.
            UpstreamError: If every active source fails.
        """
        cursors: dict[str, str] = {}
        if cursor is not None:
            cursors = decode_multi_cursor(cursor)
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
            items=merged,
            total=total,
            next_cursor=encode_multi_cursor(next_cursors) if next_cursors else None,
            source=names,
        )
        return page, warnings


class MetadataService:
    """Enrichment chain: route by id_kinds, fill-missing merge, cache results."""

    def __init__(self, registry: PluginRegistry, config: AppConfig, cache: Cache) -> None:
        """Initialize the metadata enrichment service.

        Args:
            registry: Registry used to resolve metadata providers.
            config: Application configuration, including provider priority.
            cache: Cache used to reuse enriched metadata.
        """
        self._registry = registry
        self._config = config
        self._cache = cache

    def enrich(
        self, paper: Paper, *, only_source: str | None = None, cache_result: bool = True
    ) -> tuple[Paper, list[str]]:
        """Fill missing paper metadata using compatible providers.

        Providers run in configured priority order and stop once the title and
        abstract are present. Cached results are merged without overwriting
        values already supplied by the caller.

        Args:
            paper: Paper whose identifiers seed the enrichment chain.
            only_source: Restrict the chain to one metadata provider.
            cache_result: Whether a newly enriched result may be written to the cache.

        Returns:
            The enriched paper and non-fatal warning messages.

        Raises:
            UsageError: If ``only_source`` cannot handle the paper's identifiers.
            ConfigError: If a provider reports invalid configuration.
            NotFoundError: If no provider accepts the identifiers or no title is found.
            UpstreamError: If all eligible providers fail.
        """
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
            f"meta:v{SCHEMA_VERSION}:{_METADATA_CACHE_VERSION}:"
            + json.dumps(paper.identifiers, sort_keys=True)
            + f":{only_source}"
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            merged, merge_warnings = merge_papers(paper, Paper.model_validate(cached), source="")
            return merged, warnings + merge_warnings

        current = paper
        cache_value = Paper(identifiers=dict(paper.identifiers))
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
            cache_value, _ = merge_papers(cache_value, incoming, source=provider.meta.name)
            warnings.extend(merge_warnings)

        if failures == len(providers):
            raise UpstreamError("All metadata sources failed", identifiers=paper.identifiers)
        if not current.title:
            raise NotFoundError("No metadata found", identifiers=paper.identifiers)
        if cache_result and cache_value.title:
            self._cache.set(cache_key, cache_value.model_dump(mode="json"), ttl=_METADATA_TTL)
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
        """Initialize the full-text pipeline.

        Args:
            registry: Registry used to resolve locator, downloader, and extractor plugins.
            config: Application configuration, including default locators and output.
            cache: Cache for artifacts and output-file mappings.
            metadata: Service used to resolve identifiers and enrich paper metadata.
        """
        self._registry = registry
        self._config = config
        self._cache = cache
        self._metadata = metadata

    def _locate(
        self, identifier: str, locators: list[str] | None
    ) -> tuple[Paper, list[FullTextCandidate], list[str]]:
        """Resolve an identifier and collect full-text candidates.

        Args:
            identifier: DOI, PMID, PMCID, or other identifier accepted by the parser.
            locators: Locator plugin names, or ``None`` to use configured locators.

        Returns:
            The enriched paper, deduplicated candidates, and non-fatal warnings.

        Raises:
            UsageError: If the identifier or plugin selection is invalid.
            NotFoundError: If metadata cannot be resolved.
            UpstreamError: If metadata enrichment fails.
        """
        ident = parse_identifier(identifier)
        stub = Paper(identifiers={ident.kind: ident.value})
        paper, warnings = self._metadata.enrich(stub)
        return paper, self._collect_candidates(paper, locators, warnings), warnings

    def locate(
        self,
        identifier: str,
        *,
        fmt: ArtifactFormat | None = None,
        locators: list[str] | None = None,
    ) -> tuple[FullTextLinks, list[str]]:
        """Find and rank open-access full-text locations without downloading them.

        Args:
            identifier: Paper identifier accepted by ``parse_identifier``.
            fmt: Required output format; landing-page candidates are always excluded.
            locators: Locator plugin names, or ``None`` to use configured locators.

        Returns:
            Paper metadata, ranked candidates, and non-fatal warnings.

        Raises:
            UsageError: If the identifier or plugin selection is invalid.
            NotFoundError: If metadata cannot be resolved.
            UpstreamError: If metadata enrichment fails.
        """
        paper, candidates, warnings = self._locate(identifier, locators)
        if fmt is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.format != "landing" and self._format_compatible(candidate, fmt)
            ]
        return (
            FullTextLinks(paper=paper, candidates=self._rank(candidates, fmt or "pdf")),
            warnings,
        )

    def fetch(
        self,
        identifier: str,
        *,
        fmt: ArtifactFormat | None = None,
        output: Path | None = None,
        locators: list[str] | None = None,
        downloader: str | None = None,
        extractor: str | None = None,
    ) -> tuple[FullText, list[str]]:
        """Retrieve, validate, optionally extract, and store a paper's full text.

        Ranked candidates are tried until one succeeds. ``text`` output can be
        extracted from PDF, XML, or text artifacts; other formats require an
        exact format match. Reusable results may be served from cache.

        Args:
            identifier: Paper identifier accepted by ``parse_identifier``.
            fmt: Desired output format; defaults to PDF unless inferred elsewhere.
            output: Explicit output file or configured output path override.
            locators: Locator plugin names, or ``None`` to use configured locators.
            downloader: Force one downloader plugin instead of candidate recommendations.
            extractor: Force one extractor plugin for conversion to text.

        Returns:
            The stored full-text record, warnings, and failed-attempt messages.

        Raises:
            UsageError: If an argument, output path, or forced plugin is invalid.
            ConfigError: If no suitable extractor is installed or configured.
            FullTextUnavailableError: If no candidate can be retrieved successfully.
            UpstreamError: If metadata enrichment fails.
        """
        output_path, artifact_format = self._resolve_output(fmt, output)
        paper, candidates, warnings = self._locate(identifier, locators)
        if output_path is None:
            output_path = self._default_output(
                paper, artifact_format, parse_identifier(identifier).value
            )

        attempts: list[str] = []
        use_cache = downloader is None and not (artifact_format == "text" and extractor is not None)
        for candidate in self._rank(candidates, artifact_format):
            if not self._format_compatible(candidate, artifact_format):
                continue
            artifact = self._cached_artifact(candidate, artifact_format) if use_cache else None
            if artifact is None:
                artifact = self._download(candidate, downloader, attempts)
            if artifact is None:
                continue
            try:
                if artifact.downloader != "cache":
                    # cached artifacts are final products, validated before storing
                    self._validate(artifact)
                result = self._finalize(
                    paper, artifact, candidate, artifact_format, output_path, extractor, warnings
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

    def download(
        self,
        url: str,
        *,
        fmt: ArtifactFormat | None = None,
        output: Path | None = None,
        downloader: str | None = None,
    ) -> tuple[DownloadedFullText, list[str]]:
        """Download and validate a full-text file from an explicit HTTP(S) URL.

        The format is taken from ``fmt``, then the output extension, then the
        URL extension. Without ``output``, a filename is derived from the URL.

        Args:
            url: Absolute HTTP or HTTPS URL of the full-text file.
            fmt: Explicit artifact format, otherwise inferred when possible.
            output: Destination path; defaults to a filename in the current directory.
            downloader: Force one downloader plugin instead of recommendations.

        Returns:
            The stored download record and failed-attempt messages.

        Raises:
            UsageError: If the URL, format, output path, or downloader is invalid.
            UpstreamError: If download or content validation fails.
        """
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise UsageError(f"Expected an HTTP(S) full-text URL, got {url!r}.")
        if fmt is None and output is not None:
            fmt = _OUTPUT_EXTENSIONS.get(output.suffix.lower())
        if fmt is None:
            fmt = _OUTPUT_EXTENSIONS.get(Path(parsed.path).suffix.lower())
        if output is None:
            if fmt is None:
                raise UsageError(
                    "Cannot infer the download format from the URL; "
                    "specify --format pdf, xml, or text."
                )
            stem = Path(parsed.path).stem or "fulltext"
            output = Path(f"{_filename_slug(stem)}{_FORMAT_EXTENSIONS[fmt]}")
        output_path, artifact_format = self._resolve_output(fmt, output)
        output_path = cast(Path, output_path)
        candidate = FullTextCandidate(url=url, format=artifact_format, locator=["user"])
        candidate.downloaders = self._recommended_downloader_names(candidate)
        attempts: list[str] = []
        artifact = self._download(candidate, downloader, attempts)
        if artifact is None:
            raise UpstreamError(
                "All downloaders failed for the full-text URL.",
                url=url,
                attempts=attempts,
            )
        self._validate(artifact)
        digest = self._store_output(artifact.content, artifact.format, output_path)
        self._cache.set(
            f"file:{candidate.url}:{artifact_format}",
            {
                "sha256": digest,
                "ext": artifact.format,
                "artifact_format": artifact_format,
                "extractor": None,
                "extracted_from": None,
            },
            ttl=_FILEMAP_TTL,
        )
        return (
            DownloadedFullText(
                source_url=url,
                format=artifact_format,
                path=output_path,
                sha256=digest,
                downloader=artifact.downloader,
                license=artifact.license,
            ),
            attempts,
        )

    def extract(
        self,
        source: Path,
        *,
        output: Path | None = None,
        extractor: str | None = None,
    ) -> tuple[ExtractedFullText, list[str]]:
        """Extract UTF-8 text from a local PDF or JATS XML file.

        Args:
            source: Existing ``.pdf`` or ``.xml`` input file.
            output: Destination text file; defaults to ``source`` with a ``.txt`` suffix.
            extractor: Force one extractor plugin instead of the preferred extractor.

        Returns:
            The extraction record and non-fatal warning messages.

        Raises:
            UsageError: If the input or output path, extension, or extractor is invalid.
            ConfigError: If no suitable extractor is installed or configured.
            UpstreamError: If input validation or text extraction fails.
        """
        if not source.is_file():
            raise UsageError(f"Input file not found: {source}")
        source_format = _OUTPUT_EXTENSIONS.get(source.suffix.lower())
        if source_format not in {"pdf", "xml"}:
            raise UsageError(
                f"Unsupported input extension {source.suffix!r}; expected .pdf or .xml."
            )
        output_path, _ = self._resolve_output("text", output or source.with_suffix(".txt"))
        output_path = cast(Path, output_path)
        artifact = Artifact(
            format=cast(ArtifactFormat, source_format),
            content=source.read_bytes(),
            source_url=source.resolve().as_uri(),
            downloader="local",
        )
        self._validate(artifact)
        warnings: list[str] = []
        data, ext, extractor_name, extracted_from = self._extract_text(
            artifact, extractor, warnings
        )
        digest = self._store_output(data, ext, output_path)
        return (
            ExtractedFullText(
                source_path=source,
                source_format=extracted_from,
                path=output_path,
                sha256=digest,
                extractor=extractor_name,
            ),
            warnings,
        )

    def _store_output(self, data: bytes, ext: str, output_path: Path) -> str:
        """Store content by digest and write it to the requested output path.

        Args:
            data: Final file content.
            ext: Extension without a leading dot, such as ``pdf`` or ``txt``.
            output_path: Destination path, whose parent directories are created.

        Returns:
            The SHA-256 digest of the content.
        """
        _, digest = self._cache.store_file(data, ext)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return digest

    def _resolve_output(
        self, fmt: ArtifactFormat | None, output: Path | None
    ) -> tuple[Path | None, ArtifactFormat]:
        """Resolve the final output path and validate its format.

        Args:
            fmt: Explicit format, which must agree with a recognized output suffix.
            output: Explicit path, configured path, or ``None`` for automatic naming.

        Returns:
            The resolved path (or ``None``) and effective artifact format.

        Raises:
            UsageError: If the path is a directory or its extension conflicts with the format.
        """
        configured_output = self._config.fetch.output
        output_path = output or (Path(configured_output) if configured_output else None)
        if output_path is None:
            return None, fmt or "pdf"
        if output_path.exists() and output_path.is_dir():
            raise UsageError(f"Output path is a directory: {output_path}")
        suffix = output_path.suffix.lower()
        inferred_format = _OUTPUT_EXTENSIONS.get(suffix)
        if suffix and inferred_format is None:
            raise UsageError(
                f"Unsupported output extension {suffix!r}; expected .pdf, .xml, or .txt."
            )
        artifact_format = fmt or inferred_format or "pdf"
        if inferred_format is not None and inferred_format != artifact_format:
            raise UsageError(
                f"Output extension {suffix!r} implies format {inferred_format!r}, "
                f"but --format is {artifact_format!r}."
            )
        if not suffix:
            output_path = output_path.with_suffix(_FORMAT_EXTENSIONS[artifact_format])
        return output_path, artifact_format

    def _default_output(self, paper: Paper, fmt: ArtifactFormat, fallback_id: str) -> Path:
        """Choose a title-based output filename without overwriting an existing file.

        Args:
            paper: Paper supplying the title and preferred identifiers.
            fmt: Output format used to select the extension.
            fallback_id: Identifier used when the paper has no preferred identifier.

        Returns:
            A title-only path, or a title-and-identifier path on collision.
        """
        title_slug = _filename_slug(paper.title or "paper")
        extension = _FORMAT_EXTENSIONS[fmt]
        output_path = Path(f"{title_slug}{extension}")
        if not output_path.exists():
            return output_path
        identifier = next(
            (
                paper.identifiers[kind]
                for kind in _ID_OUTPUT_PRIORITY
                if paper.identifiers.get(kind)
            ),
            fallback_id,
        )
        return Path(f"{title_slug}_{_filename_slug(identifier, max_bytes=80)}{extension}")

    def _collect_candidates(
        self, paper: Paper, locators: list[str] | None, warnings: list[str]
    ) -> list[FullTextCandidate]:
        """Collect and deduplicate full-text candidates from metadata and locators.

        Existing paper links seed the pool. Configured or selected locators then
        contribute fallback candidates, and downloader recommendations are filled
        in for every result.

        Args:
            paper: Enriched paper with optional existing full-text links.
            locators: Locator names; ``None`` uses configuration, while an empty
                list enables every registered locator.
            warnings: Mutable list to which non-fatal locator errors are appended.

        Returns:
            Candidates deduplicated by URL and format.

        Raises:
            UsageError: If a requested locator plugin is unavailable.
        """
        names = locators if locators is not None else self._config.fetch.locators
        plugins = (
            [cast(Locator, self._registry.get("locator", name)) for name in names]
            if names
            else [cast(Locator, p) for p in self._registry.list("locator")]
        )
        collected: dict[tuple[str, str], FullTextCandidate] = {}

        def add(candidate: FullTextCandidate) -> None:
            """Add a candidate or merge it with an existing URL/format match.

            Args:
                candidate: Candidate to insert into the collection.
            """
            key = (candidate.url, candidate.format)
            if key in collected:
                collected[key] = merge_candidate(collected[key], candidate)
            else:
                collected[key] = candidate.model_copy(deep=True)

        # Links captured at search/enrich time seed the pool; locators still run
        # for fallback diversity (merge, not short-circuit).
        for link in paper.fulltext_links:
            add(link)
        for loc in plugins:
            try:
                resolved = loc.resolve(paper)
            except PaperToolsError as exc:
                # includes ConfigError: a misconfigured locator must not block the
                # others (e.g. fetch works without unpaywall email); enrich stays strict.
                warnings.append(f"{loc.meta.name}: {exc.message}")
                continue
            for candidate in resolved:
                add(candidate)
        candidates = list(collected.values())
        for candidate in candidates:
            if not candidate.downloaders:
                candidate.downloaders = self._recommended_downloader_names(candidate)
        return candidates

    def _rank(
        self, candidates: list[FullTextCandidate], fmt: ArtifactFormat
    ) -> list[FullTextCandidate]:
        """Sort candidates by format fit, locator trust, and license availability.

        For text output, XML ranks before text and PDF. Trusted locators rank
        ahead of Unpaywall and other sources; candidates with a known license
        rank ahead of those without one. Original order breaks ties.

        Args:
            candidates: Candidates to rank.
            fmt: Requested output format.

        Returns:
            A new list ordered from most to least preferred.
        """

        def key(c: FullTextCandidate) -> tuple[int, int, int]:
            """Build the format, trust, and license sort key for a candidate.

            Args:
                c: Candidate to score.

            Returns:
                A tuple where lower values indicate higher preference.
            """
            if fmt == "text":
                format_score = {"xml": 0, "text": 1, "pdf": 2}.get(c.format, 3)
            else:
                format_score = 0 if c.format == fmt else 1
            locators = set(c.locator)
            trust_score = 0 if locators & _TRUSTED_LOCATORS else 1 if "unpaywall" in locators else 2
            license_score = 0 if c.license else 1
            return (format_score, trust_score, license_score)

        return sorted(candidates, key=key)

    @staticmethod
    def _format_compatible(candidate: FullTextCandidate, fmt: ArtifactFormat) -> bool:
        """Check whether a candidate can satisfy the requested output format.

        Args:
            candidate: Candidate whose artifact format is checked.
            fmt: Requested output format.

        Returns:
            ``True`` for exact matches, or for PDF, XML, and text candidates
            when text output is requested. Landing pages are never compatible.
        """
        if candidate.format == "landing":
            return False
        if fmt == "text":
            return candidate.format in {"pdf", "xml", "text"}
        return candidate.format == fmt

    def _matching_downloaders(self, candidate: FullTextCandidate) -> list[Downloader]:
        """Find downloaders that support a candidate's format and URL.

        Args:
            candidate: Full-text candidate to download.

        Returns:
            Matching downloaders, with specific plugins before ``http_direct``.
        """
        downloaders = [
            cast(Downloader, d)
            for d in self._registry.list("downloader")
            if candidate.format in d.formats and d.supports(candidate)
        ]
        # specific downloaders before the generic http_direct fallback
        return sorted(downloaders, key=lambda d: d.meta.name == "http_direct")

    def _recommended_downloader_names(self, candidate: FullTextCandidate) -> list[str]:
        """List downloader plugin names suitable for a candidate.

        Args:
            candidate: Full-text candidate to download.

        Returns:
            Recommended plugin names in fallback order.
        """
        return [downloader.meta.name for downloader in self._matching_downloaders(candidate)]

    def _downloaders_for(
        self, candidate: FullTextCandidate, forced: str | None
    ) -> list[Downloader]:
        """Resolve the downloader fallback chain for a candidate.

        Args:
            candidate: Full-text candidate to download.
            forced: Optional plugin name that disables automatic fallback.

        Returns:
            Available, compatible downloaders in attempt order.

        Raises:
            UsageError: If the forced plugin is unavailable or incompatible.
        """
        if forced is not None:
            dl = cast(Downloader, self._registry.get("downloader", forced))
            if candidate.format not in dl.formats or not dl.supports(candidate):
                raise UsageError(
                    f"Downloader {forced!r} does not support candidate {candidate.url}"
                )
            return [dl]
        names = candidate.downloaders or self._recommended_downloader_names(candidate)
        downloaders: list[Downloader] = []
        for name in dict.fromkeys(names):
            try:
                downloader = cast(Downloader, self._registry.get("downloader", name))
            except UsageError:
                continue
            if candidate.format in downloader.formats and downloader.supports(candidate):
                downloaders.append(downloader)
        return downloaders

    def _cached_artifact(
        self, candidate: FullTextCandidate, fmt: ArtifactFormat
    ) -> Artifact | None:
        """Load a previously stored final artifact for a URL and output format.

        Args:
            candidate: Candidate whose cached file mapping is looked up.
            fmt: Requested final artifact format.

        Returns:
            Cached content marked with downloader ``cache``, or ``None`` on a miss.
        """
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
        """Try compatible downloaders until one returns an artifact.

        Args:
            candidate: Full-text candidate to download.
            forced: Optional plugin name that disables automatic fallback.
            attempts: Mutable list to which downloader failures are appended.

        Returns:
            The first downloaded artifact, or ``None`` if every downloader fails.

        Raises:
            UsageError: If the forced plugin is unavailable or incompatible.
        """
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
        """Validate downloaded content before extraction or storage.

        PDFs must have a PDF signature and at least 1 KiB of content. XML must
        parse safely and have an ``article`` root element. Text must be non-empty.

        Args:
            artifact: Downloaded artifact to validate.

        Raises:
            UpstreamError: If the content does not match its declared format.
        """
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
        """Select an extractor compatible with the source artifact format.

        Args:
            source_format: Format of the artifact to extract.
            forced: Optional plugin name; otherwise the preferred extractor is used.

        Returns:
            The selected extractor plugin.

        Raises:
            UsageError: If the forced plugin is unavailable or incompatible.
            ConfigError: If no compatible extractor is installed.
        """
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

    def _extract_text(
        self,
        artifact: Artifact,
        extractor_name: str | None,
        warnings: list[str],
    ) -> tuple[bytes, str, str, Literal["pdf", "xml"]]:
        """Extract non-empty text and encode it as UTF-8.

        Args:
            artifact: Validated PDF or XML artifact.
            extractor_name: Optional extractor plugin name.
            warnings: Mutable list for quality warnings, including PDF extraction caveats.

        Returns:
            UTF-8 bytes, ``txt`` extension, extractor name, and source format.

        Raises:
            UsageError: If the requested extractor is unavailable or incompatible.
            ConfigError: If no compatible extractor is installed.
            UpstreamError: If the extractor produces empty text.
        """
        extractor = self._pick_extractor(artifact.format, extractor_name)
        text = extractor.extract(artifact.content, source_format=artifact.format)
        if not text.strip():
            raise UpstreamError("Extractor produced empty text", url=artifact.source_url)
        if extractor.meta.name == "pypdf":
            warnings.append("text extracted from PDF by pypdf; quality may be limited")
        return (
            text.encode("utf-8"),
            "txt",
            extractor.meta.name,
            cast(Literal["pdf", "xml"], artifact.format),
        )

    def _finalize(
        self,
        paper: Paper,
        artifact: Artifact,
        candidate: FullTextCandidate,
        fmt: ArtifactFormat,
        output_path: Path,
        extractor_name: str | None,
        warnings: list[str],
    ) -> FullText:
        """Finalize an artifact, write the output, and record reusable provenance.

        Cached artifacts are already final products and are not re-extracted.
        Fresh PDF or XML artifacts are converted when text output is requested.

        Args:
            paper: Metadata associated with the full text.
            artifact: Downloaded or cached artifact.
            candidate: Candidate that supplied the artifact URL and license.
            fmt: Requested final output format.
            output_path: Destination path for the final content.
            extractor_name: Optional extractor plugin name for text conversion.
            warnings: Mutable list for extraction warnings.

        Returns:
            A full-text record containing paths, digests, and provenance.

        Raises:
            UsageError: If the requested extractor is unavailable or incompatible.
            ConfigError: If no compatible extractor is installed.
            UpstreamError: If text extraction fails.
        """
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
            data, ext, extractor_used, extracted_from = self._extract_text(
                artifact, extractor_name, warnings
            )
        else:
            data = artifact.content
            ext = artifact.format

        digest = self._store_output(data, ext, output_path)
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
        return FullText(
            paper=paper,
            format=fmt,
            path=output_path,
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
        """Construct metadata, search, and fetch services from shared dependencies."""
        self.metadata = MetadataService(self.registry, self.config, self.cache)
        self.search = SearchService(self.registry, self.config, self.metadata)
        self.fetch = FetchService(self.registry, self.config, self.cache, self.metadata)
