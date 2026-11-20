# paper-search 开发计划

> 配套架构设计见 [architecture.md](architecture.md)（v2，五类插件角色）。估算以人周计，总计约 6–7.5 人周；M2/M3 与 M4 部分任务可并行压缩。
>
> 状态：执行中。**M0–M5 已完成**（163 个离线测试全绿 + 13 个 live 冒烟：S2 无 key 共享限额时按设计跳过；ruff/mypy strict 全绿；MCP stdio 全流程已验证；schema 1.0 快照门禁进 CI）。**M6 进行中**：插件指南 / 模板 / bioRxiv 生态验证 / README 已完成，三包 uv build 通过；PyPI 发布待用户确定包名（paper-search / paper-search-cli 已被占用）与 token。

## 里程碑总览

| 里程碑 | 内容 | 估算 | 关键产出 | 状态 |
|---|---|---|---|---|
| M0 | 项目脚手架 | 0.5 周 | uv 项目可运行，CI 绿 | ✅ 完成 |
| M1 | 核心框架 + 五角色插件机制 | 1.5 周 | fake 插件端到端跑通 search→enrich→locate→download→extract | ✅ 完成 |
| M2 | 检索 MVP：PubMed + Europe PMC | 1 周 | `search` / `get` 真实可用，`--enrich` 补全 | ✅ 完成 |
| M3 | 全文 MVP：Unpaywall + PMC OA + Europe PMC + 提取器 | 1 周 | `fetch` 拿到 OA PDF/XML/text | ✅ 完成 |
| M4 | 搜索源扩展：Crossref + OpenAlex + S2 | 1–1.5 周 | 五源齐备，跨库补全与标识符归一 | ✅ 完成 |
| M5 | AI 集成：MCP 服务器 + 契约冻结 | 1 周 | Qoder/Claude 可挂载使用 | ✅ 完成 |
| M6 | 发布与插件生态 | 0.5–1 周 | PyPI 可安装，插件指南 + 模板 | 🔄 进行中（非发布部分完成） |

---

## M0 项目脚手架（0.5 周）

**目标**：uv 工具链与质量门禁就位，空 CLI 可运行。

- [x] `uv init` src 布局，`.python-version` 固定 3.11，`pyproject.toml`（hatchling 构建）
- [x] 依赖：typer、rich、pydantic、httpx、diskcache、platformdirs；dev 组：ruff、mypy、pytest、respx
- [x] Typer 根应用 + `--version` / `--json` 全局选项骨架，异常→退出码映射
- [x] ruff（lint+format）、mypy 严格模式配置；pytest 目录骨架
- [x] GitHub Actions：`uv sync --locked` → ruff → mypy → pytest（3.11/3.12/3.13 矩阵）
- [x] README 草稿（定位、安装、合规声明）

**验收**：`uv run paper-search --help` 与 `--version` 正常；`uv run pytest` 通过；提交 `uv.lock`；CI 全绿。

## M1 核心框架 + 五角色插件机制（1.5 周）

**目标**：不依赖任何真实 API，用 fake 插件把五角色流水线端到端跑通。

- [x] `core/models.py`：Paper / Author / Identifier / SearchPage / FullTextCandidate / FullText（含 extractor/extracted_from 溯源字段）
- [x] `core/query.py`：统一 Query 模型 + raw 互斥校验
- [x] `core/errors.py`：异常层次与错误码（对应退出码 2/3/4/5）
- [x] `core/config.py`：TOML + env + CLI 三级合并，platformdirs 路径
- [x] `core/http.py`：httpx 封装、按 host 令牌桶、退避重试、UA
- [x] `core/cache.py`：diskcache 封装 + sha256 文件缓存
- [x] `core/plugins.py`：五个 entry-point group 发现、PluginContext 注入、同名覆盖、角色注册表
- [x] 五类 Protocol：Searcher / MetadataProvider / Locator / Downloader / Extractor
- [x] `core/services.py`：SearchService（路由/分页）、MetadataService（补全链：id_kinds 路由、fill-missing 合并、冲突告警）、FetchService（候选收集/排序/下载路由/降级/校验/提取）
- [x] CLI：`sources` / `providers`（按角色分组）/ `config` / `cache` / `schema` 命令；render 双输出
- [x] tests：五角色 fake 插件注册进测试专用 entry points，端到端覆盖 search/get/fetch（含 --format text）与全部退出码
- [x] contract 测试套件骨架（按角色参数化）；enrich 合并策略单元测试

**验收**：fake 插件下 `search --json` / `get --json` / `fetch --format text --json` 输出符合契约；enrich 不覆盖已有字段、冲突进 warnings；`schema` 输出合法 JSON Schema；故意构造的失败路径退出码正确；契约套件可复用于后续真实插件。

## M2 检索 MVP：PubMed + Europe PMC（1 周）

**目标**：两个核心生物医学源真实可用，检索与补全双角色就位。

- [x] `plugins/pubmed.py`：Searcher（esearch/esummary）+ MetadataProvider（efetch 补摘要/作者/PMCID），api_key 支持，3/10 req/s 限流
- [x] `plugins/europepmc.py`：Searcher + MetadataProvider，游标分页
- [x] 两源查询翻译表（text/author/journal/year/oa）+ 单元测试
- [x] CLI `search`（--limit/--cursor/--fields/--oa-only/--raw/--enrich）与 `get`（补全链）
- [x] respx 回放测试；`live` 标记真实冒烟脚本
- [x] 搜索结果缓存（TTL 1h）与补全结果缓存（7d）接入

**验收**：`search "CRISPR base editing" --source pubmed --json` 返回含 DOI/PMID 的真实结果；`--enrich` 后摘要缺失率显著下降且 sources 记录贡献插件；`get pmid:...` 与 `get doi:...` 归一化一致；断网/429 场景退出码 3 且错误结构化；回放测试离线全绿。

## M3 全文 MVP：定位 + 下载 + 提取（1 周）

**目标**：给 DOI/PMID 能稳定拿到 OA 全文（PDF/XML/text），拿不到时给出明确出路。

- [x] `plugins/unpaywall.py`：Locator（OA 副本定位）+ MetadataProvider（只补 oa_status/license）；email 配置校验，缺失→退出码 5
- [x] `plugins/http_direct.py`：通用 Downloader（魔数/体积/XML 校验由 FetchService 统一执行），落盘、sha256
- [x] `plugins/pmc_oa.py`：Locator（OA Web Service + idconv）+ Downloader（tar.gz 内存解包，不落盘解压）
- [x] `plugins/europepmc.py` 增加 Locator + Downloader：fullTextXML（PDF 直链由 pmc_oa/unpaywall 覆盖）
- [x] `plugins/jats.py`：Extractor（XML→纯文本，内置）；`plugins/pypdf_extractor.py`：Extractor（PDF→纯文本，extra `text`）
- [x] FetchService 编排落地：去重（URL+格式）、排序（格式>可信度>license）、supports() 路由、降级、landing 兜底、提取阶段
- [x] CLI `fetch`：--format/--out/--locator/--downloader/--extractor、文件命名 `{doi_slug}.{ext}`、批量 NDJSON
- [x] 文件缓存与提取文本缓存命中路径；respx 回放 + live 冒烟

**验收**：已知 OA DOI 拿到 PDF 且魔数校验通过；PMC 文献拿到 XML；`--format text` 走"下载→提取"流水线且 FullText 记录 extractor/extracted_from；闭源 DOI 返回 `FULLTEXT_UNAVAILABLE` + 出版商链接 + 退出码 4；重复 fetch 命中缓存（含 text 不重复下载）；Unpaywall 缺 email 时退出码 5。

## M4 搜索源扩展：Crossref + OpenAlex + Semantic Scholar（1–1.5 周）

**目标**：五源齐备，跨库补全与标识符归一一致。

- [x] `plugins/crossref.py`：Searcher + MetadataProvider（/works），mailto polite pool
- [x] `plugins/openalex.py`：Searcher + MetadataProvider + Locator（best_oa_location）
- [x] `plugins/semantic_scholar.py`：Searcher + MetadataProvider（Graph API），api_key 支持，1 req/s 限流与缓存强化
- [x] 跨库标识符归一与去重（DOI 主键）；补全链优先级与冲突告警在五源下验证
- [x] 三源查询翻译表 + 五角色契约测试全绿
- [x] `--fields` 裁剪完善；批量 fetch NDJSON 稳定性（M1 已就位，M4 复验）

**验收**：同一 DOI 在五源 `get` 的 identifiers 归一一致；五源契约测试全部通过；S2 无 key 限流下批量查询不触发封禁（退避生效）；跨源补全冲突只告警不覆盖。

## M5 AI 集成：MCP 服务器 + 契约冻结（1 周）

**目标**：AI 助理两条通道（JSON CLI / MCP）都达到可日常使用的稳定度。

- [x] extra `mcp`：官方 SDK（mcp>=2.0，MCPServer），`paper-search mcp`（stdio）；缺 extra 报 USAGE 并给安装指引
- [x] 四个工具：search_papers / get_paper / fetch_fulltext / list_sources，入参 schema 与 CLI 同源，返回同一 envelope
- [x] `schema_version 1.0` 冻结；schema 快照测试进 CI 强制门禁（tests/snapshots/schema_v1.json + CHANGELOG）
- [x] `examples/agent-usage.md`：shell 调用范式、退出码处理、NDJSON 批量、错误恢复建议（示例逐条实测可执行）
- [x] MCP 客户端挂载验证：官方 SDK ClientSession 真实 stdio 子进程往返 + live search→get→fetch 全流程；Qoder/Claude 挂载配置见 agent-usage

**验收**：MCP 客户端挂载后完成端到端文献获取；schema 快照测试拦截字段变更；agent-usage 示例逐条可执行。

## M6 发布与插件生态（0.5–1 周）

**目标**：外部用户可安装，外部开发者可写插件。

- [ ] `uv build` + `uv publish` 发布 PyPI；验证 `uvx paper-search` 与 `uv tool install paper-search`（build 已通过；包名被占用，发布待用户确定新名与 token）
- [x] `docs/plugin-guide.md`：五类角色接口、查询翻译表、配置命名空间、契约测试接入、多角色注册、发布流程
- [x] 插件模板仓库（最小可运行 Searcher + MetadataProvider 示例，含 Locator/Downloader/Extractor 可选骨架）
- [x] 以 bioRxiv 插件作为第三方案例验证扩展机制（模板派生，独立包安装后自动出现在 `sources`；真实 API 验证通过）
- [x] README 完善：安装、快速上手、合规声明、插件生态链接

**验收**：干净环境 `uvx paper-search search ...` 可用；模板插件 `uv pip install -e` 后自动注册并通过契约测试；PyPI 页面与文档链接完整。

---

## 贯穿性约定

### uv 工作流

```bash
uv sync                      # 安装/同步环境（含 dev 组）
uv run paper-search ...      # 运行 CLI
uv run pytest                # 测试（-m live 跑真实冒烟）
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv add <pkg>                 # 加依赖（自动更新 uv.lock）
uv build && uv publish       # 发布
```

### 开发规范

- 每个插件必须通过其声明角色的 contract 套件才可合并；新增上游 API 必须附 respx 回放测试。
- JSON 契约字段变更需更新 schema 快照并在 CHANGELOG 标注（M5 后视为破坏性变更）。
- 提交信息用 Conventional Commits（feat/fix/docs/test/chore）。
- 密钥一律走配置/环境变量，禁止出现在日志、测试夹具与 JSON 输出中。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 上游 API 变更/限流收紧 | 检索/下载失败 | 回放测试隔离日常开发；退避重试；api_key/mailto 配置化；live 冒烟定期跑 |
| S2 无 key 共享限额低 | 批量场景易 429 | 默认 1 req/s + 缓存强化；文档引导申请 key |
| 补全链放大请求量 | --enrich 批量时触发限流 | 按 host 限流统一约束；补全缓存 7d；优先级链提前终止 |
| 版权合规 | 法律风险 | OA-only 硬约束写进架构与 README；插件指南禁止灰色来源 |
| PDF 文本提取质量差 | AI 阅读体验 | 优先 XML；pypdf 结果标注 extractor；GROBID 以 Extractor 插件进 backlog |
| 插件接口演进破坏第三方 | 生态受损 | 五角色接口保持最小；语义化版本；变更走 CHANGELOG |
| Windows 路径/编码问题 | 本地开发受阻 | pathlib 全程、显式 UTF-8、CI 加 windows-latest 冒烟 |

## Backlog（M6 之后）

- bioRxiv/medRxiv、arXiv q-bio 搜索插件（bioRxiv 已在 M6 作生态验证）
- `extract` 命令：对本地 PDF/XML 文件直接跑 Extractor 流水线
- GROBID / marker 深度全文解析（Extractor 插件，extra）
- 多源聚合搜索与跨库排序（聚合+去重+聚合游标已实现；跨库相关性排序目前为轮转交错启发式）
- 引用网络：citations / references 命令（OpenAlex/S2 数据）
- 导出 BibTeX / CSL-JSON
- 机构订阅场景：仅解析并展示机构访问链接，不获取内容