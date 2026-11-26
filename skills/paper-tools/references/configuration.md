# 配置、环境变量与缓存

## 配置优先级

CLI 选项 > `PAPER_TOOLS_*` 环境变量 > TOML 配置文件 > 默认值。

```bash
paper-tools config path
paper-tools config list --json
paper-tools config get plugins.unpaywall.email
paper-tools config set general.timeout 45
paper-tools config set plugins.openalex.api_key YOUR_KEY
```

`config get/list` 会屏蔽 key、token、secret 等敏感值。

## 主要配置

```toml
[general]
default_source = "pubmed"
timeout = 30.0
mailto = "you@lab.org"

[fetch]
format_priority = ["pdf", "xml", "text"]
# output = "./custom.pdf"
locators = []

[metadata]
enrich_priority = ["pubmed", "europepmc", "crossref", "openalex", "semantic_scholar", "unpaywall"]

[output]
search_fields = ["title", "identifiers.doi", "year", "cited_by_count", "abstract"]
get_fields = ["title", "identifiers.doi", "year", "cited_by_count", "journal", "oa_status", "abstract"]

[plugins.unpaywall]
email = "you@lab.org"

[plugins.openalex]
api_key = "YOUR_KEY"

[plugins.semantic_scholar]
api_key = "YOUR_KEY"
```

- `fetch.locators` 为空表示全部定位器；`--locator all` 可临时覆盖。
- `fetch.output` 是固定输出文件名；未设置时 `fetch` 使用安全化文章标题。
- `metadata.enrich_priority` 控制补全链顺序。
- `output.search_fields` 与 `output.get_fields` 分别控制 CLI/MCP 的 `search` 与 `get`
  JSON 论文字段。对象嵌套用 `.`（如 `identifiers.doi`），数组用 `[]`（如
  `authors[].name`），返回结构保持对象或数组原类型。数组为空或包含 `all` 表示返回全部
  Paper 字段；`all` 会要求补全全部字段。单次调用的 `--fields` 或 MCP `fields` 优先于配置。
- 字段裁剪只改变输出，不会自动触发补全；`search` 仍需 `--enrich` 或 MCP `enrich=true`
  才能填充摘要等元数据。`get` 与启用补全的 `search` 会按所选字段继续补全，缓存键也包含字段集合。

## 环境变量

```bash
export PAPER_TOOLS_DEFAULT_SOURCE=europepmc
export PAPER_TOOLS_TIMEOUT=45
export PAPER_TOOLS_MAILTO=you@lab.org
export PAPER_TOOLS_UNPAYWALL__EMAIL=you@lab.org
export PAPER_TOOLS_OPENALEX__API_KEY=YOUR_KEY
export PAPER_TOOLS_SEMANTIC_SCHOLAR__API_KEY=YOUR_KEY
export PAPER_TOOLS_OUTPUT__SEARCH_FIELDS='["title", "identifiers.doi", "year"]'
export PAPER_TOOLS_OUTPUT__GET_FIELDS='["title", "abstract", "cited_by_count"]'
```

插件与 output 选项使用双下划线分隔命名空间和选项名。

## 缓存

- HTTP 响应、搜索结果和元数据使用磁盘缓存。
- PDF/XML/text 产物按 SHA256 保存；文件映射记录最终格式和提取溯源。
- `--no-cache` 适合排障或强制刷新。
- `cache clear` 清理响应和元数据缓存，保留已下载产物文件。
- `cache stats` 查看位置、条目数和体积。
