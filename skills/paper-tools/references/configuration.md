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

## 环境变量

```bash
export PAPER_TOOLS_DEFAULT_SOURCE=europepmc
export PAPER_TOOLS_TIMEOUT=45
export PAPER_TOOLS_MAILTO=you@lab.org
export PAPER_TOOLS_UNPAYWALL__EMAIL=you@lab.org
export PAPER_TOOLS_OPENALEX__API_KEY=YOUR_KEY
export PAPER_TOOLS_SEMANTIC_SCHOLAR__API_KEY=YOUR_KEY
```

插件选项使用双下划线分隔插件名和选项名。

## 缓存

- HTTP 响应、搜索结果和元数据使用磁盘缓存。
- PDF/XML/text 产物按 SHA256 保存；文件映射记录最终格式和提取溯源。
- `--no-cache` 适合排障或强制刷新。
- `cache clear` 清理响应和元数据缓存，保留已下载产物文件。
- `cache stats` 查看位置、条目数和体积。
