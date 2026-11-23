"""sources command: full plugin inventory grouped by the five roles."""

from __future__ import annotations

import typer

from paper_tools.cli import context, render


def register(app: typer.Typer) -> None:
    @app.command()
    def sources(ctx: typer.Context) -> None:
        """List all registered plugins (searcher/metadata/locator/downloader/extractor)."""
        opts = ctx.obj
        with render.error_guard(opts, "sources"):
            services = context.build_services(opts)
            data = services.registry.describe()
            if opts.json_output:
                render.emit_json(
                    render.success_envelope("sources", data, services.registry.load_warnings)
                )
            else:
                render.render_inventory(data)
