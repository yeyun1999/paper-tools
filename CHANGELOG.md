# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。
JSON 契约（`schema_version`）自 M5 起冻结（当前 **1.1**）：任何字段变更必须更新
`tests/snapshots/schema_v1.json` 快照、在本文件标注，并视为破坏性变更（提升 schema_version）。

## [未发布]

### 修复

- **PMC 全文获取迁移至 AWS Article Datasets**：PMC OA Web Service 停用后，`pmc_oa`
  不再调用返回 404 的旧接口；改用 PMC ID Converter 选择当前版本，并从官方
  `pmc-oa-opendata` 元数据获取 PDF/XML 直链。修复 PMC8851247 等文章的 PDF
  被误报为 `FULLTEXT_UNAVAILABLE`。
- **修复 Unpaywall 部分元数据与 PMC 仓库副本**：补全标题、作者、年份、期刊和文献类型，
  避免 `get --source unpaywall` 将有效记录误报为 `NOT_FOUND`；定位时将 PMC 仓库的
  `pmh_id` 解析为官方数据集 PDF/XML，出版商直链下载失败时仍可获取仓库副本。

### 变更（破坏性：CLI）

- **`fetch` 改为单篇输入**：`fetch ID` 每次只获取一篇文献，传入多个 ID 返回用法错误
  （退出码 2）；`--json` 始终输出单个 JSON 对象，不再产生 NDJSON。单篇业务错误仍写入
  stdout 结果流；MCP `fetch_fulltext` 本就单篇，不受影响；`get` 的批量 NDJSON 保持不变。

- **`fetch` 输出参数改为文件名**：CLI `--out DIR` 改为 `--output FILE`，MCP `out_dir`
  改为 `output`，配置 `fetch.out_dir` 改为可选的 `fetch.output`。默认使用当前目录下的
  安全化文章标题，重名时追加 DOI（其次 PMID/PMCID 等 ID）；显式 `output` 保持固定文件名。
  未指定格式时按 `.pdf` / `.xml` / `.txt` 推断，无扩展名时按格式补全（默认 PDF）；
  格式与扩展名冲突或不支持扩展名返回 `USAGE`。

### 变更（破坏性：schema_version 1.0 → 1.1）

- **Paper 新增 `fulltext_links` 字段**（`list[FullTextCandidate]`）：OpenAlex /
  Semantic Scholar / Europe PMC 在搜索与补全映射时即捕获源生 OA 全文链接
  （PDF/XML/landing）；`merge_papers` 按 url+format 并集；FetchService 将其作为
  种子候选并入定位池（合并而非短路，定位器照常运行保留降级多样性）。
  schema 快照已重新生成；`SCHEMA_VERSION` 移至 core/models.py 统一管理。
- **补全缓存键含 schema_version**：契约升级自动失效旧缓存（避免旧缓存缺失新字段）。
- **`get` 支持批量**：`get ID...` 逐篇补全，`--json` 多 ID 输出 NDJSON（单 ID 仍单对象），
  `--fields` 逐条裁剪；MCP `get_paper` 保持单篇（客户端可并行调用）。
  **契约调整**：`get` 的逐 ID 错误（含单 ID）从 stderr 移至 stdout 结果流，与 `fetch` 对齐；
  进程级错误（用法/配置）仍走 stderr。
- **项目更名**：因 PyPI 上 `paper-search` 名称已被占用，包名、CLI 命令、Python 导入名
  及配套标识符全部改为 `paper-tools` / `paper_tools`：分发名 `paper-search`→`paper-tools-cli`
  （`paper-tools` 亦被 PyPI 拒，见下条），模块 `paper_search`→`paper_tools`，
  命令 `paper-search`→`paper-tools`，环境变量前缀
  `PAPER_SEARCH_`→`PAPER_TOOLS_`，异常基类 `PaperSearchError`→`PaperToolsError`，
  entry-point 组 `paper_search.*`→`paper_tools.*`，User-Agent 与配置/缓存目录名同步更新，
  插件包 `paper-search-biorxiv`→`paper-tools-biorxiv`、模板 `paper-search-plugin-template`→
  `paper-tools-plugin-template`。未发布阶段无兼容负担，旧名不做别名保留。
- **分发名定为 `paper-tools-cli`**：`paper-tools` 被 PyPI 以「与已有项目过于相似」拒绝
  （已有空壳项目 `papertools`，PEP 503 规范化后同名）。仅分发名改变，Python 模块仍为
  `paper_tools`、命令仍为 `paper-tools`；插件包依赖声明同步改为 `paper-tools-cli`。
- **定位阶段配置错误不再阻断 fetch**：Locator 的 `ConfigError`（如 Unpaywall 缺 email）
  降级为 warning 并跳过该定位器，其余定位器照常工作；补全链（`get`/`--enrich`）保持
  严格传播（退出码 5）。
- **`--locator` 支持多个定位器**：CLI 可重复指定（`--locator a --locator b`）或逗号分隔
  （`--locator a,b`），两者可混用；`--locator all` 强制使用全部已注册定位器（覆盖配置）；
  MCP `fetch_fulltext` 的 `locator` 为逗号分隔字符串，同样支持 `all`。
  帮助中的默认值显示实际生效内容（未配置显示 all，配置后显示列表）。
  新增配置 `fetch.locators`（默认 Locator 列表，空 = 全部已注册），
  `--locator` 未指定时生效。服务层 `FetchService.fetch` 参数 `locator: str` 改为
  `locators: list[str]`（发布前调整）。
- **`sources` 与 `providers` 合并为单一 `sources` 命令**：一次展示全部五类角色插件；
  `providers` 命令移除（发布前调整，无兼容负担）。`sources --json` 的 data 现含
  searcher/metadata/locator/downloader/extractor 五个分组。MCP `list_sources` 本就返回全角色，不受影响。
- `search --source` 帮助动态列出可用检索插件与实际默认源；`get --source`、
  `fetch --locator/--downloader/--extractor` 帮助同样列出各角色可用插件；补齐全部选项描述。
- **MCP 工具参数说明与 CLI 帮助对齐**：`search_papers.source`、`get_paper.source`、
  `fetch_fulltext.locator/downloader/extractor` 动态列出各角色已加载插件；
  默认值显示实际生效配置（`general.default_source`、`fetch.locators`、`fetch.output`）
  而非配置键名；`get_paper.identifier` 与 `fetch_fulltext.format` 描述同步 CLI 措辞。

### 新增

- **MIT 许可证与发布元数据**：新增 `LICENSE`；`pyproject.toml` 补 `license` /
  `license-files` / `authors` / `keywords` / `classifiers`，sdist 排除
  `plugin-template`、`plugins-biorxiv`、`.github`（子项目为独立分发包）。
- **多源聚合搜索**：`search --source` 支持重复指定 / 逗号分隔 / `all`（MCP `search_papers`
  的 `source` 同语义）。多源并发检索，按 DOI→PMID→标题指纹去重，`merge_papers` 合并
  （identifiers 并集、sources 溯源、冲突告警），轮转交错排序；失败源降级 warning。
  `--limit` 仅约束每个源的返回量，合并去重后不截断（发布前调整：此前多源页会在全局
  截断到 limit，导致被截掉的候选随游标推进丢失）。
  多源 `next_cursor` 为免转义聚合游标 `ms1.<源名>:<游标>,...`（游标段对 `% : ,` 最小
  百分号转义；命令行整体加引号即可，无嵌套 JSON 转义之扰；发布前调整，替代原 JSON
  聚合游标；输入端仍兼容裸 JSON 对象）；插件注册名新增字符合约（`[A-Za-z0-9]` 开头，
  仅允许字母数字与 `._-`，不合规抛 `PluginError`）；单源游标不变；`total` 为
  去重前各源之和（近似）。服务层 `SearchService.search` 参数 `source: str` 改为
  `sources: list[str]`（发布前调整）。
- **OpenAlex api_key 支持**：配置 `plugins.openalex.api_key` 后，检索/补全/定位全部请求
  附 `Authorization: Bearer <key>` 头，限流由 5 提至官方上限 10 req/s；未配置行为不变。
- **HttpClient POST 支持**：`request()` 增加 `json_body` / `data`（表单）请求体参数；
  新增 `post_json()`（JSON 响应解析，限流/退避重试与 GET 一致），
  为批量查询类 POST API（如 S2 batch）铺路。POST 缓存按 `cache_ttl` 显式开启，
  缓存键含请求体 sha256（JSON 键序无关），不同 body 不串键；GET 缓存键保持不变。
- **M6 插件生态（非发布部分）**：`docs/plugin-guide.md` 开发指南；`plugin-template/`
  最小可运行插件模板（Searcher + MetadataProvider + 可选角色骨架，respx + 契约测试）；
  `plugins-biorxiv/` 第三方验证案例（bioRxiv/medRxiv 官方 details API 元数据插件，
  安装后自动注册，真实 API 验证通过）。主包与两插件包 `uv build` 通过。
  PyPI 发布待包名确定（原候选名 `paper-search` 已被占用，后定为 `paper-tools`）。
- **M5 MCP 服务器**：`paper-tools mcp`（stdio，extra `mcp`，依赖官方 SDK `mcp>=2.0`）。
  四个工具 `search_papers` / `get_paper` / `fetch_fulltext` / `list_sources`，
  入参语义与 CLI 选项同源，返回与 `--json` 完全一致的 envelope（schema_version 1.0）。
  缺 extra 时 CLI 报 USAGE（退出码 2）并给出安装指引。
- **契约冻结门禁**：`tests/test_schema_snapshot.py` + `tests/snapshots/schema_v1.json`
  快照测试进 CI；MCP 工具入参 schema 契约测试（`tests/test_mcp.py`）。
- **M4 搜索源扩展**：Crossref、OpenAlex（含 Locator）、Semantic Scholar 插件；
  五源查询翻译表；跨库标识符归一（DOI 主键、`normalize_pmcid`、OpenAlex 短 ID、S2 externalIds）。
- **M3 全文流水线**：Unpaywall / PMC OA / Europe PMC 定位与下载，`http_direct` 通用下载器，
  JATS 与 pypdf 提取器（extra `text`）；`fetch --format pdf|xml|text`（初版批量 NDJSON，
  现已改为未发布版本中的单篇输入）；文件缓存存最终产物（text 命中不重复下载/提取，保留 extractor 溯源）。
- **M2 检索 MVP**：PubMed、Europe PMC 插件，`search` / `get` / `--enrich` 补全链。
- **M0–M1 框架**：五角色插件机制（Searcher / MetadataProvider / Locator / Downloader / Extractor），
  entry-point 发现，统一 Query / 错误码 / 退出码（0/2/3/4/5），TOML+env+CLI 配置，
  按 host 限流与退避重试，diskcache 缓存，`sources` / `providers` / `config` / `cache` / `schema` 命令。

### 修复

- Windows GBK 控制台输出非 ASCII 崩溃：CLI 强制 UTF-8 stdout/stderr。
- `--version` 恒报 `0.0.0`：分发改名为 `paper-tools-cli` 后 `importlib.metadata.version()`
  查的是旧名，落入 fallback 分支。已改查新分发名，并加回归测试（0.1.0 发布版含此缺陷）。
- `fetch --format text` 二次调用缓存命中被误当 XML 重新校验：缓存改存最终产物并跳过重复校验。
- 补全链与定位阶段吞掉 ConfigError：改为直接传播（退出码 5）。
- HTTP 重试耗尽错误信息缺失状态码：details 现含最后一次上游状态码。