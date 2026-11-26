# 排障

## CONFIG

- `plugins.unpaywall.email` 未设置：运行 `paper-tools config set plugins.unpaywall.email <email>`。
- TOML 无效或值类型错误：运行 `paper-tools config list` 定位问题。
- 环境变量覆盖配置文件：检查 `PAPER_TOOLS_*`。

## UPSTREAM

- 先确认网络、代理和上游状态。
- 使用 `--verbose` 查看 stderr 日志。
- 使用 `--no-cache` 排除旧响应。
- 搜索器失败时可换源；多源搜索会保留成功来源并返回 warnings。

## FULLTEXT_UNAVAILABLE

- 检查 `error.details.publisher_url` 和候选 `locator`。
- 闭源或非 OA 文献无法获取全文。
- PMC 文献确认 PMID/PMCID 正确，并检查 PMC OA 定位器是否加载。
- 文本提取失败时尝试其他 PDF/XML 候选，或改用 XML 提取。

## 搜索结果为空

- 确认搜索器支持该检索式。
- `raw` 语法不可跨源复制；加载对应 raw 文件。
- Crossref 的 `--raw` 只设置 `query`，不设置 `filter`。
- Semantic Scholar 的 `--raw` 不会附加 `venue/year/openAccessPdf`。
- 去掉过窄字段标签或扩大年份范围。

## JSON 无法解析

- 确认命令使用了 `--json`。
- stdout 不应包含 Rich 人类输出；日志和警告应在 stderr。
- 多 ID `get` 是 NDJSON，不是单个 JSON 数组。

## 插件未发现

- 运行 `paper-tools sources --json` 查看 load warnings。
- 确认 entry-point group 和类路径正确。
- 修改入口点后重新安装 editable 包：`uv sync --locked --all-extras`。
- Windows 下若 `paper-tools.exe` 被运行中的 MCP 占用，先停止该进程再同步。

## Windows 特定问题

- 非 ASCII 输出乱码：CLI 入口会强制 UTF-8；重定向时保持 UTF-8。
- `pytest` 出现 `Failed to canonicalize script path`：改用 `python -m pytest`。
- `paper-tools.exe` 无法删除：检查是否有 `paper-tools mcp` 正在运行。
