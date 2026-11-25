"""schema command: export JSON Schemas for AI assistants and tooling."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from pydantic import BaseModel

from paper_tools.cli import render
from paper_tools.core.errors import UsageError
from paper_tools.core.models import (
    Artifact,
    Author,
    DownloadedFullText,
    ExtractedFullText,
    FullText,
    FullTextCandidate,
    FullTextLinks,
    Identifier,
    Paper,
    SearchPage,
)
from paper_tools.core.query import Query

_MODELS: dict[str, type[BaseModel]] = {
    "Author": Author,
    "Identifier": Identifier,
    "Paper": Paper,
    "Query": Query,
    "SearchPage": SearchPage,
    "FullTextCandidate": FullTextCandidate,
    "Artifact": Artifact,
    "FullTextLinks": FullTextLinks,
    "DownloadedFullText": DownloadedFullText,
    "ExtractedFullText": ExtractedFullText,
    "FullText": FullText,
}

_COMMAND_MODELS: dict[str, tuple[str, ...]] = {
    "search": ("Query", "SearchPage"),
    "get": ("Paper",),
    "locate": ("FullTextLinks",),
    "download": ("DownloadedFullText",),
    "extract": ("ExtractedFullText",),
    "fetch": ("FullText",),
}


def register(app: typer.Typer) -> None:
    @app.command()
    def schema(
        ctx: typer.Context,
        command: Annotated[
            str | None,
            typer.Argument(
                help=(
                    "Limit to one command's models "
                    "(search/get/locate/download/extract/fetch); omit for all."
                )
            ),
        ] = None,
    ) -> None:
        """Print JSON Schemas (always JSON, regardless of --json)."""
        opts = ctx.obj
        with render.error_guard(opts, "schema"):
            if command is not None:
                if command not in _COMMAND_MODELS:
                    raise UsageError(
                        f"Unknown command {command!r}; expected one of {sorted(_COMMAND_MODELS)}"
                    )
                names = _COMMAND_MODELS[command]
            else:
                names = tuple(_MODELS)
            data: dict[str, Any] = {name: _MODELS[name].model_json_schema() for name in names}
            render.emit_json(data)
