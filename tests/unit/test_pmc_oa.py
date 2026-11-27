"""PMC Article Datasets Locator tests: ID conversion and AWS metadata."""

from __future__ import annotations

import httpx
import pytest
import respx

from paper_tools.core.models import Paper
from paper_tools.core.plugins import PluginContext
from paper_tools.plugins.pmc_oa import IDCONV, S3_BASE, PmcOaLocator

VERSION = "PMC123.1"
PDF_URL = f"{S3_BASE}/{VERSION}/{VERSION}.pdf"
XML_URL = f"{S3_BASE}/{VERSION}/{VERSION}.xml"
METADATA_URL = f"{S3_BASE}/{VERSION}/{VERSION}.json"
RECORD = {
    "pmcid": "PMC123",
    "pmid": 999,
    "doi": "10.1234/abc",
    "versions": [{"pmcid": VERSION, "current": True}],
}
METADATA = {
    "pmcid": "PMC123",
    "version": 1,
    "license_code": "CC BY-NC-ND",
    "pdf_url": f"s3://pmc-oa-opendata/{VERSION}/{VERSION}.pdf?md5=pdf-md5",
    "xml_url": f"s3://pmc-oa-opendata/{VERSION}/{VERSION}.xml?md5=xml-md5",
}


def mock_lookup(record: dict[str, object] | None = RECORD) -> None:
    records = [record] if record else []
    respx.get(IDCONV).mock(
        return_value=httpx.Response(200, json={"status": "ok", "records": records})
    )


def mock_metadata(metadata: dict[str, object] = METADATA) -> None:
    respx.get(METADATA_URL).mock(return_value=httpx.Response(200, json=metadata))


@respx.mock
def test_locator_yields_direct_pdf_and_xml(plugin_ctx: PluginContext) -> None:
    mock_lookup()
    mock_metadata()
    candidates = PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmcid": "PMC123"}))
    assert {(c.url, c.format) for c in candidates} == {
        (f"{PDF_URL}?md5=pdf-md5", "pdf"),
        (f"{XML_URL}?md5=xml-md5", "xml"),
    }
    assert all(c.locator == ["pmc_oa"] for c in candidates)
    assert all(c.license == "cc-by-nc-nd" for c in candidates)


@respx.mock
@pytest.mark.parametrize(("kind", "value"), [("pmid", "999"), ("doi", "10.1234/abc")])
def test_locator_resolves_identifier_via_idconv(
    plugin_ctx: PluginContext, kind: str, value: str
) -> None:
    mock_lookup()
    mock_metadata()
    candidates = PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={kind: value}))
    assert [candidate.format for candidate in candidates] == ["pdf", "xml"]


@respx.mock
def test_locator_selects_current_version(plugin_ctx: PluginContext) -> None:
    mock_lookup(
        {
            **RECORD,
            "versions": [
                {"pmcid": "PMC123.1", "current": False},
                {"pmcid": "PMC123.2", "current": True},
            ],
        }
    )
    respx.get(f"{S3_BASE}/PMC123.2/PMC123.2.json").mock(
        return_value=httpx.Response(
            200,
            json={
                **METADATA,
                "pdf_url": None,
                "xml_url": "s3://pmc-oa-opendata/PMC123.2/PMC123.2.xml?md5=xml-md5",
            },
        )
    )
    candidates = PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmcid": "PMC123"}))
    assert [(c.url, c.format) for c in candidates] == [
        (f"{S3_BASE}/PMC123.2/PMC123.2.xml?md5=xml-md5", "xml")
    ]


@respx.mock
def test_locator_no_record(plugin_ctx: PluginContext) -> None:
    mock_lookup(None)
    assert PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmid": "999"})) == []


@respx.mock
def test_locator_embargoed_record(plugin_ctx: PluginContext) -> None:
    mock_lookup({**RECORD, "live": False})
    assert PmcOaLocator(plugin_ctx).resolve(Paper(identifiers={"pmcid": "PMC123"})) == []


def test_locator_no_identifiers(plugin_ctx: PluginContext) -> None:
    assert PmcOaLocator(plugin_ctx).resolve(Paper()) == []
