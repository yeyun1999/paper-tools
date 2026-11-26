# 输出契约与错误

## Envelope

当前 `schema_version` 为 `1.2`。

```json
{
  "schema_version": "1.2",
  "command": "search",
  "data": {},
  "warnings": []
}
```

```json
{
  "schema_version": "1.2",
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
| `get` | `Paper` | `title`、`identifiers`、`authors`、`abstract`、`oa_status`、`fulltext_links` |
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
