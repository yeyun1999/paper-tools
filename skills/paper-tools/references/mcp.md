# MCP 使用说明

## 启动

```bash
uv sync --extra mcp
paper-tools mcp
```

MCP 使用 stdio；协议外日志必须走 stderr。客户端配置示例：

```json
{
  "mcpServers": {
    "paper-tools": {
      "command": "paper-tools",
      "args": ["mcp"]
    }
  }
}
```

确保 `paper-tools` 已安装并位于客户端可访问的 `PATH` 中。

## 工具

| 工具 | 用途 | 主要参数 |
|---|---|---|
| `search_papers` | 检索文献 | `query`、`source`、`limit`、`cursor`、`author`、`journal`、`year_from`、`year_to`、`oa_only`、`raw`、`enrich` |
| `get_paper` | 补全单篇元数据 | `identifier`、`source` |
| `fetch_fulltext` | 一键获取 OA 全文 | `identifier`、`format`、`output`、`locator`、`downloader`、`extractor` |
| `list_sources` | 列出五类插件 | 无参数 |

MCP 当前不暴露独立的 `locate` / `download` / `extract`；分阶段能力使用 CLI。

## search_papers

```json
{
  "query": "CRISPR base editing",
  "source": "pubmed,europepmc",
  "limit": 20,
  "enrich": true
}
```

- `source` 为逗号分隔插件名；`all` 搜索全部来源。
- `limit` 是每个来源的上限，范围 1–100。
- `cursor` 原样回传 `data.next_cursor`。
- `raw` 是搜索器原生语法，与其他查询字段互斥。

## get_paper

```json
{
  "identifier": "pmid:38308006",
  "source": "pubmed"
}
```

`source` 省略时按元数据补全优先级选择；也可限定单个 metadata 插件。

## fetch_fulltext

```json
{
  "identifier": "pmcid:PMC13434336",
  "format": "text",
  "output": "papers/paper.txt",
  "locator": "pmc_oa,europepmc",
  "downloader": "http_direct",
  "extractor": "jats"
}
```

- `format`：`pdf`、`xml` 或 `text`；省略时按输出扩展名推断，默认 PDF。
- `locator`：逗号分隔；`all` 强制全部定位器。
- `downloader` / `extractor`：强制指定插件；省略时使用候选推荐或默认选择。
- 闭源文献返回 `FULLTEXT_UNAVAILABLE`，details 中包含出版商链接。

## 返回契约

成功：

```json
{
  "schema_version": "1.2",
  "command": "search",
  "data": {},
  "warnings": []
}
```

失败：

```json
{
  "schema_version": "1.2",
  "error": {
    "code": "UPSTREAM",
    "message": "Request failed",
    "details": {}
  }
}
```

MCP 业务错误作为 error envelope 返回，不抛异常，也没有进程退出码。agent 必须检查 `error.code` 后决定重试、修正参数或提示用户。
