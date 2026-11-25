"""Generic http_direct downloader tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_tools.core.errors import UsageError
from paper_tools.core.models import FullTextCandidate
from paper_tools.core.plugins import PluginContext
from paper_tools.plugins.europepmc import fulltext_xml_url
from paper_tools.plugins.http_direct import HttpDirectDownloader
from paper_tools.plugins.pmc_oa import S3_BASE
from tests.conftest import PDF_BYTES


def test_supports_http_only(plugin_ctx: PluginContext) -> None:
    dl = HttpDirectDownloader(plugin_ctx)
    assert dl.supports(FullTextCandidate(url="https://x.org/a.pdf", format="pdf", locator=["l"]))
    assert not dl.supports(FullTextCandidate(url="ftp://x.org/a.pdf", format="pdf", locator=["l"]))


@pytest.mark.parametrize(
    ("url", "fmt"),
    [
        (fulltext_xml_url("PMC123"), "xml"),
        (f"{S3_BASE}/PMC123.1/PMC123.1.pdf", "pdf"),
    ],
)
def test_supports_builtin_source_urls(plugin_ctx: PluginContext, url: str, fmt: str) -> None:
    candidate = FullTextCandidate(url=url, format=fmt, locator=["europepmc"])  # type: ignore[arg-type]
    assert HttpDirectDownloader(plugin_ctx).supports(candidate)


@respx.mock
def test_download_pdf(plugin_ctx: PluginContext) -> None:
    respx.get("https://x.org/a.pdf").mock(return_value=httpx.Response(200, content=PDF_BYTES))
    candidate = FullTextCandidate(url="https://x.org/a.pdf", format="pdf", locator=["l"])
    artifact = HttpDirectDownloader(plugin_ctx).download(candidate)
    assert artifact.format == "pdf"
    assert artifact.content == PDF_BYTES
    assert artifact.downloader == "http_direct"


def test_landing_rejected(plugin_ctx: PluginContext) -> None:
    candidate = FullTextCandidate(url="https://x.org/page", format="landing", locator=["l"])
    with pytest.raises(UsageError):
        HttpDirectDownloader(plugin_ctx).download(candidate)
