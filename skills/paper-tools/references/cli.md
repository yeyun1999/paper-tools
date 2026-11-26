# CLI 使用说明

## 调用方式

```bash
paper-tools --help
paper-tools <command> --help
```

安装后直接执行 `paper-tools`。全局选项可放在子命令前后。

## 全局选项

| 选项 | 说明 |
|---|---|
| `--json` | stdout 输出 JSON；日志和警告走 stderr |
| `--quiet` | 抑制非必要人类可读输出 |
| `--verbose` | DEBUG 日志输出到 stderr |
| `--no-cache` | 绕过响应、元数据和文件映射缓存 |
| `--timeout SECONDS` | 覆盖 HTTP 超时 |
| `--config PATH` | 使用指定 TOML 配置 |
| `--version` | 显示版本 |

## 命令

| 命令 | 用途 | 关键选项 |
|---|---|---|
| `search [QUERY]` | 检索文献，默认返回浅记录 | `--source`、`--limit`、`--cursor`、`--author`、`--journal`、`--year-from`、`--year-to`、`--oa-only`、`--raw`、`--fields`、`--enrich` |
| `get ID...` | 按标识符补全元数据 | `--source`、`--fields` |
| `locate ID` | 定位全文候选，不下载 | `--format`、`--locator` |
| `download URL` | 下载并校验一个全文直链 | `--format`、`--output`、`--downloader` |
| `extract FILE` | 本地 PDF/JATS XML → text | `--output`、`--extractor` |
| `fetch ID` | 一键定位 → 下载 → 可选提取 | `--format`、`--output`、`--locator`、`--downloader`、`--extractor` |
| `sources` | 列出五类插件及加载警告 | `--json` |
| `config get/set/list/path` | 管理配置 | 点分键；`set` 值为 TOML literal 或字符串 |
| `cache clear/stats` | 清理响应/元数据缓存或查看统计 | `clear` 保留产物文件 |
| `schema [COMMAND]` | 导出 JSON Schema | 支持 `search/get/locate/download/extract/fetch` |
| `mcp` | 启动 stdio MCP 服务器 | 需要 `mcp` extra |

## 检索

```bash
# 结构化查询
paper-tools search "CRISPR base editing" --source pubmed --limit 20 --json

# 跨源并发检索
paper-tools search "CRISPR" --source pubmed,europepmc --limit 20 --json
paper-tools search "CRISPR" --source all --limit 20 --json

# 原生查询
paper-tools search --source pubmed --raw 'CRISPR[Title] AND 2023:2026[dp]' --json

# 补全元数据并裁剪字段
paper-tools search "CRISPR" --source europepmc --enrich --fields title,identifiers.doi,year,abstract --json

# 数组嵌套投影：只保留每位作者的姓名
paper-tools get pmid:38308006 --fields 'authors[].name' --json

# 返回并尝试补全全部 Paper 字段（覆盖 output.search_fields）
paper-tools search "CRISPR" --enrich --fields all --json

# 分页：原样回传 next_cursor
paper-tools search "CRISPR" --source pubmed --cursor '<next_cursor>' --json
```

`--source` 可重复或逗号分隔；`all` 强制全部搜索器。多源 `--limit` 限制每个来源，合并去重后不再截断。
`search` 默认输出 `title,identifiers.doi,year,cited_by_count,abstract`，`get` 默认输出
`title,identifiers.doi,year,cited_by_count,journal,oa_status,abstract`；可用 `[output]` 配置分别修改。
对象嵌套使用 `.`，数组嵌套使用 `[]`，例如 `identifiers.doi`、`authors[].name`；
输出保留原对象/数组结构，不再把标识符提升到顶层。`--fields all` 返回全部 Paper 字段，
并在 `get` 或 `search --enrich` 中要求补全全部字段；显式 `--fields` 优先于配置。

## 元数据

```bash
paper-tools get pmid:38308006 --json
paper-tools get doi:10.1038/s41586-020-2649-2 --source crossref --json

# 多 ID：JSON 输出为 NDJSON
paper-tools get pmid:38308006 doi:10.1038/s41586-020-2649-2 --fields title,identifiers.doi,year --json
```

支持的标识符：`doi:`、`pmid:`、`pmcid:`、`openalex:`、`s2:`、`arxiv:`、DOI URL、裸 DOI 和纯数字 PMID。

## 全文获取

```bash
# 一键获取
paper-tools fetch pmcid:PMC13434336 --format pdf --output papers/paper.pdf --json
paper-tools fetch doi:10.1093/nar/gkag769 --format text --output papers/paper.txt --json

# 分阶段
paper-tools locate pmcid:PMC13434336 --format xml --json
paper-tools download "$FULLTEXT_URL" --format xml --output papers/paper.xml --json
paper-tools extract papers/paper.xml --output papers/paper.txt --json
```

- `fetch` 每次只处理一个 ID。
- `locate --format text` 接受 PDF/XML/text 来源；未指定格式时保留 landing 候选。
- `download` 未指定格式时依次按 `--output` 扩展名、URL 路径推断；显式无扩展名输出默认 PDF。
- `fetch` 默认使用安全化文章标题；重名时追加 DOI、PMID、PMCID 等 ID。
- 内置下载器只有 `http_direct`；第三方下载器可通过 entry points 接入。

## 输出与错误

- 单篇命令的 `--json` 输出单个对象。
- 多 ID `get` 的 `--json` 输出 NDJSON。
- 单篇业务错误写入 stdout 结果流；进程级用法/配置错误写入 stderr。
- 退出码：`0` 成功，`2` 用法，`3` 上游/未找到，`4` 全文不可得，`5` 配置错误。
