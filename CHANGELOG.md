# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。
JSON 契约（`schema_version`）自 M5 起冻结为 **1.0**：任何字段变更必须更新
`tests/snapshots/schema_v1.json` 快照、在本文件标注，并视为破坏性变更（提升 schema_version）。

## [未发布]

### 变更

- **项目更名**：因 PyPI 上 `paper-search` 名称已被占用，包名、CLI 命令、Python 导入名
  及配套标识符全部改为 `paper-tools` / `paper_tools`：分发名 `paper-search`→`paper-tools`，
  模块 `paper_search`→`paper_tools`，命令 `paper-search`→`paper-tools`，环境变量前缀
  `PAPER_SEARCH_`→`PAPER_TOOLS_`，异常基类 `PaperSearchError`→`PaperToolsError`，
  entry-point 组 `paper_search.*`→`paper_tools.*`，User-Agent 与配置/缓存目录名同步更新，
  插件包 `paper-search-biorxiv`→`paper-tools-biorxiv`、模板 `paper-search-plugin-template`→
  `paper-tools-plugin-template`。未发布阶段无兼容负担，旧名不做别名保留。
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

### 新增

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
  JATS 与 pypdf 提取器（extra `text`）；`fetch --format pdf|xml|text`，批量 NDJSON；
  文件缓存存最终产物（text 命中不重复下载/提取，保留 extractor 溯源）。
- **M2 检索 MVP**：PubMed、Europe PMC 插件，`search` / `get` / `--enrich` 补全链。
- **M0–M1 框架**：五角色插件机制（Searcher / MetadataProvider / Locator / Downloader / Extractor），
  entry-point 发现，统一 Query / 错误码 / 退出码（0/2/3/4/5），TOML+env+CLI 配置，
  按 host 限流与退避重试，diskcache 缓存，`sources` / `providers` / `config` / `cache` / `schema` 命令。

### 修复

- Windows GBK 控制台输出非 ASCII 崩溃：CLI 强制 UTF-8 stdout/stderr。
- `fetch --format text` 二次调用缓存命中被误当 XML 重新校验：缓存改存最终产物并跳过重复校验。
- 补全链与定位阶段吞掉 ConfigError：改为直接传播（退出码 5）。
- HTTP 重试耗尽错误信息缺失状态码：details 现含最后一次上游状态码。