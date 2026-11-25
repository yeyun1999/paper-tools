"""Standalone commands for locating, downloading, and extracting full text."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, TypeVar, cast

import typer
from pydantic import BaseModel

from paper_tools.cli import context, render
from paper_tools.core.config import FetchConfig, load_config
from paper_tools.core.errors import ConfigError, PaperToolsError, UsageError
from paper_tools.core.models import ArtifactFormat
from paper_tools.core.plugins import available_names
from paper_tools.core.services import Services

try:
    _FETCH_CONFIG = load_config().fetch
except ConfigError:
    _FETCH_CONFIG = FetchConfig()

_DEFAULT_LOCATORS = ", ".join(_FETCH_CONFIG.locators) if _FETCH_CONFIG.locators else "all"
LOCATOR_HELP = (
    "Locator plugins to restrict to; repeat the flag or comma-separate. "
    f"'all' forces every registered locator (default: {_DEFAULT_LOCATORS}). "
    f"Available: {', '.join(available_names('locator')) or '(none)'}."
)
DOWNLOADER_HELP = (
    f"Force a downloader plugin. Available: {', '.join(available_names('downloader')) or '(none)'}."
)
EXTRACTOR_HELP = (
    f"Force an extractor plugin. Available: {', '.join(available_names('extractor')) or '(none)'}."
)

_Result = TypeVar("_Result", bound=BaseModel)


def parse_format(value: str | None) -> ArtifactFormat | None:
    if value is not None and value not in ("pdf", "xml", "text"):
        raise UsageError(f"Invalid --format {value!r}; expected pdf, xml, or text.")
    return cast(ArtifactFormat, value) if value is not None else None


def parse_locators(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    names = [name.strip() for item in values for name in item.split(",") if name.strip()]
    return [] if "all" in names else names


def _run(
    ctx: typer.Context,
    command: str,
    operation: Callable[[Services], tuple[_Result, list[str]]],
    renderer: Callable[[_Result], None],
) -> None:
    opts = ctx.obj
    with render.error_guard(opts, command):
        services = context.build_services(opts)
        try:
            result, warnings = operation(services)
        except PaperToolsError as exc:
            if opts.json_output:
                render.emit_json(render.error_envelope(exc))
            else:
                render.err_console.print(f"[red]FAIL[/red] {command}: {exc.code}: {exc.message}")
            raise typer.Exit(exc.exit_code) from exc
        warnings = services.registry.load_warnings + warnings
        if opts.json_output:
            render.emit_json(
                render.success_envelope(command, result.model_dump(mode="json"), warnings)
            )
        else:
            renderer(result)
            render.show_warnings(warnings, opts)


def register(app: typer.Typer) -> None:
    @app.command()
    def locate(
        ctx: typer.Context,
        identifier: Annotated[
            str,
            typer.Argument(help="One ID (doi:/pmid:/pmcid: or bare DOI)."),
        ],
        fmt: Annotated[
            str | None,
            typer.Option(
                "--format",
                help=(
                    "Filter candidates to pdf or xml; text includes pdf/xml/text sources. "
                    "If omitted, show all formats including landing pages."
                ),
            ),
        ] = None,
        locator: Annotated[
            list[str] | None,
            typer.Option("--locator", help=LOCATOR_HELP),
        ] = None,
    ) -> None:
        """Resolve open-access full-text links for one paper without downloading."""
        _run(
            ctx,
            "locate",
            lambda services: services.fetch.locate(
                identifier, fmt=parse_format(fmt), locators=parse_locators(locator)
            ),
            render.render_fulltext_links,
        )

    @app.command()
    def download(
        ctx: typer.Context,
        url: Annotated[
            str,
            typer.Argument(help="Direct HTTP(S) URL from fulltext or another OA source."),
        ],
        fmt: Annotated[
            str | None,
            typer.Option(
                "--format",
                help=(
                    "Downloaded format: pdf | xml | text. If omitted, infer from the "
                    "--output extension, then the URL path; an extensionless --output "
                    "defaults to pdf when the URL has no recognized extension."
                ),
            ),
        ] = None,
        output: Annotated[
            Path | None,
            typer.Option(
                "--output",
                help=(
                    "Output filename (default: safe URL name in the current directory). "
                    "Extensions .pdf/.xml/.txt infer --format; a missing extension is appended."
                ),
            ),
        ] = None,
        downloader: Annotated[
            str | None,
            typer.Option("--downloader", help=DOWNLOADER_HELP),
        ] = None,
    ) -> None:
        """Download one direct full-text URL without locating a paper first."""
        _run(
            ctx,
            "download",
            lambda services: services.fetch.download(
                url, fmt=parse_format(fmt), output=output, downloader=downloader
            ),
            render.render_downloaded_fulltext,
        )

    @app.command()
    def extract(
        ctx: typer.Context,
        source: Annotated[
            Path,
            typer.Argument(help="Local PDF or JATS XML file to extract text from."),
        ],
        output: Annotated[
            Path | None,
            typer.Option(
                "--output",
                help=(
                    "Output text filename (default: input filename with .txt). "
                    "A missing extension is appended; other extensions are rejected."
                ),
            ),
        ] = None,
        extractor: Annotated[
            str | None,
            typer.Option("--extractor", help=EXTRACTOR_HELP),
        ] = None,
    ) -> None:
        """Extract plain text from a local PDF or JATS XML file."""
        _run(
            ctx,
            "extract",
            lambda services: services.fetch.extract(source, output=output, extractor=extractor),
            render.render_extracted_fulltext,
        )
