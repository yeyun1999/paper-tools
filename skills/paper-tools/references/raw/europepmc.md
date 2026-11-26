# Europe PMC raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source europepmc --raw '<EUROPE_PMC_QUERY>' --json
```

`--raw` 原样传入 Europe PMC REST 搜索接口的 `query` 参数。`raw` 不能与自由文本、作者、期刊、年份或 `--oa-only` 同时使用。

## 语法要点

- 布尔运算符使用大写 `AND`、`OR`、`NOT`；括号用于分组。
- 双引号用于短语。
- 字段使用 `FIELD:value`，常用字段包括 `TITLE:`、`ABSTRACT:`、`AUTH:`、`JOURNAL:`、`FIRST_PDATE:`、`PUB_YEAR:`、`DOI:`、`EXT_ID:`、`PMCID:`。
- 日期范围使用 `FIRST_PDATE:[YYYY-MM-DD TO YYYY-MM-DD]`；年份可只写四位。
- OA 限制使用 `OPEN_ACCESS:y`。
- `*` 可用于词干或前缀扩展。

## 示例

```bash
# 标题或摘要含 CRISPR，限定日期和 OA
paper-tools search --source europepmc --raw '(TITLE:CRISPR OR ABSTRACT:CRISPR) AND FIRST_PDATE:[2023 TO 2026] AND OPEN_ACCESS:y' --json

# 作者 + 期刊 + 短语
paper-tools search --source europepmc --raw 'AUTH:"Smith JA" AND JOURNAL:Nature AND "base editing"' --json

# DOI 精确检索
paper-tools search --source europepmc --raw 'DOI:10.1038/s41586-020-2649-2' --json

# PMC 全文
paper-tools search --source europepmc --raw 'PMCID:PMC13434336 AND OPEN_ACCESS:y' --json
```

## 与 PubMed 的区别

Europe PMC 使用 `TITLE:` / `AUTH:` / `FIRST_PDATE:`，不是 PubMed 的 `[ti]` / `[au]` / `[dp]`。不要直接复制 PubMed 字段标签。

## 参考

- Europe PMC RESTful Web Service：https://europepmc.org/RestfulWebService
