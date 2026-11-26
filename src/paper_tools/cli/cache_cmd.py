"""cache subcommands: clear / stats."""

from __future__ import annotations

from typing import Annotated

import typer

from paper_tools.cli import render
from paper_tools.core.cache import Cache

cache_app = typer.Typer(no_args_is_help=True, help="Manage caches.")


@cache_app.command("clear")
def clear(
    ctx: typer.Context,
    all_artifacts: Annotated[
        bool,
        typer.Option("--all", help="Also remove cached PDF, XML, and text artifacts."),
    ] = False,
) -> None:
    """Clear cached responses and metadata (artifact files are kept by default)."""
    opts = ctx.obj
    with render.error_guard(opts, "cache clear"):
        count = Cache().clear(include_artifacts=all_artifacts)
        data = {"cleared": count, "artifacts_cleared": all_artifacts}
        if opts.json_output:
            render.emit_json(render.success_envelope("cache clear", data, []))
        elif not opts.quiet:
            suffix = " and artifact files" if all_artifacts else ""
            typer.echo(f"cleared {count} entries{suffix}")


@cache_app.command("gc")
def gc(ctx: typer.Context) -> None:
    """Remove artifact files no longer referenced by a cache mapping."""
    opts = ctx.obj
    with render.error_guard(opts, "cache gc"):
        data = {"removed": Cache().prune_orphans()}
        if opts.json_output:
            render.emit_json(render.success_envelope("cache gc", data, []))
        elif not opts.quiet:
            typer.echo(f"removed {data['removed']} orphaned artifact files")


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
