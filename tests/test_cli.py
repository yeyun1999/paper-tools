"""End-to-end CLI tests with fake plugins injected at the build_services seam."""

from __future__ import annotations

import io
import json
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from paper_tools import __version__
from paper_tools.cli import cache_cmd, context, render
from paper_tools.cli.app import _force_utf8_streams, app
from paper_tools.core.config import load_config
from paper_tools.core.services import Services


@pytest.fixture
def cli(services: Services, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setattr(context, "build_services", lambda opts: services)
    return CliRunner()


def test_version_matches_distribution(cli: CliRunner) -> None:
    result = cli.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"paper-tools {__version__}"
    # Guards the distribution rename: a stale lookup name silently reports 0.0.0.
    assert __version__ == version("paper-tools-cli") != "0.0.0"


def test_search_json(cli: CliRunner) -> None:
    result = cli.invoke(app, ["search", "CRISPR", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == render.SCHEMA_VERSION
    assert payload["command"] == "search"
    assert payload["data"]["source"] == "fake"
    assert len(payload["data"]["items"]) == 2


def test_search_json_flag_before_subcommand(cli: CliRunner) -> None:
    result = cli.invoke(app, ["--json", "search", "CRISPR"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["command"] == "search"


def test_search_fields_projection(cli: CliRunner) -> None:
    result = cli.invoke(app, ["search", "CRISPR", "--fields", "title,doi", "--json"])
    item = json.loads(result.stdout)["data"]["items"][0]
    assert set(item) == {"title", "doi"}


def test_search_no_query_usage_error(cli: CliRunner) -> None:
    result = cli.invoke(app, ["search", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stderr)["error"]["code"] == "USAGE"


def test_search_human_output(cli: CliRunner) -> None:
    result = cli.invoke(app, ["search", "CRISPR"])
    assert result.exit_code == 0
    assert "CRISPR" in result.stdout


def test_get_json(cli: CliRunner) -> None:
    result = cli.invoke(app, ["get", "doi:10.1000/fake1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["abstract"]
    assert data["identifiers"]["pmcid"] == "PMC999"
    assert "fake" in data["sources"]


def test_get_not_found(cli: CliRunner) -> None:
    result = cli.invoke(app, ["get", "doi:10.1000/missing", "--json"])
    assert result.exit_code == 3
    # per-ID errors live in the stdout result stream (aligned with fetch)
    assert json.loads(result.stdout)["error"]["code"] == "NOT_FOUND"


def test_get_invalid_identifier(cli: CliRunner) -> None:
    result = cli.invoke(app, ["get", "not-an-id", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "USAGE"


def test_get_batch_ndjson(cli: CliRunner) -> None:
    result = cli.invoke(
        app,
        ["get", "doi:10.1000/fake1", "doi:10.1000/missing", "pmid:111", "--json"],
    )
    assert result.exit_code == 3  # first per-ID failure (NOT_FOUND)
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 3
    first, second, third = (json.loads(line) for line in lines)
    assert first["data"]["abstract"]
    assert second["error"]["code"] == "NOT_FOUND"
    assert third["data"]["identifiers"]["pmid"] == "111"


def test_get_batch_fields_projection(cli: CliRunner) -> None:
    result = cli.invoke(
        app, ["get", "doi:10.1000/fake1", "doi:10.1000/fake2", "--fields", "title,doi", "--json"]
    )
    assert result.exit_code == 0
    for line in result.stdout.strip().splitlines():
        assert set(json.loads(line)["data"]) == {"title", "doi"}


def test_get_single_stays_single_object(cli: CliRunner) -> None:
    result = cli.invoke(app, ["get", "doi:10.1000/fake1", "--json"])
    payload = json.loads(result.stdout)  # would raise on NDJSON
    assert payload["command"] == "get"


def test_fetch_pdf_json(cli: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "custom.pdf"
    result = cli.invoke(
        app,
        ["fetch", "doi:10.1000/fake1", "--output", str(output), "--json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["format"] == "pdf"
    assert Path(data["path"]) == output
    assert output.exists()
    assert data["downloader"] == "fake_dl"


def test_fetch_human_output(cli: CliRunner, tmp_path: Path) -> None:
    result = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--format",
            "pdf",
            "--output",
            str(tmp_path / "paper.pdf"),
        ],
    )
    assert result.exit_code == 0
    assert "OK pdf ->" in result.stdout
    assert "fake_dl" in result.stdout


def test_fetch_text_json_infers_format(cli: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "paper.txt"
    result = cli.invoke(
        app,
        ["fetch", "doi:10.1000/fake1", "--output", str(output), "--json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["format"] == "text"
    assert Path(data["path"]) == output
    assert data["extractor"] == "fake_ext"
    assert data["extracted_from"] == "xml"


def test_fetch_default_output(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = cli.invoke(app, ["fetch", "doi:10.1000/fake1", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)["data"]
    assert data["format"] == "pdf"
    assert Path(data["path"]) == Path("CRISPR_base_editing_review.pdf")
    assert (tmp_path / "CRISPR_base_editing_review.pdf").exists()


def test_fetch_format_output_mismatch(cli: CliRunner, tmp_path: Path) -> None:
    result = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--format",
            "text",
            "--output",
            str(tmp_path / "paper.pdf"),
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "USAGE"


def test_fetch_unavailable_exit_4(cli: CliRunner, tmp_path: Path) -> None:
    result = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/closed",
            "--output",
            str(tmp_path / "paper.pdf"),
            "--json",
        ],
    )
    assert result.exit_code == 4
    # Single-paper fetch errors travel in the stdout result stream.
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "FULLTEXT_UNAVAILABLE"
    assert error["details"]["publisher_url"] == "https://doi.org/10.1000/closed"


def test_fetch_rejects_multiple_identifiers(cli: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "papers" / "paper.pdf"
    result = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "doi:10.1000/fake2",
            "--output",
            str(output),
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert not output.exists()


def test_fetch_bad_format(cli: CliRunner) -> None:
    result = cli.invoke(app, ["fetch", "doi:10.1000/fake1", "--format", "docx", "--json"])
    assert result.exit_code == 2


def test_locate_json(cli: CliRunner) -> None:
    result = cli.invoke(app, ["locate", "doi:10.1000/fake1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "locate"
    assert payload["data"]["paper"]["title"] == "CRISPR base editing review"
    assert [c["format"] for c in payload["data"]["candidates"]] == ["pdf", "xml", "landing"]
    assert payload["data"]["candidates"][0]["locator"] == ["fake"]
    assert payload["data"]["candidates"][0]["downloaders"] == ["fake_dl"]
    assert payload["data"]["candidates"][2]["downloaders"] == []


def test_locate_format_filter(cli: CliRunner) -> None:
    result = cli.invoke(app, ["locate", "doi:10.1000/fake1", "--format", "text", "--json"])
    assert result.exit_code == 0
    candidates = json.loads(result.stdout)["data"]["candidates"]
    assert [c["format"] for c in candidates] == ["xml", "pdf"]


def test_locate_human_output(cli: CliRunner) -> None:
    result = cli.invoke(app, ["locate", "doi:10.1000/fake1"])
    assert result.exit_code == 0
    assert "CRISPR base editing review" in result.stdout
    assert "https://example.org/paper.pdf" in result.stdout
    assert "landing" in result.stdout
    assert "Downloaders" in result.stdout
    assert "fake_dl" in result.stdout


def test_download_json(cli: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "paper.pdf"
    result = cli.invoke(
        app,
        ["download", "https://example.org/paper.pdf", "--output", str(output), "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "download"
    assert payload["data"]["format"] == "pdf"
    assert payload["data"]["downloader"] == "fake_dl"
    assert Path(payload["data"]["path"]) == output
    assert output.read_bytes().startswith(b"%PDF")


def test_download_infers_format_from_output(cli: CliRunner, tmp_path: Path) -> None:
    output = tmp_path / "paper.xml"
    result = cli.invoke(
        app,
        ["download", "https://example.org/fulltext", "--output", str(output), "--json"],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["format"] == "xml"
    assert b"<article>" in output.read_bytes()


def test_download_default_output(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = cli.invoke(app, ["download", "https://example.org/paper.pdf", "--json"])
    assert result.exit_code == 0
    assert Path(json.loads(result.stdout)["data"]["path"]) == Path("paper.pdf")
    assert (tmp_path / "paper.pdf").exists()


def test_download_errors(cli: CliRunner, tmp_path: Path) -> None:
    unknown = cli.invoke(app, ["download", "https://example.org/fulltext", "--json"])
    assert unknown.exit_code == 2
    assert json.loads(unknown.stdout)["error"]["code"] == "USAGE"
    invalid = cli.invoke(app, ["download", "file:///tmp/paper.pdf", "--json"])
    assert invalid.exit_code == 2
    assert json.loads(invalid.stdout)["error"]["code"] == "USAGE"
    failed = cli.invoke(
        app,
        [
            "download",
            "https://example.org/fail.xml",
            "--output",
            str(tmp_path / "fail.xml"),
            "--json",
        ],
    )
    assert failed.exit_code == 3
    assert json.loads(failed.stdout)["error"]["code"] == "UPSTREAM"


def test_extract_json(cli: CliRunner, tmp_path: Path) -> None:
    source = tmp_path / "paper.xml"
    output = tmp_path / "text" / "paper.txt"
    source.write_bytes(b"<article><body><p>Hello CRISPR</p></body></article>")
    result = cli.invoke(
        app,
        ["extract", str(source), "--output", str(output), "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "extract"
    assert payload["data"]["source_format"] == "xml"
    assert payload["data"]["format"] == "text"
    assert payload["data"]["extractor"] == "fake_ext"
    assert Path(payload["data"]["path"]) == output
    assert output.read_text(encoding="utf-8").startswith("EXTRACTED[xml]")


def test_extract_default_output(cli: CliRunner, tmp_path: Path) -> None:
    source = tmp_path / "paper.xml"
    source.write_bytes(b"<article><body><p>Hello CRISPR</p></body></article>")
    result = cli.invoke(app, ["extract", str(source), "--json"])
    assert result.exit_code == 0
    assert Path(json.loads(result.stdout)["data"]["path"]) == source.with_suffix(".txt")
    assert source.with_suffix(".txt").exists()


def test_extract_errors(cli: CliRunner, tmp_path: Path) -> None:
    missing = cli.invoke(app, ["extract", str(tmp_path / "missing.xml"), "--json"])
    assert missing.exit_code == 2
    assert json.loads(missing.stdout)["error"]["code"] == "USAGE"
    source = tmp_path / "paper.txt"
    source.write_text("already text", encoding="utf-8")
    unsupported = cli.invoke(app, ["extract", str(source), "--json"])
    assert unsupported.exit_code == 2
    assert json.loads(unsupported.stdout)["error"]["code"] == "USAGE"
    xml = tmp_path / "paper.xml"
    xml.write_bytes(b"<article>")
    mismatch = cli.invoke(
        app, ["extract", str(xml), "--output", str(tmp_path / "paper.pdf"), "--json"]
    )
    assert mismatch.exit_code == 2
    assert json.loads(mismatch.stdout)["error"]["code"] == "USAGE"


def test_sources_lists_all_roles(cli: CliRunner) -> None:
    result = cli.invoke(app, ["sources", "--json"])
    data = json.loads(result.stdout)["data"]
    assert set(data) == {"searcher", "metadata", "locator", "downloader", "extractor"}
    assert data["searcher"][0]["name"] == "fake"
    assert {m["name"] for m in data["metadata"]} == {"fake", "fake2"}
    assert data["downloader"][0]["name"] == "fake_dl"
    assert data["extractor"][0]["name"] == "fake_ext"
    removed = cli.invoke(app, ["providers", "--json"])
    assert removed.exit_code == 2


def test_cache_clear_all_and_stats(
    cli: CliRunner, services: Services, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cache_cmd, "Cache", lambda: services.cache)
    output = tmp_path / "paper.pdf"
    fetched = cli.invoke(app, ["fetch", "doi:10.1000/fake1", "--output", str(output), "--json"])
    assert fetched.exit_code == 0

    stats = cli.invoke(app, ["cache", "stats", "--json"])
    assert stats.exit_code == 0
    data = json.loads(stats.stdout)["data"]
    assert data["artifact_files"] == 1
    assert data["artifact_size_bytes"] > 0

    cleared = cli.invoke(app, ["cache", "clear", "--all", "--json"])
    assert cleared.exit_code == 0
    assert json.loads(cleared.stdout)["data"] == {
        "cleared": data["entries"],
        "artifacts_cleared": True,
    }
    assert not (services.cache.root / "papers").exists()


def test_cache_gc_removes_orphans(
    cli: CliRunner, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cache_cmd, "Cache", lambda: services.cache)
    orphan, _ = services.cache.store_file(b"orphan", "txt")
    result = cli.invoke(app, ["cache", "gc", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"] == {"removed": 1}
    assert not orphan.exists()


def test_schema_command(cli: CliRunner) -> None:
    result = cli.invoke(app, ["schema", "get"])
    assert result.exit_code == 0
    assert "Paper" in json.loads(result.stdout)
    for command, model in (
        ("locate", "FullTextLinks"),
        ("download", "DownloadedFullText"),
        ("extract", "ExtractedFullText"),
        ("fetch", "FullText"),
    ):
        result = cli.invoke(app, ["schema", command])
        assert result.exit_code == 0
        assert model in json.loads(result.stdout)
    result = cli.invoke(app, ["schema", "bogus"])
    assert result.exit_code == 2


def test_config_set_get_list(cli: CliRunner, tmp_path: Path) -> None:
    config_path = str(tmp_path / "config.toml")
    result = cli.invoke(
        app,
        [
            "--config",
            config_path,
            "config",
            "set",
            "plugins.unpaywall.email",
            "me@lab.org",
            "--json",
        ],
    )
    assert result.exit_code == 0
    result = cli.invoke(
        app, ["--config", config_path, "config", "get", "plugins.unpaywall.email", "--json"]
    )
    assert json.loads(result.stdout)["data"]["value"] == "me@lab.org"
    result = cli.invoke(app, ["--config", config_path, "config", "list", "--json"])
    assert result.exit_code == 0
    result = cli.invoke(app, ["--config", config_path, "config", "path", "--json"])
    assert json.loads(result.stdout)["data"]["path"] == config_path


def test_force_utf8_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: GBK Windows console must not crash on non-ASCII output."""
    out = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    err = io.TextIOWrapper(io.BytesIO(), encoding="gbk")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    _force_utf8_streams()
    assert out.encoding == "utf-8"
    assert err.encoding == "utf-8"
    print("café 中文 é", file=out)  # must not raise UnicodeEncodeError
    out.flush()


def test_help_lists_available_plugins_and_descriptions() -> None:
    """--source/--locator/... help shows installed plugin names; no bare options."""
    runner = CliRunner(env={"COLUMNS": "200", "TERMINAL_WIDTH": "200"})
    search = runner.invoke(app, ["search", "--help"])
    assert search.exit_code == 0
    assert f"default: {load_config().general.default_source}" in search.stdout
    assert "general.default_source" not in search.stdout
    for name in ("pubmed", "europepmc", "crossref", "openalex", "semantic_scholar"):
        assert name in search.stdout
    for description in (
        "Pagination cursor",
        "Author name filter",
        "Journal name filter",
        "Publication year lower bound",
        "Publication year upper bound",
        "Restrict to open-access papers",
        "Per-source result cap",
    ):
        assert description in search.stdout
    got = runner.invoke(app, ["get", "--help"])
    assert got.exit_code == 0
    assert "unpaywall" in got.stdout
    assert "Comma-separated Paper fields to keep" in got.stdout
    assert "openalex:/s2:/arxiv:" in got.stdout
    fetched = runner.invoke(app, ["fetch", "--help"])
    assert fetched.exit_code == 0
    for name in ("pmc_oa", "http_direct", "jats"):
        assert name in fetched.stdout
    assert "default: safe article title in the current directory" in fetched.stdout
    assert "duplicate default title gets an ID suffix" in fetched.stdout
    assert "Output filename" in fetched.stdout
    assert "Output directory" not in fetched.stdout
    assert "One ID" in fetched.stdout
    assert "Batch output" not in fetched.stdout
    expected_default = ", ".join(load_config().fetch.locators) or "all"
    assert f"'all' forces every registered locator (default: {expected_default})" in fetched.stdout
    for command, description in (
        ("locate", "Filter candidates"),
        ("download", "Output filename"),
        ("extract", "Output text filename"),
    ):
        help_result = runner.invoke(app, [command, "--help"])
        assert help_result.exit_code == 0
        assert description in help_result.stdout
        assert "[default:" not in help_result.stdout
    locate_help = runner.invoke(app, ["locate", "--help"]).stdout
    for name in ("europepmc", "openalex", "pmc_oa", "unpaywall"):
        assert name in locate_help
    download_help = runner.invoke(app, ["download", "--help"]).stdout
    assert "http_direct" in download_help
    assert "europepmc" not in download_help
    assert "pmc_oa" not in download_help
    extract_help = runner.invoke(app, ["extract", "--help"]).stdout
    for name in ("jats", "pypdf"):
        assert name in extract_help
    root = runner.invoke(app, ["--help"])
    assert "Show the version and exit" in root.stdout
    config_set = runner.invoke(app, ["config", "set", "--help"])
    assert "Dotted key" in config_set.stdout
    assert "TOML literal" in config_set.stdout


def test_fetch_locator_comma_separated(cli: CliRunner, tmp_path: Path) -> None:
    result = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--locator",
            "fake",
            "--output",
            str(tmp_path / "paper.pdf"),
            "--json",
        ],
    )
    assert result.exit_code == 0
    bad = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--locator",
            "nope,fake",
            "--output",
            str(tmp_path / "paper.pdf"),
            "--json",
        ],
    )
    assert bad.exit_code == 2
    assert json.loads(bad.stdout)["error"]["code"] == "USAGE"


def test_fetch_locator_repeated_and_mixed(cli: CliRunner, tmp_path: Path) -> None:
    repeated = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--locator",
            "fake",
            "--locator",
            "fake",
            "--output",
            str(tmp_path / "repeated.pdf"),
            "--json",
        ],
    )
    assert repeated.exit_code == 0
    mixed = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--locator",
            "fake,fake",
            "--locator",
            "fake",
            "--output",
            str(tmp_path / "mixed.pdf"),
            "--json",
        ],
    )
    assert mixed.exit_code == 0


def test_fetch_locators_config_default(cli: CliRunner, services: Services, tmp_path: Path) -> None:
    services.config.fetch.locators = ["fake"]
    result = cli.invoke(
        app, ["fetch", "doi:10.1000/fake1", "--output", str(tmp_path / "paper.pdf"), "--json"]
    )
    assert result.exit_code == 0


def test_search_multi_source(cli: CliRunner, services: Services) -> None:
    from paper_tools.core.models import Paper, SearchPage
    from paper_tools.core.plugins import PluginMeta
    from paper_tools.core.query import Query

    class SecondSearcher:
        meta = PluginMeta(name="fake_b", version="0.1.0")

        def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage:
            return SearchPage(
                items=[Paper(title="Other", identifiers={"doi": "10.1000/other"})],
                total=1,
                source="fake_b",
            )

    services.registry.register("searcher", SecondSearcher())
    for args in (
        ["--source", "fake,fake_b"],
        ["--source", "fake", "--source", "fake_b"],
        ["--source", "all"],
    ):
        result = cli.invoke(app, ["search", "CRISPR", *args, "--json"])
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)["data"]
        assert len(data["items"]) == 3
        assert data["source"] in {"fake,fake_b", "fake_b,fake"}
    bad = cli.invoke(app, ["search", "CRISPR", "--source", "nope", "--json"])
    assert bad.exit_code == 2


def test_fetch_locator_all_overrides_config(
    cli: CliRunner, services: Services, tmp_path: Path
) -> None:
    services.config.fetch.locators = ["nope"]
    result = cli.invoke(
        app,
        [
            "fetch",
            "doi:10.1000/fake1",
            "--locator",
            "all",
            "--output",
            str(tmp_path / "paper.pdf"),
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["source_url"] == "https://example.org/paper.pdf"
