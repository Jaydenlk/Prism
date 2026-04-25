# Fix #3+ — Skills Search 数据源根因式重构(删 GitHubSource + MarketplaceCatalogSource)

> Date: 2026-04-20
> Defect: fix#3 验收阻塞 — `/skills/search` 返空(GitHubSource 需 token + LocalSource 文件系统空)
> Source of truth: WebFetched `https://code.claude.com/docs/en/discover-plugins`(2026-04-20)+ exa empty-state 最佳实践调研

---

## 0. Source of Truth

### Claude Code 官方 plugin discovery(primary source)

> "A marketplace is a catalog of plugins... `/plugin` opens 4-tab UI with **Discover** tab to browse plugins from all your marketplaces."

**关键**:Claude Code **不调 GitHub Code Search API**。用户先 `/plugin marketplace add owner/repo` → 注册 catalog → 从已注册 marketplaces 的 catalog 内浏览/搜索。无任何 token 要求 for discovery(install 时按 plugin entry 的 `source` 字段决定是否需要 token,Block 1 ADR-090 已实现)。

### Exa empty-state 最佳实践(Linear / Notion 风格)

- "Search empty states: 100% neutral tone, 0% encouragement. Headlines 2-4 words. Recovery hints minimal."
- 不用 illustration / 不用感叹号 / 不用"Don't worry"

### 当前 Prism 状态(读代码确认)

- `executor/plugins/skills_registry.py:303-401` `GitHubSource` 调 GitHub Code Search API;无 token 直接返 `[]`(`skills_registry.py:346-351` log warn `no_token`);即使有 token,API rate-limited + Code Search 不稳。**与 Claude Code 官方 pattern 完全不同**。
- `LocalSource` 扫 `{workspace}/.skills/` + `.prism/skills/`;新部署里两个目录空。
- Block 1 已有 `marketplace_registry.catalog_json` JSONB 字段缓存 marketplace.json plugins[],但 `/skills/search` 从未消费。

---

## 1. Root Cause

`SkillsRegistry.search` 数据源设计违反 Claude Code 官方 pattern。GitHubSource 是 anti-pattern(强依赖外部 token + API rate limit + 与 Prism 自己的 marketplace 系统重复)。

---

## 2. Goal

用户在 SkillsSettings / SkillsPage 搜索 → **从已注册 marketplaces 的 catalog 中浏览/搜索**(同 Claude Code 官方 Discover tab 体验),无任何 token 要求。

---

## 3. Non-Goal(YAGNI)

- 不做 GitHub Code Search 替代方案(用户已通过 marketplace 注册 GitHub 仓库,catalog 已足够)
- 不做 fuzzy search(substring match 足够)
- 不做 search 结果缓存(catalog_json 已 DB-cached)
- 不做"官方 marketplace 自动注入"(用户主动 add,KISS)

---

## 4. Architecture(单一职责)

```
SkillsRegistry.search(query)
        │
        ├──→ LocalSource (扫 .skills/ + .prism/skills/) ────→ SkillPackage[]
        │
        └──→ MarketplaceCatalogSource (新)
              │
              ▼
         读 marketplace_registry 表(via DB session)
         flatten 所有 catalog_json.plugins[]
         match query (substring on name + description + keywords/tags)
              │
              ▼
         SkillPackage[](source="marketplace:{name}", source_url=plugin entry source)
        
        合并去重 → 返回
```

`GitHubSource` 整个 **删除**。

### MarketplaceCatalogSource 实现要点

```python
class MarketplaceCatalogSource(SkillSource):
    source_name = "marketplace"
    
    def __init__(self, db_session_factory: Callable[[], Session]) -> None:
        # session factory(每 search 起新 session,释放干净)
        self._db_factory = db_session_factory
    
    async def search(self, query: str) -> list[SkillPackage]:
        with self._db_factory() as db:
            rows = db.query(MarketplaceRegistry).all()
        
        results = []
        q = (query or "").lower().strip()
        for mp in rows:
            catalog = mp.catalog_json or {}
            for p in catalog.get("plugins", []):
                if not isinstance(p, dict) or not p.get("name"):
                    continue
                if q and not self._match(p, q):
                    continue
                results.append(SkillPackage(
                    name=p["name"],
                    description=p.get("description") or "",
                    version=str(p.get("version") or "0.0.0"),
                    source="marketplace",
                    source_url=f"marketplace://{mp.name}/{p['name']}",
                    author=(p.get("author") or {}).get("name") if isinstance(p.get("author"), dict) else None,
                    tags=list(p.get("keywords") or p.get("tags") or []),
                    installed=False,  # 由调用方 join skill_installs
                    installed_version=None,
                ))
        return results
    
    @staticmethod
    def _match(p: dict, q: str) -> bool:
        return any(q in str(v).lower() for v in [
            p.get("name", ""),
            p.get("description") or "",
            *(p.get("keywords") or p.get("tags") or []),
        ])
```

---

## 5. 后端文件改动

| File | Action | LOC |
|---|---|---|
| `executor/plugins/skills_registry.py` | 删除 `GitHubSource` class(L303-401)+ 新增 `MarketplaceCatalogSource`(~80 LOC) + 调整 `SkillsRegistry.__init__` default sources | -100 +85 |
| `backend/app/api/v1/skills.py` | `_get_registry()` 注入 `db_session_factory`(用 `app.core.database.SessionLocal`)| +8 |
| `executor/plugins/__init__.py` | 删除 `GitHubSource` export(若有) | -1 |

### `_get_registry` 改动

```python
def _get_registry():
    """Lazily build SkillsRegistry with LocalSource + MarketplaceCatalogSource."""
    from app.core.database import SessionLocal
    from executor.plugins.skills_registry import (
        LocalSource, MarketplaceCatalogSource, SkillsRegistry,
    )
    if not hasattr(_get_registry, "_cache"):
        _get_registry._cache = SkillsRegistry(sources=[
            LocalSource(),
            MarketplaceCatalogSource(db_session_factory=SessionLocal),
        ])
    return _get_registry._cache
```

---

## 6. 前端 Empty State 改动(Linear 风格)

### `frontend/Prism.html` SkillsSettingsTab L3147 区(搜索结果空时)

```jsx
{q && !searching && searchResults.length === 0 && (
  <div data-testid="search-empty-state" style={{ padding: 16, color: "var(--ink-3)", fontSize: 13 }}>
    <div style={{ fontWeight: 500, color: "var(--ink)", marginBottom: 4 }}>无匹配 "{q}"</div>
    <div style={{ fontSize: 12 }}>检查拼写,或尝试其他关键词。
    {marketplacesCount === 0 && " 还没有 marketplace? "}
    {marketplacesCount === 0 && (
      <a href="#" onClick={e => { e.preventDefault(); window.location.hash = "#skills"; }} style={{ color: "var(--amber)" }}>去注册</a>
    )}</div>
  </div>
)}
```

需 `marketplacesCount` state(useEffect 拉一次 marketplaces.list)。

### SkillsPage 主页面也加 empty state(L1638-1640 替换):

类似处理 — 现有"暂无可用技能"是合法 empty,但 query 无 match 时改为"无匹配 'xxx',检查拼写"。

---

## 7. Tests

### Python unit(8 tests on `test_marketplace_catalog_source.py`)

1. 空 marketplace_registry → 返 []
2. 1 marketplace 含 1 plugin,query 空 → 返 1
3. query match name → 返 match 项
4. query match description → 返 match 项
5. query match tags → 返 match 项
6. query mismatch → 返 []
7. 多 marketplace,query 空 → 合并所有 plugins
8. catalog_json 中 plugins entry 缺 name 字段 → skip 该 entry(不崩)

### Playwright e2e(4 场景 × 双端 = 8)

1. 0 marketplaces 注册 + 搜 → empty state "无 marketplace 已注册"+"去注册"链接
2. 有 marketplace + query 无 match → empty state "无匹配 '<query>'"
3. 有 marketplace + query match → 出结果 + 安装按钮工作(fix#3 链路)
4. 桌面 + 移动 viewport 各 empty state 文案 + 按钮 ≥36pt

---

## 8. 反打补丁验证

✅ 删除 GitHubSource 整个(根因移除,不是加 token check 兜底)
✅ MarketplaceCatalogSource 单一职责(只 catalog filter,不爬 GitHub)
✅ 复用 Block 1 已有 marketplace_registry 表 + catalog_json(无新数据源)
✅ Empty state 文案 Linear 风格(neutral tone,recovery hint 最小,exa 最佳实践)
✅ 不依赖任何外部 API token

---

## 9. Files Summary

| File | Action | LOC |
|---|---|---|
| `executor/plugins/skills_registry.py` | -GitHubSource +MarketplaceCatalogSource | -100 +85 |
| `backend/app/api/v1/skills.py` | _get_registry 改 | +8 |
| `executor/plugins/__init__.py` | clean export | -1 |
| `backend/tests/test_marketplace_catalog_source.py` | NEW | 200 |
| `frontend/Prism.html` SkillsSettingsTab + SkillsPage | empty state | +30 |
| `e2e/tests/skills-search-data-source.spec.ts` | NEW | 200 |

总:-101 +523。

---

## 10. 验收 checklist(用户自主)

- [ ] /Prism.html → 设置 → 技能 → 搜索 "test" → 应见 empty state "无 marketplace 已注册" + 链接(因为还没注册过)
- [ ] 点链接 → 跳到 /Prism.html#skills → SkillsPage Marketplace tab → 注册 `anthropics/claude-plugins-official`
- [ ] 等 catalog 拉回 → 返设置 → 技能 → 搜 "github" / "commit" 关键词 → 应出 marketplace catalog 中的 plugin 结果
- [ ] 任选一项 → 点安装(fix#3 已接通)→ 走完 install 流
- [ ] 移动端(F12 iPhone)同样路径

---

*End of spec — ~750 字,based on WebFetched + exa primary sources。*
