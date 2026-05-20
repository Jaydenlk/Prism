# P0 产品体验修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 4 项"用户会离开"的产品问题，从"能用"到"好用"

**Architecture:** 4 项独立修复，互不依赖，可并行。后端改 3 个文件，前端改 2 个文件。

**Tech Stack:** Python/FastAPI (后端), Vanilla HTML+React JSX (前端), Redis (token 黑名单)

---

### Task 1: Session 刷新 + Auth 加固

**Files:**
- Modify: `backend/app/api/v1/auth.py:91-101` (cookie secure)
- Modify: `backend/app/api/v1/auth.py:212-223` (logout token 撤销)
- Modify: `backend/app/api/v1/auth.py:396-413` (删除 dev_default_admin)
- Modify: `backend/app/core/dependencies.py:86-118` (is_active 检查)
- Modify: `backend/app/services/auth_service.py:205-212` (refresh is_active 检查)

- [ ] **Step 1: Cookie secure 跟随环境**

`backend/app/api/v1/auth.py:97` — 将 `secure=True` 改为根据环境决定：

```python
def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh_token HttpOnly cookie to *response* (ADR-052)."""
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.PRISM_ENV == "production",
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=_REFRESH_COOKIE_PATH,
    )
```

- [ ] **Step 2: get_current_user 加 is_active + token 黑名单检查**

`backend/app/core/dependencies.py:86-118` — 在 user 查询后加检查：

```python
def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> "User":
    from app.models.user import User

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
        jti: str | None = payload.get("jti")
    except HTTPException:
        raise
    except Exception:
        raise credentials_exc

    # Token 黑名单检查 (logout 撤销)
    if jti:
        from app.core.database import redis_client
        if redis_client and redis_client.get(f"blacklist:{jti}"):
            raise credentials_exc

    user: User | None = db.get(User, user_id)
    if user is None:
        raise credentials_exc

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )

    return user
```

- [ ] **Step 3: refresh 加 is_active 检查**

`backend/app/services/auth_service.py:205-212` — user 查询后加：

```python
        user = UserService(self._db).get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer exists",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is disabled",
            )

        return create_access_token(user.id)
```

- [ ] **Step 4: logout 撤销 token**

`backend/app/api/v1/auth.py:212-223` — 加 Redis 黑名单：

```python
@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    _user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[dict]:
    """Log out: delete cookie + blacklist current access token."""
    response.delete_cookie(key=_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)

    # 黑名单当前 access token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            payload = decode_token(auth_header[7:])
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                ttl = max(1, int(exp - __import__("time").time()))
                from app.core.database import redis_client
                if redis_client:
                    redis_client.setex(f"blacklist:{jti}", ttl, "1")
        except Exception:
            pass  # token 已无效也无所谓，logout 本身不应失败

    return ApiResponse(data={"message": "logged out"})
```

- [ ] **Step 5: 确认 access token 含 jti**

检查 `backend/app/core/security.py` 中 `create_access_token` 是否在 payload 中包含 `jti` 字段。如果没有，加上：

```python
import uuid

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_ACCESS_TOKEN_EXPIRE_SECONDS)
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)
```

- [ ] **Step 6: 删除 dev_default_admin**

`backend/app/api/v1/auth.py:396-413` — 删除泄露明文密码的逻辑：

```python
    return ApiResponse(
        data=AuthProvidersResponse(
            email_password=True,
            email_magic=True,
            email_otp=True,
            phone_password=phone_enabled,
            google=google_enabled,
        )
    )
```

同时从 `backend/app/schemas/auth.py` 中：
- `AuthProvidersResponse` 删除 `dev_default_admin` 字段
- 删除 `DevDefaultAdmin` schema

- [ ] **Step 7: 验证**

```bash
# 登录获取 token
curl -s -X POST http://localhost:8080/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@prism.dev","password":"PrismAdmin!2026"}'
# 预期: 200 + access_token + refresh cookie

# 确认 /auth/providers 不再泄露密码
curl -s http://localhost:8080/api/v1/auth/providers | python -m json.tool
# 预期: 无 dev_default_admin 字段

# logout 后旧 token 应失效
# 1. 保存 access_token
# 2. POST /auth/logout
# 3. 用旧 token GET /auth/me
# 预期: 401
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/v1/auth.py backend/app/core/dependencies.py backend/app/services/auth_service.py backend/app/core/security.py backend/app/schemas/auth.py
git commit -m "fix(auth): secure cookie follows env, logout revokes token, enforce is_active"
```

---

### Task 2: 首屏加载提速

**Files:**
- Modify: `frontend/Prism.html:24-26`
- Modify: `frontend/admin.html:329-331`

- [ ] **Step 1: Prism.html 换 production React**

`frontend/Prism.html:24-25` — 替换 CDN URL：

```html
<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js" crossorigin="anonymous"></script>
```

删除 SRI integrity 属性（production 的 hash 不同）。

- [ ] **Step 2: admin.html 换 production React**

`frontend/admin.html:329-330` — 同样替换：

```html
<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js" crossorigin="anonymous"></script>
```

- [ ] **Step 3: 验证**

用 Playwright 加载 http://localhost:8080：
- Console 无 React development mode warnings
- 页面功能不受影响（登录、对话、导航）

- [ ] **Step 4: Commit**

```bash
git add frontend/Prism.html frontend/admin.html
git commit -m "perf(frontend): switch to React production builds"
```

---

### Task 3: 状态栏真实数据

**Files:**
- Modify: `frontend/Prism.html:4816-4822`

- [ ] **Step 1: 替换硬编码为动态数据**

`frontend/Prism.html:4815-4823` — 将硬编码的状态栏替换为从 session/run 数据中读取：

```jsx
          {page !== "chat" && (
            <div className="statusbar">
              {(() => {
                const lastRun = runs && runs.length > 0 ? runs[runs.length - 1] : null;
                const prov = lastRun?.provider_id || currentProvider || "—";
                const model = lastRun?.model || "—";
                return <>
                  <div className="kv"><span>provider</span> <b>{prov}</b></div>
                  <div className="kv"><span>模型</span> <b>{model}</b></div>
                </>;
              })()}
              <div style={{ flex: 1 }}/>
              <div className="kv"><span>harness</span> <b style={{ color: "var(--teal)" }}>● active</b></div>
            </div>
          )}
```

删除虚假的 "缓存: 72%" — 如果没有真实的 cache hit rate API，不显示比显示假数据好。

- [ ] **Step 2: 同步清理 ObsPage 假数据**

`frontend/Prism.html:4018` — 将硬编码的 "412 每月 runs, 72% 缓存命中, 18k 每天审计事件" 改为从 API 读取或显示 "—"。

- [ ] **Step 3: 验证**

Playwright 检查：
- 新会话状态栏显示 "—"（无数据时）
- 发送消息后，状态栏显示真实 provider + model
- 无假数据残留

- [ ] **Step 4: Commit**

```bash
git add frontend/Prism.html
git commit -m "fix(frontend): replace hardcoded statusbar with live data"
```

---

### Task 4: 代码高亮暗色主题

**Files:**
- Modify: `frontend/Prism.html:8`

- [ ] **Step 1: 换暗色主题 CSS**

`frontend/Prism.html:8` — 从亮色 `github.min.css` 换为暗色 `github-dark.min.css`：

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/styles/github-dark.min.css">
```

highlight.js JS 和 marked.setOptions 配置已经正确（lines 28-36），不需要改。

- [ ] **Step 2: 验证**

Playwright 发送消息 "写一个 Python 快速排序"，检查：
- 代码块有语法着色（关键字、字符串、注释不同颜色）
- 暗色背景与整体 UI 协调
- 多语言（Python/JS/SQL）正确高亮

- [ ] **Step 3: Commit**

```bash
git add frontend/Prism.html
git commit -m "fix(frontend): switch highlight.js to dark theme for code blocks"
```

---

## 执行顺序

4 项独立，推荐并行。如果串行：Task 4 → Task 2 → Task 3 → Task 1（从简到复杂）。
