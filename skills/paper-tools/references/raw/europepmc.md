# Europe PMC raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source europepmc --raw '<EUROPE_PMC_QUERY>' --json
```

`--raw` 原样传入 Europe PMC REST 搜索接口的 `query` 参数。程序不会把 `--author`、`--journal`、年份或 OA 条件附加到 raw 表达式后面；这些条件与 `--raw` 互斥。

`--limit`、`--cursor`、`--fields` 和 `--enrich` 仍可使用。

## 1. 基本语法

- 布尔运算符使用大写 `AND`、`OR`、`NOT`。
- 括号用于分组。
- 双引号用于短语。
- 字段格式为 `FIELD:value`。
- `*` 可用于前缀或词干扩展。
- 相邻概念通常需要显式 AND；不要假设与 PubMed 完全一致。

```text
CRISPR AND "base editing"
(CRISPR OR "prime editing") AND FIRST_PDATE:[2023 TO 2026]
CRISPR NOT review
```

## 2. 常用字段

| 字段 | 含义 | 示例 |
|---|---|---|
| `TITLE:` | Title | `TITLE:CRISPR` |
| `ABSTRACT:` | Abstract | `ABSTRACT:"base editing"` |
| `TITLE_ABS:` | Title + Abstract | `TITLE_ABS:CRISPR` |
| `AUTH:` | Author | `AUTH:"Smith JA"` |
| `JOURNAL:` | Journal | `JOURNAL:Nature` |
| `FIRST_PDATE:` | First publication date | `FIRST_PDATE:[2023 TO 2026]` |
| `PUB_YEAR:` | Publication year | `PUB_YEAR:2024` |
| `DOI:` | DOI | `DOI:10.1038/s41586-020-2649-2` |
| `EXT_ID:` | External ID | `EXT_ID:38308006` |
| `PMID:` | PubMed ID | `PMID:38308006` |
| `PMCID:` | PMC ID | `PMCID:PMC13434336` |
| `PUB_TYPE:` | Publication type | `PUB_TYPE:review` |
| `OPEN_ACCESS:` | OA 状态 | `OPEN_ACCESS:y` |
| `IN_EPMC:` | Europe PMC 全文 | `IN_EPMC:y` |
| `HAS_ABSTRACT:` | 是否有摘要 | `HAS_ABSTRACT:y` |
| `HAS_PDF:` | 是否有 PDF | `HAS_PDF:y` |
| `SRC:` | 来源库 | `SRC:MED` / `SRC:PMC` |
| `MESH_TERMS:` | MeSH 主题词 | `MESH_TERMS:"CRISPR-Cas Systems"` |
| `KEYWORD:` | 关键词 | `KEYWORD:"base editing"` |
| `CITED_COUNT:` | 引用次数 | `CITED_COUNT:>10` |

不同 Europe PMC 索引记录的字段覆盖范围不同。精确字段查不到结果时，可退回 `TITLE_ABS:` 或普通关键词。

## 3. 日期

日期范围使用方括号和 `TO`：

```text
FIRST_PDATE:[2023 TO 2026]
FIRST_PDATE:[2023-01-01 TO 2026-12-31]
FIRST_PDATE:2024
```

单年可简写为：

```text
PUB_YEAR:2024
```

示例：

```bash
paper-tools search --source europepmc --raw 'TITLE:CRISPR AND FIRST_PDATE:[2023 TO 2026]' --json
```

## 4. OA 与全文

| 需求 | 表达式 |
|---|---|
| OA 记录 | `OPEN_ACCESS:y` |
| Europe PMC 中有全文 | `IN_EPMC:y` |
| 有 PDF | `HAS_PDF:y` |
| 有摘要 | `HAS_ABSTRACT:y` |
| PMC 来源 | `SRC:PMC` |
| MEDLINE 来源 | `SRC:MED` |

`OPEN_ACCESS:y` 不等于一定能在 paper-tools 中下载；最终仍取决于 Locator 是否找到可访问的 PDF/XML 直链。

## 5. 短语、截断与作者

```text
"base editing"
AUTH:"Smith JA"
AUTH:Smith AND JOURNAL:Nature
vaccin*
```

作者名建议加双引号，减少同名作者噪声。期刊名使用 `JOURNAL:`，不要使用 PubMed 的 `[ta]`。

## 6. 文献类型

```text
PUB_TYPE:review
PUB_TYPE:"clinical trial"
PUB_TYPE:preprint
```

出版类型值取决于上游记录。若不确定，可先不做类型限制，再在结果中检查 `publication_type`。

## 7. 引用次数

```text
CITED_COUNT:>10
CITED_COUNT:>100
```

引用次数适合快速缩小高影响结果范围，但新论文和冷门领域会被系统性低估，不应作为唯一筛选条件。

## 8. 常用检索模板

### 近期 OA 研究

```bash
paper-tools search --source europepmc --raw '(TITLE:CRISPR OR TITLE_ABS:"base editing") AND FIRST_PDATE:[2023 TO 2026] AND OPEN_ACCESS:y' --json
```

### 作者 + 期刊

```bash
paper-tools search --source europepmc --raw 'AUTH:"Smith JA" AND JOURNAL:Nature AND (CRISPR OR "gene editing")' --json
```

### 仅 Europe PMC 全文

```bash
paper-tools search --source europepmc --raw 'TITLE_ABS:"antimicrobial resistance" AND IN_EPMC:y AND HAS_PDF:y' --json
```

### 高引用研究

```bash
paper-tools search --source europepmc --raw 'TITLE_ABS:"base editing" AND FIRST_PDATE:[2020 TO 2026] AND CITED_COUNT:>50' --json
```

### 精确标识符

```bash
paper-tools search --source europepmc --raw 'DOI:10.1038/s41586-020-2649-2' --json
paper-tools search --source europepmc --raw 'PMCID:PMC13434336' --json
```

已知标识符时，通常优先使用 `get`。

### PICO 临床检索

```bash
paper-tools search --source europepmc --raw '(TITLE_ABS:"type 2 diabetes" OR MESH_TERMS:"Diabetes Mellitus, Type 2") AND (TITLE_ABS:empagliflozin OR TITLE_ABS:"SGLT2 inhibitor") AND (TITLE_ABS:cardiovascular OR MESH_TERMS:"Cardiovascular Diseases")' --json
```

## 9. 与 PubMed 的差异

| PubMed | Europe PMC |
|---|---|
| `CRISPR[ti]` | `TITLE:CRISPR` |
| `"base editing"[tiab]` | `TITLE_ABS:"base editing"` |
| `Smith JA[au]` | `AUTH:"Smith JA"` |
| `Nature[ta]` | `JOURNAL:Nature` |
| `2023:2026[dp]` | `FIRST_PDATE:[2023 TO 2026]` |
| `free full text[sb]` | `OPEN_ACCESS:y` / `IN_EPMC:y` |

不要直接复制 PubMed 字段标签。

## 10. 当前 raw 的能力边界

`--raw` 只控制 `query`。Europe PMC 的排序、结果类型等独立参数不会从 raw 中解析；paper-tools 当前只暴露 `limit` 和 `cursor`。需要按引用次数或日期排序时，应直接使用 Europe PMC API 或扩展插件。

## 11. 常见误区

- 使用 `[ti]`、`[au]`、`[dp]` 等 PubMed 标签。
- 在 raw 后又添加 `--year-from` 或 `--oa-only`。
- 认为 `OPEN_ACCESS:y` 保证有 PDF/XML 下载链接。
- 忘记给多概念加 AND。
- 过度使用 `CITED_COUNT` 导致新论文漏检。

## 参考

- Europe PMC RESTful Web Service：https://europepmc.org/RestfulWebService
