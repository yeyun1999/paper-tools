## Appendix 1：Indexed Fields（索引字段）

### 1. Core bibliographic（核心书目信息）

| Field | Description | Example |
|---|---|---|
| `EXT_ID:` | 按外部 ID 检索出版物（即仓储级分配的 ID，与来源共同构成唯一标识） | `EXT_ID:10826746` |
| `PMCID:` | 按 PubMed Central ID 检索（适用于有全文的文献） | `PMCID:PMC1287967` |
| `TITLE:` | 在标题中检索一个或多个词 | `TITLE:aspirin`，`TITLE:"protein knowledgebase"` |
| `ABSTRACT:` | 在摘要中检索一个或多个词 | `ABSTRACT:malaria`，`ABSTRACT:"chicken pox"` |
| `PUB_YEAR:` | 按出版年份检索（YYYY 格式），支持范围检索语法 | `PUB_YEAR:2000`，`PUB_YEAR:[2000 TO 2001]` |
| `E_PDATE:` | 电子出版日期（首次在线发表时间） | `E_PDATE:2013-12-15`，`E_PDATE:20070930`，`E_PDATE:[2000-12-18 TO 2014-12-30]`，`E_PDATE:[20040101 TO 20140101]` |
| `FIRST_PDATE:` | 首次出版日期（电子或印刷中较早者）；日期不完整时（如仅有年份）由算法确定取值 | `FIRST_PDATE:1995-02-01`，`FIRST_PDATE:20000101`，`FIRST_PDATE:[2000-10-14 TO 2010-11-15]`，`FIRST_PDATE:[20040101 TO 20140101]` |
| `P_PDATE:` | 期刊卷期的印刷出版日期 | `P_PDATE:1982-10-01`，`P_PDATE:20140101`，`P_PDATE:[2000-12-18 TO 2014-12-30]`，`P_PDATE:[20031114 TO 20141115]` |
| `EMBARGO_DATE:` | Europe PMC 被允许提供该文全文的起始日期（2015 年 3 月起收录的文献持有该日期） | `EMBARGO_DATE:[2015-03-01 TO 2015-03-31]`，`EMBARGO_DATE:2015-03-15` |
| `EMBARGOED_MAN:` | 依据全文相对于 `EMBARGO_DATE` 的可获取性限定结果。若在 20160101 请求 `EMBARGOED_MAN:Y`，将被翻译为 `EMBARGO_DATE:[20160101 TO *]`；`EMBARGOED_MAN:N` 翻译为 `EMBARGO_DATE:[* TO 20160101]` | `EMBARGOED_MAN:Y`，`EMBARGOED_MAN:N` |
| `AUTH:` | 在作者列表中检索姓氏及（可选）名首字母 | `AUTH:einstein`，`AUTH:"Smith AB"` |
| `INVESTIGATOR:` | 通过指定研究者检索出版物 | `INVESTIGATOR:"Orlandini F"` |
| `AUTHORID_TYPE:` | 列出与某一 ORCID 关联的出版物 | `AUTHORID_TYPE:ORCID` |
| `AUTHORID:` | 列出与指定 ORCID 关联的全部出版物 | `AUTHORID:"0000-0002-1767-9318"` |
| `AFF:` | 在作者单位（affiliation）字段检索词 | `AFF:ebi`，`AFF:"university of cambridge"` |
| `JOURNAL:` | 期刊名称，可用全称或缩写检索 | `JOURNAL:"biology letters"`，`JOURNAL:"biol lett"` |
| `ISSN:` | 按 ISSN 检索期刊（可参考 NCBI 在 PubMed 的期刊与 ISSN 列表） | `ISSN:0028-0836` |
| `VOLUME:` | 检索期刊卷，最适合与 `JOURNAL/PUB_YEAR/VOLUME/ISSUE/SPAGE` 组合使用 | `JOURNAL:"biology letters" VOLUME:10` |
| `ISSUE:` | 检索期刊期，最适合与 `JOURNAL/PUB_YEAR/VOLUME/ISSUE/SPAGE` 组合使用 | `JOURNAL:"biology letters" VOLUME:10 ISSUE:2` |
| `SPAGE:` | 检索起始页为第 N 页的文章，最好与 `JOURNAL` 或其他字段组合 | `SPAGE:25` |
| `LICENSE:` | 按指定的 Creative Commons 许可证检索（出版方赋值已分组，见下）。`LICENSE:"CC BY-SA"` 等价于 `"cc by sa" OR "cc-by sa" OR "cc by-sa" OR "cc-by-sa"`。各分组取值：• CC BY：`"cc"`, `"cc by"`, `"cc-by"`• CC BY-SA：`"cc"`, `"cc by sa"`, `"cc-by sa"`, `"cc by-sa"`, `"cc-by-sa"`• CC BY-ND：`"cc"`, `"cc by nd"`, `"cc-by nd"`, `"cc by-nd"`, `"cc-by-nd"`• CC BY-NC：`"cc"`, `"cc by nc"`, `"cc-by nc"`, `"cc by-nc"`, `"cc-by-nc"`• CC BY-NC-ND：`"cc"`, `"cc by nc nd"`, `"cc-by nc nd"`, `"cc by-nc nd"`, `"cc by nc-nd"`, `"cc-by-nc nd"`, `"cc by-nc-nd"`, `"cc-by nc-nd"`, `"cc-by-nc-nd"`• CC BY-NC-SA：`"cc"`, `"cc by nc sa"`, `"cc-by nc sa"`, `"cc by-nc sa"`, `"cc by nc-sa"`, `"cc-by-nc sa"`, `"cc by-nc-sa"`, `"cc-by nc-sa"`, `"cc-by-nc-sa"` | `LICENSE:"cc by sa"` 等（同左分组写法均可）；`LICENSE:cc`（返回全部已分配 CC 许可的文章） |
| `EPMC_AUTH_MAN:` | 识别通过 Europe PMC plus（原 UKPMC+）稿件投稿系统提交的稿件 | `EPMC_AUTH_MAN:y` |
| `NIH_AUTH_MAN:` | 识别通过 NIH 稿件投稿系统提交的稿件 | `NIH_AUTH_MAN:y` |
| `AUTH_MAN:` | 检索经稿件投稿系统提交的文章 | `AUTH_MAN:y` |
| `AUTH_MAN_ID:` | 通过稿件投稿 ID 查找文章 | `AUTH_MAN_ID:EMS59581` |

### 2. Article metadata（文章元数据）

| Field | Description | Example |
|---|---|---|
| `DISEASE:` | 检索挖掘出的疾病 | `DISEASE:dysthymias` |
| `GENE_PROTEIN:` | 检索挖掘出 GENE_PROTEINS 的记录 | `GENE_PROTEIN:gng11` |
| `GOTERM:` | 检索挖掘出 GOTERM 的记录 | `GOTERM:apoptosis` |
| `IS_SCANNED:` | 检索扫描/OCR 内容 | `IS_SCANNED:y` |
| `LANG:` | 限定检索语种 X | `LANG:fre`，`LANG:eng` |
| `GRANT_AGENCY:` | 按资助研究的资助机构限定 | `GRANT_AGENCY:wellcome`，`GRANT_AGENCY:"medical research council"` |
| `GRANT_ID:` | 按资助研究的基金 ID 限定 | `GRANT_ID:100229`，`GRANT_ID:71672` |
| `KW:` | 按关键词限定（含 MeSH 及出版方提供的术语） | `KW:galactosylceramides`，`KW:"recombinant proteins"` |
| `CHEM:` | 按 MeSH 物质限定 | `CHEM:propantheline`，`CHEM:"protein kinases"` |
| `HAS_ABSTRACT:` | 按是否存在摘要限定结果 | `HAS_ABSTRACT:y`，`HAS_ABSTRACT:n` |
| `ORGANISM:` | 检索挖掘出的生物体 | `ORGANISM:terebratulide` |
| `PUB_TYPE:` | 按出版物类型限定 | `PUB_TYPE:review`，`PUB_TYPE:"retraction of publication"` |
| `HAS_VERSION_EVALUATIONS:` | 限定结果为带有同行评审/评估的文章或其任一版本 | `HAS_VERSION_EVALUATIONS:y`；`HAS_VERSION_EVALUATIONS:n` |

### 3. Full text availability（全文可获取性）

| Field | Description | Example |
|---|---|---|
| `BODY:` | 在全文正文中检索词 | `BODY:PCR` |
| `DOI:` | 按数字对象标识符（DOI）检索出版物 | `DOI:10.1007/bf00197367`，`DOI:10.1097/aln.0b013e3181b87edb` |
| `HAS_DOI:` | 限定为有或没有 DOI 的出版物 | `HAS_DOI:y`，`HAS_DOI:n` |
| `IN_PMC:` | 按 PubMed Central 中是否有全文限定 | `IN_PMC:y` |
| `IN_EPMC:` | 按 Europe PMC 中是否有全文限定 | `IN_EPMC:y` |
| `HAS_PDF:` | 按是否有全文 PDF 版本限定 | `HAS_PDF:y` |

### 4. Collection metadata（馆藏元数据）

| Field | Description | Example |
|---|---|---|
| `SRC:` | 检索来自特定仓储的文章（可用数据源见第 3 节） | `SRC:ctx`，`SRC:hir` |
| `HAS_XREFS:` | 限定为含有指向其他数据库交叉引用的文章（数据库列表见第 6 节） | `HAS_XREFS:y` |
| `HAS_CRD:` | 按是否存在指向相关内容的链接限定。CRD 是提供文章评论的数据库 | `HAS_CRD:y` |
| `HAS_TM:` | 限定为经文本挖掘的全文文章（或反之） | `HAS_TM:y` |
| `HAS_REFLIST:` | 限定为含参考文献列表的出版物（或反之） | `HAS_REFLIST:y` |
| `CREATION_DATE:` | 按进入 Europe PMC 数据库的日期检索（YYYY-MM-DD 格式），支持范围检索语法 | `CREATION_DATE:2010-11-11`，`CREATION_DATE:[2010-11-11 TO 2010-12-11]` |
| `UPDATE_DATE:` | 按在 Europe PMC 数据库中的更新日期检索（YYYY-MM-DD 格式），支持范围检索语法 | `UPDATE_DATE:2011-11-11`，`UPDATE_DATE:[2011-11-11 TO 2011-12-11]` |
| `OPEN_ACCESS:` | 限定为开放获取（Open Access）文章 | `OPEN_ACCESS:y` |
| `HAS_LABSLINKS:` | 列出含第三方提供链接的文章（使用 Europe PMC External Links Service） | `HAS_LABSLINKS:y` |
| `HAS_DATA:` | 列出带有 `related_data` 或 `supporting_data` 标签的数据-文献链接的文章 | `HAS_DATA:y` |
| `HAS_SUPPL:` | 列出带有补充数据（如电子表格、视频文件等）的文章 | `HAS_SUPPL:y` |
| `LABS_PUBS:` | 按提供方 ID 列出含外部链接的文章 | `LABS_PUBS:1001` |

### 5. Content set filter（内容集过滤）

| Field | Description | Example |
|---|---|---|
| `SB:` | 限定结果为 EuroFIR 子集 | `SB:eurofir` |

### 6. Books（图书）

| Field | Description | Example |
|---|---|---|
| `ISBN:` | 按 ISBN 检索图书 | `ISBN:9780815340720` |
| `ED:` | 按编者检索图书 | `ED:jensen`，`HAS_BOOK:y` |
| `PUBLISHER:` | 按出版方检索图书 | `PUBLISHER:"OUP Oxford"`，`HAS_BOOK:y` |
| `HAS_BOOK:` | 列出 Europe PMC Bookshelf 上的全文图书 | `HAS_BOOK:y` |
| `BOOK_ID:` | 通过指定其 `NBK` 编号查找 Europe PMC Bookshelf 上的全文图书 | `BOOK_ID:NBK27326` |

### 7. Database cross references（数据库交叉引用）

| Field | Description | Example |
|---|---|---|
| `ARXPR_PUBS:` | 显示指向指定 ArrayExpress ID 链接的出版物 | `ARXPR_PUBS:E-GEOD-22481` |
| `UNIPROT_PUBS:` | 显示指向指定 UniProt ID 链接的出版物 | `UNIPROT_PUBS:q1rdg3` |
| `EMBL_PUBS:` | 显示指向指定 EMBL ID 链接的出版物 | `EMBL_PUBS:KJ634683` |
| `PDB_PUBS:` | 显示指向指定 PDBe ID 链接的出版物 | `PDB_PUBS:2w3z` |
| `INTACT_PUBS:` | 显示指向指定 IntAct ID 链接的出版物 | `INTACT_PUBS:ebi-493556` |
| `INTERPRO_PUBS:` | 显示指向指定 InterPro ID 链接的出版物 | `INTERPRO_PUBS:ipr013998` |
| `CHEBI_PUBS:` | 显示指向指定 ChEBI ID 链接的出版物 | `CHEBI_PUBS:62806` |
| `CHEBITERM:` | 检索挖掘出的化学术语 | `CHEBITERM:dihydrocapsaicin` |
| `CRD_LINKS:` | 显示指向指定相关内容 ID 链接的出版物 | `CRD_LINKS:22001008219` |
| `HAS_ARXPR:` | 限定为（不）含 ArrayExpress 目录链接的出版物 | `HAS_ARXPR:y` |
| `HAS_UNIPROT:` | 限定为（不）含 UniProt 目录链接的出版物 | `HAS_UNIPROT:y` |
| `HAS_EMBL:` | 限定为（不）含 EMBL 数据库链接的出版物 | `HAS_EMBL:y` |
| `HAS_PDB:` | 限定为（不）含 PDBe 数据库链接的出版物 | `HAS_PDB:y` |
| `HAS_INTACT:` | 限定为（不）含 IntAct 数据库链接的出版物 | `HAS_INTACT:y` |
| `HAS_INTERPRO:` | 限定为（不）含 InterPro 数据库链接的出版物 | `HAS_INTERPRO:y` |
| `HAS_CHEBI:` | 限定为（不）含 ChEBI 词典链接的出版物 | `HAS_CHEBI:y` |
| `HAS_CHEMBL:` | 限定为（不）含 ChEMBL 链接的出版物 | `HAS_CHEMBL:y` |
| `HAS_OMIM:` | 限定为（不）含 OMIM 链接的出版物 | `HAS_OMIM:y` |
| `CITES:` | 检索引用某给定文章的出版物，文章以 `ID_source` 格式指定（来源见第 3 节） | `CITES:8521067_med`，`CITES:IND43783977_agr` |
| `CITED:` | 检索被引用 N 次的出版物 | `CITED:100` |
| `REFFED_BY:` | 检索引用指定文章的出版物，格式 `ID_source`（来源见第 3 节） | `REFFED_BY:9497246_med` |

### 8. Database citations（数据库引用）

| Field | Description | Example |
|---|---|---|
| `ACCESSION_ID:` | 查找含指定登录号（accession number）的文章 | `ACCESSION_ID:A12360` |
| `ACCESSION_TYPE:` | 查找引用某类数据库记录的文章，各类型取值如下 | `ACCESSION_TYPE:arrayexpress`（ArrayExpress 记录）`bioproject`（欧洲核苷酸档案中的 BioProject 记录）`biosample`（BioSamples 记录）`doi`（数据 DOI）`ega`（欧洲基因组-表型档案 EGA 记录）`emdb`（电子显微镜数据 bank EMDB 中的 EM 资源记录）`ensembl`（Ensembl 记录）`eudract`（EU Clinical Trials Register 的 EudraCT 记录）`gen`（欧洲核苷酸档案记录）`go`（Gene Ontology 记录）`interpro`（InterPro 记录）`nct`（美国 NIH ClinicalTrials.gov 注册库的 NCT 临床研究记录）`omim`（OMIM 记录）`pdb`（欧洲蛋白质数据库 PDB 记录）`pfam`（蛋白家族 Pfam 记录）`pxd`（ProteomeXchange 记录）`refseq`（参考序列数据库 RefSeq 记录）`refsnp`（dbSNP 短遗传变异数据库 RefSNP 记录）`sprot`（蛋白质序列与功能信息资源 UniProt 记录）`treefam`（动物基因树数据库 TreeFam 记录） |

### 9. Section-level search（章节级检索）

| Field | Description | Example |
|---|---|---|
| `ABBR:` | 在 Abbreviations（缩略语）章节中检索词 | `ABBR:mRNA` |
| `ACK_FUND:` | 在 Acknowledgements & Funding（致谢与资助）章节中检索词 | `ACK_FUND:ERC` |
| `APPENDIX:` | 在 Appendix（附录）章节中检索词 | `APPENDIX:ethics` |
| `AUTH_CON:` | 在 Author Contribution（作者贡献）章节中检索短语 | `AUTH_CON:"Smith"` |
| `CASE:` | 在 Case Study（案例研究）章节中检索词 | `CASE:leukemia` |
| `COMP_INT:` | 在 Competing Interest（利益冲突）章节中检索短语 | `COMP_INT:"no conflict"` |
| `CONCL:` | 在 Conclusion（结论）章节中检索词 | `CONCL:osteoporosis` |
| `DISCUSS:` | 在 Discussion（讨论）章节中检索词 | `DISCUSS:cardiovascular` |
| `FIG:` | 在 Figures（图）章节中检索短语 | `FIG:"in vitro"` |
| `INTRO:` | 在 Introduction & Background（引言与背景）章节中检索短语 | `INTRO:"protein interactions"` |
| `KEYWORD:` | 在 Keywords（关键词）章节中检索词 | `KEYWORD:isoform` |
| `METHODS:` | 在 Materials & Methods（材料与方法）章节中检索短语 | `METHODS:"yeast two-hybrid"` |
| `OTHER:` | 在 Others（其他）章节中检索短语 | `OTHER:"transgenic mice"` |
| `REF:` | 在 References（参考文献）章节中检索词 | `REF:COX2` |
| `RESULTS:` | 在 Results（结果）章节中检索短语 | `RESULTS:"in vivo"` |
| `SUPPL:` | 在 Supplementary Information（补充信息）章节中检索词（指示补充数据的可获取位置） | `SUPPL:supplementary` |
| `TABLE:` | 在 Tables（表）章节中检索词 | `TABLE:comparison` |
