"""Dual output rendering: Rich for humans, stable JSON envelopes for machines."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from paper_tools.cli.context import GlobalOpts
from paper_tools.core.errors import PaperToolsError
from paper_tools.core.models import (
    SCHEMA_VERSION,
    DownloadedFullText,
    ExtractedFullText,
    FullText,
    FullTextLinks,
    Paper,
    SearchPage,
)

console = Console()
err_console = Console(stderr=True)


def success_envelope(command: str, data: Any, warnings: list[str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "data": data,
        "warnings": warnings,
    }


def error_envelope(exc: PaperToolsError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "error": {"code": exc.code, "message": exc.message, "details": exc.details},
    }


def emit_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def emit_ndjson(payloads: list[dict[str, Any]]) -> None:
    for payload in payloads:
        typer.echo(json.dumps(payload, ensure_ascii=False, default=str))


def emit_error_json(exc: PaperToolsError) -> None:
    typer.echo(json.dumps(error_envelope(exc), ensure_ascii=False, default=str), err=True)


@contextmanager
def error_guard(opts: GlobalOpts, command: str) -> Iterator[None]:
    """Map PaperToolsError to structured output + exit code; keep stdout JSON-pure."""
    try:
        yield
    except PaperToolsError as exc:
        if opts.json_output:
            emit_error_json(exc)
        else:
            err_console.print(f"[bold red]{exc.code}[/bold red]: {exc.message}")
            for key, value in exc.details.items():
                err_console.print(f"  {key}: {value}")
        raise typer.Exit(exc.exit_code) from exc


def filter_fields(data: dict[str, Any], fields: str) -> dict[str, Any]:
    """Project a Paper dict onto requested fields; identifier kinds are promoted."""
    result: dict[str, Any] = {}
    identifiers = data.get("identifiers", {})
    for field in (f.strip() for f in fields.split(",")):
        if not field:
            continue
        if field in data:
            result[field] = data[field]
        elif field in identifiers:
            result[field] = identifiers[field]
    return result


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render_search_page(page: SearchPage) -> None:
    table = Table(title=f"Results from {page.source} (total: {page.total})")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Year", justify="right")
    table.add_column("Title", max_width=60)
    table.add_column("Journal", max_width=25)
    table.add_column("DOI", max_width=30)
    table.add_column("OA")
    for i, paper in enumerate(page.items, 1):
        table.add_row(
            str(i),
            str(paper.year or ""),
            _truncate(paper.title, 60),
            _truncate(paper.journal or "", 25),
            paper.identifiers.get("doi", ""),
            paper.oa_status,
        )
    console.print(table)
    if page.next_cursor:
        console.print(f"next cursor: {page.next_cursor}")


def render_paper(paper: Paper) -> None:
    console.print(f"[bold]{paper.title}[/bold]")
    if paper.authors:
        console.print(", ".join(a.name for a in paper.authors))
    meta = [str(paper.year or ""), paper.journal or "", paper.publication_type or ""]
    console.print(" | ".join(part for part in meta if part))
    for kind, value in paper.identifiers.items():
        console.print(f"{kind}: {value}")
    console.print(
        f"OA: {paper.oa_status}" + (f" | license: {paper.license}" if paper.license else "")
    )
    if paper.publisher_url:
        console.print(f"publisher: {paper.publisher_url}")
    if paper.abstract:
        console.print(f"\n{paper.abstract}")
    if paper.sources:
        console.print(f"\n[dim]sources: {', '.join(paper.sources)}[/dim]")


def render_fulltext(result: FullText) -> None:
    console.print(f"[green]OK[/green] {result.format} -> {result.path}")
    console.print(f"  source: {result.source_url} (via {result.downloader})")
    if result.extractor:
        console.print(f"  extracted from {result.extracted_from} by {result.extractor}")


def render_fulltext_links(result: FullTextLinks) -> None:
    console.print(f"[bold]{result.paper.title or 'Full-text candidates'}[/bold]")
    if not result.candidates:
        console.print("No full-text candidates found.")
        return
    table = Table()
    table.add_column("Format")
    table.add_column("URL")
    table.add_column("Locators")
    table.add_column("Downloaders")
    table.add_column("License")
    for candidate in result.candidates:
        table.add_row(
            candidate.format,
            candidate.url,
            ", ".join(candidate.locator),
            ", ".join(candidate.downloaders),
            candidate.license or "",
        )
    console.print(table)


def render_downloaded_fulltext(result: DownloadedFullText) -> None:
    console.print(f"[green]OK[/green] {result.format} -> {result.path}")
    console.print(f"  source: {result.source_url} (via {result.downloader})")


def render_extracted_fulltext(result: ExtractedFullText) -> None:
    console.print(f"[green]OK[/green] text -> {result.path}")
    console.print(f"  source: {result.source_path} ({result.source_format})")
    console.print(f"  extractor: {result.extractor}")


def render_inventory(groups: dict[str, list[dict[str, Any]]]) -> None:
    for role, entries in groups.items():
        table = Table(title=role)
        table.add_column("Name", style="bold")
        table.add_column("Version")
        table.add_column("Description")
        table.add_column("Attributes")
        for entry in entries:
            attrs = ", ".join(
                f"{key}={','.join(entry[key])}"
                for key in ("id_kinds", "formats", "source_formats")
                if key in entry
            )
            table.add_row(entry["name"], entry["version"], entry["description"], attrs)
        console.print(table)


def show_warnings(warnings: list[str], opts: GlobalOpts) -> None:
    if opts.quiet or opts.json_output:
        return
    for warning in warnings:
        err_console.print(f"[yellow]warning[/yellow]: {warning}")
