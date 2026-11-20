"""PDF -> plain text extractor via pypdf (optional ``text`` extra).

Without the extra installed, entry-point discovery skips this plugin with a
load warning; the fetch service then reports a ConfigError pointing at the extra.
"""

from __future__ import annotations

import io

import pypdf
from pypdf.errors import PdfReadError

from paper_search.core.errors import UpstreamError
from paper_search.core.plugins import PluginContext, PluginMeta


class PypdfExtractor:
    meta = PluginMeta(name="pypdf", version="0.1.0", description="PDF text extraction via pypdf")
    source_formats = frozenset({"pdf"})

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def extract(self, data: bytes, *, source_format: str) -> str:
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except PdfReadError as exc:
            raise UpstreamError("Cannot read PDF for text extraction") from exc
        text = "\n\n".join(page for page in pages if page)
        if not text:
            raise UpstreamError("pypdf extracted no text (scanned/image-only PDF?)")
        return text
