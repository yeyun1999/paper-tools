# MCP Agent 使用指南

## 启动

安装 MCP 扩展并启动 stdio 服务：

```bash
uv sync --extra mcp
paper-tools mcp
```

客户端配置：

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

## 工具选择

| 工具 | 何时使用 |
|---|---|
| `list_sources` | 不确定可用搜索器、定位器、下载器或提取器时 |
| `search_papers` | 按关键词、字段或 raw 语法检索文献 |
| `get_paper` | 已确定文献标识符，需要完整元数据 |
| `locate_fulltext` | 已确定文献标识符，需要检查 OA 候选链接、格式和下载器推荐，但不下载 |
| `fetch_fulltext` | 已确定文献标识符，需要 OA 全文文件或纯文本 |

MCP 当前不暴露独立的 `download` / `extract`。需要直接下载候选 URL 或对本地文件分阶段提取时，使用 CLI。

## 推荐工作流

### 1. 检索

调用 `search_papers`，根据问题选择搜索策略：

- 宽泛探索：使用短关键词，先获取高相关结果。
- 精确检索：使用作者、期刊、年份等结构化条件。
- 复杂条件：使用目标搜索器的 `raw` 语法，并加载对应 raw 参考文件。
- 跨源查全：选择多个来源或 `all`，随后按 DOI/PMID 去重。

默认返回的文献可能是浅记录。摘要、作者、OA 状态或出版类型不足时，启用 `enrich`，或对选中文献调用 `get_paper`。

### 2. 选择文献

从检索结果中优先选择：

- DOI/PMID/PMCID 完整的记录。
- 标题与目标问题直接相关的记录。
- 标注为 OA 或已有全文链接的记录。

不要把标题相似但标识符冲突的记录自动合并；必要时调用 `get_paper` 核实。

### 3. 补全元数据

对选中文献调用 `get_paper`。优先使用已有标识符；只有当前来源信息不足时再限定其他 metadata 插件。

### 4. 检查全文候选（可选）

调用 `locate_fulltext` 查看排序后的 OA 候选，不下载文件：

- 检查 `format`、`locator`、`downloaders` 和 `license`。
- 用 `format=pdf|xml|text` 过滤候选；省略时包含 landing page。
- 用 `locator` 限定定位器，传 `all` 强制使用全部已注册定位器。

### 5. 获取全文

调用 `fetch_fulltext`：

- 需要阅读或 AI 分析时，优先请求 text。
- 需要保留排版、图表或原始全文时，请求 PDF 或 XML。
- 输出路径应明确、可写，并使用与目标格式一致的扩展名。
- 让程序使用默认定位器、下载器和提取器；只有诊断或特殊需求时才强制指定插件。

### 6. 消费结果

- 始终先检查返回对象是否包含 `error`。
- 成功时读取 `data`，并检查 `warnings` 是否影响结果可用性。
- 返回模型的完整字段见 `references/output-contract.md`，不要在每次调用时重复推断 schema。

## 分页与多源检索

- 有下一页时，原样回传 `next_cursor`；不要解析、截断或重新编码。
- 多源游标是不透明 token，可能以 `ms1.` 开头。
- 多源检索的 `limit` 是每个来源的上限，合并去重后结果可能更多。
- 跨源结果按 DOI 优先、PMID 次之、标题兜底去重；保留标识符最完整的记录。

## raw 检索

`raw` 使用目标搜索器的原生语法，不可跨源复制。使用前加载对应文件：

- PubMed：`references/raw/pubmed.md`
- Europe PMC：`references/raw/europepmc.md`
- Crossref：`references/raw/crossref.md`
- OpenAlex：`references/raw/openalex.md`
- Semantic Scholar：`references/raw/semantic-scholar.md`

raw 与其他查询字段互斥。需要组合条件时，把条件写进原生表达式；需要多个同义词时，使用上游支持的 OR，或分别查询后按标识符合并。

## 错误处理

MCP 业务错误作为 error envelope 返回，不抛异常，也没有进程退出码。按 `error.code` 决策：

| code | Agent 动作 |
|---|---|
| `USAGE` | 修正参数或查询组合，不直接重试 |
| `NOT_FOUND` | 核实标识符，换 metadata 来源，或告知用户未找到 |
| `UPSTREAM` | 稍后重试；持续失败时换源或检查网络 |
| `FULLTEXT_UNAVAILABLE` | 展示出版商链接，说明非 OA；不尝试绕过付费墙 |
| `CONFIG` | 提示用户修复配置，例如 Unpaywall email 或 API key |

