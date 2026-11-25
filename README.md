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
uv run paper-tools locate pmcid:PMC13434336 --json  # 只定位全文链接，不下载
uv run paper-tools download "$FULLTEXT_URL" --output title.pdf
uv run paper-tools extract title.pdf --output title.txt # 本地 PDF/JATS XML → 纯文本
uv run paper-tools fetch pmcid:PMC13434336 --output title.txt   # 一键：定位 → 下载 → 提取
uv run paper-tools fetch doi:10.1093/nar/gkag769 --format pdf
uv run paper-tools sources                            # 查看已注册插件
```

`fetch` 每次只接受一个文献标识符，仍是一键流程；需要控制处理阶段时，可依次使用 `locate`（定位链接）、`download`（下载直链）和 `extract`（提取纯文本）。`get` 支持多 ID 批量查询。`fetch` 全文默认使用安全化的文章标题作为文件名并保存到当前目录，重名时追加 DOI/PMID 等 ID；可用 `--output FILE` 指定固定文件名，未指定 `--format` 时按 `.pdf` / `.xml` / `.txt` 扩展名推断格式。

`download` 未指定格式时依次按 `--output` 扩展名和 URL 路径推断；未提供 `--output` 且 URL 无法识别时必须提供 `--format`，显式无扩展名的 `--output` 默认 PDF。默认文件名取自 URL。内置下载器已统一为 `http_direct`，Europe PMC、PMC S3 和其他 HTTP(S) 直链都由它处理。`locate` 的每个候选会返回 `locator` 来源列表和有序的 `downloaders` 推荐列表；`fetch` 按该顺序尝试下载，显式 `--downloader` 仍可强制覆盖。`extract` 只支持 PDF/JATS XML → text，默认把输入文件同目录的同名文件改为 `.txt`，也可用 `--output` 指定位置。三个新命令同样支持 `--json`，并返回各自的结果模型。

AI 助理除 `--json` CLI 外，还可挂载 MCP 服务器（stdio，四个工具与 CLI 契约一致）：

```bash
uv sync --extra mcp
uv run paper-tools mcp        # 挂载配置见 examples/agent-usage.md
```

闭源文献不会绕过付费墙：`fetch` 返回 `FULLTEXT_UNAVAILABLE`（退出码 4）并附出版商链接。

## 安装

PyPI 分发名为 `paper-tools-cli`，安装后的命令仍是 `paper-tools`：

```bash
uv tool install paper-tools-cli          # 或 pipx install paper-tools-cli
paper-tools search "CRISPR" --limit 5 --json

uvx --from paper-tools-cli paper-tools sources   # 免安装一次性运行
pip install paper-tools-cli[text]        # 需要 PDF 文本提取时带上 extra
```

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