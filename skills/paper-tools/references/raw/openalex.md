# OpenAlex raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source openalex --raw '<OPENALEX_SEARCH>' --json
```

`--raw` 原样传入 OpenAlex `/works` 的 `search` 参数。它不会设置 `filter`，也不会切换到 `search.title` 或 `search.exact`。

## 语法要点

- 布尔运算符使用大写 `AND`、`OR`、`NOT`。
- 未写布尔运算符的相邻词按 AND 处理。
- 双引号用于短语。
- 括号用于分组；优先级为 NOT > AND > OR。
- `~N` 可用于词项模糊匹配或短语邻近搜索。
- `search` 会搜索标题、摘要、全文和关键词；不是精确字段过滤。
- 通配符需要 `search.exact`，当前 raw 无法指定该参数，因此不要把 `*` 当作可靠的通配符方案。

## 示例

```bash
# 布尔 + 短语
paper-tools search --source openalex --raw '("base editing" OR "prime editing") AND CRISPR NOT review' --json

# 相邻词默认 AND
paper-tools search --source openalex --raw 'antimicrobial resistance' --json

# 模糊匹配
paper-tools search --source openalex --raw 'machin~1 learning' --json

# 短语邻近
paper-tools search --source openalex --raw '"climate change"~5 health' --json
```

需要日期、OA、作者 ID 等精确条件时，使用不带 `--raw` 的结构化查询；结构化模式会生成 `filter`，例如 `from_publication_date`、`until_publication_date`、`is_oa`。

## 参考

- OpenAlex Searching：https://help.openalex.org/api/searching/
- OpenAlex Filtering：https://help.openalex.org/api/filtering/
