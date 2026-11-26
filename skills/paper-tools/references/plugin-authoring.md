# 插件开发参考

## 角色

| 角色 | 职责 | 入口点组 |
|---|---|---|
| Searcher | 关键词检索，返回 `SearchPage` | `paper_tools.searchers` |
| MetadataProvider | 按标识符补全 `Paper` | `paper_tools.metadata` |
| Locator | 将文献元数据解析为 `FullTextCandidate` | `paper_tools.locators` |
| Downloader | 将候选 URL 下载为 `Artifact` | `paper_tools.downloaders` |
| Extractor | PDF/JATS XML → 非空 text | `paper_tools.extractors` |

## 注册

```toml
[project.entry-points."paper_tools.locators"]
my_source = "my_package.plugin:MyLocator"

[project.entry-points."paper_tools.downloaders"]
my_downloader = "my_package.plugin:MyDownloader"
```

安装后运行 `paper-tools sources --json` 检查是否加载。同名注册会覆盖内置插件并产生 warning。

## Locator

输入始终是 `Paper`，可能只有 DOI/PMID/PMCID 等标识符。若上游需要 ID 而非 URL，在 Locator 中构造请求 URL：

```python
return [
    FullTextCandidate(
        url="https://example.org/efetch?db=pmc&id=PMC123&retmode=xml",
        format="xml",
        locator=["my_source"],
    )
]
```

- `locator` 是列表，至少包含 `[self.meta.name]`。
- `format` 使用 `pdf`、`xml`、`text` 或 `landing`。
- landing 只用于展示，不会下载。
- 服务层按 URL+格式合并候选，并聚合 locator 列表。

## Downloader

```python
class MyDownloader:
    meta = PluginMeta(name="my_downloader", version="0.1.0")
    formats = frozenset({"pdf", "xml"})

    def supports(self, candidate: FullTextCandidate) -> bool:
        return candidate.url.startswith("https://example.org/")

    def download(self, candidate: FullTextCandidate) -> Artifact:
        content = self.ctx.http.get_bytes(candidate.url)
        return Artifact(
            format=candidate.format,
            content=content,
            source_url=candidate.url,
            downloader=self.meta.name,
            license=candidate.license,
        )
```

- `supports()` 是程序判断链接支持范围的入口，应轻量、无网络请求。
- `download()` 可实现多线程、分片、POST 或特殊重试；遵守上游限流。
- `Artifact.downloader` 必须等于 `meta.name`。
- PDF/XML 最终校验由服务层统一执行，插件无需重复。
- 当前内置下载器只有 `http_direct`；普通 GET 直链无需新增 Downloader。

## Extractor

实现 `extract(data, *, source_format) -> str`，返回非空文本。不可解析或空文本抛 `UpstreamError`。不可信 XML 必须使用 `defusedxml`。

## 验证

- 为每个上游添加 respx 离线回放测试。
- 真实 API 冒烟测试使用 `live` 标记。
- 通过角色契约：URL/格式合法、产物格式匹配、溯源插件名正确、提取文本非空。
