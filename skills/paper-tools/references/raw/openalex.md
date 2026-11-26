# OpenAlex raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source openalex --raw '<OPENALEX_SEARCH>' --json
```

`--raw` 原样传入 OpenAlex `/works` 的 `search` 参数。它不会设置 `filter`，也不会切换到 `search.title`、`search.title_and_abstract` 或 `search.exact`。

`--raw` 与 `--author`、`--journal`、`--year-from`、`--year-to`、`--oa-only` 互斥。

## 1. search 搜索范围

OpenAlex `search` 会匹配：

- title 和 alternate titles
- abstract
- fulltext（仅限 OpenAlex 有全文的数据）
- keywords

因此，`search` 比“只搜标题”更宽。作者姓名也可能出现在摘要或全文中；精确作者检索应使用作者实体或 filter，而不是把姓名放进 `search`。

## 2. 布尔运算

使用大写 `AND`、`OR`、`NOT`：

```text
CRISPR AND "base editing"
CRISPR OR "prime editing"
CRISPR NOT review
```

没有布尔运算符的相邻词按 AND 处理：

```text
antimicrobial resistance
```

等价于：

```text
antimicrobial AND resistance
```

### 优先级

1. `NOT`
2. `AND`
3. `OR`

因此：

```text
a AND b OR c
```

表示：

```text
(a AND b) OR c
```

复杂表达式必须用括号：

```text
("base editing" OR "prime editing") AND CRISPR NOT review
```

### 减号不是 NOT

```text
asthma -mice
```

不会排除 mice。正确写法：

```text
asthma NOT mice
```

## 3. 短语

双引号用于短语：

```text
"base editing"
"machine learning"
```

不加引号时，多个词通常按相关性匹配，不要求连续出现。

## 4. 邻近检索

短语后添加 `~N`：

```text
"climate change"~5
```

表示两个词之间最多相隔 5 个位置，词序可以不同。多个短语也可组合：

```text
"machine learning"~5~"neural network"
```

## 5. 模糊匹配

词项后添加 `~N`，允许最多 N 次字符编辑：

```text
machin~1
```

适合拼写变体。`N` 通常为 1 或 2；模糊度过高会增加噪声。

## 6. 通配符限制

OpenAlex 文档支持 `*` 和 `?`，但当前 paper-tools raw 使用默认 `search`，而通配符需要 `search.exact`。因此：

- 不要把 `machin*` 当作可靠的 raw 通配符。
- raw 无法指定 `search.exact`。
- 需要截断时，直接使用 OpenAlex API 的 `search.exact`，或改用 PubMed/Europe PMC raw。

## 7. 大小写、词干与停用词

- OpenAlex 默认使用词干处理，例如 `possums` 可匹配 `possum`。
- 默认搜索可能移除 `the`、`an` 等停用词。
- 重音通常不影响匹配。
- 默认搜索匹配完整词，不使用前缀匹配。

## 8. 长查询限制

OpenAlex GET 请求 URL 上限约为 8190 字节。包含大量 OR 术语的系统综述表达式可能超限。

处理方式：

1. 将 OR 术语拆成多个较小查询。
2. 分别检索后用 DOI/ID 合并去重。
3. 或直接使用 OpenAlex OQL POST 接口；当前 `--raw` 不支持 POST。

## 9. 常用检索模板

### 布尔 + 短语

```bash
paper-tools search --source openalex --raw '("base editing" OR "prime editing") AND CRISPR NOT review' --json
```

### 标题片段 + 年份概念

```bash
paper-tools search --source openalex --raw '"molecular basis" AND editing' --json
```

raw 不能设置年份过滤；需要年份时使用结构化模式。

### 邻近检索

```bash
paper-tools search --source openalex --raw '"climate change"~5 health' --json
```

### 模糊匹配

```bash
paper-tools search --source openalex --raw 'machin~1 learning' --json
```

### 排除概念

```bash
paper-tools search --source openalex --raw '"antimicrobial resistance" AND poultry NOT review' --json
```

### 作者姓名噪声

不推荐：

```bash
paper-tools search --source openalex --raw 'Jennifer Doudna' --json
```

推荐先查作者实体，再用作者 ID 过滤 works；或使用其他支持作者字段的搜索器。

## 10. raw 与 filter 的分工

| 条件 | raw `search` | 结构化模式 / filter |
|---|---|---|
| 标题、摘要、全文关键词 | 支持 | 支持 |
| 布尔 AND/OR/NOT | 支持 | 不适用 |
| 短语、邻近、模糊 | 支持 | 不适用 |
| 出版年份 | 不直接支持 | `--year-from` / `--year-to` |
| OA | 不直接支持 | `--oa-only` |
| 作者 ID、机构 ID、DOI 精确值 | 不直接支持 | 需直接 API 或插件扩展 |
| `search.exact` 通配符 | 不支持 | 需直接 API |

结构化模式示例：

```bash
paper-tools search 'CRISPR' --source openalex --year-from 2023 --year-to 2026 --oa-only --json
```

## 11. 常见误区

- 使用 PubMed `[ti]` 或 Europe PMC `TITLE:`。
- 用 `-term` 表示排除。
- 忘记括号导致 OR 分组不符合预期。
- 认为 raw 可以同时设置 `filter`。
- 依赖 `*` 通配符，但实际传入的是默认 `search`。
- 把作者姓名当作精确作者过滤。

## 参考

- OpenAlex Searching：https://help.openalex.org/api/searching/
- OpenAlex Filtering：https://help.openalex.org/api/filtering/
