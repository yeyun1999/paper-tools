"""fetch command: locate -> download -> (extract) full text."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, cast

import typer

from paper_search.cli import context, render
from paper_search.core.config import FetchConfig, load_config
from paper_search.core.errors import ConfigError, PaperSearchError, UsageError
from paper_search.core.models import ArtifactFormat
from paper_search.core.plugins import available_names

# Module-level: Typer evals string annotations against module globals.
try:
    _FETCH_CONFIG = load_config().fetch
except ConfigError:
    _FETCH_CONFIG = FetchConfig()
_DEFAULT_LOCATORS = ", ".join(_FETCH_CONFIG.locators) if _FETCH_CONFIG.locators else "all"
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
        identifiers: Annotated[
            list[str],
            typer.Argument(
                help="One or more IDs (doi:/pmid:/pmcid: or bare DOI), processed independently."
            ),
        ],
        fmt: Annotated[
            str,
            typer.Option("--format", help="Output format: pdf | xml | text (download + extract)."),
        ] = "pdf",
        out: Annotated[
            Path | None,
            typer.Option("--out", help=f"Output directory (default: {_FETCH_CONFIG.out_dir})."),
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
        """Retrieve open-access full text. Batch output is NDJSON with --json."""
        opts = ctx.obj
        with render.error_guard(opts, "fetch"):
            if fmt not in ("pdf", "xml", "text"):
                raise UsageError(f"Invalid --format {fmt!r}; expected pdf, xml, or text.")
            artifact_format = cast(ArtifactFormat, fmt)
            locator_names = (
                [name.strip() for item in locator for name in item.split(",") if name.strip()]
                if locator
                else None
            )
            if locator_names is not None and "all" in locator_names:
                locator_names = []  # explicit all overrides the fetch.locators config
            services = context.build_services(opts)
            payloads: list[dict[str, Any]] = []
            exit_code = 0
            for identifier in identifiers:
                try:
                    result, warnings = services.fetch.fetch(
                        identifier,
                        fmt=artifact_format,
                        out_dir=out,
                        locators=locator_names,
                        downloader=downloader,
                        extractor=extractor,
                    )
                except PaperSearchError as exc:
                    payloads.append(render.error_envelope(exc))
                    if exit_code == 0:
                        exit_code = exc.exit_code
                    if not opts.json_output:
                        render.err_console.print(
                            f"[red]FAIL[/red] {identifier}: {exc.code}: {exc.message}"
                        )
                    continue
                warnings = services.registry.load_warnings + warnings
                payloads.append(
                    render.success_envelope("fetch", result.model_dump(mode="json"), warnings)
                )
                if not opts.json_output:
                    render.render_fulltext(result)
                    render.show_warnings(warnings, opts)
            if opts.json_output:
                if len(payloads) == 1:
                    render.emit_json(payloads[0])
                else:
                    render.emit_ndjson(payloads)
            if exit_code:
                raise typer.Exit(exit_code)
