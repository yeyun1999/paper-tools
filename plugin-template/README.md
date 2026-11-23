# paper-tools 插件模板

最小可运行的 **Searcher + MetadataProvider** 示例，含 Locator / Downloader / Extractor 可选骨架。
示例 API（`api.example.org`）是虚构的，测试用 respx 回放；派生时替换为你的真实来源。

## 派生步骤

1. 复制本目录，改 `pyproject.toml` 的 `name`（建议 `paper-tools-<source>`）与包目录名。
2. 改 entry-point 名（`example` → 你的源名）与 `PluginMeta.name`（两者一致）。
3. 替换 `searcher.py` / `metadata.py` / `mapping.py` 中的 API URL、查询翻译表与响应映射。
4. 用真实响应更新 `tests/test_example.py` 的回放夹具；保留契约不变量测试。
5. 可选角色：实现 `skeletons.py` 后取消 `pyproject.toml` 对应 entry-point 注释。

## 开发与验证

```bash
cd plugin-template
uv sync                      # 依赖主包（[tool.uv.sources] 指向 ../，editable）
uv run pytest                # respx 回放 + 契约测试

# 安装进主环境后自动出现在 sources：
uv pip install -e ./plugin-template
uv run paper-tools sources --json
```

> 注意：主环境执行 `uv sync` 会移除未写入主项目依赖的插件包；
> 日常开发用 `uv pip install -e` 安装插件，或把插件加进主项目 dev 依赖。

## 硬约束

- 只允许官方 API 与开放获取（OA）来源；禁止任何绕过付费墙的实现。
- 密钥走 `ctx.config.plugin_config("<name>")` / 环境变量，禁止出现在日志与 JSON 输出。
- 不可信 XML 一律 `defusedxml` 解析。
- 每个声明角色必须通过契约测试；新增上游 API 必须附 respx 回放测试。

详见主仓库 [docs/plugin-guide.md](../docs/plugin-guide.md)。