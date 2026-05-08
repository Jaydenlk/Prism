# Marketplace 注册 UX 改善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户一键添加常用 marketplace，改善注册入口的可发现性和易用性。

**Architecture:** 后端新增 presets 端点返回推荐 marketplace 列表（含已注册状态）。前端 Marketplace tab 顶部新增推荐区域，显示预置列表 + 一键添加。URL 输入框改善提示文案。

**Tech Stack:** Python FastAPI / Vanilla JS (Prism.html)

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/api/v1/marketplaces.py` | 修改 | 新增 `GET /presets` 端点 |
| `frontend/apiClient.js` | 修改 | 新增 `marketplaces.presets()` 方法 |
| `frontend/Prism.html` | 修改 | Marketplace tab 推荐区域 + URL placeholder 改善 |

---

### Task 1: 后端 — 新增 presets 端点

**Files:**
- Modify: `backend/app/api/v1/marketplaces.py:36-58`

- [ ] **Step 1: 在 router 定义之后、`_to_response` 之前，添加预置列表常量和端点**

在 `marketplaces.py` 的 `router = APIRouter(...)` 行之后添加：

```python
PRESET_MARKETPLACES = [
    {
        "name": "Anthropic Official",
        "url": "anthropics/claude-plugins-official",
        "description": "Anthropic 官方 Claude Code 插件市场",
    },
    {
        "name": "gstake",
        "url": "gstake/claude-plugins",
        "description": "gstake 社区插件市场",
    },
]


@router.get(
    "/presets",
    response_model=ApiResponse[list[dict]],
    summary="List preset marketplace sources with registration status",
)
async def list_preset_marketplaces(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[list[dict]]:
    registered_urls = {
        m.url for m in db.query(MarketplaceRegistry.url).all()
    }
    result = []
    for preset in PRESET_MARKETPLACES:
        result.append({
            **preset,
            "registered": preset["url"] in registered_urls,
        })
    return ApiResponse(data=result)
```

**注意:** 此端点必须放在 `list_marketplaces` 端点之前，否则 FastAPI 会把 `/presets` 当作 `/{id}` 路径参数匹配。

- [ ] **Step 2: 验证端点**

Run: `curl -s http://localhost:8080/api/v1/marketplaces/presets -H "Authorization: Bearer <token>" | python -m json.tool`

Expected: 返回包含 2 条预置 marketplace 的 JSON，其中 anthropic 的 `registered: true`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/marketplaces.py
git commit -m "feat: add GET /marketplaces/presets endpoint for recommended sources"
```

---

### Task 2: 前端 — apiClient 新增 presets 方法

**Files:**
- Modify: `frontend/apiClient.js:569-586`

- [ ] **Step 1: 在 marketplaces 模块的 `list()` 方法之前添加 presets 方法**

在 `const marketplaces = {` 之后、`list()` 之前添加：

```javascript
    presets() {
      return request('GET', '/marketplaces/presets');
    },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apiClient.js
git commit -m "feat: add marketplaces.presets() API method"
```

---

### Task 3: 前端 — Marketplace tab 推荐区域 + URL 提示改善

**Files:**
- Modify: `frontend/Prism.html:1346-1354` (状态变量)
- Modify: `frontend/Prism.html:1418-1456` (处理器)
- Modify: `frontend/Prism.html:1916-1932` (Marketplace tab UI)

- [ ] **Step 1: 添加 presets 状态变量**

在 SkillsPage 函数内的状态变量区域（现有 marketplace 相关 state 附近），添加：

```javascript
  const [presets, setPresets] = React.useState([]);
```

- [ ] **Step 2: 加载 presets 数据**

在 `loadMarketplaces` 函数附近添加：

```javascript
  async function loadPresets() {
    try {
      const resp = await PrismAPI.marketplaces.presets();
      setPresets(Array.isArray(unwrap(resp)) ? unwrap(resp) : []);
    } catch (_) { /* presets are non-critical */ }
  }
```

在 `useEffect` 的初始化调用中（`loadInstalled(); loadMarketplaces();` 附近）追加 `loadPresets();`。

- [ ] **Step 3: 添加一键添加处理器**

```javascript
  async function handleAddPreset(preset) {
    setMktAdding(true);
    try {
      await PrismAPI.marketplaces.create({ url: preset.url, name: preset.name });
      addToast("success", "已添加", `${preset.name} marketplace 已注册，正在同步目录…`);
      await loadMarketplaces();
      await loadPresets();
      await doSearch(q, source);
    } catch (err) {
      addToast("danger", "添加失败", err.message || String(err));
    }
    setMktAdding(false);
  }
```

- [ ] **Step 4: 修改 Marketplace tab UI — 添加推荐区域 + 改善 URL 提示**

将 Marketplace tab 内容区域（行 1918-1932）替换为：

```jsx
              <div data-testid="skill-install-panel-marketplace" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* 推荐来源 */}
                {presets.length > 0 && (
                  <div style={{ marginBottom: 6 }}>
                    <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginBottom: 8 }}>推荐来源</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {presets.map(p => (
                        <div key={p.url} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--paper)" }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--ink)" }}>{p.name}</div>
                            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>{p.description}</div>
                          </div>
                          <button
                            className={`btn sm ${p.registered ? "ghost" : "primary"}`}
                            disabled={p.registered || mktAdding}
                            onClick={() => handleAddPreset(p)}
                            style={{ whiteSpace: "nowrap", fontSize: 11 }}
                          >{p.registered ? "已添加" : "添加"}</button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 自定义注册 */}
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                  自定义注册
                </div>
                <label>
                  <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginBottom: 5 }}>Marketplace URL</div>
                  <input data-testid="marketplace-url-input" className="input" value={mktUrl} onChange={e => setMktUrl(e.target.value)} placeholder="owner/repo 或 marketplace.json 链接"/>
                </label>
                <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: -6 }}>
                  支持 GitHub owner/repo、.git 链接、或 .json 直链
                </div>
                <label>
                  <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginBottom: 5 }}>显示名称</div>
                  <input data-testid="marketplace-name-input" className="input" value={mktName} onChange={e => setMktName(e.target.value)} placeholder="my-marketplace"/>
                </label>
                <button data-testid="marketplace-add-submit" className="btn primary" style={{ justifyContent: "center", marginTop: 4 }} onClick={handleAddMarketplace} disabled={mktAdding}>
                  {mktAdding ? "添加中…" : "添加 Marketplace"}
                </button>
```

- [ ] **Step 5: Commit**

```bash
git add frontend/Prism.html frontend/apiClient.js
git commit -m "feat: add preset marketplace recommendations + improve registration UX"
```
