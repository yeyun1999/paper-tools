### PubMed 检索字段速查表

| 字段名（标签） | 字段描述 | 检索示例 |
| :--- | :--- | :--- |
| Affiliation `[ad]` | 作者、团体作者或研究者的所属机构（由出版商提供）。2014 年起收录多位作者单位；跨多位作者的单位可用临近检索锁定同一单位 | `UCLA[ad]`；`"Hopkins Bloomberg Public"[ad:~45]` |
| All Fields `[all]` | 所有字段。不加标签的词默认在此检索，并经过 ATM 自动术语匹配（映射到 MeSH 词、期刊名、作者名等） | `diabetes[all]`；`diabetes`（等效） |
| Article Identifier `[aid]` | 出版商提交的文献编号，如 DOI、PII。建议加双引号，且**不要**带 `doi.org/` 前缀 | `"10.1016/j.cell.2020.01.001"[aid]` |
| Author `[au]` | 作者姓名，格式为「姓 + 空格 + 最多两个名首字母 + 后缀」，不加标点；会自动截断匹配不同首字母 | `fauci as[au]`；`o'brien jc jr[au]`；`"o'brien j"[au]`（关闭截断） |
| Author Identifier `[auid]` | 作者/团体/研究者的唯一标识符（ORCID、ISNI、VIAF 等） | `orcid 0000-0001-5027-4446[auid]` |
| Book `[book]` | NCBI Bookshelf 的图书题录。也可用无标签词 `pmcbook`（图书+章节）、`pmcbooktitle`（图书）、`pmcbookchapter`（章节） | `genereviews[book]`；`ataxia AND pmcbookchapter` |
| Completion Date `[dcom]` | NLM 内部处理完成日期，**不参与** All Fields 检索，必须带标签 | `2020/01:2020/06[dcom]` |
| Conflict of Interest Statement `[cois]` | 文中利益冲突声明内容（出版商提供或 PMC 全文含） | `financial[cois]`；`hascois`（所有含声明的记录） |
| Corporate Author `[cn]` | 团体/集体作者（如学会、协作组），按期刊原文显示 | `american heart association[cn]` |
| Create Date `[crdt]` | 题录首次进入 PubMed 的日期，**不参与** All Fields 检索；定期追踪新文献时比 `[dp]` 更全 | `"last 30 days"[crdt]` |
| EC/RN Number `[rn]` | 化学物质/酶编号：CAS 登记号、酶委员会 EC 号、FDA UNII 号 | `2751-14-6[rn]`；`EC 1.1.1.57[rn]` |
| Editor `[ed]` | 图书或章节的编者 | `smith j[ed]` |
| Entry Date `[edat]` | 题录录入 PubMed 的日期（旧称 Entrez Date），「Most Recent」排序依据；**不参与** All Fields 检索 | `2024[edat]`；`2024/01:2024/06[edat]` |
| Filter `[filter]` / `[sb]` | LinkOut 与 Clinical Queries 等技术性过滤标签 | `free full text[sb]`；`full text[sb]`；`LitCGeneral[Filter]` |
| First Author Name `[1au]` | 仅检索第一作者（个人）姓名 | `chen[1au]` |
| Full Author Name `[fau]` | 作者全名（2002 年起出版的文献），可正序或倒序输入 | `julia s wong[fau]`；`wong julia s[fau]` |
| Full Investigator Name `[fir]` | 研究者/协作组成员全名 | `harry janes[fir]`；`janes harry[fir]` |
| Grants and Funding `[gr]` | 基金号、合同号、机构内课题号；可按编号、资助代码、机构、国家分段检索 | `CA101211[gr]`；`NIH[gr]`；`"intramural nih"[gr]` |
| Investigator `[ir]` | 研究者或协作组成员（非署名作者），格式同作者字段 | `soller b[ir]` |
| ISBN `[isbn]` | 图书或章节的国际标准书号 | `978-0-12-345678-9[isbn]` |
| Issue `[ip]` | 期刊期号（含部分、增刊号） | `5[ip]` |
| Journal `[ta]` | 期刊：可用全称、NLM 缩写或 ISSN/eISSN；含特殊字符时去掉括号等再输入 | `J Biol Chem[ta]`；`0021-9258[ta]`；`"science"[ta]` |
| Language `[la]` | 文献出版语种；多数语言可用前三个字母 | `english[la]`；`chi[la]`；`jpn[la]`（日语例外） |
| Last Author Name `[lastau]` | 仅检索最后一位（常为通讯）作者姓名 | `fauci[lastau]` |
| Location ID `[lid]` | 充当页码的 DOI 或出版商 ID（电子页码）；建议加双引号 | `"10.1038/s41586-020-2649-2"[lid]` |
| MeSH Date `[mhda]` | MeSH 主题词被加到题录上的日期，**不参与** All Fields 检索 | `2020/03:2020/04[mhda]` |
| MeSH Major Topic `[majr]` | 文章的核心主题词（题录中带星号 `*` 的 MeSH 词） | `cytokines[majr]`；`plants/genetics[majr]` |
| MeSH Subheadings `[sh]` | 副主题词「自由浮动」检索（不绑定某个主题词）；可用两字母缩写；自动含下位副主题词，`[sh:noexp]` 可关闭 | `hypertension[mh] AND toxicity[sh]`；`dh[sh]` |
| MeSH Terms `[mh]` | NLM 受控词表 MeSH 主题词；默认自动包含下位词，用 `[mh:noexp]` 关闭；主题词/副主题词用斜杠连接 | `neoplasms[mh]`；`neoplasms[mh:noexp]`；`neoplasms/diet therapy` |
| Modification Date `[lr]` | 已完成题录的最近修订日期，**不参与** All Fields 检索 | `2023[lr]` |
| NLM Unique ID `[jid]` | NLM 目录分配给期刊的字母数字唯一 ID | `0375267[jid]` |
| Other Term `[ot]` | 作者关键词（非 MeSH 主题词）；`haskeyword` 可检索所有含关键词的记录 | `CRISPR[ot]`；`haskeyword` |
| Pagination `[pg]` | 页码，**只能检索首页页码**（记录中显示完整起止页） | `3248[pg]` |
| Personal Name as Subject `[ps]` | 该人物是文章论述对象（而非作者）时检索 | `varmus h[ps]` |
| Pharmacological Action `[pa]` | 具有某种药理作用的物质索引（含 MeSH 词与补充概念） | `anti-inflammatory agents[pa]` |
| Place of Publication `[pl]` | 期刊出版国别（只到国家，区域不可检索，需自行 OR 各国）；**不参与** All Fields / Text Word 检索 | `england[pl]` |
| PMCID and MID（无标签） | 直接输入 PMC 号或 NIH 手稿号检索 | `PMC2600426`；`hasnihmsid` |
| PMID `[pmid]` | PubMed 唯一标识号，永久不变、不复用；多个 PMID 用空格分隔会自动 OR | `16381840[pmid]`；`17170002 16381840` |
| Publication Date `[dp]`（=`[pdat]`） | 发表日期，格式 `yyyy/mm/dd`（月日可省），区间用冒号；另有 `[epdat]` 电子版、`[ppdat]` 印刷版 | `2019/01/01:2019/06/30[dp]`；`"last 5 years"[dp]` |
| Publication Type `[pt]` | 文献类型；默认含下位类型，`[pt:noexp]` 关闭 | `review[pt]`；`randomized controlled trial[pt]`；`preprint[pt]` |
| Publisher `[pubn]` | Bookshelf 类记录的出版商名称 | `elsevier[pubn]` |
| Secondary Source ID `[si]` | 二次数据源及其登录号（GenBank、GEO、PubChem、ClinicalTrials.gov 等），格式「来源/登录号」 | `genbank/AF001892[si]`；`ClinicalTrials.gov[si]` |
| Subset `[sb]` | 按主题、期刊类别或题录状态限定子集 | `medline[sb]`；`pubmednotmedline[sb]`；`"pubmed pmc"[sb]`；`all[sb]` |
| Supplementary Concept `[nm]` | 补充概念记录：化学物、协议、疾病或生物体名称，同义词自动映射 | `IL2 protein, human[nm]` |
| Text Words `[tw]` | 文本词：标题、摘要、MeSH 词、副主题词、出版类型、物质名、团体作者、作者关键词等 | `kidney allograft[tw]` |
| Title `[ti]` | 仅检索文献题名（图书则为合集题名） | `covid-19[ti]` |
| Title/Abstract `[tiab]` | 题名 + 摘要 + 作者关键词，是平衡查全与查准最常用字段 | `"PD-1 inhibitor"[tiab]` |
| Transliterated Title `[tt]` | 非英语原文题名的转写形式；**不**包含在 Text Word 检索中 | `（原文语种题名）[tt]` |
| Volume `[vi]` | 期刊卷号 | `13[vi]` |



### 常用 `[pt]` 文献类型代码表
在 PubMed 中，`[pt]`（Publication Type，文献类型）字段标签用于精准限定文章的信息类型或传达方式。

| 文献类型分类 | 英文文献类型名称 | 对应 `[pt]` 检索代码 | 描述与说明 |
| :--- | :--- | :--- | :--- |
| **基础文献类型** | Journal Article | `Journal Article[pt]` | 期刊论文，是 NLM 数据库中最主要的文献类型。 |
| **原始研究** | Clinical Trial | `Clinical Trial[pt]` | 临床试验，作者报告自己收集和分析数据的实证研究。 |
| | Randomized Controlled Trial | `Randomized Controlled Trial[pt]` | 随机对照试验（RCT），评估干预措施效果的高级别临床研究。 |
| | Comparative Study | `Comparative Study[pt]` | 比较研究，直接比较两种或多种干预措施优劣的研究。 |
| | Case Reports | `Case Reports[pt]` | 病例报告，描述特定患者的临床表现、诊断或治疗过程。 |
| | Validation Study | `Validation Study[pt]` | 验证研究，通常涉及诊断模型、评分量表或生物标志物的外部验证。 |
| **循证与综述** | Review | `Review[pt]` | 综述，总结已发表的研究并讨论其趋势和关系。 |
| | Systematic Review | `Systematic Review[pt]` | 系统评价，采用严格、系统的方法收集并综合相关研究证据。 |
| | Meta-Analysis | `Meta-Analysis[pt]` | 荟萃分析，使用统计学方法将多个独立研究的数据进行定量合并分析。 |
| **指南与共识** | Practice Guideline | `Practice Guideline[pt]` | 实践指南，为临床决策提供基于证据的系统性建议。 |
| | Consensus Statement | `Consensus Statement[pt]` | 共识声明（注：2026年更新前名为 Consensus Development Conference）。 |
| **会议与前沿** | Conference Proceedings | `Conference Proceedings[pt]` | 会议论文集（注：2026年更新前名为 Congress）。 |
| | Meeting Abstract | `Meeting Abstract[pt]` | 会议摘要，国际顶级医学会议上发布的最新临床试验数据或初步结果。 |
| **其他特殊类型** | Books and Documents | `Books and Documents[pt]` | 图书与文档，包含专著、教科书等。 |
| | Editorial | `Editorial[pt]` | 社论，期刊编辑或出版商对当前医学/科学事务发表的观点或政策声明。 |
| | Letter | `Letter[pt]` | 读者来信，针对期刊已发表文章的评论或专业交流。 |

### 💡 `[pt]` 字段检索注意事项

1. **自动扩展下位词**：默认情况下，使用 `[pt]` 检索时会自动包含其下位的文献类型（例如检索 `Review[pt]` 可能会包含 `Systematic Review`）。若需精确限定单一类型，可使用 `[pt:noexp]` 关闭自动扩展。
2. **大小写与拼写**：在高级检索框中使用时，必须使用完整的英文名称，如 `Randomized Controlled Trial[pt]`，不能简写或随意更改大小写。
3. **结合布尔逻辑**：常与 `AND` 结合使用以缩小范围，例如查找关于“心力衰竭”的随机对照试验：`"Heart Failure"[MeSH] AND "Randomized Controlled Trial"[pt]`。
