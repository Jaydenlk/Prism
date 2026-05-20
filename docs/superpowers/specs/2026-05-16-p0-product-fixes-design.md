# P0 产品体验修复设计

> **日期**: 2026-05-16
> **目标**: 修复 4 项"用户会离开"的产品问题，从"能用"到"好用"
> **对标**: Manus / Poco 商业级标准

---

## Fix 1: Session 刷新 + Auth 加固

### 问题
- `secure=True` cookie + HTTP-only nginx = refresh token 不发送 → 用户每 15 分钟被踢
- `is_active` 未检查 → 禁用用户仍可无限续期
- logout 不撤销 token → 点退出仍能访问
- `/auth/providers` 返回明文 admin 密码

### 改动

**`backend/app/api/v1/auth.py`**:
- `set_refresh_cookie()`: `secure` 改为 `settings.PRISM_ENV == "production"`
- `get_auth_config()`: 删除 `dev_default_admin` 字段

**`backend/app/core/dependencies.py`**:
- `get_current_user()`: 查到用户后检查 `user.is_active`，False → 401
- 同时检查 token jti 是否在 Redis 黑名单中

**`backend/app/services/auth_service.py`**:
- `refresh()`: 同样检查 `is_active`
- `logout()`: 解析 access_token 的 jti，`SETEX blacklist:{jti} {remaining_ttl} 1`

### 验证
- 开发环境登录 → refresh 成功（cookie 被发送）
- 禁用用户 → 401
- logout 后旧 token → 401

---

## Fix 2: 首屏加载提速

### 问题
React development.js (~3x 大) + Babel standalone (运行时编译 4800 行 JSX) → 5-10 秒白屏

### 改动

**`frontend/Prism.html`** 和 **`frontend/admin.html`**:
```
- https://unpkg.com/react@18.3.1/umd/react.development.js
+ https://unpkg.com/react@18.3.1/umd/react.production.min.js

- https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js
+ https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js
```

Babel standalone 保留（完整替代是 DOC-10 Vite 迁移范畴）。

### 验证
- 页面加载时间 < 3 秒
- Console 无 React dev warnings
- 所有功能不受影响

---

## Fix 3: 状态栏真实数据

### 问题
`Prism.html:4816-4822` 硬编码 "provider: anthropic, 模型: auto-v2, 缓存: 72%"

### 改动

**`frontend/Prism.html`** StatusBar 组件:
- 从当前 session 最近一次 run 的数据读取 provider/model
- cache hit rate 从 `/admin/stats/dashboard` 读取（如果有）
- 无数据时显示 "—" 而非假数据
- 有 run 正在执行时实时更新

### 验证
- 新建会话 → 状态栏显示 "—"
- 发送消息后 → 状态栏显示真实 provider + model
- 数值与 API 返回一致

---

## Fix 4: 代码高亮

### 问题
AI 返回的代码块无语法高亮，纯白文本

### 改动

**`frontend/Prism.html`**:
- 引入 highlight.js 暗色主题 CSS（github-dark 或 atom-one-dark）
- 在 `marked` 配置中设置 `highlight` 回调:
  ```js
  marked.setOptions({
    highlight: function(code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return hljs.highlightAuto(code).value;
    }
  });
  ```
- 对已渲染的消息执行 `hljs.highlightAll()` 确保历史消息也高亮

### 验证
- 发送 "写一个 Python hello world" → 代码块有语法着色
- 多语言测试（Python/JS/SQL）→ 正确识别语言
- 历史消息代码也高亮

---

## 范围约束

- 不改架构（Vite 迁移是 DOC-10）
- 不加新功能（onboarding/file upload 是 P1）
- 4 项改动互相独立，可并行
- 改完即测，Playwright 验证
