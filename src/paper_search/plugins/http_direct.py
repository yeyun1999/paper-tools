"""Generic HTTP downloader: last-resort transfer for any direct http(s) URL."""

from __future__ import annotations

from paper_search.core.errors import UsageError
from paper_search.core.models import Artifact, FullTextCandidate
from paper_search.core.plugins import PluginContext, PluginMeta


class HttpDirectDownloader:
    meta = PluginMeta(
        name="http_direct", version="0.1.0", description="Plain HTTP(S) download fallback"
    )
    formats = frozenset({"pdf", "xml", "text"})

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def supports(self, candidate: FullTextCandidate) -> bool:
        return candidate.url.startswith(("http://", "https://"))

    def download(self, candidate: FullTextCandidate) -> Artifact:
        if candidate.format == "landing":
            raise UsageError("http_direct cannot download landing pages", url=candidate.url)
        content = self.ctx.http.get_bytes(candidate.url)
        return Artifact(
            format=candidate.format,
            content=content,
            source_url=candidate.url,
            downloader="http_direct",
            license=candidate.license,
        )
