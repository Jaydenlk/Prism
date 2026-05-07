# Phase 1: Merge + 清零 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all mock data, placeholder tabs, and dead code from the frontend — every page shows real API data, every admin tab has real functionality.

**Architecture:** Frontend-heavy changes consuming already-working backend APIs. One root cause fix in apiClient (harness.analytics parameter mismatch). Admin tabs built as self-contained React components inside admin.html. Entropy scheduler added to backend lifespan.

**Tech Stack:** Vanilla HTML/JS (frontend), Python/FastAPI (backend), Playwright MCP (E2E)

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `frontend/Prism.html` | User-facing SPA | Modify: ObsPage (L2651-2686), delete mock constants (L122-158) |
| `frontend/apiClient.js` | API client | Modify: fix harness.analytics param mismatch (L605-606) |
| `frontend/admin.html` | Admin console | Modify: replace 5 Placeholder components with real implementations (L1646-1653) |
| `backend/app/main.py` | App lifespan | Modify: add entropy scheduler task |

---

### Task 1: Merge audit/prd-vs-reality branch to develop

**Files:**
- No file changes — git operations only

- [ ] **Step 1: Verify audit branch is clean and tests pass**

```bash
cd "E:/Agent program/PrismV3/.worktrees/audit-prd-vs-reality"
git status --short
# Expected: clean working tree

cd "E:/Agent program/PrismV3/.worktrees/audit-prd-vs-reality/backend"
python -m pytest tests/ -q --ignore=tests/test_plugin_validate_dispatch.py
# Expected: 134+ passed

cd "E:/Agent program/PrismV3/.worktrees/audit-prd-vs-reality"
python -m pytest executor/tests/ -q
# Expected: 12+ passed
```

- [ ] **Step 2: Merge audit branch into develop**

```bash
cd "E:/Agent program/PrismV3"
git merge audit/prd-vs-reality --no-ff -m "merge: audit/prd-vs-reality — 8 P0/P1 fixes (password, dead buttons, theme, persistence)"
```

- [ ] **Step 3: Verify develop still green after merge**

```bash
cd "E:/Agent program/PrismV3/backend"
python -m pytest tests/ -q --ignore=tests/test_plugin_validate_dispatch.py
# Expected: all pass

cd "E:/Agent program/PrismV3"
python -m pytest executor/tests/ -q
# Expected: all pass
```

- [ ] **Step 4: Commit verification**

```bash
git log --oneline -12
# Expected: 8 audit commits + merge commit visible
```

---

### Task 2: Fix apiClient harness.analytics parameter mismatch

**Files:**
- Modify: `frontend/apiClient.js:605-606`

**Root cause:** Frontend sends `?window=7d` (string), backend expects `?days=7` (int) + `?offset_days=0` (int). This causes the analytics API to always use defaults, ignoring frontend-requested window.

- [ ] **Step 1: Fix the parameter mapping**

In `frontend/apiClient.js`, replace:

```javascript
analytics({ window: w = '7d' } = {}) {
  return request('GET', '/harness/analytics', { query: { window: w } });
},
```

with:

```javascript
analytics({ days = 7, offset_days = 0 } = {}) {
  return request('GET', '/harness/analytics', { query: { days, offset_days } });
},
```

- [ ] **Step 2: Verify no other code references the old `window` parameter**

```bash
cd "E:/Agent program/PrismV3/frontend"
grep -n "harness\.analytics" Prism.html admin.html apiClient.js
```

Expected: only the apiClient definition. If any caller passes `{ window: '7d' }`, update it to `{ days: 7 }`.

- [ ] **Step 3: Syntax check**

```bash
node --check "E:/Agent program/PrismV3/frontend/apiClient.js"
# Expected: no output (clean)
```

- [ ] **Step 4: Commit**

```bash
git add frontend/apiClient.js
git commit -m "fix(apiClient): harness.analytics sends days/offset_days instead of window string

Root cause: backend expects ?days=7&offset_days=0 (int params),
frontend was sending ?window=7d (string) — always fell through to defaults.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Delete dead mock constants from Prism.html

**Files:**
- Modify: `frontend/Prism.html:122-158`

- [ ] **Step 1: Verify constants are truly unreferenced**

```bash
cd "E:/Agent program/PrismV3/frontend"
# Search for each constant name being used (not just defined)
grep -n "PROVIDERS\b" Prism.html | grep -v "^122:" | grep -v "^const "
grep -n "MCP_SERVERS\b" Prism.html | grep -v "^130:" | grep -v "^const "
grep -n "IM_CHANNELS\b" Prism.html | grep -v "^137:" | grep -v "^const "
grep -n "\bSKILLS\b" Prism.html | grep -v "^143:" | grep -v "^const "
grep -n "RECENT_RUNS\b" Prism.html | grep -v "^152:" | grep -v "^const "
```

Expected: no matches (constants are dead code).

- [ ] **Step 2: Delete lines 122-158**

Remove the entire block of 5 mock constant arrays (PROVIDERS, MCP_SERVERS, IM_CHANNELS, SKILLS, RECENT_RUNS).

- [ ] **Step 3: Verify page still loads**

```bash
node --check "E:/Agent program/PrismV3/frontend/apiClient.js"
# Prism.html is JSX-in-script, not parseable by node --check, but apiClient should still pass
```

- [ ] **Step 4: Commit**

```bash
git add frontend/Prism.html
git commit -m "chore: delete 5 dead mock constants (PROVIDERS/MCP_SERVERS/IM_CHANNELS/SKILLS/RECENT_RUNS)

These were dev-time placeholder data never referenced by any component.
All pages already use real API calls via PrismAPI.*.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: ObsPage — replace hardcoded mock with real harness analytics

**Files:**
- Modify: `frontend/Prism.html` — ObsPage component (currently L2651-2686)

- [ ] **Step 1: Rewrite ObsPage to fetch real data**

Replace the entire `function ObsPage()` (L2651-2686) with:

```javascript
function ObsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    PrismAPI.harness.analytics({ days: 7 })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message || '加载失败'); setLoading(false); });
  }, []);

  if (loading) return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">可观测性</div>
        <div className="page-sub">加载中…</div>
      </div>
    </div>
  );

  if (error) return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">可观测性</div>
        <div className="page-sub" style={{ color: 'var(--red)' }}>{error}</div>
      </div>
    </div>
  );

  if (!data || data.runs_analyzed === 0) return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">可观测性</div>
        <div className="page-sub">暂无运行数据 — 发起一次对话后回来看。</div>
      </div>
    </div>
  );

  const avg = data.averages || {};
  const totals = data.totals || {};
  const cache = data.cache_stats || {};
  const toolErrorRate = totals.tool_calls > 0
    ? ((totals.tool_errors / totals.tool_calls) * 100).toFixed(1) + '%'
    : '0%';
  const compactionRate = data.runs_analyzed > 0
    ? ((totals.compaction_events / data.runs_analyzed) * 100).toFixed(0) + '%'
    : '0%';
  const cacheHitRatio = cache.hit_ratio != null
    ? (cache.hit_ratio * 100).toFixed(0) + '%'
    : 'N/A';

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-title">可观测性</div>
        <div className="page-sub">最近 {data.period?.days || 7} 天 · {data.runs_analyzed} 次运行</div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 28 }}>
        <div className="stat-card">
          <div className="label">平均轮次</div>
          <div className="val">{(avg.turn_count || 0).toFixed(1)}</div>
          <div className="trend">{data.runs_analyzed} runs</div>
        </div>
        <div className="stat-card">
          <div className="label">工具错误率</div>
          <div className="val">{toolErrorRate}</div>
          <div className="trend">{totals.tool_errors || 0} / {totals.tool_calls || 0}</div>
        </div>
        <div className="stat-card">
          <div className="label">Compaction 率</div>
          <div className="val">{compactionRate}</div>
          <div className="trend">{totals.compaction_events || 0} 次</div>
        </div>
        <div className="stat-card">
          <div className="label">Cache 命中率</div>
          <div className="val">{cacheHitRatio}</div>
          <div className="trend">{((cache.hit_tokens || 0) / 1000).toFixed(0)}K tokens</div>
        </div>
      </div>

      <div className="section-title">Harness 治理概览</div>
      <div className="card" style={{ padding: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, fontSize: 13 }}>
          <div><span style={{ color: "var(--ink-3)" }}>护栏触发</span><div style={{ fontSize: 20, fontWeight: 600 }}>{totals.guardrail_triggers || 0}</div></div>
          <div><span style={{ color: "var(--ink-3)" }}>权限拒绝</span><div style={{ fontSize: 20, fontWeight: 600 }}>{totals.permission_denials || 0}</div></div>
          <div><span style={{ color: "var(--ink-3)" }}>Hook 触发</span><div style={{ fontSize: 20, fontWeight: 600 }}>{totals.hook_fires || 0}</div></div>
          <div><span style={{ color: "var(--ink-3)" }}>循环检测</span><div style={{ fontSize: 20, fontWeight: 600 }}>{totals.loop_detections || 0}</div></div>
          <div><span style={{ color: "var(--ink-3)" }}>Fork 数</span><div style={{ fontSize: 20, fontWeight: 600 }}>{totals.fork_count || 0}</div></div>
          <div><span style={{ color: "var(--ink-3)" }}>峰值上下文</span><div style={{ fontSize: 20, fontWeight: 600 }}>{((avg.peak_context_usage_ratio || 0) * 100).toFixed(0)}%</div></div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify syntax**

```bash
node --check "E:/Agent program/PrismV3/frontend/apiClient.js"
```

- [ ] **Step 3: Commit**

```bash
git add frontend/Prism.html
git commit -m "feat(obs): ObsPage consumes real /harness/analytics API — zero mock data

Replaces 4 hardcoded stat-cards + 7 fake traces with live data:
- avg turn_count, tool error rate, compaction rate, cache hit ratio
- harness governance summary (guardrails, permissions, hooks, loops, forks)
- empty state when no runs exist

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Admin — implement 5 placeholder tabs with real data

**Files:**
- Modify: `frontend/admin.html` — replace Placeholder entries in PAGES map (L1640-1653)

This is the largest task. Each tab is a self-contained component consuming an existing backend API. All 5 tabs follow the same pattern: fetch on mount → loading state → render data → empty state.

- [ ] **Step 1: Implement GuardrailsPage component**

Add before the `PAGES` constant in admin.html:

```javascript
function GuardrailsPage() {
  const [config, setConfig] = useState(null);
  const [entropy, setEntropy] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      PrismAPI.harness.config().catch(() => null),
      PrismAPI.harness.entropyCheck().catch(() => null),
    ]).then(([cfg, ent]) => {
      setConfig(cfg); setEntropy(ent); setLoading(false);
    });
  }, []);

  if (loading) return <div className="page-head"><div className="page-title">护栏</div><div className="page-sub">加载中…</div></div>;

  const rules = config?.effective?.custom_guardrail_rules || [];
  const policies = config?.effective?.permission_policies || [];
  const alerts = entropy?.alerts || [];

  return (
    <div>
      <div className="page-head">
        <div className="page-title">护栏</div>
        <div className="page-sub">平台级护栏规则 + Entropy 信号</div>
      </div>

      <div className="section-title">护栏规则 ({rules.length})</div>
      {rules.length === 0
        ? <div className="panel" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>使用默认护栏规则（破坏性命令拦截、速率限制、PII 过滤）</div>
        : <div className="panel">{rules.map((r, i) => (
            <div key={i} className="list-row">
              <span style={{ fontWeight: 500 }}>{r.rule_id || r.name || `Rule ${i+1}`}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{r.description || r.action || '—'}</span>
            </div>
          ))}</div>
      }

      <div className="section-title" style={{ marginTop: 24 }}>权限策略 ({policies.length})</div>
      {policies.length === 0
        ? <div className="panel" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>使用默认权限策略</div>
        : <div className="panel">{policies.map((p, i) => (
            <div key={i} className="list-row">
              <span style={{ fontWeight: 500 }}>{p.tool_pattern || `Policy ${i+1}`}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{p.decision || '—'}</span>
            </div>
          ))}</div>
      }

      <div className="section-title" style={{ marginTop: 24 }}>Entropy 告警 ({alerts.length})</div>
      {alerts.length === 0
        ? <div className="panel" style={{ padding: 32, textAlign: "center", color: "var(--teal)" }}>所有信号正常 ✓</div>
        : <div className="panel">{alerts.map((a, i) => (
            <div key={i} className="list-row" style={{ borderLeft: "3px solid var(--red)" }}>
              <span style={{ fontWeight: 500, color: "var(--red)" }}>{a.signal}</span>
              <span style={{ fontSize: 13 }}>当前 {a.current_value?.toFixed?.(3) ?? a.current_value} · 阈值 {a.threshold?.toFixed?.(3) ?? a.threshold}</span>
            </div>
          ))}</div>
      }
    </div>
  );
}
```

- [ ] **Step 2: Implement SkillsAdminPage component**

```javascript
function SkillsAdminPage() {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    PrismAPI.skills.listInstalled()
      .then(data => { setSkills(Array.isArray(data) ? data : data?.skills || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const handleToggle = async (name, currentEnabled) => {
    await PrismAPI.skills.patch(name, { enabled: !currentEnabled });
    setSkills(prev => prev.map(s => s.name === name ? { ...s, enabled: !currentEnabled } : s));
  };

  const handleUninstall = async (name) => {
    if (!confirm(`卸载 ${name}？`)) return;
    await PrismAPI.skills.uninstall(name);
    setSkills(prev => prev.filter(s => s.name !== name));
  };

  if (loading) return <div className="page-head"><div className="page-title">Skills</div><div className="page-sub">加载中…</div></div>;

  return (
    <div>
      <div className="page-head">
        <div className="page-title">Skills 管理</div>
        <div className="page-sub">全局已安装 {skills.length} 个 Skill</div>
      </div>
      {skills.length === 0
        ? <div className="panel" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>暂无已安装的 Skill</div>
        : <div className="panel">{skills.map(s => (
            <div key={s.name || s.id} className="list-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 500 }}>{s.name}</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{s.description || s.source || '—'} · v{s.version || '?'}</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className={`btn sm ${s.enabled !== false ? '' : 'ghost'}`} onClick={() => handleToggle(s.name, s.enabled !== false)}>
                  {s.enabled !== false ? '已启用' : '已禁用'}
                </button>
                <button className="btn sm ghost" style={{ color: "var(--red)" }} onClick={() => handleUninstall(s.name)}>卸载</button>
              </div>
            </div>
          ))}</div>
      }
    </div>
  );
}
```

- [ ] **Step 3: Implement BillingPage component**

```javascript
function BillingPage() {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    PrismAPI.admin.getUsage()
      .then(d => { setUsage(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="page-head"><div className="page-title">账务</div><div className="page-sub">加载中…</div></div>;
  if (!usage) return <div className="page-head"><div className="page-title">账务</div><div className="page-sub" style={{ color: "var(--red)" }}>加载失败</div></div>;

  const total = usage.total_cost_usd ?? 0;
  const cacheSavings = usage.total_cache_savings_usd ?? 0;
  const providers = usage.per_provider || [];
  const trend = usage.daily_trend_30d || [];

  return (
    <div>
      <div className="page-head">
        <div className="page-title">账务</div>
        <div className="page-sub">全局 Provider 用量与花费</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 24 }}>
        <div className="stat-card"><div className="label">总花费</div><div className="val">${total.toFixed(2)}</div></div>
        <div className="stat-card"><div className="label">Cache 节省</div><div className="val" style={{ color: "var(--teal)" }}>${cacheSavings.toFixed(2)}</div></div>
        <div className="stat-card"><div className="label">总 Token</div><div className="val">{((usage.total_input_tokens || 0) + (usage.total_output_tokens || 0)).toLocaleString()}</div></div>
        <div className="stat-card"><div className="label">总 Runs</div><div className="val">{usage.total_runs || 0}</div></div>
      </div>

      <div className="section-title">Provider 分布</div>
      <div className="panel" style={{ padding: 20 }}>
        {providers.length === 0
          ? <div style={{ textAlign: "center", color: "var(--ink-3)" }}>暂无用量数据</div>
          : providers.map(p => {
              const pct = total > 0 ? (p.cost_usd / total * 100).toFixed(0) : 0;
              return (
                <div key={p.provider_name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0" }}>
                  <span style={{ width: 120, fontWeight: 500 }}>{p.provider_name}</span>
                  <div style={{ flex: 1, height: 8, background: "var(--bg)", borderRadius: 4 }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: "var(--teal)", borderRadius: 4 }}/>
                  </div>
                  <span style={{ width: 80, textAlign: "right", fontSize: 13, color: "var(--ink-3)" }}>${(p.cost_usd || 0).toFixed(2)} ({pct}%)</span>
                </div>
              );
            })
        }
      </div>

      {trend.length > 0 && (
        <>
          <div className="section-title" style={{ marginTop: 24 }}>30 天趋势</div>
          <div className="panel" style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 80 }}>
              {trend.map((d, i) => {
                const maxCost = Math.max(...trend.map(t => t.cost_usd || 0), 0.01);
                const h = ((d.cost_usd || 0) / maxCost * 100).toFixed(0);
                return <div key={i} style={{ flex: 1, height: `${h}%`, background: "var(--teal)", borderRadius: "2px 2px 0 0", minHeight: 2 }} title={`${d.date}: $${(d.cost_usd||0).toFixed(3)}`}/>;
              })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>
              <span>{trend[0]?.date || ''}</span>
              <span>{trend[trend.length-1]?.date || ''}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Implement InfraPage component**

```javascript
function InfraPage() {
  const [health, setHealth] = useState(null);
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      PrismAPI.healthDetailed().catch(() => null),
      PrismAPI.admin.getDashboard().catch(() => null),
    ]).then(([h, d]) => {
      setHealth(h); setDash(d); setLoading(false);
    });
  }, []);

  if (loading) return <div className="page-head"><div className="page-title">基础设施</div><div className="page-sub">加载中…</div></div>;

  const components = dash?.component_health || health?.checks || {};
  const statusColor = (s) => s === 'healthy' || s === true ? 'var(--teal)' : s === 'degraded' ? 'var(--amber)' : 'var(--red)';
  const statusLabel = (s) => s === 'healthy' || s === true ? '正常' : s === 'degraded' ? '降级' : typeof s === 'string' ? s : '异常';

  return (
    <div>
      <div className="page-head">
        <div className="page-title">基础设施</div>
        <div className="page-sub">组件健康状态 · 资源用量</div>
      </div>

      <div className="section-title">组件状态</div>
      <div className="panel">
        {Object.entries(components).map(([name, status]) => (
          <div key={name} className="list-row" style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontWeight: 500 }}>{name}</span>
            <span style={{ color: statusColor(status), fontWeight: 500 }}>{statusLabel(status)}</span>
          </div>
        ))}
        {Object.keys(components).length === 0 && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--ink-3)" }}>无健康数据</div>
        )}
      </div>

      {dash && (
        <>
          <div className="section-title" style={{ marginTop: 24 }}>运行概览</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
            <div className="stat-card"><div className="label">24h Runs</div><div className="val">{dash.runs_24h ?? 0}</div></div>
            <div className="stat-card"><div className="label">7d Runs</div><div className="val">{dash.runs_7d ?? 0}</div></div>
            <div className="stat-card"><div className="label">活跃会话</div><div className="val">{dash.active_sessions ?? 0}</div></div>
            <div className="stat-card"><div className="label">24h 活跃用户</div><div className="val">{dash.active_users_24h ?? 0}</div></div>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Implement ObservabilityAdminPage component**

```javascript
function ObservabilityAdminPage() {
  const [analytics, setAnalytics] = useState(null);
  const [entropy, setEntropy] = useState(null);
  const [calibrating, setCalibrating] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    Promise.all([
      PrismAPI.harness.analytics({ days: 7 }).catch(() => null),
      PrismAPI.harness.entropyCheck().catch(() => null),
    ]).then(([a, e]) => {
      setAnalytics(a); setEntropy(e); setLoading(false);
    });
  };

  useEffect(load, []);

  const handleCalibrate = async () => {
    setCalibrating(true);
    try {
      const result = await PrismAPI.harness.thresholdCalibrate();
      alert(`校准完成: ${result.suggestions?.length || 0} 个信号建议更新`);
    } catch (e) {
      alert('校准失败: ' + (e.message || e));
    }
    setCalibrating(false);
  };

  if (loading) return <div className="page-head"><div className="page-title">可观测</div><div className="page-sub">加载中…</div></div>;

  const totals = analytics?.totals || {};
  const cache = analytics?.cache_stats || {};
  const alerts = entropy?.alerts || [];

  return (
    <div>
      <div className="page-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div className="page-title">可观测性</div>
          <div className="page-sub">Harness 聚合指标 + Entropy 信号</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn sm" onClick={load}>刷新</button>
          <button className="btn sm ghost" onClick={handleCalibrate} disabled={calibrating}>
            {calibrating ? '校准中…' : '阈值校准'}
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 24 }}>
        <div className="stat-card"><div className="label">总工具调用</div><div className="val">{totals.tool_calls || 0}</div></div>
        <div className="stat-card"><div className="label">工具错误</div><div className="val">{totals.tool_errors || 0}</div></div>
        <div className="stat-card"><div className="label">护栏触发</div><div className="val">{totals.guardrail_triggers || 0}</div></div>
        <div className="stat-card"><div className="label">Cache 命中率</div><div className="val">{cache.hit_ratio != null ? (cache.hit_ratio * 100).toFixed(0) + '%' : 'N/A'}</div></div>
      </div>

      <div className="section-title">Entropy 信号 ({alerts.length} 告警)</div>
      {alerts.length === 0
        ? <div className="panel" style={{ padding: 32, textAlign: "center", color: "var(--teal)" }}>所有 8 个信号正常 ✓</div>
        : <div className="panel">{alerts.map((a, i) => (
            <div key={i} className="list-row" style={{ borderLeft: "3px solid var(--red)" }}>
              <div style={{ fontWeight: 500, color: "var(--red)" }}>{a.signal}</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>当前值: {typeof a.current_value === 'number' ? a.current_value.toFixed(4) : a.current_value} · 阈值: {typeof a.threshold === 'number' ? a.threshold.toFixed(4) : a.threshold}</div>
            </div>
          ))}</div>
      }
    </div>
  );
}
```

- [ ] **Step 6: Wire all 5 components into PAGES map**

Replace the placeholder entries in the `PAGES` constant (L1646-1653):

```javascript
// Replace these lines:
guardrails: { r: () => <Placeholder title="护栏编辑器" sub="写规则、绑 Skill、按租户分发。"/>, title: "护栏" },
plugins: { r: () => <Placeholder title="Skills 与插件审核" sub="私有 registry、待审核队列、签名密钥管理。"/>, title: "Skills" },
billing: { r: () => <Placeholder title="账务" sub="Provider 用量、月度花费、导出。"/>, title: "账务" },
infra: { r: () => <Placeholder title="基础设施" sub="Postgres、Redis、OTel、备份、子进程池。"/>, title: "基础设施" },
observability: { r: () => <Placeholder title="可观测性" sub="Trace 瓀布图在用户端的 Observability 页。"/>, title: "可观测" },
security: { r: () => <Placeholder title="安全" sub="API Key、IP 白名单、SSO、密钥轮换。"/>, title: "安全" },

// With:
guardrails: { r: () => <GuardrailsPage/>, title: "护栏" },
plugins: { r: () => <SkillsAdminPage/>, title: "Skills" },
billing: { r: () => <BillingPage/>, title: "账务" },
infra: { r: () => <InfraPage/>, title: "基础设施" },
observability: { r: () => <ObservabilityAdminPage/>, title: "可观测" },
security: { r: () => <Placeholder title="安全" sub="API Key 轮换、IP 白名单 — 需要后端扩展。"/>, title: "安全" },
```

Note: Security tab stays as Placeholder because it genuinely requires new backend endpoints (IP whitelist, key rotation) that don't exist yet. The placeholder text is updated to be honest about why.

- [ ] **Step 7: Delete the Placeholder component if no longer used**

Check if any PAGES entry still uses `<Placeholder>`. If security is the only one, keep the component. If none use it, delete it.

- [ ] **Step 8: Commit**

```bash
git add frontend/admin.html
git commit -m "feat(admin): implement 5 placeholder tabs with real API data

- GuardrailsPage: harness config + entropy signals
- SkillsAdminPage: list/enable/disable/uninstall installed skills
- BillingPage: global usage, provider distribution bar, 30d trend
- InfraPage: component health + run overview stats
- ObservabilityAdminPage: harness aggregates + entropy alerts + calibration

Security tab remains placeholder (requires new backend endpoints).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Entropy Detector scheduled task

**Files:**
- Modify: `backend/app/main.py` — add background scheduler in lifespan

- [ ] **Step 1: Read current lifespan code**

```bash
grep -n "lifespan\|async def\|yield" "E:/Agent program/PrismV3/backend/app/main.py" | head -30
```

- [ ] **Step 2: Add entropy scheduler to lifespan**

Add inside the lifespan context manager, after existing initialization, before `yield`:

```python
import asyncio
from app.services.entropy_detector import EntropyDetector
from app.services.harness_analytics import HarnessAnalytics
from app.core.database import SessionLocal

async def _entropy_scheduler():
    """Run entropy detection every hour (ADR-112)."""
    while True:
        await asyncio.sleep(3600)
        try:
            db = SessionLocal()
            try:
                analytics = HarnessAnalytics(db)
                detector = EntropyDetector(db, analytics)
                alerts = detector.detect(user_id=None)
                if alerts:
                    logger.warning("entropy.alerts_detected", count=len(alerts))
            finally:
                db.close()
        except Exception as e:
            logger.error("entropy.scheduler_error", error=str(e))

# Inside lifespan, after init, before yield:
entropy_task = asyncio.create_task(_entropy_scheduler())
```

After `yield`, cancel the task:

```python
entropy_task.cancel()
```

- [ ] **Step 3: Verify backend starts cleanly**

```bash
cd "E:/Agent program/PrismV3/backend"
python -c "from app.main import app; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(entropy): schedule hourly entropy detection in backend lifespan

ADR-112: EntropyDetector runs every 3600s, logs warnings when signals
exceed thresholds. Previously only available via manual POST /harness/entropy-check.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run full backend test suite**

```bash
cd "E:/Agent program/PrismV3/backend"
python -m pytest tests/ -q --ignore=tests/test_plugin_validate_dispatch.py
# Expected: all pass
```

- [ ] **Step 2: Run executor tests**

```bash
cd "E:/Agent program/PrismV3"
python -m pytest executor/tests/ -q
# Expected: all pass
```

- [ ] **Step 3: Frontend syntax check**

```bash
node --check "E:/Agent program/PrismV3/frontend/apiClient.js"
# Expected: clean
```

- [ ] **Step 4: Rebuild and restart Docker containers**

```bash
cd "E:/Agent program/PrismV3"
docker compose -p prismv3 build backend
docker compose -p prismv3 up -d --force-recreate backend
docker compose -p prismv3 restart nginx
```

- [ ] **Step 5: Verify health**

```bash
curl http://localhost:18888/health/ready
# Expected: {"checks": {"database": true, "redis": true, ...}}
```
