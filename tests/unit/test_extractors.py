"""Extractor tests: JATS XML -> text and pypdf PDF -> text."""

from __future__ import annotations

import pytest

from paper_tools.core.errors import UpstreamError
from paper_tools.core.plugins import PluginContext
from paper_tools.plugins.jats import JatsExtractor
from paper_tools.plugins.pypdf_extractor import PypdfExtractor

JATS_XML = b"""<?xml version="1.0"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Base editing <italic>in vivo</italic></article-title>
      </title-group>
      <abstract>
        <p>Background text.</p>
        <p>Results text.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Introduction</title><p>Intro paragraph.</p></sec>
    <p>Conclusion.</p>
  </body>
</article>
"""


def minimal_pdf(text: str) -> bytes:
    """Hand-built single-page PDF with real text (valid xref offsets)."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    ).encode()
    return bytes(out)


def test_jats_extract(plugin_ctx: PluginContext) -> None:
    text = JatsExtractor(plugin_ctx).extract(JATS_XML, source_format="xml")
    assert "Base editing in vivo" in text
    assert "Background text." in text
    assert "Results text." in text
    assert "Introduction" in text
    assert "Intro paragraph." in text
    assert "Conclusion." in text
    assert text.index("Introduction") < text.index("Intro paragraph.")


def test_jats_empty_raises(plugin_ctx: PluginContext) -> None:
    with pytest.raises(UpstreamError):
        JatsExtractor(plugin_ctx).extract(b"<article/>", source_format="xml")


def test_jats_invalid_xml_raises(plugin_ctx: PluginContext) -> None:
    with pytest.raises(UpstreamError):
        JatsExtractor(plugin_ctx).extract(b"not xml at all", source_format="xml")


def test_pypdf_extract(plugin_ctx: PluginContext) -> None:
    text = PypdfExtractor(plugin_ctx).extract(minimal_pdf("Hello CRISPR"), source_format="pdf")
    assert "Hello CRISPR" in text


def test_pypdf_invalid_raises(plugin_ctx: PluginContext) -> None:
    with pytest.raises(UpstreamError):
        PypdfExtractor(plugin_ctx).extract(b"not a pdf", source_format="pdf")
