# Fix #3 — SkillsSettings 搜索结果"安装"死按钮接通

> Date: 2026-04-20
> Defect ID: #3 / 9 (admin/Prism dead-content audit 2026-04-20)
> Scope: 前端单文件改动(Prism.html SkillsSettingsTab),复用现有后端 install endpoint
> 工作量: ~0.3 session

---

## 0. Source of Truth(已 read 现有代码)

| 文件 | 关键发现 |
|---|---|
| `backend/app/api/v1/skills.py:144` `/skills/search` | response `SkillPackageResponse` 已含 `name / description / version / source(local|github) / source_url / author / tags / installed / installed_version` — **完整 install 字段已就绪** |
| `backend/app/api/v1/skills.py:243` `/skills/install` | 接受 `{skill_name, source, source_url, version, content_base64?, ...}`;`source="github"` + `source_url` 已可工作(SkillsPage GitHub tab 已使用此路径成功);`source="local"` 不带 content_base64 → fall-through 到 svc.install,只写 skill_installs 表(metadata 注册) |
| `frontend/Prism.html:1501` `SkillsPage.handleGithubInstall` | 用 `install({skill_name, source:"github", source_url, version})` 已工作 — search 结果可直接复用此 shape |
| `frontend/Prism.html:3139` `SkillsSettingsTab` | **死按钮**:`onClick={() => onToast({title:"暂不支持"})}` — 早期实现 search response 不全时的 stale safeguard |

## 1. Root Cause

死按钮 toast 是**过时残留**。Search response 后期补全了 `source_url + version + source` 但前端按钮 onClick 没同步更新 → 死代码累积。

## 2. Goal

按 SkillsSettingsTab 用户视角:**"我搜到一个 skill,我能点安装,跟 SkillsPage GitHub tab 同样链路"**。

## 3. Non-Goal(避免范围蔓延)

- **不改 backend**(0 endpoint 改动)
- **不改 search response shape**(已够)
- **不挖更深 bug**(GitHub source 是否真下载文件 vs 仅写 DB record — 这是 #10 follow-up,本 fix 只对齐 SkillsPage GitHub tab 同等行为)
- **不重构 SkillsSettingsTab**(只 wire 死按钮,UI 结构不动)

## 4. Architecture(单一职责)

```
[user 点搜索结果 "安装" 按钮]
        │
        ▼
handleInstallFromSearch(sk)  ← 新函数(SkillsSettingsTab 内)
        │
        ▼
PrismAPI.skills.install({
  skill_name: sk.name,
  source:     sk.source,        // "local" | "github"
  source_url: sk.source_url,
  version:    sk.version,
})
        │
        ▼
后端 /skills/install (既有,DB write)
        │
        ▼
loadInstalled() 刷新 → installed list 含新条
```

无新组件 / 无新后端 / 无新 schema。

## 5. 状态机(找茬完备)

每行 SkillResult 的"安装"按钮根据 `sk.installed` + `installing[name]` state 三态:

| 条件 | 显示 |
|---|---|
| `sk.installed === true` | `<span class="badge teal">已装</span>` (现有逻辑) |
| `installing[sk.name] === true` | `<button disabled>安装中…</button>` (新) |
| else | `<button class="primary" onClick={handleInstallFromSearch}>安装</button>` (旧 toast → 新真实 wire) |

## 6. Frontend 改动(精确范围)

**文件**: `frontend/Prism.html`(SkillsSettingsTab,line 3068-3171)

**state 加 1 个**(line 3074 之后):
```js
const [installingSearch, setInstallingSearch] = useState({}); // { [skill_name]: true }
```

**新函数**(在 `handleUninstall` 之前):
```js
async function handleInstallFromSearch(sk) {
  const name = sk.skill_name || sk.name;
  if (installingSearch[name]) return; // 防重
  setInstallingSearch(prev => ({ ...prev, [name]: true }));
  try {
    await PrismAPI.skills.install({
      skill_name: name,
      source: sk.source,
      source_url: sk.source_url,
      version: sk.version,
    });
    onToast({ id: Date.now(), kind: "success", title: "安装成功", body: name });
    await loadInstalled();
  } catch (err) {
    onToast({ id: Date.now(), kind: "danger", title: "安装失败", body: err.message || String(err) });
  }
  setInstallingSearch(prev => { const next = { ...prev }; delete next[name]; return next; });
}
```

**按钮 wire**(替换 line 3139 死 toast):
```jsx
{isInst ? <span className="badge teal">已装</span> : (
  <button
    data-testid={`skill-search-install-${name}`}
    className="btn sm primary"
    onClick={() => handleInstallFromSearch(sk)}
    disabled={!!installingSearch[name]}
    style={{ minHeight: 36 }}
  >{installingSearch[name] ? "安装中…" : "安装"}</button>
)}
```

## 7. Backend 改动:**0**

## 8. 测试策略(Playwright MCP / local Playwright,**找茬找错**)

### 桌面端(desktop-chromium)+ 移动端(mobile-safari)各跑

| # | 场景 | 找茬点 |
|---|---|---|
| 1 正常 | 搜 "demo" → 出结果 → 点安装 → toast success → Installed list 出现 | 输入框 placeholder / 搜索按钮 disabled 中文案 / 安装 toast 出现位置(右下) / Installed badge 颜色 |
| 2 已装边界 | mock search 返 `installed:true` → 显示"已装" badge,无安装按钮 | badge 文字一致性 / 颜色对比 / mobile 不溢出 |
| 3 并发防重 | 慢速 install + 连点 3 次 → 1 次请求触发,UI 显示"安装中…",disabled | disabled state visual feedback / 第 2-3 次点击是否完全无效 / cursor not-allowed |
| 4 失败边界 422 | mock install 返 422 detail "github source_url 必填" → danger toast "安装失败:..." | toast 颜色(danger) / 5s 自动消失 / 文字不截断 |
| 5 失败边界 500 | mock install 返 500 → danger toast | err.message 是否传到 body |
| 6 install 后状态变更 | install 成功 → 重新搜同关键词 → 该项 badge 变"已装",无安装按钮 | search 是否真重新调用 / installed 状态同步 |
| 7 移动 viewport | 搜索结果卡片单列 / 安装按钮高 ≥36px(`minHeight: 36`)/ 文字不截断 | iPhone 14 Pro 390×844 |
| 8 桌面键盘 a11y | Tab 键到安装按钮 → 焦点环可见 → Enter 触发安装 | focus ring visible / 焦点顺序逻辑 |

**总:8 场景 × 2 viewport = 16 测试**

### 后端测试

**0 改动 → 0 新增 unit tests**。复用 SkillsPage GitHub install 已有 e2e 覆盖。

## 9. 验收 checklist(用户自主)

- [ ] /Prism.html 登录 → 设置 → 技能 tab → 搜 "code" → 看到搜索结果区
- [ ] 任选未装项 → 点"安装" → 30s 内成功 toast(灰底变绿)
- [ ] 立刻点"已安装"区域 → 看到新装 skill 带版本号
- [ ] 同关键词再搜 → 该项 badge 变"已装"
- [ ] mobile viewport(F12 设备工具栏 iPhone 14 Pro) → 同样流程,按钮可点 ≥44pt(36 + padding)
- [ ] 异常路径:断网点安装 → 红色 toast "安装失败"含网络 error message

## 10. Files

| File | Action | LOC |
|---|---|---|
| `frontend/Prism.html` SkillsSettingsTab L3068-3171 | modify | +25 -2 |
| `e2e/tests/skills-settings-search-install.spec.ts` | new | +280 (8 × 2) |

总:1 modify + 1 new。

## 11. 反打补丁验证

✅ 删除死 toast(根因移除,不是加 if 绕过)
✅ 用现有 install endpoint(单一职责守住,无新 backend 接口)
✅ 不改 search response shape(已够,无 over-engineering)
✅ install state 用 dict 不用全局 boolean(防多 skill 互锁)
✅ 复用 SkillsPage GitHub install 完全相同的 install payload(消费已知工作的链路)

---

*End of spec — 写于 2026-04-20,~600 字。*
