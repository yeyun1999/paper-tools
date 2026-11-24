# AI 助理使用指南（agent-usage）

paper-tools 为 AI 助理提供两条通道，契约完全一致（`schema_version 1.1`）：

1. **JSON CLI**：任意 shell 调用 `paper-tools ... --json`，按退出码分支。
2. **MCP 服务器**：`paper-tools mcp`（stdio），四个工具，返回同样的 envelope。

所有示例均在仓库根目录、`uv sync --all-extras` 后可直接执行（`uv run` 前缀可换成已激活环境的裸命令）。

## 0. 一次性配置

```bash
# Unpaywall OA 定位需要 email（官方 API 政策）
uv run paper-tools config set plugins.unpaywall.email you@example.com
# 可选：Crossref/OpenAlex polite pool
uv run paper-tools config set general.mailto you@example.com
# 可选：Semantic Scholar 无 key 共享限额很低，批量场景建议申请
uv run paper-tools config set plugins.semantic_scholar.api_key YOUR_KEY
# 可选：OpenAlex key（Authorization: Bearer，配后限流 5→10 req/s）
uv run paper-tools config set plugins.openalex.api_key YOUR_KEY
# 可选：默认 Locator 列表（空 = 全部；--locator 可临时覆盖：重复指定或逗号分隔，'all' 强制全部）
uv run paper-tools config set fetch.locators '["pmc_oa","europepmc"]'
```

密钥只进配置/环境变量，绝不出现在日志与 JSON 输出中。

## 1. shell 调用范式

约定：`--json` 时 **stdout 只有 JSON**（日志/警告走 stderr），可安全管道解析。

```bash
# 检索（浅记录，省上下文）；--enrich 补全摘要/OA 状态
uv run paper-tools search "CRISPR base editing" --source pubmed --limit 10 --json
uv run paper-tools search "CRISPR base editing" --source europepmc --oa-only --enrich --json

# 多源聚合：并发检索 + DOI 主键去重合并（identifiers 并集、sources 记录贡献源）
# --limit 是每源返回上限；合并去重后不截断，单页结果可超过 limit
uv run paper-tools search "CRISPR base editing" --source pubmed,europepmc --limit 10 --json
uv run paper-tools search "Array programming with NumPy" --source all --json

# 字段裁剪：只要标题/DOI/年份（identifiers 内的键会被提升）
uv run paper-tools search "CRISPR base editing" --fields title,doi,year --json

# 单篇完整元数据（补全链：pubmed→europepmc→crossref→openalex→s2→unpaywall）
uv run paper-tools get pmid:38308006 --json
uv run paper-tools get doi:10.1038/s41586-020-2649-2 --fields title,doi,abstract,oa_status --json

# 批量元数据：多个 ID 一次进程，NDJSON 逐行输出（单 ID 仍为单对象）
uv run paper-tools get pmid:38308006 doi:10.1038/s41586-020-2649-2 --fields title,doi,year --json
```

Paper 的 `fulltext_links` 字段（schema 1.1）在搜索/补全期就捕获源生的 OA 全文链接
（url/format/locator/license），AI 助理可据此直接判断全文可得性，无需先 fetch；
`fetch` 也会把这些链接并入候选池。

```bash
# OA 全文：pdf / xml / text（text 走 下载→提取 流水线，优先 XML）
uv run paper-tools fetch pmcid:PMC13434336 --output papers/paper.txt --json
uv run paper-tools fetch doi:10.1093/nar/gkag769 --format pdf --json
# 未指定 --output：当前目录使用安全化文章标题；重名追加 DOI/PMID 等 ID

# 分页：取 next_cursor 原样回传续传（多源时 next_cursor 是免转义的 'ms1.' 聚合游标；
# 单源游标是不透明字符串。多源 total 为去重前各源之和，近似值）
uv run paper-tools search "CRISPR" --limit 20 --json          # data.next_cursor
uv run paper-tools search "CRISPR" --limit 20 --cursor "<next_cursor>" --json

# 能力发现与契约
uv run paper-tools sources --json        # 五角色全部插件（检索/元数据/定位/下载/提取）
uv run paper-tools schema fetch          # FullText 的 JSON Schema
```

成功 envelope：

```json
{
  "schema_version": "1.1",
  "command": "fetch",
  "data": { "path": "papers/10.1093_nar_gkag769.txt", "format": "text",
            "sha256": "…", "source_url": "…", "downloader": "europepmc",
            "extractor": "jats", "extracted_from": "xml" },
  "warnings": []
}
```

## 2. 退出码处理

| 退出码 | error.code | 含义 | agent 建议动作 |
|---|---|---|---|
| 0 | — | 成功（空结果也是成功） | 正常消费 data |
| 2 | USAGE | 参数/用法错误 | 修正参数，不要重试 |
| 3 | UPSTREAM | 上游 API/网络失败（已自动退避重试 3 次） | 稍后重试或换 `--source`；details.status 含上游状态码 |
| 4 | FULLTEXT_UNAVAILABLE | 无 OA 全文 | 把 details.publisher_url 给用户，走机构权限；**不要尝试绕过付费墙** |
| 5 | CONFIG | 配置缺失 | 按 error.message 提示执行 `config set`（如 unpaywall email） |

进程级错误的 error envelope 在 **stderr**；`fetch` / `get` 的逐文献错误作为结果信封写在 **stdout**（单篇为单个 JSON 对象，批量 `get` 为 NDJSON 中的一行）。

```bash
uv run paper-tools fetch doi:10.1001/jama.2020.2648 --format pdf --json
# 退出码 4；stdout: {"error": {"code": "FULLTEXT_UNAVAILABLE", "details": {"publisher_url": "…"}}}
```

## 3. NDJSON 批量元数据

多 ID `get` 的 `--json` 输出 NDJSON：每行一个独立 envelope（成功或错误），单 ID 失败不中断批次；进程退出码取第一个失败行的错误码。单 ID 时输出单个 JSON 对象。

```bash
uv run paper-tools get pmid:38308006 doi:10.1000/missing --json > metadata.ndjson
```

逐行处理范式（Python）：

```python
import json

with open("metadata.ndjson", encoding="utf-8") as fh:
    for line in fh:
        env = json.loads(line)
        if "error" in env:
            code = env["error"]["code"]
            if code == "NOT_FOUND":
                print("未找到元数据")
            elif code == "UPSTREAM":
                print("上游失败，可稍后重试:", env["error"]["message"])
        else:
            print("OK:", env["data"].get("title") or env["data"].get("identifiers"))
```

`fetch` 每次只接受一个 ID，`--json` 始终返回单个 JSON 对象；批量获取全文时应逐篇调用，不能将多个 `fetch` 输出直接当作 NDJSON 解析。

批量建议：控制并发为 1（工具内部已按 host 限流）；重复 fetch 命中缓存（text 不会重复下载/提取）。

## 4. 错误恢复建议

- **UPSTREAM / 429**：HttpClient 已做指数退避 + Retry-After；仍失败时等待数十秒再试，或换源（五源互为备份：`--source europepmc|crossref|openalex|semantic_scholar`）。
- **Semantic Scholar 限流**：无 key 共享限额极低，live 冒烟会按设计跳过；配置 `plugins.semantic_scholar.api_key` 后稳定。
- **FULLTEXT_UNAVAILABLE**：这是合规终态。向用户展示出版商链接与 OA 状态；可尝试 `--format xml`（PMC 副本）或换 identifier（pmcid 优先于 doi）。
- **CONFIG**：错误消息内含修复命令，执行后重试即可。注意：`fetch` 定位阶段单个定位器缺配置（如 Unpaywall email）只进 warnings、不阻断；`get` 补全链触碰到缺配置的源才会以退出码 5 中断。
- **warnings**：补全冲突、插件加载失败等在 `warnings` 数组，不阻塞成功结果；值得向用户转述但不必重试。

## 5. MCP 挂载

安装 extra 后，任何 MCP 客户端（Qoder、Claude Desktop 等）以 stdio 挂载：

```bash
uv sync --extra mcp
```

客户端配置（开发环境，仓库路径按实际修改）：

```json
{
  "mcpServers": {
    "paper-tools": {
      "command": "uv",
      "args": ["run", "--directory", "C:/MyCode/qoder/paper-tools", "paper-tools", "mcp"]
    }
  }
}
```

发布到 PyPI 后可简化为 `{"command": "uvx", "args": ["--from", "paper-tools[mcp]", "paper-tools", "mcp"]}`。

四个工具（入参语义与 CLI 选项一一对应）：

| 工具 | 关键入参 | 返回 data |
|---|---|---|
| `search_papers` | query, source（逗号分隔多个或 `all`，多源去重）, limit, cursor, author, journal, year_from/year_to, oa_only, raw, enrich | SearchPage |
| `get_paper` | identifier（doi:/pmid:/pmcid:/openalex:/s2:/arxiv: 或裸 DOI）, source | Paper |
| `fetch_fulltext` | identifier, format(可选 pdf\|xml\|text), output(文件名), locator（逗号分隔多个）/downloader/extractor | FullText（含本地路径） |
| `list_sources` | — | 五角色插件清单 |

与 CLI 的唯一差异：MCP 工具把业务错误作为 **error envelope 返回值**（不抛异常、无退出码），agent 检查返回对象是否含 `error` 键即可，分支逻辑与第 2 节表格相同。

推荐流程：`search_papers`（浅记录）→ 选中后 `get_paper`（完整元数据）→ 需要全文时 `fetch_fulltext format=text`（AI 阅读友好，优先 XML 提取）。

## 6. 合规边界（硬约束）

- 只使用官方 API 与 OA 来源；不集成、不建议任何绕过付费墙的渠道。
- 闭源文献只返回出版商链接与 OA 状态。
- 获取的全文与提取文本仅供个人研究使用，遵守各来源服务条款与版权许可。