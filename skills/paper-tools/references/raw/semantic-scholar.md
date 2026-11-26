# Semantic Scholar raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source semantic_scholar --raw '<SEMANTIC_SCHOLAR_QUERY>' --json
```

`--raw` 只设置 Semantic Scholar `/paper/search` 的 `query` 参数。它不会再附加 `venue`、`year` 或 `openAccessPdf`。

与 PubMed、Europe PMC 和 OpenAlex 不同，Semantic Scholar 的 `/paper/search` 是相关性检索接口，不提供可移植的字段标签语言。不要把 raw 当作严格布尔表达式。

## 1. query 参数

`query` 接受文本检索词。推荐输入：

- 3–8 个核心概念
- 标题片段
- 关键词组合
- 作者 + 主题
- DOI

避免输入：

- PubMed 字段标签：`CRISPR[ti]`
- Europe PMC 字段：`TITLE:CRISPR`
- 过长的完整摘要
- 大量无意义停用词
- 依赖 `AND` / `OR` / `NOT` 得到严格逻辑结果

Semantic Scholar 不保证支持布尔运算符、通配符、字段限定或短语语法。某些表达式可能作为普通文本处理，结果不可预测。

## 2. 当前 raw 不包含的参数

| 参数 | 用途 | raw 模式 |
|---|---|---|
| `query` | 检索文本 | 使用 raw 内容 |
| `fields` | 返回字段 | paper-tools 固定设置 |
| `limit` | 每页数量 | `--limit` 控制 |
| `offset` | 偏移量 | cursor 控制 |
| `venue` | 期刊/会议 | 不附加 |
| `year` | 年份范围 | 不附加 |
| `openAccessPdf` | 是否有 OA PDF | 不附加 |

结构化模式才可生成 `venue`、`year` 和 `openAccessPdf`。

## 3. 检索词设计

### 宽泛检索

```bash
paper-tools search --source semantic_scholar --raw 'CRISPR base editing' --json
```

### 更具体

```bash
paper-tools search --source semantic_scholar --raw 'CRISPR base editing genetic disease therapy' --json
```

### 标题片段

```bash
paper-tools search --source semantic_scholar --raw 'Molecular basis of base editing' --json
```

### 作者 + 主题

```bash
paper-tools search --source semantic_scholar --raw 'Jennifer Doudna CRISPR' --json
```

作者名只是查询文本，不保证只匹配作者字段。

### DOI

```bash
paper-tools search --source semantic_scholar --raw '10.1038/s41586-020-2649-2' --json
```

已知 DOI 时优先使用 `get`：

```bash
paper-tools get doi:10.1038/s41586-020-2649-2 --source semantic_scholar --json
```

### 缩写 + 全称

```bash
paper-tools search --source semantic_scholar --raw 'AMR antimicrobial resistance poultry' --json
```

同一概念可用缩写和全称分别查询，然后在客户端合并结果。

## 4. 多概念策略

由于 raw 不支持可靠 OR，可把同义词拆成多次查询：

```bash
paper-tools search --source semantic_scholar --raw 'CRISPR base editing' --json
paper-tools search --source semantic_scholar --raw 'prime editing' --json
paper-tools search --source semantic_scholar --raw 'gene editing disease therapy' --json
```

按 DOI 合并去重。不要用 `OR` 代替这种客户端合并。

## 5. 年份、期刊与 OA

raw 无法附加这些条件。需要过滤时使用结构化模式：

```bash
paper-tools search 'CRISPR' --source semantic_scholar --journal Nature --year-from 2023 --year-to 2026 --oa-only --json
```

注意：结构化模式使用普通 `query`，不支持 raw 布尔表达式。若既要复杂表达式又要 OA，建议改用 Europe PMC 或 OpenAlex。

## 6. 空查询与限制

- raw 不能为空。
- 仅指定 journal、年份或 OA 而没有 text/title/author 时，Semantic Scholar 搜索器会拒绝查询。
- 结构化模式的 journal-only 查询也不受支持。

## 7. API key 与限流

未配置 API key 时共享配额较紧。配置：

```bash
paper-tools config set plugins.semantic_scholar.api_key YOUR_KEY
```

大量查询时降低并发、增加退避，避免触发 429。paper-tools 的 HTTP 层已实现按 host 限流和重试，但仍需遵守上游政策。

## 8. 适用场景

| 需求 | 建议 |
|---|---|
| 简单关键词相关性检索 | Semantic Scholar raw |
| 严格布尔/字段检索 | PubMed 或 Europe PMC |
| 日期 + OA + 文本 | Europe PMC / OpenAlex 结构化 |
| 已知 DOI/PMID | `get` |
| 高召回跨源检索 | `--source all`，按 DOI 合并 |

## 9. 常见误区

- 使用 `AND` / `OR` / `NOT` 并期待严格逻辑。
- 使用 `[ti]`、`TITLE:` 等字段标签。
- 在 raw 后又添加 `--journal`、`--year-from` 或 `--oa-only`。
- 认为 raw 会自动附加 `openAccessPdf`。
- 一次输入过长摘要，导致相关性下降。

## 参考

- Semantic Scholar Academic Graph API Tutorial：https://www.semanticscholar.org/product/api%2Ftutorial
