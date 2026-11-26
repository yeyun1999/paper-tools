# Crossref raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source crossref --raw '<CROSSREF_QUERY>' --json
```

`--raw` 只设置 Crossref `/works` 的 `query` 参数。它不会设置 `query.title`、`query.author`、`query.container-title`、`query.bibliographic` 或 `filter`。

这是五个搜索器中 raw 表达能力最弱的一个：Crossref 的 `query` 是相关性文本查询，不是 PubMed/Europe PMC 的字段表达式。

## 1. query 参数

`query` 会在 Crossref 元数据中进行相关性匹配，适合输入：

- 文章标题或标题片段
- 关键词组合
- 作者 + 标题
- 期刊 + 主题
- DOI
- 完整参考文献文本

Crossref 不保证支持 PubMed 风格的 `AND`、`OR`、`NOT`、方括号字段标签或 `*` 通配符。即使某些词恰好是布尔单词，也应将其视为普通检索词。

## 2. 其他查询参数与当前 raw 的关系

| Crossref 参数 | 用途 | paper-tools raw 是否设置 |
|---|---|---|
| `query` | 相关性文本查询 | 是 |
| `query.title` | 标题字段查询 | 否 |
| `query.author` | 作者字段查询 | 否 |
| `query.container-title` | 期刊/容器标题 | 否 |
| `query.bibliographic` | 书目信息查询 | 否 |
| `filter` | 精确字段、日期、类型等过滤 | 否 |
| `rows` | 每页数量 | 由 `--limit` 控制 |
| `offset` | 偏移量 | 由 cursor 控制 |
| `mailto` | Polite pool | 由配置 `general.mailto` 控制 |

如果需求依赖 `filter` 或字段参数，不要试图把它们塞进 `query`。

## 3. 结构化模式可用的条件

当前 CLI 不使用 raw 时可设置：

- 自由文本：位置参数 `QUERY`
- 作者：`--author`
- 期刊：`--journal`
- 年份：`--year-from` / `--year-to`
- OA：Crossref 不支持可靠的 `--oa-only`，会返回 `USAGE`

结构化模式会生成 `query`、`query.author`、`query.container-title`，以及 `from-pub-date` / `until-pub-date` 过滤器。`query.title` 目前没有独立 CLI 选项。

## 4. raw 查询策略

### 关键词

```bash
paper-tools search --source crossref --raw 'CRISPR base editing' --json
```

### 标题片段

```bash
paper-tools search --source crossref --raw 'Molecular basis of base editing' --json
```

### 作者 + 主题

```bash
paper-tools search --source crossref --raw 'Jennifer Doudna CRISPR' --json
```

作者名只是普通文本，可能匹配作者字段，也可能匹配标题、摘要或其他元数据。

### 期刊 + 主题

```bash
paper-tools search --source crossref --raw 'Nature gene editing review' --json
```

### DOI

```bash
paper-tools search --source crossref --raw '10.1038/s41586-020-2649-2' --json
```

如果已经知道 DOI，优先使用：

```bash
paper-tools get doi:10.1038/s41586-020-2649-2 --source crossref --json
```

### 完整参考文献

```bash
paper-tools search --source crossref --raw 'Smith J. Advances in base editing. Nature. 2024.' --json
```

完整参考文献可能比关键词更精确，但结果依赖 Crossref 已登记元数据的完整度。

## 5. 日期与类型过滤

paper-tools 的结构化模式：

```bash
paper-tools search 'CRISPR' --source crossref --year-from 2023 --year-to 2026 --json
```

对应 API 过滤器概念：

```text
filter=from-pub-date:2023,until-pub-date:2026
```

常见 API 过滤器（当前不能通过 `--raw` 传入）：

| 过滤器 | 用途 |
|---|---|
| `from-pub-date` / `until-pub-date` | 出版日期范围 |
| `from-created-date` / `until-created-date` | 元数据登记日期 |
| `from-update-date` / `until-update-date` | 元数据更新日期 |
| `type` | 文献类型，如 `journal-article` |
| `issn` | 期刊 ISSN |
| `doi` | DOI 精确匹配 |
| `orcid` | 作者 ORCID |
| `has-abstract` | 是否有摘要 |
| `has-license` | 是否有许可证 |
| `has-full-text` | 是否登记全文链接 |

需要这些条件时，可使用结构化 CLI、直接调用 Crossref API，或扩展 Searcher 插件。

## 6. 如何选择搜索器

| 需求 | 推荐方式 |
|---|---|
| 复杂布尔检索 | PubMed / Europe PMC raw |
| 日期 + 作者 + 期刊精确过滤 | Europe PMC 或结构化 Crossref |
| DOI 元数据 | `get --source crossref` |
| OA 全文链接 | 搜索后用 `locate` / `fetch` |
| 简单书目关键词 | Crossref raw 可用，但语义有限 |

## 7. 常见误区

- 使用 `CRISPR[ti]` 或 `TITLE:CRISPR`；Crossref 不识别这些字段语法。
- 依赖 `AND` / `OR` / `NOT` 得到严格逻辑结果。
- 期望 `--raw` 能设置 `filter=type:journal-article`。
- 在 raw 后又添加 `--author` 或 `--year-from`。
- 使用 `--oa-only`；Crossref 没有可靠 OA 过滤。

## 参考

- Crossref REST API：https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- REST API filters：https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/
