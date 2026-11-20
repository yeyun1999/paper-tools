"""JATS XML -> plain text extractor (built-in, no extra dependencies)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from paper_search.core.errors import UpstreamError
from paper_search.core.plugins import PluginContext, PluginMeta

_BLOCK_TAGS = {"title", "p"}


def _local_tag(node: Any) -> str:
    tag = node.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _blocks(element: Any) -> list[str]:
    """Collect title/paragraph text in document order."""
    out: list[str] = []
    for node in element.iter():
        if _local_tag(node) in _BLOCK_TAGS:
            text = " ".join("".join(node.itertext()).split())
            if text:
                out.append(text)
    return out


class JatsExtractor:
    meta = PluginMeta(name="jats", version="0.1.0", description="JATS XML to plain text")
    source_formats = frozenset({"xml"})

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def extract(self, data: bytes, *, source_format: str) -> str:
        try:
            root = safe_xml_fromstring(data)
        except (ET.ParseError, DefusedXmlException) as exc:
            raise UpstreamError("Cannot parse JATS XML") from exc
        parts: list[str] = []
        title = root.find(".//article-meta/title-group/article-title")
        if title is not None:
            parts.append(" ".join("".join(title.itertext()).split()))
        for abstract in root.findall(".//article-meta/abstract"):
            parts.extend(_blocks(abstract))
        body = root.find(".//body")
        if body is not None:
            parts.extend(_blocks(body))
        text = "\n\n".join(p for p in parts if p)
        if not text.strip():
            raise UpstreamError("No extractable text in JATS XML")
        return text
