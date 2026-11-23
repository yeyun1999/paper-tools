# paper-tools-biorxiv

bioRxiv / medRxiv 预印本元数据插件（官方 [details API](https://api.biorxiv.org)，无需 key）。
从 [plugin-template](../plugin-template/) 派生的第三方案例，验证 paper-tools 插件生态。

## 能力

- **MetadataProvider**（`id_kinds = {doi}`）：按 DOI 补全标题、摘要、作者、年份、license、
  OA 状态（green）与出版商链接；自动取最新版本；biorxiv 未命中时回退 medrxiv。
- 配置：`paper-tools config set plugins.biorxiv.server medrxiv` 可改变首选服务器。

> 全文获取不在本插件范围：www.biorxiv.org 对非浏览器客户端返回 403（Cloudflare），
> 按项目合规约束不做绕过。bioRxiv 预印本全文由内置 Europe PMC（PPR 记录）/
> Unpaywall 定位链覆盖。

## 安装与验证

```bash
uv pip install -e ./plugins-biorxiv     # 安装进 paper-tools 所在环境
uv run paper-tools sources --json      # metadata 角色出现 biorxiv
uv run paper-tools get doi:10.1101/124305 --source biorxiv --json

cd plugins-biorxiv
uv sync && uv run pytest                # 独立环境：respx 回放 + 契约测试
```

> 主环境执行 `uv sync` 会移除未写入主项目依赖的插件包；重装用 `uv pip install -e`。