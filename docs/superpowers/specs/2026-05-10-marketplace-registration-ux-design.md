# Marketplace 注册 UX 改善设计

> 日期: 2026-05-10
> 优先级: P2（用户反馈第二优先）

---

## 业务需求

用户想注册新的 marketplace 来源（如 gstake），但当前 UI 入口不直观，用户不知道该输入什么 URL。需要预置常用 marketplace 一键添加。

### 期望链路

```
用户打开 Marketplace tab → 看到推荐 marketplace 列表 → 一键添加 → 自动同步目录 → 看到插件数 → 可浏览安装
```

### 也支持

```
用户输入自定义 URL（owner/repo 或 .json 链接）→ 添加 → 同步 → 使用
```

---

## 改动范围

### 1. 后端：预置 marketplace 列表

**文件:** `backend/app/api/v1/marketplaces.py`

新增端点 `GET /api/v1/marketplaces/presets`，返回预置 marketplace 列表，标记已注册状态。

预置列表硬编码在端点中：

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
```

响应中每条增加 `registered: bool` 字段，通过查已注册列表匹配 url。

### 2. 前端：推荐 Marketplace 区域

**文件:** `frontend/Prism.html`

Marketplace tab 顶部新增"推荐来源"区域：
- 加载时调用 `GET /presets` 获取预置列表
- 每条显示：名称 + 描述 + "添加"按钮
- 已注册的显示"已添加"（灰色禁用态）
- 点击"添加"→ 调用 `create({ url, name })` → 自动同步 → 刷新列表

### 3. 前端：URL 输入框改善

- placeholder 改为 `owner/repo 或 marketplace.json 链接`
- 输入框下方加一行格式提示：`支持 GitHub owner/repo、.git 链接、或 .json 直链`

---

## 不涉及

- 安装流程改善（P4）
- Plugin Builder v2（P3）
- 搜索相关改动（P1 已完成）
