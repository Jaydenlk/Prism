# Skills Market 搜索体验改善设计

> 日期: 2026-05-10
> 状态: 待确认
> 优先级: P1（用户反馈最核心痛点）

---

## 业务需求

用户在 Skills Market 搜索 skill 时，期望输入关键词就能找到所有相关结果，类似 npm search 体验。

### 用户痛点

1. 搜 "design" 只匹配 name 含 "design" 的，搜不到 description 里写着 "UI layout" 的相关 skill
2. 拼错 "wheather" 直接无结果，不容错
3. 输 "finance agent" 作为整体匹配，几乎无命中
4. GitHub 搜 "weather" 返回 "awesome-go" 等无关仓库
5. 结果排序无逻辑，用户要自己翻找
6. 无结果时只说"检查拼写"，没有帮助

### 期望链路

```
用户输入关键词 → 拆词 → 模糊匹配 → 加权评分 → 排序展示（已安装置顶 > 本地/Marketplace 按分数 > GitHub 按 star）→ 每次展示 10 条 → 无结果给有用建议
```

---

## 改动范围

### 1. 后端：评分引擎（`executor/plugins/skills_registry.py`）

**新增** `score_match(query: str, pkg: SkillPackage) -> float` 函数：

- 将 query 按空白拆成 token 列表
- 每个 token 对 name/tags/description 做模糊匹配（`rapidfuzz.fuzz.partial_ratio`）
- 加权：name × 5, tags × 3, description × 1
- 阈值：相似度 ≥ 60 才计分
- 返回归一化总分 0-100

**替换** `LocalSource._matches` 和 `_marketplace_entry_matches`：用评分函数替代精确子串匹配，score > 0 即命中。

**修改** `SkillPackage`：新增 `score: float = 0.0` 和 `stars: int = 0` 字段。

**修改** `SkillsRegistry.search`：结果排序规则——
1. 已安装的 skill 置顶
2. 本地/Marketplace 结果按 score 降序
3. GitHub 结果排在最后，按 stars 降序
4. 合并后取前 10 条返回

### 2. 后端：GitHub 查询优化（`executor/plugins/github_source.py`）

- 查询词加 `topic:skill OR topic:mcp-server` 限定，减少无关仓库
- 保存 `stargazers_count` 到 `SkillPackage.stars`
- `per_page` 改为 10

### 3. 后端：API 默认值（`backend/app/api/v1/skills.py`）

- `limit` 默认值从 20 改为 10

### 4. 前端：无结果 UX（`frontend/Prism.html`）

- 替换"检查拼写,或尝试其他关键词"为更有用的建议文案
- 有查询词无结果时：提示"试试更短的关键词"或"浏览全部 skill"

### 5. 新依赖

- `rapidfuzz>=3.0`（C 扩展，性能好，用于编辑距离模糊匹配）

---

## 不涉及

- Marketplace 注册 UX
- Plugin Builder v2
- 安装流程改善
- 分页/加载更多（本次只限制为 10 条）
