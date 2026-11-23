# paper-tools

面向生物医学研究者的文献检索与开放获取全文下载 CLI，同时为 AI 助理提供稳定的 JSON 接口。

- 检索 / 元数据补全 / 全文定位 / 下载 / 文本提取五类能力全部插件化，`uv pip install paper-tools-xxx` 即可接入新的搜索源或下载来源。
- 所有命令支持 `--json`：字段稳定、退出码明确、错误结构化，便于脚本与 AI 助理调用。
- 使用 [uv](https://docs.astral.sh/uv/) 管理环境。

> 状态：早期开发中（M0–M5 已完成：五源检索 PubMed / Europe PMC / Crossref / OpenAlex / Semantic Scholar，元数据补全、OA 全文 PDF/XML/text 获取、MCP 服务器可用；下一步 M6 发布与插件生态）。设计文档见 [docs/architecture.md](docs/architecture.md)，开发计划见 [docs/roadmap.md](docs/roadmap.md)，AI 助理调用指南见 [examples/agent-usage.md](examples/agent-usage.md)。

## 快速上手

```bash
uv sync --all-extras                     # 含 PDF 文本提取（pypdf）
# Unpaywall OA 定位需要 email（官方 API 政策，一次性配置）
uv run paper-tools config set plugins.unpaywall.email you@example.com

uv run paper-tools search "CRISPR base editing" --source pubmed --limit 10
uv run paper-tools search "CRISPR base editing" --source europepmc --enrich
uv run paper-tools search "CRISPR base editing" --source crossref --limit 5
uv run paper-tools get pmid:38308006 --json          # AI 助理：稳定 JSON 输出
uv run paper-tools fetch pmcid:PMC13434336 --format text   # OA 全文 → 纯文本
uv run paper-tools fetch doi:10.1093/nar/gkag769 --format pdf
uv run paper-tools sources                            # 查看已注册插件
```

AI 助理除 `--json` CLI 外，还可挂载 MCP 服务器（stdio，四个工具与 CLI 契约一致）：

```bash
uv sync --extra mcp
uv run paper-tools mcp        # 挂载配置见 examples/agent-usage.md
```

闭源文献不会绕过付费墙：`fetch` 返回 `FULLTEXT_UNAVAILABLE`（退出码 4）并附出版商链接。

## 安装与运行（开发）

```bash
uv sync --all-extras         # 同步环境（含 dev 依赖与 text extra）
uv run paper-tools --help   # 运行 CLI
uv run pytest                # 离线测试（-m live 跑真实 API 冒烟）
uv run ruff check .          # lint
uv run mypy                  # 类型检查
```

## 插件生态

五类能力（检索 / 元数据补全 / 全文定位 / 下载 / 文本提取）全部插件化，第三方包安装后自动注册：

```bash
uv pip install -e ./plugins-biorxiv      # 示例：bioRxiv/medRxiv 元数据插件
uv run paper-tools sources --json       # metadata 角色出现 biorxiv
```

- 开发指南：[docs/plugin-guide.md](docs/plugin-guide.md)（接口、查询翻译、配置、契约测试、发布）
- 插件模板：[plugin-template/](plugin-template/)（最小 Searcher + MetadataProvider + 可选角色骨架）
- 第三方案例：[plugins-biorxiv/](plugins-biorxiv/)（官方 details API，含 respx 测试）

## 合规声明

本工具只使用官方 API 与开放获取（OA）来源，不集成任何绕过付费墙的渠道。订阅文献仅返回出版商链接与 OA 状态，请通过机构权限访问。获取的全文与提取文本仅供个人研究使用，请遵守各来源的服务条款与版权许可。