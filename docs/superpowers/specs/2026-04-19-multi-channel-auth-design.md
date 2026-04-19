# Prism v2 — Multi-Channel Auth Design

> **Status**: approved
> **Date**: 2026-04-19
> **Author**: Opus 4.7 + user 确认
> **Scope**: 在现有 email+password+invite 基础上，追加多通道登录 / 注册 + 忘记密码 + Google OAuth。SMS 短信验证暂缓（保留接入点）。

---

## 1. 目标

| 登录方式（并存） | 注册方式 |
|---|---|
| 邮箱 + 密码（现有） | 邮箱 + 密码 + 邀请码（现有） |
| 邮箱 Magic Link | 手机 + 密码 + 邀请码（**本期**；**不做 SMS 验证**） |
| 邮箱 OTP 6 位码 | Google OAuth 首次登录 → 可配置是否要邀请码 |
| 手机 + 密码（无 SMS） | |
| Google OAuth | |
| （未来）手机 OTP | |

补充：忘记密码（邮件重置链接）、已登录用户可在设置页绑定/解绑 Google + 手机 + 额外邮箱。

---

## 2. 架构

### 2.1 新组件

| 组件 | 职责 | 位置 |
|---|---|---|
| `AuthChallengeService` | 统一发放/验证一次性 token（magic link / OTP / password reset / 未来 SMS OTP） | `backend/app/services/auth_challenge_service.py` |
| `EmailService` | 封装 SMTP 发邮件；未配置 SMTP 时降级到 structlog INFO 输出邮件内容（dev 友好） | `backend/app/services/email_service.py` |
| `GoogleOAuthService` | Authorize URL 构造、code → token 交换、id_token 解析 | `backend/app/services/google_oauth_service.py` |
| `AuthConfigService` | 管理 auth 全局开关（邀请制是否对 OAuth 生效，etc.） | `backend/app/services/auth_config_service.py` |

### 2.2 Challenge token 模型（Redis）

所有一次性凭证统一用 `AuthChallengeService`：

```
key = auth:challenge:{type}:{challenge_id}
value = json {
  "identifier": "user@example.com" | "+8613800138000",
  "user_id": "<uuid or null>",
  "code": "123456" | null,   # OTP 时填，magic link 时 null
  "extra": { ... },          # 可选业务数据
}
TTL = 15 分钟
```

一次性使用：验证通过后 `DEL key`。

Challenge type 枚举：`magic_link_email` / `otp_email` / `password_reset_email` / `otp_sms`（未来）。

### 2.3 DB schema 变更（migration 006）

```sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20) UNIQUE NULL;
ALTER TABLE users ADD COLUMN phone_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN google_id VARCHAR(255) UNIQUE NULL;
ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE;  -- magic link 成功登录时置 true

CREATE TABLE auth_config (
    key VARCHAR(100) PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL
);
-- bootstrap rows:
INSERT INTO auth_config (key, value_json) VALUES
  ('allow_oauth_signup_without_invite', 'false'),
  ('allow_phone_registration',           'true'),
  ('require_email_verification',         'false');
```

`users.password_hash` 字段 **仍保留 NOT NULL**，Google-only 用户注册时填一个无意义随机值（永远验不过）避免 schema 破坏。

### 2.4 新 API 端点

```
POST /auth/email-magic/request     { email } → 202（若邮箱已注册发送登录链接；未注册时返 202 也不泄漏）
POST /auth/email-magic/verify      { challenge_id, token } → TokenResponse

POST /auth/email-otp/request       { email } → 202
POST /auth/email-otp/verify        { email, code } → TokenResponse

POST /auth/forgot-password         { email } → 202
POST /auth/reset-password          { challenge_id, token, new_password } → { message }

POST /auth/phone-register          { phone, password, invite_code } → TokenResponse
POST /auth/phone-login             { phone, password } → TokenResponse

GET  /auth/google/authorize        → 302 redirect 到 Google OAuth consent
GET  /auth/google/callback         → 302 redirect 回前端（带 tmp token or error）
POST /auth/google/complete         { tmp_token, invite_code? } → TokenResponse（invite 为必填取决于 AuthConfig）

GET  /admin/auth-config            → 全部 key/value
PATCH /admin/auth-config           { key, value_json } → 更新单条
```

### 2.5 Google OAuth 流程

```
1. 前端点击 "用 Google 登录" → 跳 /auth/google/authorize?next=<front_url>
2. Backend 构造 Google consent URL（client_id / redirect_uri / scope=email profile / state=csrf）
3. Google 回调 /auth/google/callback?code=...&state=...
4. Backend 校验 state → exchange code → 拿到 id_token + email + google_id
5. 查 users:
   - 存在 google_id 匹配 → 直接登录（set cookie + return access token）
   - 存在 email 匹配 → 合并账号：users.google_id = <id>、email_verified=true，登录
   - 都不匹配（新用户）:
     * 如 auth_config.allow_oauth_signup_without_invite = true → 自动创建 user（role=user），登录
     * 否则 → 生成 tmp_token (Redis SETEX 10min 存 {google_id, email, name})
             → 前端引导填邀请码 → POST /auth/google/complete
6. 登录成功 → 写 audit_log + set refresh cookie + 返回 access token
```

### 2.6 SMTP 集成

- 复用已有 `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` (DOC-12 Task 12.8)
- 未配置时 `EmailService.send()` 退化为 `logger.info("email.dev_log", to=..., subject=..., body=...)` — dev/docker logs 里能直接看到 magic link/OTP，免配置
- 生产环境启动时如果 `SMTP_HOST` 为空则 `logger.warning("auth.email_dev_mode")`

### 2.7 Google OAuth 配置

新增 env：
```
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/api/v1/auth/google/callback
```

未配置时：
- `GET /auth/google/authorize` 返 503 "Google OAuth 未配置"
- 前端 LoginScreen 检测 `GET /auth/providers` 返回 `{ google: false, ... }` → Google 按钮隐藏

### 2.8 前端

**LoginScreen**（Prism.html）改造：
- 顶部 Tab：邮箱登录 / 手机登录
- 邮箱登录 Tab 下：
  - 默认"邮箱+密码"双字段
  - 下方"或使用 Magic Link / 6 位验证码"链接切换
- 手机登录 Tab 下："手机+密码"（简单直接）
- 底部：
  - "用 Google 登录"按钮（仅当 `/auth/providers.google=true`）
  - "忘记密码" 链接（进入 /auth/forgot-password 流程，弹独立小页）
  - "还没账号？" 链接 → 切注册
- 注册界面：邮箱/手机两个 Tab + 邀请码字段

**admin.html** 新增 "Auth Config" 小面板：
- 列表显示 auth_config 所有 key/value + 当前值
- 每行 toggle / 编辑
- 第一个开关：`allow_oauth_signup_without_invite`（对应本期决策 C）

---

## 3. 数据流举例

### 3.1 邮箱 Magic Link 登录

```
user@example.com → POST /auth/email-magic/request
→ Backend: 查 users by email
  - 有：create_challenge(type=magic_link_email, identifier=email, user_id=<id>)
        → token = secrets.token_urlsafe(32)
        → Redis SETEX auth:challenge:magic_link_email:{token} json(...) 900s
        → email.send(to, subject="登录 Prism", body=f"点此登录: {FRONT_URL}/auth/magic?token={token}")
  - 无：do nothing（不返回用户枚举 hint）
→ 前端显示 "已发送,请查收邮箱"
→ 用户点邮件链接 → 前端 /auth/magic?token=... → 自动 POST /auth/email-magic/verify { token }
→ Backend: GETDEL challenge → 拿到 user_id → issue tokens → set cookie → return access
→ 前端拿到 token 跳主界面
```

### 3.2 Phone 注册 + 登录

```
注册：POST /auth/phone-register { phone: "+8613800138000", password: "xxx", invite_code: "PRISM-..." }
     → validate invite → hash password → INSERT users(phone=...) → return tokens
登录：POST /auth/phone-login { phone: "+86...", password: "xxx" }
     → 同 email-login 只是查字段换成 phone
```

### 3.3 Google OAuth 新用户（邀请制开启）

```
1. 前端 → GET /auth/google/authorize → 302 到 Google
2. 用户授权 → Google → GET /auth/google/callback?code=...
3. Backend 换 id_token → email=new@gmail.com google_id=xyz
4. users 里没有 → config.allow_oauth_signup_without_invite=false
5. Redis SETEX auth:oauth_pending:{tmp_token} json{google_id, email, name} 600s
6. 302 到前端 /auth/complete-signup?tmp_token=xxx
7. 前端引导用户填邀请码 → POST /auth/google/complete { tmp_token, invite_code }
8. Backend: validate invite → create user + google_id → issue tokens
```

---

## 4. 错误处理

- `/auth/email-magic/request`：始终返 202（不论邮箱是否注册，避免 user enumeration）
- Invite code 无效 / 过期 / 用尽 → 400 + 具体原因
- Magic link token 已用 / 过期 → 401 "链接已失效，请重新请求"
- Google callback state mismatch → 400 "CSRF 校验失败"
- SMTP 失败（未配置时不当失败，降级 log）

---

## 5. 测试策略

单元测试：
- `AuthChallengeService.create/verify/expire/reuse-blocked`
- `EmailService.send` 配置/无配置两路径
- `GoogleOAuthService` 构造 URL / 解析 id_token

集成测试（用 httpx + fakeredis）：
- email-magic 完整 happy path
- OTP wrong code 3 次锁定
- Phone register 流程
- Google OAuth 3 场景（已有 google_id / 邮箱合并 / 全新 + invite gate）

---

## 6. 实施拆分

**Task A — 后端核心**（先跑通）
- Migration 006（users 扩列 + auth_config 表）
- AuthChallengeService + EmailService
- 8 个 /auth 新端点（magic/OTP/forgot/reset/phone-register/phone-login）
- Admin /admin/auth-config + /auth/providers（公开，让前端探测启用哪些登录方式）

**Task B — Google OAuth**
- GoogleOAuthService（authlib / google-auth）
- 3 个 Google 相关端点（authorize / callback / complete）
- 账号合并逻辑 + invite gate 判定

**Task C — 前端 LoginScreen 改造**
- Prism.html：Tab 布局 + magic link / OTP 小流程 + 手机 Tab + Google 按钮 + 忘记密码
- admin.html：Auth Config 面板 + OAuth 开关

**Task D — E2E + 文档**
- 文档更新（API 手册 §1 auth 章节）
- docker logs 观察 magic link email 示例

---

## 7. 非目标

- **SMS 发送**：短信 SDK 接入留给后续（占位 schema 已支持）
- **MFA / 2FA**：本期不做
- **账号绑定 UI**：最小版在设置页显示已有绑定 + 解绑，新绑 Google/手机留后续
- **第三方 OAuth 除 Google 外**（Github / WeChat / 微博）：预留扩展点，本期不实现
