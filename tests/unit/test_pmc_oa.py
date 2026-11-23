"""PMC OA Subset plugin tests: OA service XML replay + in-memory tar.gz packages."""

from __future__ import annotations

import io
import tarfile

import httpx
import pytest
import respx

from paper_tools.core.errors import UpstreamError
from paper_tools.core.models import FullTextCandidate, Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.plugins.pmc_oa import IDCONV, OA_SERVICE, PmcOaDownloader, PmcOaLocator
from tests.conftest import PDF_BYTES, XML_BYTES

TGZ_URL = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/ab/cd/PMC123.tar.gz"
OA_XML = (
    b"<OA><records><record id='PMC123'>"
    b"<link format='tgz' href='ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/ab/cd/PMC123.tar.gz'/>"
    b"</record></records></OA>"
)
OA_ERROR_XML = b"<OA><error code='idIsNotOpenAccess'>not in OA subset</error></OA>"


def make_package(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


PACKAGE = make_package({"PMC123/paper.nxml": XML_BYTES, "PMC123/paper.pdf": PDF_BYTES})


@respx.mock
def test_locator_tgz_yields_xml_and_pdf(plugin_ctx: PluginContext) -> None:
    respx.get(OA_SERVICE).mock(return_value=httpx.Response(200, content=OA_XML))
    candidates = PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmcid": "PMC123"}))
    assert {(c.url, c.format) for c in candidates} == {(TGZ_URL, "xml"), (TGZ_URL, "pdf")}
    assert all(c.locator == "pmc_oa" for c in candidates)


@respx.mock
def test_locator_resolves_pmid_via_idconv(plugin_ctx: PluginContext) -> None:
    respx.get(IDCONV).mock(
        return_value=httpx.Response(200, json={"records": [{"pmcid": "PMC123"}]})
    )
    respx.get(OA_SERVICE).mock(return_value=httpx.Response(200, content=OA_XML))
    candidates = PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"}))
    assert candidates


@respx.mock
def test_locator_not_open_access(plugin_ctx: PluginContext) -> None:
    respx.get(OA_SERVICE).mock(return_value=httpx.Response(200, content=OA_ERROR_XML))
    assert PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmcid": "PMC123"})) == []


def test_locator_no_identifiers(plugin_ctx: PluginContext) -> None:
    assert PmcOaLocator(plugin_ctx).resolve(Paper()) == []


@respx.mock
@pytest.mark.parametrize(("fmt", "expected"), [("xml", XML_BYTES), ("pdf", PDF_BYTES)])
def test_downloader_extracts_from_package(
    plugin_ctx: PluginContext, fmt: str, expected: bytes
) -> None:
    respx.get(TGZ_URL).mock(return_value=httpx.Response(200, content=PACKAGE))
    candidate = FullTextCandidate(url=TGZ_URL, format=fmt, locator="pmc_oa")  # type: ignore[arg-type]
    artifact = PmcOaDownloader(plugin_ctx).download(candidate)
    assert artifact.content == expected
    assert artifact.downloader == "pmc_oa"


@respx.mock
def test_downloader_missing_member(plugin_ctx: PluginContext) -> None:
    pdf_only = make_package({"PMC123/paper.pdf": PDF_BYTES})
    respx.get(TGZ_URL).mock(return_value=httpx.Response(200, content=pdf_only))
    candidate = FullTextCandidate(url=TGZ_URL, format="xml", locator="pmc_oa")
    with pytest.raises(UpstreamError):
        PmcOaDownloader(plugin_ctx).download(candidate)


@respx.mock
def test_direct_pdf_link(plugin_ctx: PluginContext) -> None:
    pdf_url = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/ab/cd/PMC123.pdf"
    oa_xml = (
        b"<OA><records><record id='PMC123'>"
        b"<link format='pdf' href='" + pdf_url.encode() + b"'/>"
        b"</record></records></OA>"
    )
    respx.get(OA_SERVICE).mock(return_value=httpx.Response(200, content=oa_xml))
    respx.get(pdf_url).mock(return_value=httpx.Response(200, content=PDF_BYTES))
    candidates = PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmcid": "PMC123"}))
    assert [(c.url, c.format) for c in candidates] == [(pdf_url, "pdf")]
    artifact = PmcOaDownloader(plugin_ctx).download(candidates[0])
    assert artifact.content == PDF_BYTES


def test_supports_only_pmc_oa_candidates(plugin_ctx: PluginContext) -> None:
    dl = PmcOaDownloader(plugin_ctx)
    assert dl.supports(FullTextCandidate(url=TGZ_URL, format="xml", locator="pmc_oa"))
    assert not dl.supports(FullTextCandidate(url=TGZ_URL, format="xml", locator="unpaywall"))
