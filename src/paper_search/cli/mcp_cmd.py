"""mcp command: stdio MCP server for AI assistants (requires the 'mcp' extra)."""

from __future__ import annotations

import typer

from paper_search.cli import render


def register(app: typer.Typer) -> None:
    @app.command()
    def mcp(ctx: typer.Context) -> None:
        """Run the MCP server over stdio (install with: uv sync --extra mcp)."""
        opts = ctx.obj
        with render.error_guard(opts, "mcp"):
            from paper_search.mcp_server import run

            run(opts)
