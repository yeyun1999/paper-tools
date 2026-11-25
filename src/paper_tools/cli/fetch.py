"""fetch command: locate -> download -> (extract) full text."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from paper_tools.cli import context, render
from paper_tools.cli.fulltext import (
    DOWNLOADER_HELP,
    EXTRACTOR_HELP,
    LOCATOR_HELP,
    parse_format,
    parse_locators,
)
from paper_tools.core.config import FetchConfig, load_config
from paper_tools.core.errors import ConfigError, PaperToolsError

# Module-level: Typer evals string annotations against module globals.
try:
    _FETCH_CONFIG = load_config().fetch
except ConfigError:
    _FETCH_CONFIG = FetchConfig()
_DEFAULT_OUTPUT = _FETCH_CONFIG.output or "safe article title in the current directory"
_FORMAT_HELP = (
    "Output format: pdf | xml | text (download + extract). If omitted, infer from the "
    "--output extension; default to pdf when no extension is present."
)
_OUTPUT_HELP = (
    f"Output filename (default: {_DEFAULT_OUTPUT}). A duplicate default title gets an ID "
    "suffix. Extensions .pdf/.xml/.txt infer --format when omitted; a missing extension "
    "is appended."
)


def register(app: typer.Typer) -> None:
    @app.command()
    def fetch(
        ctx: typer.Context,
        identifier: Annotated[
            str,
            typer.Argument(help="One ID (doi:/pmid:/pmcid: or bare DOI)."),
        ],
        fmt: Annotated[
            str | None,
            typer.Option("--format", help=_FORMAT_HELP),
        ] = None,
        output: Annotated[
            Path | None,
            typer.Option("--output", help=_OUTPUT_HELP),
        ] = None,
        locator: Annotated[
            list[str] | None,
            typer.Option("--locator", help=LOCATOR_HELP),
        ] = None,
        downloader: Annotated[
            str | None,
            typer.Option("--downloader", help=DOWNLOADER_HELP),
        ] = None,
        extractor: Annotated[
            str | None,
            typer.Option("--extractor", help=EXTRACTOR_HELP),
        ] = None,
    ) -> None:
        """Retrieve open-access full text for one paper (locate->download->extract)."""
        opts = ctx.obj
        with render.error_guard(opts, "fetch"):
            artifact_format = parse_format(fmt)
            locator_names = parse_locators(locator)
            services = context.build_services(opts)
            try:
                result, warnings = services.fetch.fetch(
                    identifier,
                    fmt=artifact_format,
                    output=output,
                    locators=locator_names,
                    downloader=downloader,
                    extractor=extractor,
                )
            except PaperToolsError as exc:
                if opts.json_output:
                    render.emit_json(render.error_envelope(exc))
                else:
                    render.err_console.print(
                        f"[red]FAIL[/red] {identifier}: {exc.code}: {exc.message}"
                    )
                raise typer.Exit(exc.exit_code) from exc
            warnings = services.registry.load_warnings + warnings
            if opts.json_output:
                render.emit_json(
                    render.success_envelope("fetch", result.model_dump(mode="json"), warnings)
                )
            else:
                render.render_fulltext(result)
                render.show_warnings(warnings, opts)
