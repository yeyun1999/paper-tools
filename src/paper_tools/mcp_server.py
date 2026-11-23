"""MCP server (stdio) exposing the CLI services to AI assistants.

Requires the ``mcp`` extra. Tools return the same JSON envelopes as
``paper-tools --json`` (schema_version 1.0), so agents can share one contract
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

Typical flow: search_papers -> get_paper (full metadata) -> fetch_fulltext
(pdf / xml / text). Only official APIs and open-access copies are used;
closed-access papers return an error envelope with code FULLTEXT_UNAVAILABLE
and a publisher link instead of full text.

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
    """Construct the MCPServer with the four paper-tools tools registered."""
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

    @server.tool(
        description=(
            "Search literature. Returns a SearchPage envelope (items may be stubs; "
            "set enrich=true for full metadata). Supports pagination via cursor."
        )
    )
    def search_papers(
        query: Annotated[str | None, Field(description="Free-text query.")] = None,
        source: Annotated[
            str | None,
            Field(
                description="Search plugin: pubmed|europepmc|crossref|openalex|semantic_scholar."
            ),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=100, description="Max results (1-100).")] = 20,
        cursor: Annotated[
            str | None, Field(description="Pagination cursor from next_cursor.")
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
            page, warnings = services.search.search(
                q, source=source, limit=limit, cursor=cursor, enrich=enrich
            )
        except PaperToolsError as exc:
            return _failure(exc)
        warnings = services.registry.load_warnings + warnings
        return render.success_envelope("search", page.model_dump(mode="json"), warnings)

    @server.tool(
        description=(
            "Fetch complete metadata for one paper via the enrichment chain. "
            "Identifier: doi:/pmid:/pmcid:/openalex:/s2:/arxiv: prefixed ID or bare DOI."
        )
    )
    def get_paper(
        identifier: Annotated[str, Field(description="e.g. doi:10.1038/... or pmid:38308006.")],
        source: Annotated[
            str | None, Field(description="Restrict enrichment to one metadata plugin.")
        ] = None,
    ) -> dict[str, Any]:
        try:
            ident = parse_identifier(identifier)
            stub = Paper(identifiers={ident.kind: ident.value})
            paper, warnings = services.metadata.enrich(stub, only_source=source)
        except PaperToolsError as exc:
            return _failure(exc)
        warnings = services.registry.load_warnings + warnings
        return render.success_envelope("get", paper.model_dump(mode="json"), warnings)

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
        format: Annotated[str, Field(description="pdf | xml | text")] = "pdf",
        out_dir: Annotated[
            str | None, Field(description="Output directory (default: ./papers).")
        ] = None,
        locator: Annotated[
            str | None,
            Field(
                description=(
                    "Comma-separated locator plugins to restrict to; 'all' forces every "
                    "registered locator (default: fetch.locators config, else all)."
                )
            ),
        ] = None,
        downloader: Annotated[str | None, Field(description="Force a downloader plugin.")] = None,
        extractor: Annotated[str | None, Field(description="Force an extractor plugin.")] = None,
    ) -> dict[str, Any]:
        try:
            if format not in ("pdf", "xml", "text"):
                raise UsageError(f"Invalid format {format!r}; expected pdf, xml, or text.")
            artifact_format = cast(ArtifactFormat, format)
            locator_names = (
                [name.strip() for name in locator.split(",") if name.strip()] if locator else None
            )
            if locator_names is not None and "all" in locator_names:
                locator_names = []  # explicit all overrides the fetch.locators config
            result, warnings = services.fetch.fetch(
                identifier,
                fmt=artifact_format,
                out_dir=Path(out_dir) if out_dir else None,
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
