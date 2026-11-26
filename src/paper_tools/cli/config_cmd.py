"""config subcommands: get / set / list / path."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from paper_tools.cli import render
from paper_tools.core.config import (
    config_path_for_write,
    load_config,
    mask_secrets,
    set_config_value,
)
from paper_tools.core.errors import UsageError

config_app = typer.Typer(no_args_is_help=True, help="Manage configuration.")


def _lookup(data: dict[str, Any], key: str) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise UsageError(f"Config key {key!r} is not set.")
        node = node[part]
    return node


@config_app.command("get")
def get_value(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dotted key, e.g. plugins.unpaywall.email")],
) -> None:
    """Read one merged config value (secrets masked)."""
    opts = ctx.obj
    with render.error_guard(opts, "config get"):
        config = load_config(opts.config_path)
        value = _lookup(mask_secrets(config.model_dump(mode="json")), key)
        if opts.json_output:
            render.emit_json(
                render.success_envelope("config get", {"key": key, "value": value}, [])
            )
        else:
            typer.echo(value)


@config_app.command("set")
def set_value(
    ctx: typer.Context,
    key: Annotated[
        str,
        typer.Argument(
            help="Dotted key: general.*, fetch.*, metadata.*, output.*, or plugins.<name>.*"
        ),
    ],
    value: Annotated[
        str,
        typer.Argument(help="Value as TOML literal (true/123 become bool/number) or plain string."),
    ],
) -> None:
    """Write one value to the config file."""
    opts = ctx.obj
    with render.error_guard(opts, "config set"):
        path = set_config_value(key, value, opts.config_path)
        if opts.json_output:
            render.emit_json(
                render.success_envelope("config set", {"key": key, "path": str(path)}, [])
            )
        elif not opts.quiet:
            typer.echo(f"set {key} in {path}")


@config_app.command("list")
def list_values(ctx: typer.Context) -> None:
    """Show merged configuration (secrets masked)."""
    opts = ctx.obj
    with render.error_guard(opts, "config list"):
        config = load_config(opts.config_path)
        data = mask_secrets(config.model_dump(mode="json"))
        if opts.json_output:
            render.emit_json(render.success_envelope("config list", data, []))
        else:
            render.console.print_json(data=data)


@config_app.command("path")
def show_path(ctx: typer.Context) -> None:
    """Print the config file path."""
    opts = ctx.obj
    with render.error_guard(opts, "config path"):
        path: Path = config_path_for_write(opts.config_path)
        if opts.json_output:
            render.emit_json(render.success_envelope("config path", {"path": str(path)}, []))
        else:
            typer.echo(path)


def register(app: typer.Typer) -> None:
    app.add_typer(config_app, name="config")
