"""get command: full metadata via the enrichment chain."""

from __future__ import annotations

from typing import Annotated

import typer

from paper_search.cli import context, render
from paper_search.core.models import Paper, parse_identifier
from paper_search.core.plugins import available_names

# Module-level: Typer evals string annotations against module globals.
_PROVIDER_HELP = (
    "Restrict enrichment to one plugin. Available: "
    f"{', '.join(available_names('metadata')) or '(none)'}."
)


def register(app: typer.Typer) -> None:
    @app.command()
    def get(
        ctx: typer.Context,
        identifier: Annotated[
            str,
            typer.Argument(
                help="doi:/pmid:/pmcid:/openalex:/s2:/arxiv: ID, DOI URL, bare DOI, or PMID digits."
            ),
        ],
        source: Annotated[
            str | None,
            typer.Option("--source", help=_PROVIDER_HELP),
        ] = None,
        fields: Annotated[
            str | None,
            typer.Option(
                "--fields",
                help="Comma-separated Paper fields to keep, e.g. title,doi,abstract.",
            ),
        ] = None,
    ) -> None:
        """Fetch complete metadata for one paper."""
        opts = ctx.obj
        with render.error_guard(opts, "get"):
            ident = parse_identifier(identifier)
            stub = Paper(identifiers={ident.kind: ident.value})
            services = context.build_services(opts)
            paper, warnings = services.metadata.enrich(stub, only_source=source)
            warnings = services.registry.load_warnings + warnings
            data = paper.model_dump(mode="json")
            if fields:
                data = render.filter_fields(data, fields)
            if opts.json_output:
                render.emit_json(render.success_envelope("get", data, warnings))
            else:
                render.render_paper(paper)
                render.show_warnings(warnings, opts)
