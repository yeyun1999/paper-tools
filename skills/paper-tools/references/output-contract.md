# 输出契约与错误

## Envelope

当前 `schema_version` 为 `1.3`。

```json
{
  "schema_version": "1.3",
  "command": "search",
  "data": {},
  "warnings": []
}
```

```json
{
  "schema_version": "1.3",
  "error": {
    "code": "USAGE",
    "message": "Invalid arguments",
    "details": {}
  }
}
```

## 主要 data 模型

| 命令 | data | 关键字段 |
|---|---|---|
| `search` | `SearchPage` | `items`、`total`、`next_cursor`、`source` |
| `get` | `Paper` | `title`、`identifiers`、`authors`、`abstract`、`oa_status`、`fulltext_links`、文献计量字段 |
| `locate` | `FullTextLinks` | `paper`、`candidates` |
| `download` | `DownloadedFullText` | `source_url`、`format`、`path`、`sha256`、`downloader` |
| `extract` | `ExtractedFullText` | `source_path`、`source_format`、`path`、`sha256`、`extractor` |
| `fetch` | `FullText` | `paper`、`format`、`path`、`sha256`、`source_url`、`downloader`、`extractor`、`extracted_from` |

`FullTextCandidate`：

```json
{
  "url": "https://example.org/paper.xml",
  "format": "xml",
  "locator": ["europepmc", "openalex"],
  "downloaders": ["http_direct"],
  "license": "cc-by"
}
```

- `format`：`pdf`、`xml`、`text` 或 `landing`。
- `locator`：发现该候选的定位器列表；同 URL+格式会合并。
- `downloaders`：按推荐尝试顺序排列的下载器；landing 为空。
- `Paper.fulltext_links` 是搜索/补全阶段捕获的链接；`locate.candidates` 是最终合并、排序并补充下载器推荐的结果。

## Paper 文献计量字段

- `issn`：期刊 ISSN；优先使用印刷版/来源提供的首选值。
- `impact_factor`：期刊影响因子；无可靠来源时为 `null`，不以 OpenAlex 引用均值替代。
- `cited_by_count`：被引用次数；`references_count`：参考文献数；未知为 `null`，真实零值为 `0`。
- `cited_by_papers` / `reference_papers`：引用关系论文摘要列表。每项包含 `title`、
  `identifiers`、`authors`、`year`，不递归包含引用关系。列表仅反映现有上游响应已提供的数据，
  不保证完整；为空表示未获得条目。

## 默认字段投影

CLI 与 MCP 使用同一套配置：

- `search`：`title,identifiers.doi,year,cited_by_count,abstract`
- `get`：`title,identifiers.doi,year,cited_by_count,journal,oa_status,abstract`

可通过 `[output]` 的 `search_fields` / `get_fields` 分别修改。显式 `--fields` 或 MCP
`fields` 优先于配置；`all` 返回完整 Paper，并要求 `get` 或启用补全的 `search` 尝试补全
全部 Paper 字段。对象路径用 `.`，数组路径用 `[]`，例如 `identifiers.doi` 返回
`{"identifiers":{"doi":"..."}}`，`authors[].name` 返回 `{"authors":[{"name":"..."}]}`。
数组投影保留元素位置，缺失叶字段输出空对象；不再把 `doi` 等标识符提升到顶层。
字段投影不改变 `SearchPage` 的分页字段，也不会让 `search` 自动启用补全；`get` 与
启用补全的 `search` 会按所选字段继续补全；补全链不维护汇总缓存，上游响应由各 provider
的 HTTP 缓存复用。

## JSON 与 NDJSON

- 单 ID 命令始终输出一个 JSON 对象。
- 多 ID `get` 在 `--json` 下输出 NDJSON，每行一个成功或错误 envelope。
- 批量 `get` 退出码取第一个失败项；失败不中断后续 ID。

## 退出码

| 码 | error.code | 含义 | 建议 |
|---|---|---|---|
| 0 | — | 成功，包括空结果 | 正常消费 data |
| 2 | `USAGE` | 参数或查询组合错误 | 修正参数，不重试 |
| 3 | `UPSTREAM` / `NOT_FOUND` | 上游失败或元数据未找到 | 稍后重试或换源 |
| 4 | `FULLTEXT_UNAVAILABLE` | 无 OA 全文 | 展示出版商链接 |
| 5 | `CONFIG` | 缺少配置或配置无效 | 修复配置后重试 |

## 流位置

- JSON 成功：stdout。
- 单篇业务错误：stdout 结果流。
- 进程级用法/配置错误：stderr。
- 日志、插件加载警告和文本警告：stderr。
