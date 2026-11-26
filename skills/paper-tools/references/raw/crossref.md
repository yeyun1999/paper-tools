# Crossref raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source crossref --raw '<CROSSREF_QUERY>' --json
```

`--raw` 只设置 Crossref `/works` 的 `query` 参数。它不会设置 `query.title`、`query.author`、`query.container-title` 或 `filter`。

## 使用方式

- 将 `raw` 当作相关性文本查询，可输入关键词、标题片段、作者、期刊或 DOI。
- 不要套用 PubMed 的 `[ti]` 字段标签或 Europe PMC 的 `TITLE:` 语法。
- Crossref 的精确字段和日期条件通过 `filter` 实现，但当前 `--raw` 不暴露 `filter`。
- `raw` 与结构化查询字段互斥；需要字段/日期条件时，改用不带 `--raw` 的结构化查询。

## 示例

```bash
# 关键词
paper-tools search --source crossref --raw 'CRISPR base editing' --json

# 标题片段
paper-tools search --source crossref --raw 'Molecular basis of base editing' --json

# DOI
paper-tools search --source crossref --raw '10.1038/s41586-020-2649-2' --json
```

需要日期过滤时使用结构化模式：

```bash
paper-tools search 'CRISPR' --source crossref --year-from 2023 --year-to 2026 --json
```

结构化模式可生成 `query.title`、`query.author`、`query.container-title`，以及 `from-pub-date` / `until-pub-date` 过滤器。

## 参考

- Crossref REST API：https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- REST API filters：https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/
