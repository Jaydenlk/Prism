# Skills Market GUI Phase 1a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Skills Market 从"盲搜盲装"升级为"发现 → 预览 → 安装"的完整体验，每条搜索结果有来源标签，点击可看 README 详情。

**Architecture:** 后端增加 GitHub 数据源适配器 + README 内容端点。前端 SkillsPage 重做搜索结果卡片（来源 badge）和详情面板（README 渲染）。

**Tech Stack:** Python 3.11+ / FastAPI / httpx / Vanilla React (CDN) / Markdown 渲染

---

## File Map

| 文件 | 操作 | 职责 |
|---|---|---|
| `executor/plugins/github_source.py` | Create | GitHub SkillSource 适配器 |
| `executor/plugins/skills_registry.py` | Modify | 注册 GitHubSource |
| `executor/tests/test_github_source.py` | Create | GitHub 搜索测试 |
| `backend/app/api/v1/skills.py` | Modify | 增加 `/skills/{name}/readme` 端点 |
| `backend/app/schemas/skill.py` | Modify | 增强 SkillPackageResponse |
| `frontend/Prism.html` | Modify | SkillsPage 重做 |
| `frontend/styles.css` | Modify | 来源 badge + 详情面板样式 |

---

### Task 1: GitHub SkillSource 适配器

**Files:**
- Create: `executor/plugins/github_source.py`
- Test: `executor/tests/test_github_source.py`

- [ ] **Step 1: 写失败测试**

```python
"""GitHub SkillSource adapter tests."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch
from executor.plugins.github_source import GitHubSource

@pytest.fixture
def source():
    return GitHubSource()

class TestGitHubSourceSearch:
    @pytest.mark.asyncio
    async def test_search_returns_skill_packages(self, source):
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "repository": {
                        "full_name": "owner/repo",
                        "description": "A useful skill",
                        "html_url": "https://github.com/owner/repo",
                        "stargazers_count": 42,
                        "topics": ["skill", "ai"],
                        "owner": {"login": "owner"},
                    },
                    "path": "skills/my-skill/SKILL.md",
                }
            ]
        }
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            results = await source.search("useful")
        assert len(results) == 1
        assert results[0].name == "my-skill"
        assert results[0].source == "github"
        assert "github.com/owner/repo" in results[0].source_url

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, source):
        results = await source.search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_api_error_returns_empty(self, source):
        mock_response = AsyncMock()
        mock_response.status_code = 403
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            results = await source.search("test")
        assert results == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd executor && python -m pytest tests/test_github_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'executor.plugins.github_source'`

- [ ] **Step 3: 实现 GitHubSource**

```python
"""GitHub SkillSource — 搜索 GitHub 仓库中的 SKILL.md 文件。

使用 GitHub Code Search API 查找包含 SKILL.md 的公开仓库，
将每个匹配结果映射为 SkillPackage。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from executor.plugins.skills_registry import SkillPackage, SkillSource

logger = logging.getLogger(__name__)

_GITHUB_SEARCH_URL = "https://api.github.com/search/code"
_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)


class GitHubSource(SkillSource):
    """搜索 GitHub 公开仓库中的 SKILL.md。"""

    @property
    def source_name(self) -> str:
        return "github"

    async def search(self, query: str) -> list[SkillPackage]:
        if not query.strip():
            return []
        github_query = f"filename:SKILL.md {query}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    _GITHUB_SEARCH_URL,
                    params={"q": github_query, "per_page": 20},
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
        seen_repos: set[str] = set()
        for item in data.get("items", []):
            repo = item.get("repository", {})
            full_name = repo.get("full_name", "")
            if full_name in seen_repos:
                continue
            seen_repos.add(full_name)

            path = item.get("path", "")
            skill_name = path.split("/")[-2] if "/" in path else full_name.split("/")[-1]

            results.append(SkillPackage(
                name=skill_name,
                description=repo.get("description") or "",
                version="latest",
                source="github",
                source_url=repo.get("html_url", f"https://github.com/{full_name}"),
                author=repo.get("owner", {}).get("login"),
                tags=repo.get("topics") or [],
            ))
        return results

    async def fetch(self, package_id: str, version: str | None = None):
        raise NotImplementedError("GitHub fetch requires git clone — use marketplace install flow")

    async def get_versions(self, package_id: str) -> list[str]:
        return ["latest"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd executor && python -m pytest tests/test_github_source.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: 注册 GitHubSource 到 SkillsRegistry**

修改 `executor/plugins/skills_registry.py`，在 `SkillsRegistry.__init__` 中添加：

```python
from executor.plugins.github_source import GitHubSource
# 在 sources 列表中添加
self._sources.append(GitHubSource())
```

- [ ] **Step 6: 运行全量 executor 测试**

Run: `cd executor && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add executor/plugins/github_source.py executor/tests/test_github_source.py executor/plugins/skills_registry.py
git commit -m "feat: add GitHub SkillSource adapter — search repos with SKILL.md"
```

---

### Task 2: 后端 README 端点 + 增强搜索响应

**Files:**
- Modify: `backend/app/api/v1/skills.py`
- Modify: `backend/app/schemas/skill.py`

- [ ] **Step 1: 增强 SkillPackageResponse schema**

在 `backend/app/schemas/skill.py` 的 `SkillPackageResponse` 中添加字段：

```python
class SkillPackageResponse(BaseModel):
    # ... existing fields ...
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    readme_available: bool = False
```

- [ ] **Step 2: 添加 README 端点**

在 `backend/app/api/v1/skills.py` 添加：

```python
@router.get("/{skill_name}/readme", response_model=ApiResponse[dict])
async def get_skill_readme(
    skill_name: str,
    source_url: str = Query(default="", description="GitHub URL or marketplace source"),
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
) -> ApiResponse[dict]:
    """获取 Skill 的 README 内容。

    优先从已安装路径读取，否则从 source_url 远程获取。
    """
    # 1. 已安装？从本地路径读
    svc = SkillInstallService(db)
    install = svc.get_install(str(current_user.id), skill_name)
    if install and install.metadata_.get("install_path"):
        readme_path = Path(install.metadata_["install_path"]) / "SKILL.md"
        if readme_path.exists():
            return ApiResponse(data={"skill_name": skill_name, "content": readme_path.read_text(encoding="utf-8"), "source": "local"})

    # 2. GitHub URL？从 raw.githubusercontent.com 拉
    if source_url and "github.com" in source_url:
        raw_url = source_url.replace("github.com", "raw.githubusercontent.com").rstrip("/") + "/main/SKILL.md"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(raw_url)
                if resp.status_code == 200:
                    return ApiResponse(data={"skill_name": skill_name, "content": resp.text, "source": "github"})
        except httpx.HTTPError:
            pass

    # 3. 已安装的 content 端点兜底
    if install:
        content_resp = await get_skill_content(skill_name, db, current_user)
        return ApiResponse(data={"skill_name": skill_name, "content": content_resp.data.get("content", ""), "source": "installed"})

    raise HTTPException(404, f"README not found for {skill_name}")
```

- [ ] **Step 3: 运行 backend 测试**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All existing pass, no regression

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/skills.py backend/app/schemas/skill.py
git commit -m "feat: add /skills/{name}/readme endpoint + enhanced search response"
```

---

### Task 3: 前端 — 搜索结果来源 Badge + 详情面板

**Files:**
- Modify: `frontend/Prism.html` (SkillsPage component)
- Modify: `frontend/styles.css`
- Modify: `frontend/apiClient.js`

- [ ] **Step 1: apiClient 添加 getReadme 方法**

在 `frontend/apiClient.js` 的 skills 对象中添加：

```javascript
getReadme(name, sourceUrl) {
    const params = sourceUrl ? `?source_url=${encodeURIComponent(sourceUrl)}` : "";
    return request("GET", `/skills/${encodeURIComponent(name)}/readme${params}`);
},
```

- [ ] **Step 2: 添加来源 badge + 详情面板 CSS**

在 `frontend/styles.css` 添加：

```css
/* Skills source badges */
.skill-source-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.skill-source-badge.github { background: #24292e; color: #fff; }
.skill-source-badge.marketplace { background: var(--teal); color: #fff; }
.skill-source-badge.local { background: var(--amber); color: var(--ink); }
.skill-source-badge.manus { background: #6366f1; color: #fff; }

/* Skill detail panel */
.skill-detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: min(520px, 90vw);
  height: 100vh;
  background: var(--paper);
  border-left: 1px solid var(--line);
  box-shadow: var(--shadow-3);
  z-index: 60;
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.25s ease;
}
.skill-detail-panel.open {
  transform: translateX(0);
}
.skill-detail-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.skill-detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
.skill-detail-body .readme-content {
  line-height: 1.6;
  font-size: 14px;
}
.skill-detail-body .readme-content h1,
.skill-detail-body .readme-content h2,
.skill-detail-body .readme-content h3 {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
}
.skill-detail-body .readme-content pre {
  background: var(--bg);
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
}
.skill-detail-body .readme-content code {
  background: var(--bg);
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 13px;
}
.skill-detail-actions {
  padding: 16px 24px;
  border-top: 1px solid var(--line);
  display: flex;
  gap: 8px;
}
@media (max-width: 640px) {
  .skill-detail-panel {
    width: 100vw;
  }
}
```

- [ ] **Step 3: 重写 SkillsPage 搜索结果卡片**

在 `frontend/Prism.html` 的 SkillsPage 组件中，替换搜索结果渲染部分。每个结果卡片包含：
- 来源 badge（GitHub/Marketplace/Local，根据 `result.source` 字段）
- 名称 + 版本
- 作者
- 描述（截断 2 行）
- 点击展开详情面板

关键 JSX 片段（搜索结果卡片）：

```jsx
function SourceBadge({ source }) {
    const labels = { github: "GitHub", marketplace: "Marketplace", local: "Local", manus: "Manus" };
    return <span className={`skill-source-badge ${source}`}>{labels[source] || source}</span>;
}
```

- [ ] **Step 4: 实现 SkillDetailPanel 组件**

```jsx
function SkillDetailPanel({ skill, onClose, onInstall, installed }) {
    const [readme, setReadme] = useState("");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!skill) return;
        setLoading(true);
        PrismAPI.skills.getReadme(skill.name, skill.source_url)
            .then(data => setReadme(data.content || ""))
            .catch(() => setReadme("README 暂不可用"))
            .finally(() => setLoading(false));
    }, [skill?.name]);

    if (!skill) return null;

    return (
        <div className={`skill-detail-panel ${skill ? "open" : ""}`}>
            <div className="skill-detail-header">
                <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <h3 style={{ margin: 0 }}>{skill.name}</h3>
                        <SourceBadge source={skill.source}/>
                        <span className="badge">{skill.version}</span>
                    </div>
                    {skill.author && <div style={{ color: "var(--ink-4)", marginTop: 4 }}>by {skill.author}</div>}
                    <p style={{ marginTop: 8, color: "var(--ink-3)" }}>{skill.description}</p>
                </div>
                <button className="icon-btn" onClick={onClose}><Icon name="close" size={16}/></button>
            </div>
            <div className="skill-detail-body">
                {loading ? <div>加载中…</div> : (
                    <div className="readme-content" dangerouslySetInnerHTML={{ __html: simpleMarkdown(readme) }}/>
                )}
            </div>
            <div className="skill-detail-actions">
                {installed
                    ? <button className="btn sm" disabled>已安装</button>
                    : <button className="btn sm primary" onClick={() => onInstall(skill)}>安装</button>
                }
                {skill.source_url && <a href={skill.source_url} target="_blank" rel="noopener" className="btn sm">查看源码</a>}
            </div>
        </div>
    );
}
```

- [ ] **Step 5: 添加简易 Markdown → HTML 渲染函数**

```javascript
function simpleMarkdown(md) {
    if (!md) return "";
    return md
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/^### (.+)$/gm, "<h3>$1</h3>")
        .replace(/^## (.+)$/gm, "<h2>$1</h2>")
        .replace(/^# (.+)$/gm, "<h1>$1</h1>")
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/```[\s\S]*?```/g, m => `<pre>${m.slice(3, -3).trim()}</pre>`)
        .replace(/^- (.+)$/gm, "<li>$1</li>")
        .replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>")
        .replace(/\n\n/g, "</p><p>")
        .replace(/^/, "<p>").replace(/$/, "</p>");
}
```

- [ ] **Step 6: 在 SkillsPage 中集成详情面板**

添加 state: `const [detailSkill, setDetailSkill] = useState(null);`

搜索结果卡片的 `onClick` 设为 `() => setDetailSkill(result)`

在 SkillsPage return 末尾添加 `<SkillDetailPanel skill={detailSkill} onClose={() => setDetailSkill(null)} ... />`

- [ ] **Step 7: Commit**

```bash
git add frontend/Prism.html frontend/styles.css frontend/apiClient.js
git commit -m "feat: Skills Market GUI — source badges + README detail panel"
```

---

### Task 4: 集成验证

- [ ] **Step 1: 重建 backend + 重启**

```bash
docker compose -p prismv3 build backend && docker compose -p prismv3 up -d --force-recreate --no-deps backend && docker compose -p prismv3 restart nginx
```

- [ ] **Step 2: Playwright 桌面端验证**

1. 导航到 Skills Market 页面
2. 搜索 "weather" — 确认结果有来源 badge（GitHub/Marketplace）
3. 点击一个搜索结果 — 确认详情面板滑入，显示 README 内容
4. 确认"安装"按钮可点击
5. 确认"查看源码"链接有效
6. 关闭详情面板

- [ ] **Step 3: Playwright 移动端验证**

1. viewport 390×844
2. 重复桌面端步骤
3. 确认详情面板全屏（width: 100vw）

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: verify Skills Market GUI redesign — source badges + detail panel"
```
