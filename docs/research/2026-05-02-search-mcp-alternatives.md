# Search MCP 方案调研报告

**日期**: 2026-05-02  
**背景**: Prism v3 准备为 Agent 接入网页搜索能力，已知将接 exa（HTTP transport，付费 API）。本报告调研其他候选方案，为组合选型提供依据。  
**方法**: 每个候选均通过 WebSearch 查官方信息 + WebFetch 抓官网原始页面核实，不凭训练数据填写。

---

## 1. 速查对比表

| 候选 | 官方 MCP 仓库 | Transport | Auth | 免费额度 | 付费起步 | AI-Ready 输出 | 自托管选项 | 注册难度 | 速率限制 | 推荐度 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Tavily** | ✅ `tavily-ai/tavily-mcp` | stdio + HTTP(remote) | API Key / OAuth | 1,000 q/月 | $0.008/credit（PAYG）| ⭐⭐⭐⭐⭐ snippet+answer | ❌ | 低（注册即得 key） | 未公开细节 | ⭐⭐⭐⭐⭐ |
| **Brave Search** | ✅ `brave/brave-search-mcp-server` | stdio（默认）+ HTTP | API Key（header） | $5/月 credits（≈1,000 q） | $5/1,000 q（PAYG） | ⭐⭐⭐⭐ snippet+schema | ❌ | 低 | 50 q/s | ⭐⭐⭐⭐ |
| **Serper** | ❌ 仅社区包装 | stdio（社区实现） | API Key | 2,500 credits（一次性） | ~$1/1,000 q（量大）| ⭐⭐⭐ 裸 SERP JSON | ❌ | 低 | 未公开 | ⭐⭐⭐ |
| **SerpAPI** | ✅ `serpapi/serpapi-mcp` | HTTP（Streamable） | API Key（path/header） | 250 q/月 | $25/月（1,000 q）| ⭐⭐⭐ 裸 SERP JSON | ❌ | 低 | 200 q/h（Starter） | ⭐⭐⭐ |
| **Firecrawl** | ✅ `firecrawl/firecrawl-mcp-server` | stdio + HTTP | API Key（Bearer） | 500 credits（一次性） | $16/月（3,000 credits）| ⭐⭐⭐⭐ 爬虫+结构化 | ❌（有云托管）| 低 | 2 并发（免费）| ⭐⭐⭐⭐ |
| **Perplexity Sonar** | ✅ `perplexityai/modelcontextprotocol` | stdio | API Key（env var） | 无免费额度 | $5–$8/1,000 req + token 费 | ⭐⭐⭐⭐⭐ AI 生成答案+引用 | ❌ | 低 | 未公开 | ⭐⭐⭐⭐ |
| **Bing Web Search** | ❌ 官方已退役 | — | — | — | — | — | ❌ | — | — | ⭐（**已废弃**）|
| **DuckDuckGo** | ❌ 仅社区实现 | stdio（社区） | 无需 key | 无限（非官方）| 免费 | ⭐⭐ 受限 instant answer | ❌ | 极低（无需注册）| 约 1 q/s | ⭐⭐ |
| **Kagi** | ✅ `kagisearch/kagimcp` | stdio + HTTP（可选）| API Key（env var） | 无（Beta 邀请制）| $25/1,000 q | ⭐⭐⭐⭐ 高质量无广告 | ❌ | 高（需邀请+订阅）| 未公开 | ⭐⭐（Beta 限制）|
| **SearXNG** | ❌ 仅社区实现 | stdio + HTTP（社区）| 无需 key | 无限（自托管）| 服务器成本 | ⭐⭐ 聚合结果 | ✅ 完全自托管 | 中（需部署实例）| 取决于部署 | ⭐⭐⭐（自托管路径）|
| **Linkup** | ✅ `LinkupPlatform/linkup-mcp-server` | stdio + HTTP | API Key（Bearer）| €5/月（≈1,000 q）| €5/1,000 q（standard）| ⭐⭐⭐⭐ fast/standard/deep | ❌ | 低 | 未公开 | ⭐⭐⭐⭐ |
| **Jina AI** | ✅ `jina-ai/MCP` | HTTP（Streamable）| API Key（Bearer，可选）| 10M tokens（一次性）| token-based，起步便宜 | ⭐⭐⭐⭐ 搜索+读取+重排 | ❌ | 低 | 100 RPM（免费 key）| ⭐⭐⭐ |

> 备注：
> - Bing Web Search API 已于 2025 年 3 月正式关停，新项目不应使用。
> - Serper 无官方 MCP 仓库，现有实现均为社区第三方包装（`garylab/serper-mcp-server`、`marcopesani/mcp-server-serper` 等），可信度低于官方维护项目。
> - DuckDuckGo Instant Answer API 无官方 MCP，社区实现存在，但 Instant Answer 仅返回结构化卡片（地理/计算/百科等），不具备全文 web search 能力。
> - Kagi 搜索 API 截至 2026-05 仍为 closed beta，需邮件申请邀请（support@kagi.com）。

---

## 2. Top 3 详解

### 2.1 Tavily — AI Agent 专用搜索首选

**官网**: https://tavily.com  
**MCP 仓库**: https://github.com/tavily-ai/tavily-mcp  
**注册步骤**: 官网注册 → 邮件验证 → 控制台生成 API key → 直接使用（约 3 步）

**为什么进 Top 3**: Tavily 是目前唯一专门为 AI Agent + RAG 工作流设计的搜索 API，返回结构已针对 LLM 优化（含 answer、snippets、score），无需 agent 自行解析裸 HTML。官方 MCP 同时支持 stdio（本地）和 Remote HTTP（`https://mcp.tavily.com/mcp/`），还支持 OAuth，集成最简。免费层 1,000 q/月满足轻量测试；PAYG 模式 $0.008/credit 灵活按量付费。2026-02 被 Nebius 收购，短期内产品连续性有一定风险，需关注。

**与 exa 的差异化定位**: 定位高度重叠（两者都是 AI-first search），Tavily 更偏 RAG/Agent 工具，exa 偏语义相似度检索。两者互为竞争替代而非互补；若已有 exa，Tavily 可作为 cost 对比或 fallback。

---

### 2.2 Brave Search — 独立索引 + 官方 MCP 最成熟

**官网**: https://brave.com/search/api/  
**MCP 仓库**: https://github.com/brave/brave-search-mcp-server（官方，92 releases，最新 v2.0.80，2026-04-21）  
**注册步骤**: brave.com/search/api → 申请 API key → 仪表盘配置 → 4 步以内

**为什么进 Top 3**: Brave 拥有完全独立爬取的搜索索引（不依赖 Google/Bing），附加 schema-enriched snippets、infobox 等结构化数据，对 Agent 较友好。官方 MCP 由 Brave 官方维护（非社区），更新活跃，支持 stdio/HTTP 双模式，auth 为标准 header API key，集成成本低。$5/月 免费 credits（约 1,000 次查询）足够 POC 验证。2026-02 Brave 取消了免费永久 tier，改为每月 $5 credits，需注意。

**与 exa 的差异化定位**: **互补**。exa 偏语义/内容相关性检索，适合"找相似文章"；Brave 偏传统关键词+独立索引，适合"找最新新闻/事实"。组合使用可覆盖不同 query 类型，降低对单一供应商的依赖。

---

### 2.3 Linkup — 新兴高质量 AI Search，深度研究能力强

**官网**: https://www.linkup.so  
**MCP 仓库**: https://github.com/LinkupPlatform/linkup-mcp-server（官方）  
**注册步骤**: linkup.so 注册 → 生成 API key → 约 3 步，€5 免费额度自动激活

**为什么进 Top 3**: Linkup 是候选中唯一提供 "deep search" 模式（€50/1,000 q，跨多源复杂分析）的产品，输出质量接近 Perplexity 但 API-first 设计更适合 Agent 编排。官方同时维护 Python 和 TypeScript MCP server，支持 stdio + HTTP。€5/月 免费 credits（标准 1,000 次）满足 POC，按量付费无月度锁定。知名度低于 Tavily/Brave，社区生态相对薄，属于值得关注的新兴选项。

**与 exa 的差异化定位**: **互补**。exa 擅长语义索引，Linkup "deep" 模式擅长复杂多跳研究。可将 Linkup deep 用于高价值研究型 query，exa/Brave 用于常规检索，按 query 难度路由。

---

## 3. 推荐组合

### 方案 A — 单 exa（用户已有付费 key，最简）

**适用场景**: 快速上线，不想管理多 key，exa 当前已满足需求。  
**配置**: 保持现有 exa HTTP MCP，Prism 不做 transport 扩展。  
**风险**: 单点依赖 exa；exa 定价若涨价、API 变更或服务中断无备份。  
**推荐度**: ✅ 短期可行，中期应考虑 fallback。

---

### 方案 B — exa + Brave Search（最佳互补 + fallback 组合）

**为什么选 Brave**: 独立索引与 exa 互补，官方 MCP 成熟，stdio/HTTP 双支持，$5/月 credits 低成本验证。

**Query 路由策略**:
- 语义检索 / 内容相似 → exa
- 最新事实 / 新闻 / 当前信息 → Brave Search
- exa 超出配额或失败 → Brave 自动 fallback

**Prism 集成成本**:
- Brave MCP 支持 stdio（默认），Prism 无需扩展 transport schema
- executor 新增 `brave_search` tool descriptor，约 30–50 LOC
- 无 HTTP transport 扩展工作

**月均成本估算（中规模，约 5,000 次 AI search/月）**:
- exa: 取决于现有计划
- Brave: 约 5,000 × $0.005 = $25/月

---

### 方案 C — 全开源自托管路径（零付费 API 依赖）

**技术栈**: SearXNG（自托管实例）+ 社区 MCP server（`ihor-sokoliuk/mcp-searxng`）

**是否可行**: 技术上可行，但有明确代价。

**工作量评估**:
- 部署 SearXNG Docker 实例：约 0.5 天（Docker Compose，配置 engines）
- 配置 MCP server 连接 SearXNG：约 0.5 天
- Prism executor 接入 stdio MCP：约 1 天
- 总计：约 2 天

**限制**:
1. SearXNG 是元搜索引擎（聚合 Google/Bing/DDG 结果），无自有索引，受上游 rate limit 影响
2. 社区 MCP server（非官方），维护质量无保证
3. 搜索结果质量 < 付费 AI-first API（无 answer/snippet 优化）
4. 需运维 SearXNG 实例（更新、反封禁配置等）

**推荐结论**: 方案 C 适合对数据隐私极为敏感或完全无法使用付费 API 的场景，生产环境质量不如方案 B。

---

## 4. Prism 集成成本预估

> 已知 Prism 当前仅支持 stdio MCP transport，HTTP transport 需先做 schema 扩展。

### 4.1 Tavily

- **MCP Transport**: stdio（本地）可直接用；Remote HTTP 需 transport schema 扩展
- **推荐接入方式**: stdio 本地运行 `npx -y tavily-mcp`，无需 HTTP transport 扩展
- **backend 改动**: 新增 tool descriptor，约 20 LOC
- **executor 改动**: 注册 tavily tool handler，约 30 LOC
- **总计约 50 LOC**，约 0.5 天

### 4.2 Brave Search

- **MCP Transport**: stdio（默认，v2.x 已改回 stdio 优先），直接可用
- **推荐接入方式**: stdio，无需 HTTP transport 扩展
- **backend 改动**: 新增 tool descriptor，约 20 LOC
- **executor 改动**: 注册 brave_search handler，约 30 LOC
- **总计约 50 LOC**，约 0.5 天

### 4.3 Linkup

- **MCP Transport**: 支持 stdio（npm 本地安装）
- **推荐接入方式**: stdio 本地，无需 HTTP transport 扩展
- **backend 改动**: 新增 tool descriptor（含 depth 参数 fast/standard/deep），约 25 LOC
- **executor 改动**: 注册 linkup handler，约 35 LOC
- **总计约 60 LOC**，约 0.5 天

### 4.4 HTTP Transport 扩展（如要接 Tavily Remote / Firecrawl Remote / SerpAPI）

若接入使用 HTTP Streamable transport 的 MCP 服务：
- Prism executor transport schema 扩展（HTTP client + auth header 注入）：约 150–200 LOC，约 2–3 天
- **结论**：短期内优先选 stdio-capable 候选（Tavily 本地 / Brave / Linkup），避免先做 transport 扩展

---

## 5. 关键 Risks / Uncertainties

### 5.1 MCP 实际状态核查

| 候选 | 官方 MCP 状态 | 风险说明 |
|---|---|---|
| Bing Web Search | **已废弃**（2025-03 关停） | 任何基于 Bing v7 key 的 MCP 包装均处于倒计时；微软替代方案 Azure Grounding with Bing 定价 $35/1K q，贵 7× |
| Serper | **无官方 MCP**，现有实现均为社区包装（`garylab/serper-mcp-server` 等），维护质量无保证 | 若 Serper 更改 API 接口，社区 MCP 可能滞后修复 |
| DuckDuckGo | **无官方 MCP**，Instant Answer API 能力受限（仅结构化卡片，非全 web search） | 社区 MCP 率限行为不透明，大规模使用可能触发 IP 封禁 |
| SearXNG | **无官方 MCP**，全为社区实现，本身是元搜索引擎 | 依赖上游 Google/Bing 接口，可能被下游封锁；运维负担高 |
| Kagi | 官方 MCP 存在，但 **Search API 仍为 closed beta** | 无法自助注册，必须邮件申请，不适合短期集成计划 |

### 5.2 近期价格 / 政策变化风险

| 候选 | 变化事项 | 风险等级 |
|---|---|---|
| **Tavily** | 2026-02 被 Nebius 收购，定价策略可能随收购整合而调整 | 中（短期影响小，长期需关注） |
| **Brave Search** | 2026-02 取消永久免费 tier，改为每月 $5 credits，已涨价一次 | 中（已变化，再次涨价概率存在）|
| **Perplexity Sonar** | Per-request fee（$5–$22/1K）+ token fee 双收，成本结构复杂，实际单次 query 成本可能比表面高 | 中（计费模型需仔细估算）|
| **SerpAPI** | 按月订阅制（credits 不跨月），对 bursty workload 实际成本高 30–50%；价格在主要 SERP API 中偏贵 | 高（对非稳定流量不友好）|
| **Firecrawl** | 爬虫 + 搜索混合产品，credits 同时覆盖 scrape/search/extract，单纯搜索场景性价比取决于用途比例 | 低（定价透明，但需确认搜索 vs 爬虫 credit 分配）|

### 5.3 其他不确定性

- **Perplexity MCP 官方仓库**（`perplexityai/modelcontextprotocol`）使用 stdio，但 Perplexity Sonar 模型本身是对话+搜索合体，每次 `perplexity_ask` 都会消耗 token，与纯搜索 API 成本模型差异大，需单独评估是否适合 Prism 的 Agent search 场景（Agent 可能更需要原始 web 结果而非 AI 生成答案）。
- **Linkup** 目前知名度低于 Tavily/exa/Brave，社区生态薄，若公司出现经营问题，迁移成本存在。

---

## 附：数据来源（一手官方页面）

- Tavily MCP 文档: https://docs.tavily.com/documentation/mcp
- Tavily 定价: https://www.tavily.com/pricing
- Tavily MCP 仓库: https://github.com/tavily-ai/tavily-mcp
- Brave Search API: https://brave.com/search/api/
- Brave MCP 仓库: https://github.com/brave/brave-search-mcp-server
- Serper: https://serper.dev/
- SerpAPI MCP: https://serpapi.com/integrations/mcp
- SerpAPI 定价: https://serpapi.com/pricing
- Firecrawl MCP 文档: https://docs.firecrawl.dev/mcp-server
- Firecrawl 定价: https://firecrawl.dev/pricing
- Perplexity MCP 文档: https://docs.perplexity.ai/guides/mcp-server
- Perplexity 定价: https://docs.perplexity.ai/docs/getting-started/pricing
- Bing Search API（已关停）: https://azure.microsoft.com/pricing/details/cognitive-services/v5/search-api/
- Kagi Search API: https://help.kagi.com/kagi/api/search.html
- Kagi MCP 仓库: https://github.com/kagisearch/kagimcp
- Linkup 定价: https://www.linkup.so/pricing
- Linkup MCP 文档: https://docs.linkup.so/pages/integrations/mcp/mcp
- Linkup MCP 仓库: https://github.com/LinkupPlatform/linkup-mcp-server
- Jina AI MCP 仓库: https://github.com/jina-ai/MCP
- Jina AI Reader 定价: https://jina.ai/reader/
- SearXNG MCP（社区）: https://github.com/ihor-sokoliuk/mcp-searxng
