# PubMed raw 搜索语法

## 在 paper-tools 中

```bash
paper-tools search --source pubmed --raw '<PUBMED_QUERY>' --json
```

`--raw` 原样传入 PubMed ESearch 的 `term` 参数。程序不会补齐字段、括号或日期，也不会把其他 CLI 查询条件附加到表达式后面。

`--raw` 与自由文本、`--author`、`--journal`、`--year-from`、`--year-to`、`--oa-only` 互斥。`--limit`、`--cursor`、`--fields` 和 `--enrich` 仍可正常使用。

## 1. 基本查询单元

### 单词与概念

```text
CRISPR
base editing
CRISPR base editing
```

未写布尔运算符时，PubMed 通常按 AND 组合概念，并可能执行 Automatic Term Mapping（ATM），把词语映射到 MeSH 术语及其下位词。需要可预测结果时，显式写运算符和字段标签。

### 精确短语

```text
"base editing"
"CRISPR-Cas9"
```

双引号用于短语。若短语不在 PubMed phrase index 中，引号可能被忽略并回退到 ATM。标题/摘要字段中的短语也可使用 `"base editing"[tiab]`。

### 显式 AND / OR / NOT

```text
CRISPR AND "base editing"
CRISPR OR "prime editing"
CRISPR NOT review
```

- 布尔运算符使用大写。
- PubMed 按从左到右的顺序处理；复杂表达式必须用括号分组。
- `NOT` 用于排除，不要依赖 `-term`。

```text
(CRISPR OR "prime editing") AND ("base editing" OR "gene editing") NOT review[pt]
```

## 2. 字段标签

字段标签放在方括号中，大小写和空格通常不影响解析。字段标签会关闭 ATM，把检索限制在指定字段。

| 标签 | 字段 | 示例 |
|---|---|---|
| `[ti]` | Title | `CRISPR[ti]` |
| `[tiab]` | Title/Abstract | `"base editing"[tiab]` |
| `[tw]` | 文本词：标题、摘要、MeSH 词、副主题词、出版类型、物质名、团体作者、作者关键词等 | `vaccin*[tw]` |
| `[au]` | Author | `Smith JA[au]` |
| `[1au]` | First Author | `Smith JA[1au]` |
| `[lastau]` | Last Author | `Smith JA[lastau]` |
| `[ad]` | Affiliation | `Harvard[ad]` |
| `[ta]` | Journal | `Nature[ta]` |
| `[dp]` | Publication Date | `2023:2026[dp]` |
| `[pt]` | Publication Type | `review[pt]` |
| `[mh]` | MeSH Terms | `CRISPR-Cas Systems[mh]` |
| `[majr]` | MeSH Major Topic | `Neoplasms[majr]` |
| `[sh]` | MeSH Subheading | `genetics[sh]` |
| `[sb]` | Subset / Filter | `free full text[sb]` |
| `[pmid]` | PMID | `38308006[pmid]` |
| `[pmcid]` | PMCID | `PMC13434336[pmcid]` |
| `[aid]` | Article Identifier / DOI | `10.1038/s41586-020-2649-2[aid]` |

同一字段的多个词必须分别加标签：

```text
CRISPR[ti] AND editing[ti]
```

不要写成 `CRISPR editing[ti]`，后者可能被当作短语处理。

## 3. 日期

常用格式：

```text
2026[dp]
2026/01[dp]
2026/01/01[dp]
2023:2026[dp]
2023/01/01:2026/12/31[dp]
"last 3 years"[dp]
```

- `[dp]`：出版日期，包含电子和印刷出版信息。
- `[edat]`：进入 PubMed 的日期。
- `[crdt]`：记录创建日期。
- 日期范围两端都包含。

示例：

```bash
paper-tools search --source pubmed --raw 'CRISPR[ti] AND 2023:2026[dp]' --json
```

## 4. 截断与通配符

`*` 替代零个或多个字符：

```text
vaccin*
organi*ation*
"breast feed*"
```

限制：

- 第一个 `*` 前至少有 4 个字符，例如 `colo*` 可用，`col*` 不可用。
- 同一个词可以使用多个 `*`。
- 短语中使用 `*` 时保留双引号。
- 通配符会关闭 ATM，可能漏掉 MeSH 扩展词。

## 5. 邻近检索

格式：

```text
"term1 term2"[field:~N]
```

- `N` 是两个词之间允许的最大词距。
- `N=0` 表示相邻，但词序可以不同。
- 支持 `[ti]`、`[tiab]`、`[ad]`。
- 邻近检索不能与通配符共同使用。

```bash
paper-tools search --source pubmed --raw '"patient physician relationship"[tiab:~0]' --json
paper-tools search --source pubmed --raw '"rationing healthcare"[ti:~2]' --json
```

## 6. 文献类型、亚组与全文限制

| 需求 | 表达式 |
|---|---|
| 免费全文 | `free full text[sb]` |
| 有全文链接 | `full text[sb]` |
| PMC 免费全文 | `pubmed pmc[sb]` |
| 系统综述过滤策略 | `systematic[sb]` |
| MEDLINE | `medline[sb]` |
| 排除预印本 | `NOT preprint[pt]` |
| 综述 | `review[pt]` |
| 临床试验 | `clinical trial[pt]` |
| 随机对照试验 | `randomized controlled trial[pt]` |
| 有摘要 | `hasabstract` |
| 结构化摘要 | `hasstructuredabstract` |

`systematic[sb]` 与 `systematic review[pt]` 不同：前者是 PubMed 的系统综述检索策略，后者只是出版类型。

## 7. MeSH 与临床检索

MeSH 主题词：

```text
"CRISPR-Cas Systems"[mh]
Neoplasms[mh]
Neoplasms[majr]
```

主题词加副标目：

```text
Neoplasms/genetics[mh]
```

临床概念块示例：

```text
("base editing"[tiab] OR "CRISPR-Cas Systems"[mh])
AND ("genetic therapy"[tiab] OR "Gene Editing"[mh])
AND (humans[mh] NOT animals[mh])
```

注意：`humans[mh] NOT animals[mh]` 会排除同时分配了 animals 和 humans 的记录，可能影响召回率。

## 8. 标识符精确检索

```bash
paper-tools search --source pubmed --raw '38308006[pmid]' --json
paper-tools search --source pubmed --raw 'PMC13434336[pmcid]' --json
paper-tools search --source pubmed --raw '10.1038/s41586-020-2649-2[aid]' --json
```

如果已经知道标识符，通常优先使用 `get`，而不是 `search`。

## 9. 常用检索模板

### 近期 OA 研究

```bash
paper-tools search --source pubmed --raw '(CRISPR[tiab] OR "base editing"[tiab]) AND 2023:2026[dp] AND free full text[sb] NOT review[pt]' --json
```

### 作者 + 期刊 + 主题

```bash
paper-tools search --source pubmed --raw 'Smith JA[au] AND Nature[ta] AND (CRISPR[tiab] OR "gene editing"[tiab])' --json
```

### 临床问题 PICO

```bash
paper-tools search --source pubmed --raw '("type 2 diabetes"[tiab] OR "Diabetes Mellitus, Type 2"[mh]) AND ("SGLT2 inhibitor*"[tiab] OR empagliflozin[tiab]) AND (cardiovascular[tiab] OR "Cardiovascular Diseases"[mh])' --json
```

### 系统综述初检

```bash
paper-tools search --source pubmed --raw '("antimicrobial resistance"[tiab] OR "antimicrobial resistance"[mh]) AND (poultry[tiab] OR chickens[mh]) AND (2020:2026[dp])' --json
```

## 10. Shell 引用

包含空格、括号、方括号、双引号或 `*` 时，使用单引号包裹整个表达式：

```bash
paper-tools search --source pubmed --raw '("base editing" OR "prime editing") AND 2023:2026[dp]' --json
```

表达式本身包含单引号时，需按 shell 规则转义或改用双引号并转义内部双引号。

## 11. 常见误区

- 把 Europe PMC 的 `TITLE:` 直接粘贴到 PubMed。
- 忘记给同一字段的每个词添加标签。
- 使用小写 `and` / `or` / `not` 代替大写布尔运算符。
- 复杂表达式不使用括号，导致 NOT 排除范围过大。
- 认为 `free full text[sb]` 等于 PMC 全文；它还包含出版商免费全文。
- 认为引号一定关闭 ATM；字段标签和短语索引行为仍需注意。
- 在 `--raw` 后再添加 `--author` 或 `--year-from`；程序会拒绝这种组合。

## 参考

- PubMed User Guide：https://pubmed.ncbi.nlm.nih.gov/help/
