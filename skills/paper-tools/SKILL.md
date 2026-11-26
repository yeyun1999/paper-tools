---
name: paper-tools
description: 使用 paper-tools CLI 或 MCP 检索生物医学文献、补全元数据、定位和下载开放获取全文、提取文本，或编写 PubMed/Europe PMC/Crossref/OpenAlex/Semantic Scholar raw 查询。适用于文献检索、全文获取、JSON 自动化、MCP 集成和插件开发。
---

# paper-tools 使用 Skill

## Overview

使用 `paper-tools` 完成文献检索、元数据补全、OA 全文定位、下载和文本提取。优先使用 `--json` 或 MCP，确保输出可解析、错误可分支处理。

## 选择工作流

- 只要最终全文：使用 `fetch`，一次完成定位、下载和可选文本提取。
- 需要检查候选链接或下载器：依次使用 `locate` → `download` → `extract`。
- 只要元数据：使用 `get`；批量检索使用 `search`。
- 通过 AI 客户端远程调用：使用 MCP 的 `search_papers` / `get_paper` / `locate_fulltext` / `fetch_fulltext`。

## 标准流程

1. 运行 `paper-tools sources --json`，确认所需搜索器、定位器、下载器和提取器已注册。
2. 检索文献，优先选择与目标匹配的单一搜索器；跨源检索使用 `--source all` 或逗号分隔列表。
3. 需要摘要、作者、OA 状态或出版类型时，对选中文献执行 `get`，或在 `search` 中使用 `--enrich`。
4. 只需全文链接时执行 `locate`；检查候选的 `format`、`locator` 和 `downloaders`。
5. 下载候选 URL，或直接执行 `fetch` 获取最终文件。
6. 需要纯文本时，对 PDF/JATS XML 执行 `extract`，或使用 `fetch --format text`。

## 关键规则

- 将 `raw` 视为上游原生语法，不可跨搜索器移植；使用前加载对应 raw 参考文件。
- `raw` 与 `query/author/journal/year/oa_only` 互斥；需要组合条件时写入原生表达式。
- 多源结果按 DOI、PMID 或标题去重；`--limit` 是每个来源的上限，合并后可能超过该值。
- 分页时原样回传 `data.next_cursor`；多源游标是以 `ms1.` 开头的不透明 token。
- `locate` 的每个候选包含 `locator` 来源列表和有序 `downloaders` 推荐列表；下载按该顺序尝试，`--downloader` 可强制覆盖。
- JSON 模式下 stdout 只包含 JSON；日志和警告位于 stderr。

## 资源路由

- CLI 命令、选项和示例：`references/cli.md`
- MCP 启动、工具选择与 Agent 工作流：`references/mcp.md`
- JSON Schema、结果模型、NDJSON 和退出码：`references/output-contract.md`
- 配置键、环境变量和缓存：`references/configuration.md`
- 常见错误与 Windows 问题：`references/troubleshooting.md`
- 自定义 Locator/Downloader/Extractor：`references/plugin-authoring.md`
- Raw 查询：
  - `references/raw/pubmed.md`
  - `references/raw/europepmc.md`
  - `references/raw/crossref.md`
  - `references/raw/openalex.md`
  - `references/raw/semantic-scholar.md`
