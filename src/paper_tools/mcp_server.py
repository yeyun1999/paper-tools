"""MCP server (stdio) exposing the CLI services to AI assistants.

Requires the ``mcp`` extra. Tools return the same JSON envelopes as
``paper-tools --json`` (schema_version 1.3), so agents can share one contract
across the shell and MCP channels.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast

from pydantic import Field, ValidationError

from paper_tools import __version__
from paper_tools.cli import context, render
from paper_tools.cli.context import GlobalOpts
from paper_tools.core.errors import PaperToolsError, UsageError
from paper_tools.core.models import ArtifactFormat, Paper, parse_identifier
from paper_tools.core.query import Query

if TYPE_CHECKING:
    from mcp.server.mcpserver import MCPServer

_INSTRUCTIONS = """\
Literature search and open-access full-text retrieval for biomedical research.

Typical flow: search_papers -> get_paper (full metadata) -> locate_fulltext
(inspect OA candidates) -> fetch_fulltext (pdf / xml / text). Only official APIs
and open-access copies are used; closed-access papers return an error envelope
with code FULLTEXT_UNAVAILABLE and a publisher link instead of full text.

Every tool returns a JSON object: on success {schema_version, command, data,
warnings}; on failure {schema_version, error: {code, message, details}}.
Error codes: USAGE (bad input), UPSTREAM (network/API failure, retry later),
FULLTEXT_UNAVAILABLE (no OA copy; give the user the publisher link),
CONFIG (missing configuration, e.g. plugins.unpaywall.email).
"""


def _import_mcp() -> type[MCPServer[Any]]:
    """Import the SDK lazily so the core CLI works without the extra."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise UsageError(
            "MCP support requires the 'mcp' extra. "
            "Install with: uv sync --extra mcp (or: pip install 'paper-tools[mcp]')."
        ) from exc
    return MCPServer


def build_server(opts: GlobalOpts | None = None) -> MCPServer[Any]:
    """Construct the MCPServer with the five paper-tools tools registered."""
    mcp_server_cls = _import_mcp()
    opts = opts or GlobalOpts()
    services = context.build_services(opts)

    server = mcp_server_cls(
        name="paper-tools",
        version=__version__,
        instructions=_INSTRUCTIONS,
        log_level="WARNING",
    )

    def _failure(exc: PaperToolsError) -> dict[str, Any]:
        return render.error_envelope(exc)

    # Mirror the CLI help: list installed plugin names per role and show
    # resolved config values (not config key names) as defaults.
    def _available(role: str) -> str:
        return ", ".join(services.registry.names(role)) or "(none)"

    default_source = services.config.general.default_source
    default_locators = ", ".join(services.config.fetch.locators) or "all"
    default_output = services.config.fetch.output or "safe article title in the current directory"
    default_search_fields = ",".join(services.config.output.search_fields) or "all"
    default_get_fields = ",".join(services.config.output.get_fields) or "all"

    @server.tool(
        description=(
            "Search literature. Returns a SearchPage envelope (items may be stubs; "
            "set enrich=true for full metadata). Supports pagination via cursor."
        )
    )
    def search_papers(
        query: Annotated[str | None, Field(description="Free-text query.")] = None,
        source: str | None = Field(
            default=None,
            description=(
                "Search plugin(s), comma-separated; 'all' searches every source "
                f"with dedup (default: {default_source}). Available: {_available('searcher')}."
            ),
        ),
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=100,
                description=(
                    "Per-source result cap (1-100). Single-source pages return at most "
                    "this many; multi-source merges all deduped hits and may exceed it."
                ),
            ),
        ] = 20,
        cursor: Annotated[
            str | None,
            Field(
                description=(
                    "Pagination cursor from a previous data.next_cursor (multi-source: "
                    "'ms1.' token, pass back verbatim; legacy JSON object also accepted)."
                )
            ),
        ] = None,
        author: Annotated[str | None, Field(description="Author name filter.")] = None,
        journal: Annotated[str | None, Field(description="Journal name filter.")] = None,
        year_from: Annotated[int | None, Field(description="Publication year lower bound.")] = None,
        year_to: Annotated[int | None, Field(description="Publication year upper bound.")] = None,
        oa_only: Annotated[bool, Field(description="Restrict to open-access papers.")] = False,
        raw: Annotated[
            str | None, Field(description="Native engine query (not portable; exclusive).")
        ] = None,
        enrich: Annotated[bool, Field(description="Run the metadata enrichment chain.")] = False,
        fields: str | None = Field(
            default=None,
            description=(
                "Comma-separated Paper field paths; use 'identifiers.doi' for objects and "
                "'authors[].name' for arrays; 'all' returns every field and requires full "
                "enrichment "
                f"(default: {default_search_fields})."
            ),
        ),
    ) -> dict[str, Any]:
        try:
            try:
                q = Query(
                    text=query,
                    author=author,
                    journal=journal,
                    year_from=year_from,
                    year_to=year_to,
                    open_access=True if oa_only else None,
                    raw=raw,
                )
            except ValidationError as exc:
                raise UsageError(str(exc)) from exc
            source_names = (
                [name.strip() for name in source.split(",") if name.strip()] if source else None
            )
            if source_names is not None and "all" in source_names:
                source_names = services.registry.names("searcher")
            selected_fields = render.resolve_output_fields(
                fields, services.config.output.search_fields
            )
            page, warnings = services.search.search(
                q,
                sources=source_names,
                limit=limit,
                cursor=cursor,
                enrich=enrich,
                required_fields=render.enrichment_fields(selected_fields) if enrich else None,
            )
        except PaperToolsError as exc:
            return _failure(exc)
        warnings = services.registry.load_warnings + warnings
        try:
            data = page.model_dump(mode="json")
            if selected_fields is not None:
                data["items"] = [
                    render.filter_fields(item, selected_fields) for item in data["items"]
                ]
        except PaperToolsError as exc:
            return _failure(exc)
        return render.success_envelope("search", data, warnings)

    @server.tool(
        description=(
            "Fetch complete metadata for one paper via the enrichment chain. "
            "Identifier: doi:/pmid:/pmcid:/openalex:/s2:/arxiv: prefixed ID or bare DOI."
        )
    )
    def get_paper(
        identifier: Annotated[
            str,
            Field(
                description=(
                    "doi:/pmid:/pmcid:/openalex:/s2:/arxiv: prefixed ID, DOI URL, "
                    "or bare DOI (e.g. doi:10.1038/... or pmid:38308006)."
                )
            ),
        ],
        source: str | None = Field(
            default=None,
            description=(
                f"Restrict enrichment to one metadata plugin. Available: {_available('metadata')}."
            ),
        ),
        fields: str | None = Field(
            default=None,
            description=(
                "Comma-separated Paper field paths; use 'identifiers.doi' for objects and "
                "'authors[].name' for arrays; 'all' returns every field and requires full "
                "enrichment "
                f"(default: {default_get_fields})."
            ),
        ),
    ) -> dict[str, Any]:
        try:
            ident = parse_identifier(identifier)
            stub = Paper(identifiers={ident.kind: ident.value})
            selected_fields = render.resolve_output_fields(
                fields, services.config.output.get_fields
            )
            paper, warnings = services.metadata.enrich(
                stub, only_source=source, required_fields=render.enrichment_fields(selected_fields)
            )
        except PaperToolsError as exc:
            return _failure(exc)
        warnings = services.registry.load_warnings + warnings
        try:
            data = paper.model_dump(mode="json")
            if selected_fields is not None:
                data = render.filter_fields(data, selected_fields)
        except PaperToolsError as exc:
            return _failure(exc)
        return render.success_envelope("get", data, warnings)

    @server.tool(
        description=(
            "Resolve open-access full-text candidates for one paper without downloading. "
            "Returns ranked links with formats, locator sources, downloader recommendations, "
            "and licenses."
        )
    )
    def locate_fulltext(
        identifier: Annotated[str, Field(description="doi:/pmid:/pmcid: ID or bare DOI.")],
        format: Annotated[
            str | None,
            Field(
                description=(
                    "Filter candidates to pdf or xml; text includes pdf/xml/text sources. "
                    "If omitted, show all formats including landing pages."
                )
            ),
        ] = None,
        locator: str | None = Field(
            default=None,
            description=(
                "Locator plugins to restrict to, comma-separated; 'all' forces every "
                f"registered locator (default: {default_locators}). "
                f"Available: {_available('locator')}."
            ),
        ),
    ) -> dict[str, Any]:
        try:
            if format is not None and format not in ("pdf", "xml", "text"):
                raise UsageError(f"Invalid format {format!r}; expected pdf, xml, or text.")
            artifact_format = cast(ArtifactFormat, format) if format is not None else None
            locator_names = (
                [name.strip() for name in locator.split(",") if name.strip()] if locator else None
            )
            if locator_names is not None and "all" in locator_names:
                locator_names = []
            result, warnings = services.fetch.locate(
                identifier, fmt=artifact_format, locators=locator_names
            )
        except PaperToolsError as exc:
            return _failure(exc)
        warnings = services.registry.load_warnings + warnings
        return render.success_envelope("locate", result.model_dump(mode="json"), warnings)

    @server.tool(
        description=(
            "Retrieve open-access full text (pdf|xml|text) for one paper. "
            "Returns a FullText envelope with the local file path, sha256, and "
            "provenance. Closed-access papers return a FULLTEXT_UNAVAILABLE error "
            "envelope with the publisher link; never bypass paywalls."
        )
    )
    def fetch_fulltext(
        identifier: Annotated[str, Field(description="doi:/pmid:/pmcid: ID or bare DOI.")],
        format: Annotated[
            str | None,
            Field(
                description=(
                    "Output format: pdf | xml | text (download + extract). If omitted, infer "
                    "from the output extension; default to pdf when no extension is present."
                )
            ),
        ] = None,
        output: str | None = Field(
            default=None,
            description=(
                f"Output filename (default: {default_output}). A duplicate default title gets "
                "an ID suffix. Extensions .pdf/.xml/.txt infer format when omitted; a missing "
                "extension is appended."
            ),
        ),
        locator: str | None = Field(
            default=None,
            description=(
                "Locator plugins to restrict to, comma-separated; 'all' forces every "
                f"registered locator (default: {default_locators}). "
                f"Available: {_available('locator')}."
            ),
        ),
        downloader: str | None = Field(
            default=None,
            description=f"Force a downloader plugin. Available: {_available('downloader')}.",
        ),
        extractor: str | None = Field(
            default=None,
            description=(
                f"Force an extractor plugin for format='text'. "
                f"Available: {_available('extractor')}."
            ),
        ),
    ) -> dict[str, Any]:
        try:
            if format is not None and format not in ("pdf", "xml", "text"):
                raise UsageError(f"Invalid format {format!r}; expected pdf, xml, or text.")
            artifact_format = cast(ArtifactFormat, format) if format is not None else None
            locator_names = (
                [name.strip() for name in locator.split(",") if name.strip()] if locator else None
            )
            if locator_names is not None and "all" in locator_names:
                locator_names = []  # explicit all overrides the fetch.locators config
            result, warnings = services.fetch.fetch(
                identifier,
                fmt=artifact_format,
                output=Path(output) if output else None,
                locators=locator_names,
                downloader=downloader,
                extractor=extractor,
            )
        except PaperToolsError as exc:
            return _failure(exc)
        warnings = services.registry.load_warnings + warnings
        return render.success_envelope("fetch", result.model_dump(mode="json"), warnings)

    @server.tool(
        description=(
            "List registered plugins grouped by role (searcher, metadata, locator, "
            "downloader, extractor) with versions, descriptions, and load warnings."
        )
    )
    def list_sources() -> dict[str, Any]:
        inventory = services.registry.describe()
        return render.success_envelope("sources", inventory, services.registry.load_warnings)

    return server


def run(opts: GlobalOpts | None = None) -> None:
    """Start the stdio MCP server (blocks until the client disconnects)."""
    build_server(opts).run(transport="stdio")
