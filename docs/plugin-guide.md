# paper-tools 插件开发指南

paper-tools 的五类能力全部插件化：第三方包安装后**自动注册**，无需改主程序。
本指南覆盖接口、约定、测试与发布。可运行起点：[plugin-template/](../plugin-template/)；
真实第三方案例：[plugins-biorxiv/](../plugins-biorxiv/)。

## 1. 五类角色与流水线

```
search ──> enrich ──> locate ──> download ──> extract
Searcher   Metadata   Locator    Downloader   Extractor
           Provider
```

| 角色 | entry-point group | 职责 |
|---|---|---|
| Searcher | `paper_tools.searchers` | 统一 Query → 上游检索 → SearchPage |
| MetadataProvider | `paper_tools.metadata` | 按标识符补全 Paper（fill-missing） |
| Locator | `paper_tools.locators` | 定位 OA 全文候选（url + format） |
| Downloader | `paper_tools.downloaders` | 候选 URL → 字节产物 Artifact |
| Extractor | `paper_tools.extractors` | 字节产物 → 纯文本 |

一个类可实现多个角色并注册进多个 group（内置 `europepmc` 同时是
Searcher / MetadataProvider / Locator / Downloader）。同名注册会覆盖并产生
`load_warnings`；加载失败的插件被跳过并告警，不影响其余插件。

## 2. 快速上手（模板派生）

```bash
cp -r plugin-template paper-tools-mysource
cd paper-tools-mysource
# 1. pyproject.toml：改 name、包目录、entry-point 名
# 2. PluginMeta.name 与 entry-point 名保持一致
# 3. 替换 API URL / 查询翻译表 / 响应映射
uv sync && uv run pytest                 # 独立环境：respx 回放 + 契约测试
uv pip install -e .                      # 安装进 paper-tools 所在环境
paper-tools sources --json              # 自动出现你的源
```

> 主环境 `uv sync` 会移除未写入主项目依赖的插件包；插件日常安装用 `uv pip install -e`。

## 3. 接口参考（typing.Protocol）

所有插件构造函数接收 `PluginContext(config, http, cache)`，并声明类属性
`meta = PluginMeta(name, version, description)`。接口定义见
[src/paper_tools/core/plugins.py](../src/paper_tools/core/plugins.py)。
`name` 必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`（用作多源聚合游标的段键，不能含
`:` `,` `%` 或空白），不合规的注册抛 `PluginError`。

### Searcher

```python
class MySearcher:
    meta = PluginMeta(name="mysource", version="0.1.0", description="…")

    def __init__(self, ctx: PluginContext) -> None: ...

    def search(self, q: Query, *, limit: int = 20, cursor: str | None = None) -> SearchPage: ...
```

- `SearchPage(items, total, next_cursor, source)`：`source` 必须等于 `meta.name`；
  `len(items) <= limit`；每个 Paper 至少有 `title` 与 `identifiers`。
- 分页：把上游游标原样放进 `next_cursor`，续传时透传。
- 浅记录即可（摘要可缺）；`--enrich` 由服务层走补全链。

### MetadataProvider

```python
class MyMetadata:
    meta = PluginMeta(...)
    id_kinds = frozenset({"doi", "pmid"})  # 声明可处理的标识符类型

    def enrich(self, paper: Paper) -> Paper: ...
```

- 服务按 `id_kinds ∩ paper.identifiers` 路由；补全链优先级由
  `metadata.enrich_priority` 配置，未列出的第三方插件排在内置链之后（按名排序）。
- **fill-missing 契约**：返回你能补全的字段即可，服务合并且**不覆盖已有字段**；
  标识符冲突只进 warnings。本源没有该文献时原样返回入参 stub（不要抛错）。
- 上游 404 建议吞掉返回 stub；网络/限流错误抛 `UpstreamError` 交服务层告警降级。

### Locator

```python
class MyLocator:
    meta = PluginMeta(...)

    def resolve(self, paper: Paper) -> list[FullTextCandidate]: ...
```

- `FullTextCandidate(url, format, locator, license?)`：`format ∈ {pdf, xml, text, landing}`；
  `locator` 必须等于 `meta.name`；url 必须 http(s)。
- `landing` 候选仅作闭源兜底展示，不会被下载。
- 排序由 FetchService 统一执行（格式匹配 > 来源可信度 > license）；去重按 (url, format)。

### Downloader

```python
class MyDownloader:
    meta = PluginMeta(...)
    formats = frozenset({"pdf", "xml"})  # 可产出的格式

    def supports(self, candidate: FullTextCandidate) -> bool: ...
    def download(self, candidate: FullTextCandidate) -> Artifact: ...
```

- `supports()` 按 URL 前缀 / `candidate.locator` 判断；专用下载器先于通用 `http_direct` 被路由。
- `Artifact(format, content, source_url, downloader, license?)`：`downloader == meta.name`。
- 魔数（PDF `%PDF` + ≥1KB）、XML 合法性（defusedxml + 根 `article`）、体积校验由
  FetchService 统一执行，插件无需重复；打包格式（如 PMC tar.gz）在内存解包，不落盘解压。
- 普通 HTTP 直链无需写下载器：`http_direct` 已覆盖。

### Extractor

```python
class MyExtractor:
    meta = PluginMeta(...)
    source_formats = frozenset({"pdf", "xml"})

    def extract(self, data: bytes, *, source_format: str) -> str: ...
```

- 返回非空纯文本；不可解析/空文本抛 `UpstreamError`（服务层降级到下一候选）。
- **不可信 XML 必须用 `defusedxml`**（内置 jats 提取器可参考）。
- FullText 会记录 `extractor` / `extracted_from` 溯源字段。

## 4. 统一 Query 与查询翻译表

`Query`（[core/query.py](../src/paper_tools/core/query.py)）字段：
`text / title / author / journal / year_from / year_to / open_access / raw`。
`raw` 与结构化字段互斥（模型层校验）；空查询非法。

插件职责是把统一 Query 翻译成上游原生参数。内置五源翻译表见
[architecture.md §6](architecture.md)。约定：

- 不支持的过滤项**显式抛 `UsageError`** 并指引可用源（例：Crossref 无可靠 OA 过滤，
  `--oa-only` 时报错建议 pubmed/europepmc/openalex），不要静默忽略。
- `raw` 直通上游原生语法，不做翻译。
- 年份区间映射到上游的 from/until 过滤；期刊/作者映射到对应检索字段。

## 5. 标识符与模型约定

- DOI 主键：一律 `normalize_doi()`（小写、去 resolver 前缀）；PMCID 用
  `normalize_pmcid()`（补 PMC 前缀）。跨源同一 DOI 的 identifiers 必须归一一致。
- `Paper.oa_status ∈ {gold, green, hybrid, bronze, closed, unknown}`；
  预印本记 `green`，`publication_type="preprint"`。
- 搜索/补全响应里若带 OA 全文直链（PDF/XML），映射时填入 `Paper.fulltext_links`
  （`FullTextCandidate(url, format, locator=meta.name, license)`）；FetchService 会将其
  并入候选池，省掉定位阶段的重复请求。参考 openalex/semantic_scholar/europepmc 映射。
- 密钥只从 `ctx.config.plugin_config("<name>")` 或环境变量读取；
  **禁止出现在日志、测试夹具与 JSON 输出**。

## 6. 配置命名空间

插件配置一律放 `plugins.<name>.*`：

```bash
paper-tools config set plugins.mysource.api_key KEY
paper-tools config set plugins.mysource.server prod
```

代码内 `self.ctx.config.plugin_config("mysource").get("api_key")`。
缺失必需配置时抛 `ConfigError`（消息附修复命令）。传播行为分阶段：补全链中直接传播
（退出码 5）；定位阶段降级为 warning 并跳过该定位器，不阻断其余定位器与 fetch。
参考 `plugins/unpaywall.py` 的 email 校验。

## 7. HTTP 与缓存

统一走 `ctx.http`（[core/http.py](../src/paper_tools/core/http.py)）：

- `get_json(url, params=…, headers=…, cache_ttl=…)`：GET 响应缓存。
  约定 TTL：检索 1h（3600）、元数据 7d（604800）。
- `post_json(url, json_body=…, data=…, headers=…, cache_ttl=…)`：POST JSON 体或表单
  （如批量查询 API）；默认不缓存，幂等查询 API 可传 `cache_ttl` 开启（缓存键含请求体哈希，
  键序无关）；限流/重试与 GET 一致。
- 自动退避重试 429/5xx ×3（含 Retry-After）；耗尽抛 `UpstreamError`（details 含状态码）。
- **新 API host 默认不限流**：插件应在 `__init__` 里
  `ctx.http.set_rate_limit("api.mysource.org", 1.0)` 声明上游限额；
  有 key 提升限额时同样用 `set_rate_limit`（参考 pubmed api_key 3→10 req/s）。
- 文件级缓存（sha256）由 FetchService 统一管理，下载器无需关心。

## 8. 契约测试（合并门禁）

每个声明角色必须通过契约不变量（主仓库
[tests/contract/test_plugin_contract.py](../tests/contract/test_plugin_contract.py)，
模板内附对齐版本）：

| 角色 | 不变量 |
|---|---|
| 全部 | meta.name/version 非空 |
| Searcher | source==meta.name；len(items)<=limit；item 有 title+identifiers |
| MetadataProvider | id_kinds 非空；enrich 返回 Paper |
| Locator | candidate.url 为 http(s)；candidate.locator==meta.name |
| Downloader | formats 非空；artifact.format∈formats；content 非空；downloader==meta.name |
| Extractor | source_formats 非空；各格式产出非空 str |

新增上游 API **必须附 respx 回放测试**（离线确定性）；真实冒烟打 `live` 标记。
模板测试文件可直接派生。

## 9. 发布流程

```bash
uv build                      # sdist + wheel
uv publish                    # 需要 PyPI token（UV_PUBLISH_TOKEN）
# 用户侧：
uv pip install paper-tools-mysource
paper-tools sources          # 自动注册
```

- 包名建议 `paper-tools-<source>`；entry-point 名与 `PluginMeta.name` 一致且全局唯一
  （与内置插件同名会覆盖并告警——这是有意的替换机制，请在 README 声明）。
- 语义化版本；接口演进见主仓库 CHANGELOG（schema 1.1 已冻结，JSON 字段变更视为破坏性：
  提升 `SCHEMA_VERSION`、重新生成快照、CHANGELOG 标注）。
- 主包 PyPI 分发名为 `paper-tools-cli`（`paper-search` 已被占用；`paper-tools` 与已有
  `papertools` 规范化同名被拒），但模块仍是 `paper_tools`、命令仍是 `paper-tools`，
  插件包依赖写 `dependencies = ["paper-tools-cli"]`；发布前模板与
  bioRxiv 包用 `[tool.uv.sources]` 指向本地主包，发布后改为普通版本约束。

## 10. 合规硬约束

- 只允许官方 API 与开放获取（OA）来源；**禁止任何绕过付费墙/反爬的实现**。
  案例：bioRxiv 插件只做元数据（api.biorxiv.org 开放），www.biorxiv.org 的
  Cloudflare 403 不做绕过，全文交由 Europe PMC（PPR）/Unpaywall 链覆盖。
- 闭源文献只返回出版商链接与 OA 状态。
- 获取的全文仅供个人研究使用，遵守各来源服务条款与版权许可。