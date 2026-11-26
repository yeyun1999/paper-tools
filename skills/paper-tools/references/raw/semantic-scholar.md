# Semantic Scholar raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source semantic_scholar --raw '<SEMANTIC_SCHOLAR_QUERY>' --json
```

`--raw` 只设置 Semantic Scholar `/paper/search` 的 `query` 参数。它不会再附加 `venue`、`year` 或 `openAccessPdf`。

## 使用方式

- 使用自然语言关键词或短语，不要依赖 PubMed/Europe PMC 字段标签。
- 不保证支持 `AND`、`OR`、`NOT`、通配符或字段限定语法；需要可移植行为时使用普通关键词。
- `raw` 与结构化字段互斥；无法在同一次 raw 请求中附加期刊、年份或 OA 条件。
- 查询不能为空；仅指定 journal 而不指定 text/title/author 不受支持。

## 示例

```bash
paper-tools search --source semantic_scholar --raw 'CRISPR base editing' --json

paper-tools search --source semantic_scholar --raw 'antimicrobial resistance in poultry' --json

paper-tools search --source semantic_scholar --raw '10.1038/s41586-020-2649-2' --json
```

需要期刊、年份或 OA 条件时，使用结构化模式：

```bash
paper-tools search 'CRISPR' --source semantic_scholar --journal Nature --year-from 2023 --year-to 2026 --oa-only --json
```

## 参考

- Semantic Scholar Academic Graph API Tutorial：https://www.semanticscholar.org/product/api%2Ftutorial
