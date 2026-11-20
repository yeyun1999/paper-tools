"""MCP server tests: tool contracts via fake plugins + real stdio roundtrip."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp extra not installed (uv sync --extra mcp)")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typer.testing import CliRunner

from paper_search import mcp_server
from paper_search.cli import context
from paper_search.cli.app import app
from paper_search.core.errors import UsageError
from tests.conftest import make_services


def _payload(result: Any) -> dict[str, Any]:
    if result.structured_content is not None:
        return dict(result.structured_content)
    return dict(json.loads(result.content[0].text))


def _call(server: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async def run() -> Any:
        return await server.call_tool(name, arguments)

    result = asyncio.run(run())
    assert not result.is_error
    return _payload(result)


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    services = make_services(tmp_path)
    monkeypatch.setattr(context, "build_services", lambda opts: services)
    return mcp_server.build_server()


def test_tools_registered(server: Any) -> None:
    async def run() -> list[str]:
        return [t.name for t in await server.list_tools()]

    assert asyncio.run(run()) == [
        "search_papers",
        "get_paper",
        "fetch_fulltext",
        "list_sources",
    ]


def test_tool_input_schemas(server: Any) -> None:
    """Freeze the MCP tool input contract (same semantics as the CLI flags)."""

    async def run() -> dict[str, Any]:
        return {t.name: t for t in await server.list_tools()}

    tools = asyncio.run(run())
    search_props = tools["search_papers"].input_schema["properties"]
    assert {
        "query",
        "source",
        "limit",
        "cursor",
        "author",
        "journal",
        "year_from",
        "year_to",
        "oa_only",
        "raw",
        "enrich",
    } <= set(search_props)
    assert tools["get_paper"].input_schema["required"] == ["identifier"]
    fetch_schema = tools["fetch_fulltext"].input_schema
    assert fetch_schema["required"] == ["identifier"]
    assert {"format", "out_dir", "locator", "downloader", "extractor"} <= set(
        fetch_schema["properties"]
    )
    assert not tools["list_sources"].input_schema.get("properties")


def test_search_papers_success(server: Any) -> None:
    payload = _call(server, "search_papers", {"query": "CRISPR", "limit": 2})
    assert payload["schema_version"] == "1.0"
    assert payload["command"] == "search"
    assert len(payload["data"]["items"]) == 2
    assert payload["data"]["items"][0]["identifiers"]["doi"] == "10.1000/fake1"


def test_search_papers_invalid_query_returns_error_envelope(server: Any) -> None:
    payload = _call(server, "search_papers", {"query": "x", "raw": "native"})
    assert payload["error"]["code"] == "USAGE"


def test_search_papers_multi_source(server: Any) -> None:
    payload = _call(server, "search_papers", {"query": "CRISPR", "source": "fake,fake"})
    assert len(payload["data"]["items"]) == 2  # same source twice -> deduped
    assert payload["data"]["source"] == "fake,fake"
    all_payload = _call(server, "search_papers", {"query": "CRISPR", "source": "all"})
    assert len(all_payload["data"]["items"]) == 2
    assert all_payload["data"]["source"] == "fake"


def test_get_paper_enriches(server: Any) -> None:
    payload = _call(server, "get_paper", {"identifier": "doi:10.1000/fake1"})
    data = payload["data"]
    assert data["abstract"] == "An abstract about base editing."
    assert data["identifiers"]["pmcid"] == "PMC999"
    assert "fake" in data["sources"]


def test_fetch_fulltext_pdf(server: Any, tmp_path: Path) -> None:
    out = tmp_path / "out"
    payload = _call(
        server,
        "fetch_fulltext",
        {"identifier": "doi:10.1000/fake1", "format": "pdf", "out_dir": str(out)},
    )
    path = Path(payload["data"]["path"])
    assert path.read_bytes().startswith(b"%PDF")
    assert payload["data"]["format"] == "pdf"


def test_fetch_fulltext_text_provenance(server: Any, tmp_path: Path) -> None:
    payload = _call(
        server,
        "fetch_fulltext",
        {
            "identifier": "doi:10.1000/fake1",
            "format": "text",
            "out_dir": str(tmp_path / "out"),
        },
    )
    data = payload["data"]
    assert data["extractor"] == "fake_ext"
    assert data["extracted_from"] in {"pdf", "xml"}
    assert Path(data["path"]).read_text(encoding="utf-8").startswith("EXTRACTED[")


def test_fetch_fulltext_locator_list(server: Any, tmp_path: Path) -> None:
    payload = _call(
        server,
        "fetch_fulltext",
        {
            "identifier": "doi:10.1000/fake1",
            "format": "pdf",
            "out_dir": str(tmp_path / "out"),
            "locator": "fake",
        },
    )
    assert payload["data"]["source_url"] == "https://example.org/paper.pdf"


def test_fetch_fulltext_locator_all(server: Any, tmp_path: Path) -> None:
    payload = _call(
        server,
        "fetch_fulltext",
        {
            "identifier": "doi:10.1000/fake1",
            "format": "pdf",
            "out_dir": str(tmp_path / "out"),
            "locator": "all",
        },
    )
    assert payload["data"]["source_url"] == "https://example.org/paper.pdf"


def test_fetch_fulltext_closed_returns_error_envelope(server: Any, tmp_path: Path) -> None:
    payload = _call(
        server,
        "fetch_fulltext",
        {
            "identifier": "doi:10.1000/closed",
            "format": "pdf",
            "out_dir": str(tmp_path / "out"),
        },
    )
    assert payload["error"]["code"] == "FULLTEXT_UNAVAILABLE"


def test_fetch_fulltext_invalid_format(server: Any) -> None:
    payload = _call(server, "fetch_fulltext", {"identifier": "doi:10.1000/fake1", "format": "docx"})
    assert payload["error"]["code"] == "USAGE"


def test_list_sources_roles(server: Any) -> None:
    payload = _call(server, "list_sources", {})
    data = payload["data"]
    assert set(data) == {"searcher", "metadata", "locator", "downloader", "extractor"}
    assert any(entry["name"] == "fake" for entry in data["searcher"])


def test_missing_extra_raises_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise UsageError("MCP support requires the 'mcp' extra.")

    monkeypatch.setattr(mcp_server, "_import_mcp", boom)
    with pytest.raises(UsageError):
        mcp_server.build_server()


def test_cli_mcp_missing_extra_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise UsageError("MCP support requires the 'mcp' extra.")

    monkeypatch.setattr(mcp_server, "_import_mcp", boom)
    result = CliRunner().invoke(app, ["--json", "mcp"])
    assert result.exit_code == 2
    assert "USAGE" in (result.stderr or result.output)


def test_stdio_roundtrip() -> None:
    """Real `paper-search mcp` subprocess: initialize, list tools, call one."""

    async def roundtrip() -> tuple[set[str], dict[str, Any]]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from paper_search.cli.app import main; main()", "mcp"],
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("list_sources", {})
            assert not result.is_error
            return {t.name for t in tools.tools}, _payload(result)

    names, payload = asyncio.run(asyncio.wait_for(roundtrip(), timeout=90))
    assert names == {"search_papers", "get_paper", "fetch_fulltext", "list_sources"}
    assert payload["schema_version"] == "1.0"
    assert "pubmed" in {entry["name"] for entry in payload["data"]["searcher"]}
