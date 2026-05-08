# Skills Market 搜索体验改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Skills Market 搜索支持多词拆分、模糊匹配、加权评分排序，结果限 10 条，无结果时给出有用建议。

**Architecture:** 后端新增 `search_scoring.py` 评分模块（单一职责），替换 `skills_registry.py` 和 `github_source.py` 中的精确子串匹配。前端调整 limit 和无结果文案。

**Tech Stack:** Python 3.11 / rapidfuzz / FastAPI / Vanilla JS (frontend)

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `executor/plugins/search_scoring.py` | **新建** | 评分引擎：拆词 + 模糊匹配 + 加权计分 |
| `executor/plugins/skills_registry.py` | 修改 | SkillPackage 加 score/stars 字段；搜索排序用评分；删除旧 `_matches` 和 `_marketplace_entry_matches` |
| `executor/plugins/github_source.py` | 修改 | 优化查询词；保存 stars；per_page=10 |
| `backend/app/api/v1/skills.py` | 修改 | 默认 limit=10 |
| `backend/requirements.txt` | 修改 | 加 rapidfuzz>=3.0 |
| `frontend/Prism.html` | 修改 | limit=10；无结果文案改善（两处） |

---

### Task 1: 新增评分引擎 `search_scoring.py`

**Files:**
- Create: `executor/plugins/search_scoring.py`

- [ ] **Step 1: 创建评分模块**

```python
"""Skills 搜索评分引擎 — 拆词 + 模糊匹配 + 加权计分"""
from __future__ import annotations

from rapidfuzz import fuzz

WEIGHT_NAME = 5
WEIGHT_TAGS = 3
WEIGHT_DESC = 1
FUZZY_THRESHOLD = 60


def score_match(query: str, name: str, description: str, tags: list[str]) -> float:
    """对单个 skill 计算搜索相关度分数。

    将 query 按空白拆成 token，每个 token 对 name/tags/description
    做模糊匹配（partial_ratio），加权求和后归一化到 0-100。
    """
    if not query or not query.strip():
        return 100.0

    tokens = query.lower().split()
    if not tokens:
        return 100.0

    name_lower = name.lower()
    desc_lower = description.lower()
    tags_lower = [t.lower() for t in tags]

    total = 0.0
    max_possible = len(tokens) * (WEIGHT_NAME + WEIGHT_TAGS + WEIGHT_DESC) * 100

    for token in tokens:
        name_score = fuzz.partial_ratio(token, name_lower)
        best_tag_score = max((fuzz.partial_ratio(token, t) for t in tags_lower), default=0)
        desc_score = fuzz.partial_ratio(token, desc_lower)

        if name_score >= FUZZY_THRESHOLD:
            total += name_score * WEIGHT_NAME
        if best_tag_score >= FUZZY_THRESHOLD:
            total += best_tag_score * WEIGHT_TAGS
        if desc_score >= FUZZY_THRESHOLD:
            total += desc_score * WEIGHT_DESC

    return round((total / max_possible) * 100, 1) if max_possible > 0 else 0.0
```

- [ ] **Step 2: 验证模块可导入**

Run: `cd backend && python -c "from executor.plugins.search_scoring import score_match; print(score_match('weather', 'weather-skill', 'Get weather forecasts', ['api', 'weather']))"`

Expected: 输出一个大于 50 的分数

- [ ] **Step 3: Commit**

```bash
git add executor/plugins/search_scoring.py
git commit -m "feat: add search scoring engine with fuzzy matching"
```

---

### Task 2: 添加 rapidfuzz 依赖

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 在 requirements.txt 末尾添加 rapidfuzz**

在最后一行 `pynacl>=1.5.0` 之后添加：
```
rapidfuzz>=3.0.0        # Skills 搜索模糊匹配（编辑距离）
```

- [ ] **Step 2: 安装依赖**

Run: `pip install rapidfuzz>=3.0.0`

Expected: Successfully installed rapidfuzz-...

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps: add rapidfuzz for fuzzy search matching"
```

---

### Task 3: 改造 SkillPackage + LocalSource + MarketplaceCatalogSource

**Files:**
- Modify: `executor/plugins/skills_registry.py:44-62` (SkillPackage dataclass)
- Modify: `executor/plugins/skills_registry.py:267-279` (LocalSource._matches)
- Modify: `executor/plugins/skills_registry.py:400-409` (_marketplace_entry_matches)
- Modify: `executor/plugins/skills_registry.py:158-190` (LocalSource.search)
- Modify: `executor/plugins/skills_registry.py:324-382` (MarketplaceCatalogSource.search)

- [ ] **Step 1: SkillPackage 加 score 和 stars 字段**

在 `executor/plugins/skills_registry.py` 的 SkillPackage dataclass 中，`plugin_name` 字段之后添加：

```python
    score: float = 0.0              # 搜索相关度评分（0-100）
    stars: int = 0                  # GitHub star 数（仅 github 源）
```

- [ ] **Step 2: 新增 LocalSource._score 评分方法**

在 `_matches` 方法之后添加：

```python
    def _score(self, pkg: SkillPackage, query: str) -> float:
        """计算 SkillPackage 与搜索词的相关度分数。"""
        if not query:
            return 100.0
        from executor.plugins.search_scoring import score_match
        return score_match(query, pkg.name, pkg.description, pkg.tags)
```

- [ ] **Step 3: 修改 LocalSource.search 使用评分**

将 `LocalSource.search` 中的匹配和返回逻辑改为：

```python
                if pkg.name in seen:
                    continue
                seen.add(pkg.name)

                pkg.score = self._score(pkg, query)
                if pkg.score > 0:
                    results.append(pkg)
```

（删除原来的 `if self._matches(pkg, query):` 行）

- [ ] **Step 4: 替换 _marketplace_entry_matches 为评分函数**

将 `_marketplace_entry_matches` 函数替换为：

```python
def _score_marketplace_entry(entry: dict, q: str) -> float:
    """计算 marketplace entry 与搜索词的相关度分数。"""
    if not q:
        return 100.0
    from executor.plugins.search_scoring import score_match
    name = str(entry.get("name", ""))
    desc = str(entry.get("description") or "")
    tags_raw = entry.get("keywords") or entry.get("tags") or []
    tags = [str(t) for t in tags_raw if isinstance(t, (str, int))]
    return score_match(q, name, desc, tags)
```

- [ ] **Step 5: 修改 MarketplaceCatalogSource.search 使用评分**

将 `MarketplaceCatalogSource.search` 中原来的过滤逻辑：

```python
                if q and not _marketplace_entry_matches(entry, q):
                    continue
```

替换为：

```python
                entry_score = _score_marketplace_entry(entry, q)
                if q and entry_score == 0:
                    continue
```

并在构造 `SkillPackage` 时赋值 `score=entry_score`（在已有的 `plugin_name=name,` 之后添加 `score=entry_score,`）。

- [ ] **Step 6: 删除旧的 _matches 方法和 _marketplace_entry_matches 函数**

删除 `LocalSource._matches` 方法（行 267-279）和 `_marketplace_entry_matches` 函数（行 400-409）。

- [ ] **Step 7: Commit**

```bash
git add executor/plugins/skills_registry.py
git commit -m "feat: replace exact substring matching with fuzzy scoring in Local and Marketplace sources"
```

---

### Task 4: 改造 SkillsRegistry.search 排序逻辑

**Files:**
- Modify: `executor/plugins/skills_registry.py:466-520` (SkillsRegistry.search)

- [ ] **Step 1: 修改排序规则**

将 `SkillsRegistry.search` 中排序逻辑（行 508-512）：

```python
        result = sorted(
            merged.values(),
            key=lambda p: (0 if p.installed else 1, p.name),
        )
```

替换为：

```python
        result = sorted(
            merged.values(),
            key=lambda p: (
                0 if p.installed else 1,
                0 if p.source != "github" else 1,
                -p.score,
                -p.stars,
                p.name,
            ),
        )
```

排序优先级：已安装置顶 → 本地/Marketplace 优先于 GitHub → 分数高的在前 → star 多的在前 → 按名称字母序。

- [ ] **Step 2: Commit**

```bash
git add executor/plugins/skills_registry.py
git commit -m "feat: sort search results by installed > source > score > stars"
```

---

### Task 5: 优化 GitHub 查询 + 保存 stars

**Files:**
- Modify: `executor/plugins/github_source.py:26-56`

- [ ] **Step 1: 优化查询词构造 + 保存 stars + 限制 10 条**

将 `GitHubSource.search` 方法替换为：

```python
    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        github_query = f"{query} topic:skill OR topic:mcp-server in:name,description,readme"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _GITHUB_REPOS_URL,
                    params={"q": github_query, "per_page": 10, "sort": "stars"},
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code != 200:
                    logger.warning("GitHub search returned %d", resp.status_code)
                    return []
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("GitHub search failed: %s", exc)
            return []

        results: list[SkillPackage] = []
        for repo in data.get("items", []):
            results.append(SkillPackage(
                name=repo.get("name", ""),
                description=repo.get("description") or "",
                version="latest",
                source="github",
                source_url=repo.get("html_url", ""),
                author=repo.get("owner", {}).get("login"),
                tags=repo.get("topics") or [],
                stars=repo.get("stargazers_count", 0),
            ))
        return results
```

变更点：
- 查询词加 `topic:skill OR topic:mcp-server` 限定
- `per_page` 从 15 改为 10
- 保存 `stargazers_count` 到 `stars` 字段

- [ ] **Step 2: Commit**

```bash
git add executor/plugins/github_source.py
git commit -m "feat: optimize GitHub search query and store star count"
```

---

### Task 6: 后端 API 默认 limit 改为 10

**Files:**
- Modify: `backend/app/api/v1/skills.py:165`

- [ ] **Step 1: 修改 limit 默认值**

将：
```python
    limit: int = Query(default=20, ge=1, le=100, description="最大结果数（1-100）"),
```

改为：
```python
    limit: int = Query(default=10, ge=1, le=100, description="最大结果数（1-100）"),
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/v1/skills.py
git commit -m "feat: change default search limit from 20 to 10"
```

---

### Task 7: 前端搜索 limit + 无结果 UX 改善

**Files:**
- Modify: `frontend/Prism.html:1517` (doSearch limit)
- Modify: `frontend/Prism.html:1806-1817` (SkillsPage 无结果文案)
- Modify: `frontend/Prism.html:3403-3421` (SkillsSettings 无结果文案)

- [ ] **Step 1: doSearch limit 从 50 改为 10**

将 `Prism.html` 行 1517 的：
```javascript
        limit: 50,
```
改为：
```javascript
        limit: 10,
```

- [ ] **Step 2: SkillsPage 无结果文案改善**

将 `Prism.html` 行 1808-1816 的无结果区块替换为：

```jsx
            <div data-testid="skillspage-search-empty" style={{ padding: "16px 0" }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>
                {q ? `未找到 "${q}" 相关的 skill` : "暂无可搜索内容"}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                {q ? (
                  <>试试更短的关键词，或 <a href="#" onClick={e => { e.preventDefault(); setQ(""); }} style={{ color: "var(--amber)", textDecoration: "underline" }}>浏览全部</a></>
                ) : "在右侧 Marketplace tab 注册一个 catalog,或上传本地 skill。"}
              </div>
            </div>
```

- [ ] **Step 3: SkillsSettings 无结果文案改善**

将 `Prism.html` 行 3404-3420 的无结果区块替换为：

```jsx
        <div data-testid="skills-search-empty" style={{ display: "block", width: "100%", padding: "16px 12px", marginBottom: 20, background: "var(--bg)", borderRadius: 8 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>未找到 "{q}" 相关的 skill</div>
          <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
            试试更短的关键词，或换一个相近的词。
            {marketplacesCount === 0 && (
              <>
                {" 还没注册 marketplace? "}
                <a
                  data-testid="skills-search-empty-register-link"
                  href="#"
                  onClick={(e) => { e.preventDefault(); window.location.hash = "#skills"; }}
                  style={{ color: "var(--amber)", textDecoration: "underline" }}
                >去注册</a>
              </>
            )}
          </div>
        </div>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/Prism.html
git commit -m "feat: improve search UX — limit 10 results, better no-results messaging"
```
