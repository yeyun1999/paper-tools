"""search command."""

from __future__ import annotations

from typing import Annotated

import typer
from pydantic import ValidationError

from paper_tools.cli import context, render
from paper_tools.core.config import AppConfig, load_config
from paper_tools.core.errors import ConfigError, UsageError
from paper_tools.core.plugins import available_names
from paper_tools.core.query import Query

# Module-level: Typer evals string annotations against module globals, so the
# dynamic help text must not live in a register() local.
try:
    _DEFAULT_SOURCE = load_config().general.default_source
except ConfigError:
    _DEFAULT_SOURCE = AppConfig().general.default_source
_SOURCE_HELP = (
    "Search plugin(s); repeat the flag or comma-separate; 'all' searches every "
    f"source with dedup (default: {_DEFAULT_SOURCE}). Available: "
    f"{', '.join(available_names('searcher')) or '(none)'}."
)


def register(app: typer.Typer) -> None:
    @app.command()
    def search(
        ctx: typer.Context,
        query: Annotated[
            str | None,
            typer.Argument(help="Free-text query (optional if structured filters are given)."),
        ] = None,
        source: Annotated[
            list[str] | None,
            typer.Option("--source", help=_SOURCE_HELP),
        ] = None,
        limit: Annotated[
            int,
            typer.Option(
                "--limit",
                min=1,
                max=100,
                help=(
                    "Per-source result cap (1-100). Single-source pages return at most "
                    "this many; multi-source merges all deduped hits and may exceed it."
                ),
            ),
        ] = 20,
        cursor: Annotated[
            str | None,
            typer.Option("--cursor", help="Pagination cursor from a previous data.next_cursor."),
        ] = None,
        author: Annotated[str | None, typer.Option("--author", help="Author name filter.")] = None,
        journal: Annotated[
            str | None, typer.Option("--journal", help="Journal name filter.")
        ] = None,
        year_from: Annotated[
            int | None, typer.Option("--year-from", help="Publication year lower bound.")
        ] = None,
        year_to: Annotated[
            int | None, typer.Option("--year-to", help="Publication year upper bound.")
        ] = None,
        oa_only: Annotated[
            bool, typer.Option("--oa-only", help="Restrict to open-access papers.")
        ] = False,
        raw: Annotated[
            str | None,
            typer.Option(
                "--raw",
                help="Native engine query syntax; mutually exclusive with other query fields.",
            ),
        ] = None,
        fields: Annotated[
            str | None,
            typer.Option(
                "--fields",
                help="Comma-separated Paper fields to keep, e.g. title,doi,year.",
            ),
        ] = None,
        enrich: Annotated[
            bool,
            typer.Option(
                "--enrich", help="Fill missing metadata (abstract, OA status) via the enrich chain."
            ),
        ] = False,
    ) -> None:
        """Search literature (returns stub records unless --enrich)."""
        opts = ctx.obj
        with render.error_guard(opts, "search"):
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
            services = context.build_services(opts)
            source_names = (
                [name.strip() for item in source for name in item.split(",") if name.strip()]
                if source
                else None
            )
            if source_names is not None and "all" in source_names:
                source_names = services.registry.names("searcher")
            page, warnings = services.search.search(
                q, sources=source_names, limit=limit, cursor=cursor, enrich=enrich
            )
            warnings = services.registry.load_warnings + warnings
            data = page.model_dump(mode="json")
            if fields:
                data["items"] = [render.filter_fields(item, fields) for item in data["items"]]
            if opts.json_output:
                render.emit_json(render.success_envelope("search", data, warnings))
            else:
                render.render_search_page(page)
                render.show_warnings(warnings, opts)
