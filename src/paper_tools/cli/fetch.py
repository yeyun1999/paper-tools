"""fetch command: locate -> download -> (extract) full text."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

import typer

from paper_tools.cli import context, render
from paper_tools.core.config import FetchConfig, load_config
from paper_tools.core.errors import ConfigError, PaperToolsError, UsageError
from paper_tools.core.models import ArtifactFormat
from paper_tools.core.plugins import available_names

# Module-level: Typer evals string annotations against module globals.
try:
    _FETCH_CONFIG = load_config().fetch
except ConfigError:
    _FETCH_CONFIG = FetchConfig()
_DEFAULT_LOCATORS = ", ".join(_FETCH_CONFIG.locators) if _FETCH_CONFIG.locators else "all"
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
_LOCATOR_HELP = (
    "Locator plugins to restrict to; repeat the flag or comma-separate. "
    f"'all' forces every registered locator (default: {_DEFAULT_LOCATORS}). "
    f"Available: {', '.join(available_names('locator')) or '(none)'}."
)
_DOWNLOADER_HELP = (
    f"Force a downloader plugin. Available: {', '.join(available_names('downloader')) or '(none)'}."
)
_EXTRACTOR_HELP = (
    "Force an extractor plugin for --format text. Available: "
    f"{', '.join(available_names('extractor')) or '(none)'}."
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
            typer.Option("--locator", help=_LOCATOR_HELP),
        ] = None,
        downloader: Annotated[
            str | None,
            typer.Option("--downloader", help=_DOWNLOADER_HELP),
        ] = None,
        extractor: Annotated[
            str | None,
            typer.Option("--extractor", help=_EXTRACTOR_HELP),
        ] = None,
    ) -> None:
        """Retrieve open-access full text for one paper."""
        opts = ctx.obj
        with render.error_guard(opts, "fetch"):
            if fmt is not None and fmt not in ("pdf", "xml", "text"):
                raise UsageError(f"Invalid --format {fmt!r}; expected pdf, xml, or text.")
            artifact_format = cast(ArtifactFormat, fmt) if fmt is not None else None
            locator_names = (
                [name.strip() for item in locator for name in item.split(",") if name.strip()]
                if locator
                else None
            )
            if locator_names is not None and "all" in locator_names:
                locator_names = []  # explicit all overrides the fetch.locators config
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
