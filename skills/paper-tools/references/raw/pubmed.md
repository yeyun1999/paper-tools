# PubMed raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source pubmed --raw '<PUBMED_QUERY>' --json
```

`--raw` 原样传入 PubMed ESearch 的 `term` 参数，不再自动添加任何字段。`raw` 不能与自由文本、作者、期刊、年份或 `--oa-only` 同时使用。

## 语法要点

- 布尔运算符使用大写 `AND`、`OR`、`NOT`；括号用于分组。
- 双引号用于短语，例如 `"base editing"`。
- 字段标签放在方括号中，例如 `[ti]`、`[tiab]`、`[au]`、`[ta]`、`[dp]`、`[pt]`、`[sb]`。
- 日期范围使用 `起始:结束[dp]`，年份可只写四位。
- `*` 表示截断；PubMed 要求首个通配符前至少有 4 个字符。
- 字段标签会关闭 Automatic Term Mapping；多个同字段词需分别加标签。

常用字段：

| 标签 | 含义 |
|---|---|
| `[ti]` | Title |
| `[tiab]` | Title/Abstract |
| `[tw]` | Text Word |
| `[au]` | Author |
| `[ta]` | Journal |
| `[dp]` | Publication Date |
| `[pt]` | Publication Type |
| `[mh]` | MeSH Terms |
| `[sb]` | Subset，如 `free full text[sb]`、`systematic[sb]` |
| `[pmid]` / `[pmcid]` | PMID / PMCID |

## 示例

```bash
# 标题含 CRISPR，2023–2026，排除综述
paper-tools search --source pubmed --raw 'CRISPR[ti] AND 2023:2026[dp] NOT review[pt]' --json

# 标题/摘要短语 + 免费全文
paper-tools search --source pubmed --raw '"base editing"[tiab] AND free full text[sb]' --json

# 作者 + 期刊 + 截断
paper-tools search --source pubmed --raw 'Smith JA[au] AND Nature[ta] AND vaccin*[ti]' --json

# 邻近检索
paper-tools search --source pubmed --raw '"patient physician relationship"[tiab:~0]' --json
```

## 参考

- PubMed User Guide：https://pubmed.ncbi.nlm.nih.gov/help/
