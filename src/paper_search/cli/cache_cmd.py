"""cache subcommands: clear / stats."""

from __future__ import annotations

import typer

from paper_search.cli import render
from paper_search.core.cache import Cache

cache_app = typer.Typer(no_args_is_help=True, help="Manage caches.")


@cache_app.command("clear")
def clear(ctx: typer.Context) -> None:
    """Clear cached responses and metadata (artifact files are kept)."""
    opts = ctx.obj
    with render.error_guard(opts, "cache clear"):
        count = Cache().clear()
        if opts.json_output:
            render.emit_json(render.success_envelope("cache clear", {"cleared": count}, []))
        elif not opts.quiet:
            typer.echo(f"cleared {count} entries")


@cache_app.command("stats")
def stats(ctx: typer.Context) -> None:
    """Show cache location, entry count, and size."""
    opts = ctx.obj
    with render.error_guard(opts, "cache stats"):
        data = Cache().stats()
        if opts.json_output:
            render.emit_json(render.success_envelope("cache stats", data, []))
        else:
            render.console.print_json(data=data)


def register(app: typer.Typer) -> None:
    app.add_typer(cache_app, name="cache")
