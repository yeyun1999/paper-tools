"""可选角色骨架：Locator / Downloader / Extractor。

实现后在 pyproject.toml 取消对应 entry-point 注释即可注册。
合规硬约束：只允许官方 API 与 OA 来源；禁止任何绕过付费墙的实现。
"""

from __future__ import annotations

from paper_tools.core.models import Artifact, FullTextCandidate, Paper
from paper_tools.core.plugins import PluginContext, PluginMeta


class ExampleLocator:
    """定位 OA 副本：返回候选列表（url + format + locator 列表）。"""

    meta = PluginMeta(name="example", version="0.1.0", description="Template OA locator")

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def resolve(self, paper: Paper) -> list[FullTextCandidate]:
        # TODO: 查询你的 OA 定位 API，返回候选。format: pdf|xml|text|landing。
        # landing 候选仅作兜底展示，不会被下载。
        raise NotImplementedError


class ExampleDownloader:
    """下载候选 URL 为字节产物。通用 HTTP 下载可直接复用内置 http_direct。"""

    meta = PluginMeta(name="example", version="0.1.0", description="Template downloader")
    formats = frozenset({"pdf", "xml"})

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def supports(self, candidate: FullTextCandidate) -> bool:
        # 按 URL 前缀 / locator 列表判断是否由本下载器处理（专用先于通用）。
        return self.meta.name in candidate.locator

    def download(self, candidate: FullTextCandidate) -> Artifact:
        # TODO: 特殊协议（如 tar.gz 打包）在此实现；内存解包，不落盘解压。
        # 魔数/体积/XML 合法性校验由 FetchService 统一执行，无需重复。
        raise NotImplementedError


class ExampleExtractor:
    """把下载产物提取为纯文本（如 PDF/XML -> text）。"""

    meta = PluginMeta(name="example", version="0.1.0", description="Template extractor")
    source_formats = frozenset({"pdf"})

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def extract(self, data: bytes, *, source_format: str) -> str:
        # TODO: 解析 data 为纯文本；不可解析/空文本抛 UpstreamError。
        # 不可信 XML 必须用 defusedxml。
        raise NotImplementedError
