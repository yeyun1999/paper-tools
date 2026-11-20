"""Typer root application."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from paper_search import __version__
from paper_search.cli import (
    cache_cmd,
    config_cmd,
    context,
    fetch,
    get,
    inventory,
    mcp_cmd,
    schema,
    search,
)
from paper_search.cli.context import GlobalOpts

_GLOBAL_FLAGS = {"--json", "--quiet", "--verbose", "--no-cache"}
_GLOBAL_VALUE_OPTS = {"--timeout", "--config"}


def _normalize_args(args: list[str]) -> list[str]:
    """Hoist global options to the front so they work after the subcommand too.

    ``paper-search search q --json`` must behave like ``paper-search --json search q``.
    """
    front: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            rest.extend(args[i:])
            break
        name = arg.split("=", 1)[0]
        if arg in _GLOBAL_FLAGS:
            front.append(arg)
            i += 1
        elif name in _GLOBAL_VALUE_OPTS:
            front.append(arg)
            if "=" not in arg and i + 1 < len(args):
                front.append(args[i + 1])
                i += 1
            i += 1
        else:
            rest.append(arg)
            i += 1
    return front + rest


class GlobalOptionGroup(TyperGroup):
    # ctx is typer's vendored click Context (private module); Any avoids importing it.
    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        return super().parse_args(ctx, _normalize_args(args))


app = typer.Typer(
    cls=GlobalOptionGroup,
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="Literature search and open-access full-text retrieval for researchers and AI assistants.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"paper-search {__version__}")
        raise typer.Exit


@app.callback()
def root(
    ctx: typer.Context,
    json_output: Annotated[
        bool, typer.Option("--json", help="Machine-readable JSON output (logs go to stderr).")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Suppress non-essential human output.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Debug logging to stderr.")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Bypass all caches.")] = False,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="HTTP timeout in seconds.")
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Alternate config.toml path (default: user config dir)."),
    ] = None,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    opts = GlobalOpts(
        json_output=json_output,
        quiet=quiet,
        verbose=verbose,
        no_cache=no_cache,
        timeout=timeout,
        config_path=config_path,
    )
    context.configure_logging(opts)
    ctx.obj = opts


for _module in (search, get, fetch, inventory, config_cmd, cache_cmd, schema, mcp_cmd):
    _module.register(app)


def _force_utf8_streams() -> None:
    """Windows consoles may default to GBK/cp1252; the JSON contract is UTF-8.

    Reconfigure so non-ASCII titles/authors never crash or get mangled.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _force_utf8_streams()
    app()
