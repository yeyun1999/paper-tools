"""M0 smoke tests: CLI entry point is alive."""

from typer.testing import CliRunner

from paper_search import __version__
from paper_search.cli.app import app


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Literature search" in result.stdout
