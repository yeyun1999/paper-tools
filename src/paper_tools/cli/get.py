"""get command: full metadata via the enrichment chain (single or batch)."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from paper_tools.cli import context, render
from paper_tools.core.config import AppConfig, load_config
from paper_tools.core.errors import ConfigError, PaperToolsError
from paper_tools.core.models import Paper, parse_identifier
from paper_tools.core.plugins import available_names

# Module-level: Typer evals string annotations against module globals.
try:
    _DEFAULT_CONFIG = load_config()
except ConfigError:
    _DEFAULT_CONFIG = AppConfig()
_PROVIDER_HELP = (
    "Restrict enrichment to one plugin. Available: "
    f"{', '.join(available_names('metadata')) or '(none)'}."
)
_GET_FIELDS_HELP = render.output_fields_help(_DEFAULT_CONFIG.output.get_fields)


def register(app: typer.Typer) -> None:
    @app.command()
    def get(
        ctx: typer.Context,
        identifiers: Annotated[
            list[str],
            typer.Argument(
                help=(
                    "One or more IDs (doi:/pmid:/pmcid:/openalex:/s2:/arxiv:, DOI URL, "
                    "bare DOI, or PMID digits), processed independently."
                )
            ),
        ],
        source: Annotated[
            str | None,
            typer.Option("--source", help=_PROVIDER_HELP),
        ] = None,
        fields: Annotated[
            str | None,
            typer.Option("--fields", help=_GET_FIELDS_HELP),
        ] = None,
    ) -> None:
        """Fetch complete metadata for one or more papers. Batch output is NDJSON with --json."""
        opts = ctx.obj
        with render.error_guard(opts, "get"):
            services = context.build_services(opts)
            selected_fields = render.resolve_output_fields(
                fields, services.config.output.get_fields
            )
            payloads: list[dict[str, Any]] = []
            exit_code = 0
            for identifier in identifiers:
                try:
                    ident = parse_identifier(identifier)
                    stub = Paper(identifiers={ident.kind: ident.value})
                    paper, warnings = services.metadata.enrich(
                        stub,
                        only_source=source,
                        required_fields=render.enrichment_fields(selected_fields),
                    )
                except PaperToolsError as exc:
                    payloads.append(render.error_envelope(exc))
                    if exit_code == 0:
                        exit_code = exc.exit_code
                    if not opts.json_output:
                        render.err_console.print(
                            f"[red]FAIL[/red] {identifier}: {exc.code}: {exc.message}"
                        )
                    continue
                warnings = services.registry.load_warnings + warnings
                data = paper.model_dump(mode="json")
                if selected_fields is not None:
                    data = render.filter_fields(data, selected_fields)
                payloads.append(render.success_envelope("get", data, warnings))
                if not opts.json_output:
                    render.render_paper(paper)
                    render.show_warnings(warnings, opts)
            if opts.json_output:
                if len(payloads) == 1:
                    render.emit_json(payloads[0])
                else:
                    render.emit_ndjson(payloads)
            if exit_code:
                raise typer.Exit(exit_code)
