# paper-tools 架构设计

> 面向生物医学研究者的文献检索与全文获取 CLI。人类与 AI 助理双用户，检索、元数据补全、全文定位、下载、文本提取五类能力全部插件化，uv 管理环境。
>
> 状态：设计稿 v2（待评审）。v2 变更：插件接口由 2 类扩展为 5 类角色（Searcher / MetadataProvider / Locator / Downloader / Extractor），新增元数据补全链与文本提取流水线。配套开发计划见 [roadmap.md](roadmap.md)。

## 1. 定位与设计目标

- **核心场景**：按关键词/字段检索文献元数据与摘要；按 DOI/PMID 等标识符获取开放获取（OA）全文（PDF / JATS XML / 纯文本）。
- **双用户**：
  - 研究者：Rich 表格、进度提示、可读的错误信息。
  - AI 助理：所有命令支持 `--json`，字段稳定、退出码明确、错误结构化；后期提供 MCP 服务器（`paper-tools mcp`）。
- **插件化**：五类角色（检索 / 元数据补全 / 全文定位 / 下载 / 提取）都是插件，通过 Python entry points 发现。内置插件与第三方插件走完全相同的机制，`uv pip install paper-tools-xxx` 即自动接入。
- **合规边界**：只使用官方 API 与开放获取来源；不提供任何绕过付费墙的能力。订阅文献返回出版商链接与 OA 状态，由用户自行通过机构访问。
- **环境管理**：uv 单一工具链（`uv sync` / `uv run` / `uv build` / `uv publish`），提交 `uv.lock`。

## 2. 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│ 接口层                                                        │
│   CLI (Typer + Rich)           MCP Server (可选 extra)        │
│   人类输出 / --json 输出        stdio, 复用同一服务层          │
├──────────────────────────────────────────────────────────────┤
│ 应用服务层                                                    │
│   SearchService   MetadataService   FetchService              │
│   （检索）        （补全链编排）     （定位→下载→提取编排）     │
│   PluginRegistry（发现/加载/配置注入）                         │
├──────────────────────────────────────────────────────────────┤
│ 核心层                                                        │
│   models (pydantic)  query  errors  config                    │
│   http (限流/重试)   cache (diskcache + 文件缓存)              │
├──────────────────────────────────────────────────────────────┤
│ 插件接口层 (typing.Protocol, 五类角色)                         │
│   Searcher  MetadataProvider  Locator  Downloader  Extractor  │
├──────────────────────────────────────────────────────────────┤
│ 插件实现（内置，与第三方同构）                                 │
│   pubmed  europepmc  crossref  openalex  semantic_scholar     │
│   unpaywall  pmc_oa  http_direct  jats  pypdf                 │
└──────────────────────────────────────────────────────────────┘
```

完整流水线：

```
search ──► Paper 浅记录 ──enrich──► Paper 完整记录
                                      │
              ┌───────────────────────┤
              ▼                       ▼
           locate ──► 候选列表 ──► download ──► PDF/XML 产物
                                               │ (--format text)
                                               ▼
                                            extract ──► 纯文本
```

数据流（以 `fetch doi:10.1038/xxx --format pdf` 为例）：

1. CLI 解析标识符 → `MetadataService` 构造 stub Paper，走补全链取回完整元数据。
2. `FetchService` 向所有 Locator 插件收集 `FullTextCandidate`（Unpaywall 定位 OA 链接、Europe PMC / PMC OA 直接给直链）。
3. 候选去重、按格式与来源可信度排序，路由给声明支持该候选的 Downloader 逐个尝试，下载并校验（PDF 魔数、XML 可解析）。
4. 成功：写入输出目录与文件缓存，返回 `FullText` 结果；全部失败：返回出版商链接，退出码 4。
5. 若 `--format text`：产物交给对应 Extractor（XML→JATS 解析，PDF→pypdf），输出纯文本并记录提取器溯源。

## 3. 技术选型

| 组件 | 选择 | 理由 |
|---|---|---|
| Python | ≥ 3.11 | 内置 `tomllib`、完善的类型语法；`.python-version` 固定 |
| 环境/构建 | uv + hatchling | 用户指定 uv；src 布局，`uv.lock` 锁定 |
| CLI | Typer + Rich | 类型注解即参数定义，子命令组织清晰，人类输出美观 |
| 数据模型 | pydantic v2 | 校验 + 序列化 + 自动导出 JSON Schema（供 AI 与 `schema` 命令） |
| HTTP | httpx（同步） | 现代 API、超时/连接池完善；首版不做异步，避免插件接口复杂化 |
| 缓存 | diskcache + 文件缓存 | 元数据/搜索结果 KV 缓存；PDF 按哈希落盘 |
| XML 解析 | defusedxml | 上游 XML 不可信：禁实体展开/外部实体（防 XXE/billion laughs），兼容正常 JATS DOCTYPE |
| 配置 | platformdirs + TOML | 跨平台用户配置目录，环境变量覆盖 |
| 文本提取 | Extractor 插件：jats（内置）、pypdf（extra `text`） | 提取引擎与下载来源正交，可替换；GROBID 等重方案后续以插件接入 |
| MCP | 官方 `mcp` SDK（extra `mcp`） | `paper-tools mcp` 子命令，stdio 传输 |
| 质量 | ruff（lint+format）、mypy、pytest + respx | respx 拦截 httpx 做录制回放测试 |

## 4. 目录结构

```
paper-tools/
├── pyproject.toml              # 依赖、entry points、工具配置
├── uv.lock
├── .python-version
├── README.md
├── docs/
│   ├── architecture.md         # 本文档
│   ├── roadmap.md              # 开发计划
│   └── plugin-guide.md         # 插件开发指南（M6 交付）
├── src/paper_tools/
│   ├── __init__.py             # __version__
│   ├── __main__.py             # python -m paper_tools
│   ├── cli/
│   │   ├── app.py              # Typer 根应用、全局选项、异常→退出码映射
│   │   ├── search.py / get.py / fetch.py
│   │   ├── plugins.py          # sources 命令
│   │   ├── config.py / cache.py / schema.py / mcp.py
│   │   └── render.py           # Rich 表格与 JSON 双输出
│   ├── core/
│   │   ├── models.py           # Paper / Identifier / SearchPage / FullText ...
│   │   ├── query.py            # 统一查询模型
│   │   ├── errors.py           # 异常层次 + 错误码
│   │   ├── config.py           # TOML + env + CLI 三级合并
│   │   ├── http.py             # 限流、重试、UA、超时
│   │   ├── cache.py            # diskcache 封装 + PDF 文件缓存
│   │   ├── plugins.py          # entry points 发现、注册表、上下文注入
│   │   └── services.py         # SearchService / MetadataService / FetchService
│   ├── plugins/                # 内置插件（每个一文件，复杂者可成包）
│   │   ├── pubmed.py           # Searcher + MetadataProvider
│   │   ├── europepmc.py        # Searcher + MetadataProvider + Locator + Downloader
│   │   ├── crossref.py         # Searcher + MetadataProvider
│   │   ├── openalex.py         # Searcher + MetadataProvider + Locator
│   │   ├── semantic_scholar.py # Searcher + MetadataProvider
│   │   ├── unpaywall.py        # MetadataProvider(OA 字段) + Locator
│   │   ├── pmc_oa.py           # Locator + Downloader
│   │   ├── http_direct.py      # Downloader（通用）
│   │   ├── jats.py             # Extractor（XML→text）
│   │   └── pypdf_extractor.py  # Extractor（PDF→text，extra text）
│   └── py.typed
├── tests/
│   ├── unit/                   # 模型、查询翻译、插件管理器、配置、合并策略
│   ├── contract/               # 插件契约测试套件（按角色参数化，所有插件必过）
│   └── integration/            # respx 回放；live 标记的真实 API 冒烟
└── examples/
    └── agent-usage.md          # AI 助理调用示例（M5 交付）
```

## 5. 核心域模型

所有模型为 pydantic v2，字段即 JSON 契约（`schema_version = "1.1"`；1.0 于 M5 冻结，1.1 新增 Paper.fulltext_links）。示意：

```python
class Author(BaseModel):
    name: str
    orcid: str | None = None
    affiliation: str | None = None


class Paper(BaseModel):
    title: str
    identifiers: dict[str, str]  # {"doi": "10.1038/...", "pmid": "12345678", ...}
    authors: list[Author] = []
    year: int | None = None
    journal: str | None = None
    abstract: str | None = None
    publication_type: str | None = None
    oa_status: Literal["gold", "green", "hybrid", "bronze", "closed", "unknown"] = "unknown"
    publisher_url: str | None = None  # 无论 OA 与否都尽量给出
    license: str | None = None
    sources: list[str] = []  # 贡献过字段的插件名，用于溯源
    fulltext_links: list[FullTextCandidate] = []  # 搜索/补全期捕获的 OA 全文链接（1.1）


class SearchPage(BaseModel):
    items: list[Paper]  # 可能是浅记录，完整度由源决定；--enrich 补全
    total: int | None = None  # 上游给不出总数时为 None
    next_cursor: str | None = None  # 不透明游标，插件自定义编码
    source: str


class FullTextCandidate(BaseModel):
    url: str
    format: Literal["pdf", "xml", "text", "landing"]
    locator: str  # 定位到该候选的插件
    license: str | None = None


class Artifact(BaseModel):
    # Downloader 的原始产物（内存中），校验/提取/落盘由 FetchService 完成
    format: Literal["pdf", "xml", "text"]
    content: bytes
    source_url: str
    downloader: str
    license: str | None = None


class FullText(BaseModel):
    paper: Paper
    format: Literal["pdf", "xml", "text"]
    path: Path  # 落盘位置（输出目录或缓存）
    sha256: str
    source_url: str
    downloader: str  # 实际完成下载的插件
    license: str | None = None
    extractor: str | None = None  # format=text 时记录提取器
    extracted_from: Literal["pdf", "xml"] | None = None
```

标识符约定：`doi:` / `pmid:` / `pmcid:` / `openalex:` / `s2:` / `arxiv:` 前缀，裸字符串按 DOI 处理（纯数字串便捷识别为 PMID）。归一化：DOI 小写、去 `https://doi.org/` 前缀（`normalize_doi`）；PMCID 统一 `PMC` 前缀（`normalize_pmcid`，S2 等源可能给裸数字）；OpenAlex 用短 ID（`https://openalex.org/W123` → `W123`）；PMID 从 URL 取末段数字。各插件负责把自家 ID 映射进 `identifiers`（S2 的 externalIds 一次映射 DOI/PMID/PMCID/arXiv/s2），跨库去重以 DOI 为主键。

**浅记录（stub）约定**：search 返回的 Paper 只保证 `title` + 至少一个标识符；摘要、作者、OA 状态等可能缺失。补全是 MetadataProvider 的职责，不是 search 的隐含义务——这样搜索插件保持轻量，补全按需触发、可缓存。

## 6. 统一查询模型

双轨制：结构化字段（跨引擎可移植）+ 原生语法直通（保留引擎全部能力）。

```python
class Query(BaseModel):
    text: str | None = None  # 自由词
    title: str | None = None
    author: str | None = None
    journal: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    open_access: bool | None = None
    raw: str | None = None  # 引擎原生查询串；与结构化字段互斥
```

每个 Searcher 插件实现 `translate(query) -> 原生参数`，映射表写进插件开发指南。五源映射：

| 统一字段 | PubMed | Europe PMC | Crossref | OpenAlex | Semantic Scholar |
|---|---|---|---|---|---|
| `text="CRISPR"` | `CRISPR` | `CRISPR` | `query=CRISPR` | `search=CRISPR` | `query=CRISPR` |
| `author="Zhang"` | `Zhang[Author]` | `AUTH:"Zhang"` | `query.author=Zhang` | filter `raw_author_name.search:Zhang` | 并入 `query` |
| `journal="Nature"` | `Nature[Journal]` | `JOURNAL:"Nature"` | `query.container-title=Nature` | filter `primary_location.source.display_name.search:Nature` | `venue=Nature` |
| `year_from=2020, year_to=2025` | `2020:2025[dp]` | `FIRST_PDATE:[2020 TO 2025]` | filter `from-pub-date:2020,until-pub-date:2025` | filter `from_publication_date:2020-01-01,until_publication_date:2025-12-31` | `year=2020-2025` |
| `open_access=True` | `free full text[sb]` | `OPEN_ACCESS:y` | 无可靠 OA 过滤 → `UsageError` 提示换源 | filter `is_oa:true` | `openAccessPdf=true` |

`--raw` 直通时不做翻译，CLI 提示该查询不可移植到其他源。

## 7. 插件系统（五类角色）

### 7.1 角色划分与发现

流水线 `search → enrich → locate → download → extract` 对应五类角色，各占一个 entry-point group：

| 角色 | Entry-point group | 职责 | 关键属性 |
|---|---|---|---|
| Searcher | `paper_tools.searchers` | 关键词/字段检索，返回浅记录页 | — |
| MetadataProvider | `paper_tools.metadata` | 按标识符补全元数据（含按 ID 取详情） | `id_kinds`：可接受的标识符类型 |
| Locator | `paper_tools.locators` | 为 Paper 定位全文候选链接 | — |
| Downloader | `paper_tools.downloaders` | 下载候选并校验产物 | `formats`：支持的产物格式 |
| Extractor | `paper_tools.extractors` | PDF/XML → 纯文本 | `source_formats`：可处理的输入格式 |

拆分原则：**按行为职责拆，不按数据格式拆**。文本与 PDF 的差异由格式校验器和 Extractor 阶段处理，下载接口不因格式分裂——同一来源（如 Europe PMC）既给 XML 又给 PDF，只注册一个 Downloader。而"定位"与"传输"是两种真实不同的行为：Unpaywall 只定位不下载，通用 HTTP 下载器只下载不定位，因此拆为 Locator / Downloader 两个接口。

一个插件类可同时实现多个角色，注册到多个 group。内置插件在主包 `pyproject.toml` 中自我声明，与第三方完全同构：

```toml
[project.entry-points."paper_tools.searchers"]
pubmed = "paper_tools.plugins.pubmed:PubMedSearcher"
europepmc = "paper_tools.plugins.europepmc:EuropePmcSearcher"
crossref = "paper_tools.plugins.crossref:CrossrefSearcher"
openalex = "paper_tools.plugins.openalex:OpenAlexSearcher"
semantic_scholar = "paper_tools.plugins.semantic_scholar:SemanticScholarSearcher"

[project.entry-points."paper_tools.metadata"]
pubmed = "paper_tools.plugins.pubmed:PubMedMetadata"
europepmc = "paper_tools.plugins.europepmc:EuropePmcMetadata"
crossref = "paper_tools.plugins.crossref:CrossrefMetadata"
openalex = "paper_tools.plugins.openalex:OpenAlexMetadata"
semantic_scholar = "paper_tools.plugins.semantic_scholar:SemanticScholarMetadata"
unpaywall = "paper_tools.plugins.unpaywall:UnpaywallMetadata"

[project.entry-points."paper_tools.locators"]
unpaywall = "paper_tools.plugins.unpaywall:UnpaywallLocator"
europepmc = "paper_tools.plugins.europepmc:EuropePmcLocator"
pmc_oa = "paper_tools.plugins.pmc_oa:PmcOaLocator"
openalex = "paper_tools.plugins.openalex:OpenAlexLocator"

[project.entry-points."paper_tools.downloaders"]
europepmc = "paper_tools.plugins.europepmc:EuropePmcDownloader"
pmc_oa = "paper_tools.plugins.pmc_oa:PmcOaDownloader"
http_direct = "paper_tools.plugins.http_direct:HttpDirectDownloader"

[project.entry-points."paper_tools.extractors"]
jats = "paper_tools.plugins.jats:JatsExtractor"
pypdf = "paper_tools.plugins.pypdf_extractor:PypdfExtractor"
```

- `PluginRegistry` 启动时按 group 扫描 entry points，实例化并注入 `PluginContext(config, http, cache)`；同名插件允许第三方覆盖内置（打印 warning），便于替换实现。
- 第三方开发：独立发行包声明同名 group 即可；本地开发用 `uv pip install -e ./my-plugin`。不做运行时目录扫描加载 .py（避免任意代码执行的隐蔽入口）。
- 信任模型：entry point 插件即 Python 代码，安装第三方插件等同于安装任意依赖，文档中明示。

### 7.2 接口定义

```python
@dataclass(frozen=True)
class PluginMeta:
    name: str
    version: str
    description: str


class Searcher(Protocol):
    meta: PluginMeta

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage: ...


class MetadataProvider(Protocol):
    meta: PluginMeta
    id_kinds: frozenset[str]  # {"doi", "pmid", ...}，用于路由

    def enrich(self, paper: Paper) -> Paper: ...

    # 语义：只填缺失字段，不覆盖已有值； identifiers 做并集；
    # 无法处理（无可用标识符/上游无记录）时原样返回。


class Locator(Protocol):
    meta: PluginMeta

    def resolve(self, paper: Paper) -> list[FullTextCandidate]: ...


class Downloader(Protocol):
    meta: PluginMeta
    formats: frozenset[str]  # {"pdf", "xml"}

    def supports(self, candidate: FullTextCandidate) -> bool: ...
    def download(self, candidate: FullTextCandidate) -> Artifact: ...


class Extractor(Protocol):
    meta: PluginMeta
    source_formats: frozenset[str]  # {"pdf"} / {"xml"}

    def extract(self, data: bytes, *, source_format: str) -> str: ...
```

设计要点：

- **enrich 统一了"按 ID 取详情"与"补全浅记录"**：`get doi:...` 就是构造只含该标识符的 stub 走补全链；search 结果的补全是同一条链。补全来源不必是搜索引擎（Unpaywall 补 OA 状态/license）。
- **Locator 只找不下**：产出的候选由 FetchService 路由给 `supports()` 返回 True 的 Downloader；`landing` 候选永不下载，仅兜底展示。
- **Downloader 按候选路由而非按 Paper**：`http_direct` 支持任意 http(s) 直链；`pmc_oa` 只支持 PMC OA 的地址（tar.gz 内存解包，不落盘解压）；`europepmc` 只支持自家 fullTextXML 地址（PDF 由 pmc_oa/unpaywall 覆盖）。
- **Extractor 与下载正交**：`--format text` 时按产物格式选提取器（XML→jats，PDF→pypdf），可被第三方替换（GROBID、marker）；提取结果记录 `extractor` 与 `extracted_from` 溯源。

### 7.3 内置插件清单

| 插件 | 角色 | 说明 |
|---|---|---|
| pubmed | Searcher + MetadataProvider | NCBI E-utilities（esearch/esummary/efetch），默认相关性排序（Best Match），PMID/PMCID 映射，api_key 支持 |
| europepmc | Searcher + MetadataProvider + Locator + Downloader | REST API；fullTextXML 直接给 JATS XML |
| crossref | Searcher + MetadataProvider | DOI 元数据权威源，`/works`；mailto polite pool；JATS 摘要清洗为纯文本；无可靠 OA 过滤（`--oa-only` 报 UsageError） |
| openalex | Searcher + MetadataProvider + Locator | 元数据 + `best_oa_location` OA 定位；倒排索引摘要重建；cursor 分页；doi/openalex/pmid/pmcid 四路补全；可选 api_key（`Authorization: Bearer`，配后限流提至 10 req/s） |
| semantic_scholar | Searcher + MetadataProvider | Graph API；`x-api-key` 支持；DOI/PMID/PMCID/S2/ARXIV 五路补全；1 req/s + 退避应对共享限额 |
| unpaywall | MetadataProvider + Locator | enrich 只补 oa_status/license；resolve 按 DOI 查 OA 副本（需配置 email） |
| pmc_oa | Locator + Downloader | PMC OA Web Service 定位（pmid/doi 经 idconv 换 PMCID），tar.gz 内存解包取 PDF/XML；非 OA 子集返回空候选 |
| http_direct | Downloader | 通用 HTTP 传输兜底；魔数/体积/XML 校验由 FetchService 统一执行 |
| jats | Extractor | JATS XML → 纯文本（内置，无额外依赖） |
| pypdf | Extractor | PDF → 纯文本（extra `text`），质量有限需标注 |

bioRxiv/medRxiv、arXiv q-bio、GROBID 等进 backlog，作为第三方插件机制的验证案例。

## 8. 服务编排

### 8.1 SearchService（单源 / 多源聚合）

1. **路由**：`sources` 为空取 `general.default_source`；单源时游标原样透传（行为与历史版本一致）。
2. **多源并发**：多个源用线程池并发检索（各源独立 limit），失败源降级为 `warnings`，全部失败抛 `UpstreamError`（退出码 3）。
3. **去重合并**：主键 DOI → 兜底 PMID → 再兜底规范化标题指纹；重复条目走 `merge_papers`（fill-missing、identifiers 并集、sources 记录贡献源、冲突告警）。去重仅在**页内**（跨页无状态）。
4. **排序**：各源相关性分数不可比，按源顺序轮转交错（round-robin）输出；`--limit` 只约束各源返回量，合并去重后不再截断（单页可超过 limit）；`total` 为各源 total 之和（去重前，近似值）。
5. **聚合游标**：`next_cursor` 为免转义 token `ms1.<源名>:<游标>,...`（键按字典序；游标段对 `% : ,` 最小百分号转义，源名经注册时字符合约校验，命令行整体加引号即可）；续传时不在 token 中的源视为耗尽。失败但持有旧游标的源保留进度以便重试。输入兼容旧版 JSON 对象 `{source: cursor}`（手工构造子集游标仍可用）。单源游标仍是不透明字符串。

### 8.2 MetadataService（补全链）

1. **路由**：按 Paper 已有标识符与各 MetadataProvider 的 `id_kinds` 匹配，按优先级排序（pubmed/europepmc > crossref > openalex > semantic_scholar > unpaywall）。
2. **逐个 enrich**：fill-missing 合并——空字段填入、identifiers 并集、`sources` 追加贡献插件；已有字段冲突时不覆盖，记入 `warnings`。`ConfigError`（如 Unpaywall 缺 email）不降级为告警，直接传播为退出码 5。
3. **终止条件**：`get` 场景取到 title + 摘要即可提前停止（可配置）；`search --enrich` 场景对每条结果跑链，命中缓存则跳过网络。
4. **缓存**：补全结果按标识符缓存 7d，键含 `schema_version`（契约升级自动失效旧缓存）；`--no-cache` 绕过。

### 8.3 FetchService（定位 → 下载 → 提取）

1. **收集**：先以 `paper.fulltext_links`（搜索/补全期捕获的链接）作为种子候选，再调用所有 Locator 的 `resolve(paper)` 补充（合并而非短路，保留降级多样性）；Locator 的 `ConfigError`/上游错误降级为 `warnings` 并跳过该定位器（单个定位器缺配置不阻断 fetch，如未配 Unpaywall email 仍可用其余定位器）。补全链的 `ConfigError` 则保持严格传播（退出码 5）。
2. **去重排序**：按 URL+格式 去重（同一 tar.gz 可同时产出 XML 与 PDF 候选）；排序键 = 格式匹配度 > 来源可信度（europepmc/pmc_oa 直链 > unpaywall 出版商直链 > 其他）> license 明确度。
3. **下载与校验**：候选路由给 `supports()` 且 `formats` 匹配的 Downloader；PDF 校验 `%PDF` 魔数与最小体积，XML 校验可解析且含 `<article>`；失败自动降级下一候选。
4. **提取（仅 --format text）**：产物按格式选 Extractor（XML→jats 优先；PDF→pypdf，可用 `--extractor` 强制指定）；输出 `.txt` 并记录 `extractor`/`extracted_from`。
5. **落盘与缓存**：未指定 `--output` / `fetch.output` 时，在当前目录使用安全化文章标题作为文件名；重名时追加 DOI（其次 PMID/PMCID 等 ID）。显式输出保持固定文件名。未指定格式时按 `.pdf` / `.xml` / `.txt` 推断，无扩展名时补全（默认 PDF），格式与扩展名冲突返回 `USAGE`。同时写入文件缓存 `cache/papers/<sha256>.<ext>` + 映射 sidecar（sha256/ext/最终格式/extractor/extracted_from）。缓存存的是**最终产物**（text 请求存已提取文本），命中时跳过重复校验与重复提取，并恢复提取溯源；重复请求不重复下载。
6. **失败路径**：所有候选失败或 `oa_status=closed` → 结构化错误 `FULLTEXT_UNAVAILABLE`，附 `publisher_url`，退出码 4。

## 9. CLI 契约

### 9.1 命令一览

| 命令 | 功能 | 关键选项 |
|---|---|---|
| `search QUERY` | 检索（返回浅记录） | `--source`（可重复/逗号分隔/`all`，多源并发+去重；默认 `general.default_source`）、`--limit`、`--cursor`（多源为 `ms1.` 聚合游标，兼容 JSON）、`--author`、`--journal`、`--year-from/--year-to`、`--oa-only`、`--raw`、`--fields`、`--enrich`（走补全链） |
| `get ID...` | 按标识符取完整元数据（stub → 补全链），支持多个 ID 批量 | `--source`（可选，限定补全来源）、`--fields`；批量 `--json` 为 NDJSON，逐 ID 错误进 stdout 结果流，退出码取首个失败 |
| `fetch ID` | 获取单篇文献全文 | `--format pdf\|xml\|text`（可选，省略时按输出扩展名推断）、`--output FILE`（可选，默认安全化文章标题，重名追加 ID）、`--locator`（可重复指定或逗号分隔，限定定位器；`all` 强制全部；默认取 `fetch.locators` 配置，空则全部）、`--downloader`（强制指定）、`--extractor`（text 时强制指定） |
| `sources` | 列出全部已注册插件（按五类角色分组）与关键属性 | |
| `config get\|set\|list\|path` | 配置管理 | 点分键，如 `plugins.unpaywall.email` |
| `cache clear\|stats` | 缓存管理 | |
| `schema [COMMAND]` | 导出 JSON Schema（AI 用） | |
| `mcp` | 启动 MCP 服务器（extra `mcp`，stdio） | |

全局选项：`--json`、`--quiet`、`--verbose`、`--no-cache`、`--timeout SECONDS`、`--config PATH`、`--version`。

### 9.2 JSON 输出契约（AI 助理主通道）

- 单 ID 命令（包括 `fetch` / `get`）的 `--json` 输出为 stdout 上的单个 JSON 对象，日志/进度全部走 stderr：

```json
{
  "schema_version": "1.1",
  "command": "search",
  "data": { "items": [], "total": 0, "next_cursor": null, "source": "pubmed" },
  "warnings": []
}
```

- 进程级错误同样结构化，输出到 stderr，配合退出码：

```json
{
  "schema_version": "1.1",
  "error": {
    "code": "USAGE",
    "message": "Invalid --format; expected pdf, xml, or text.",
    "details": {}
  }
}
```

- 多 ID `get` 的 `--json` 输出为 NDJSON（每 ID 一行结果或错误），便于流式处理；单 ID 失败不中断批次，退出码取第一个失败。
- `fetch` 仅接受一个 ID，`--json` 始终输出单个 JSON 对象，不产生 NDJSON；传入多个 ID 返回用法错误（退出码 2）。
- `fetch` / `get` 的逐文献错误（如全文不可得、元数据未找到）作为结果信封写入 **stdout** 结果流；进程级错误（用法/配置）才走 stderr。批量仅适用于 `get`。
- `--fields` 裁剪 Paper 字段（如 `--fields title,doi,year`），降低 AI 上下文占用。
- 补全冲突、提取质量提示等以 `warnings` 数组随成功结果返回，不污染 data。

### 9.3 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功（含空结果——空结果不是错误） |
| 2 | 用法/参数错误 |
| 3 | 上游 API/网络错误（重试后仍失败） |
| 4 | 全文不可得（非 OA 或所有候选失败） |
| 5 | 配置错误（如 Unpaywall 缺 email） |

### 9.4 示例

```bash
# 研究者
paper-tools search "CRISPR base editing" --year-from 2020 --limit 20
paper-tools search "CRISPR base editing" --enrich          # 补全摘要/OA 状态
paper-tools fetch doi:10.1038/s41586-020-2649-2 --output papers/paper.pdf

# AI 助理
paper-tools search "CRISPR base editing" --source pubmed --limit 10 --json
paper-tools get pmid:12345678 --fields title,doi,abstract --json
paper-tools fetch doi:10.1038/s41586-020-2649-2 --output papers/paper.txt --json
```

## 10. MCP 服务器（M5，已实现）

- 可选依赖：extra `mcp`（官方 SDK `mcp>=2.0`，`MCPServer`）；`uv sync --extra mcp` 后运行 `paper-tools mcp`（stdio）。缺 extra 时命令报 USAGE（退出码 2）并给出安装指引；SDK 惰性导入，核心 CLI 不依赖 extra。
- 直接复用服务层（与 CLI 同一 `context.build_services`），暴露四个工具：

| MCP 工具 | 对应服务 | 返回 |
|---|---|---|
| `search_papers` | SearchService.search（可选 enrich） | SearchPage envelope |
| `get_paper` | MetadataService 补全链 | Paper envelope |
| `fetch_fulltext` | FetchService（定位→下载→提取） | FullText envelope（含落盘路径） |
| `list_sources` | PluginRegistry.describe | 五角色插件清单 envelope |

- 入参语义与 CLI 选项同源（pydantic `Field` 注解生成 inputSchema）；返回与 `--json` 完全一致的 success/error envelope（schema_version 1.1）。业务错误不抛异常，而是返回 `{"error": {code, message, details}}` envelope，agent 按 `error.code` 分支处理。
- stdio 纯度：协议外输出全部走 stderr（logging 已配置 stderr）；工具函数为同步实现，由 SDK 调度。
- 契约测试：`tests/test_mcp.py`（fake 插件下四工具 envelope/错误路径 + 真实子进程 stdio 往返 + 入参 schema 冻结）；`tests/integration/test_live.py::test_mcp_stdio_full_flow_live`（真实 API 下 search→get→fetch 全流程）。
- 挂载配置与调用范式见 [examples/agent-usage.md](../examples/agent-usage.md)。

## 11. 配置系统

优先级：CLI 选项 > 环境变量（`PAPER_TOOLS_*`）> 配置文件 > 默认值。

配置文件位置由 platformdirs 决定（Windows: `%APPDATA%/paper-tools/config.toml`）。示例：

```toml
[general]
default_source = "pubmed"
timeout = 30
mailto = "you@lab.org"          # 用于 UA 与 Crossref/OpenAlex polite pool

[plugins.pubmed]
api_key = "..."                 # 或 PAPER_TOOLS_PUBMED__API_KEY（双下划线分隔插件与选项）

[plugins.unpaywall]
email = "you@lab.org"           # Unpaywall 必填

[plugins.semantic_scholar]
api_key = "..."                 # 可选，提升限额

[plugins.openalex]
api_key = "..."                 # 可选，Authorization: Bearer；配后限流 5→10 req/s

[fetch]
format_priority = ["pdf", "xml", "text"]
# output = "./custom.pdf"   # 可选：固定输出文件名；默认使用安全化文章标题，重名追加 ID
locators = []                   # 默认 Locator 列表；空 = 全部；--locator 可覆盖，'all' 强制全部

[metadata]
enrich_priority = ["pubmed", "europepmc", "crossref", "openalex", "semantic_scholar", "unpaywall"]
```

密钥只从配置/环境变量读取，绝不写入日志与 JSON 输出。

## 12. 基础设施

### 12.1 HTTP 封装（core/http.py）

- 统一 `httpx.Client`：默认超时 30s，UA `paper-tools/<version> (+<mailto>)`。
- **按 host 令牌桶限流**，默认值可配置：

| Host | 默认速率 | 说明 |
|---|---|---|
| eutils.ncbi.nlm.nih.gov | 3 req/s（配 api_key 后 10） | NCBI 官方政策 |
| www.ncbi.nlm.nih.gov / ftp.ncbi.nlm.nih.gov | 3 req/s | PMC OA 服务与包下载，保守礼貌值 |
| www.ebi.ac.uk (Europe PMC) | 3 req/s | 保守礼貌值 |
| api.crossref.org | 5 req/s | 带 mailto 进 polite pool |
| api.openalex.org | 5 req/s（配 api_key 后 10） | 官方上限 10 req/s、10 万次/日；带 mailto 进 polite pool |
| api.semanticscholar.org | 1 req/s | 无 key 为共享限额，建议申请 key |
| api.unpaywall.org | 5 req/s | 每 email 每日 10 万次上限 |

- 重试：429/5xx 指数退避 + 抖动，尊重 `Retry-After`，最多 3 次；仍失败抛 `UpstreamError`（退出码 3）。
- 方法：`get_json` / `get_bytes`（GET，可缓存）；`post_json(json_body=… | data=…)`（POST JSON 或表单，`cache_ttl` 显式开启缓存，键含请求体 sha256，不同 body 不串键）；底层 `request(method, …)` 支持任意方法，限流/重试/错误映射统一生效。

### 12.2 缓存（core/cache.py）

- diskcache 存元数据与响应：搜索结果 TTL 1h，Paper 元数据/补全结果 7d，OA 定位 24h；`--no-cache` 绕过。
- PDF/XML/提取文本按 sha256 落盘，重复 fetch 同一文献直接命中；`cache stats` 展示体积与条目数。

### 12.3 日志

- 标准 logging；`--verbose` 输出 DEBUG 到 stderr；JSON 模式下 stdout 永远纯净。
- CLI 入口强制 stdout/stderr 为 UTF-8（`errors="replace"`）：Windows 控制台默认 GBK/cp1252 会让非 ASCII 标题/作者名崩溃或乱码，JSON 契约要求 UTF-8。

## 13. 合规边界（硬约束）

- 仅官方 API 与 OA 来源；不集成 Sci-Hub 等任何盗版渠道，不做付费墙绕过。
- 订阅文献：返回 `oa_status=closed` + 出版商链接，提示用户走机构访问。
- 记录并透传 license；下载行为遵守各来源服务条款与 robots 约定。
- 全文与提取文本仅供用户个人研究使用，README 中明示。

## 14. 测试与质量策略

- **unit**：模型校验、查询翻译表、插件发现/覆盖/角色路由、配置优先级、限流重试逻辑、enrich 合并策略（fill-missing/冲突告警）。
- **contract**：按角色参数化的契约测试套件——Searcher 返回合法 SearchPage；MetadataProvider 不覆盖已有字段、无可用 ID 时原样返回；Locator 候选合法；Downloader 产物校验；Extractor 输出非空文本且保留关键内容。新插件必须通过对应角色的契约才可内置。
- **integration**：respx 录制回放上游响应，离线可重复；真实 API 冒烟测试打 `live` 标记，`uv run pytest -m live` 手动/定时触发。
- **schema 快照**：`schema` 命令输出与黄金文件比对，防止 JSON 契约意外回归（M5 起强制）。
- CI（GitHub Actions）：`uv sync --locked` → `ruff check` → `ruff format --check` → `mypy` → `pytest`（3.11/3.12/3.13 矩阵）。

## 15. 关键设计决策记录

| 决策 | 选择 | 放弃的替代 | 理由 |
|---|---|---|---|
| 插件机制 | entry points + Protocol | pluggy、运行时目录扫描 | 标准分发机制，uv/pip 安装即接入；无隐蔽代码加载入口；接口足够小不需要 hook 编排 |
| 插件角色划分 | 五类：Searcher / MetadataProvider / Locator / Downloader / Extractor | 两类（Searcher + FullTextProvider） | 补全来源不必是搜索引擎；定位与传输是不同行为；提取引擎与下载来源正交 |
| 元数据补全 | 独立 MetadataProvider + enrich 补全链 | get(by_id) 挂在 Searcher 上 | 统一"按 ID 取详情"与"补全浅记录"；支持跨插件补全（Unpaywall 补 OA 字段） |
| 下载接口拆分维度 | 按行为拆（Locator/Downloader），格式用属性声明 | 按 PDF/文本拆两个下载接口 | 格式是数据参数不是行为边界；同源多格式不重复注册，降级链完整 |
| 文本提取 | 独立 Extractor 插件角色 | 下载器内置提取逻辑 | pypdf/GROBID/marker 可替换可独立安装；XML 与 PDF 提取器天然不同 |
| CLI 框架 | Typer | Click、argparse | 类型注解驱动，子命令与双输出模式组织成本最低 |
| HTTP 模型 | 同步 httpx | async | 插件接口简单，限流在客户端封装层统一做；并发收益对 CLI 场景有限 |
| 查询策略 | 结构化 + raw 双轨 | 仅统一 DSL | 翻译层覆盖 80% 场景，raw 保留引擎全部能力，避免 DSL 表达力天花板 |
| 全文来源 | 仅 OA | 订阅/灰色渠道 | 合规硬约束；订阅场景给链接而非内容 |
| AI 接入 | CLI JSON 先行，MCP 随后 | 仅 MCP | JSON CLI 零依赖覆盖所有 agent；MCP 复用服务层增量成本低 |
| 多源聚合 | 首版单源搜索 | 一上来就聚合排序 | 跨库去重/排序复杂，先保证单源质量；聚合进 backlog |