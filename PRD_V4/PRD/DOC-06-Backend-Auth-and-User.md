# Prism 棱镜 v2 — Backend Auth & User (DOC-06)

> **文档编号**: DOC-06  
> **版本**: 3.1  
> **日期**: 2026-04-02  
> **性质**: 实现文档 — 用户认证、注册、邀请码管理的完整后端链路（DB → Service → API）  
> **前置依赖**: DOC-01 v3（Schema: users + invite_codes）, DOC-02 v3 Task 2.1（项目骨架 + ORM 模型已就绪）  
> **Phase**: 2（后端功能模块）  
> **Task 数**: 2  
> **审计关注点**:  
> - `ENCRYPTION_KEY` 必须与 `JWT_SECRET` 分离。JWT_SECRET 用于 JWT 签名（HMAC），ENCRYPTION_KEY 用于 Provider API Key 的 AES-256 加密。两者职责不同、轮换周期不同、泄露影响不同，共用会导致：轮换 JWT_SECRET 时所有已加密的 API Key 失效，或反过来不敢轮换 JWT_SECRET

---

## 目录

1. [Task 6.1: 认证体系（注册 / 登录 / JWT / 刷新）](#task-61-认证体系)
2. [Task 6.2: 用户管理与邀请码](#task-62-用户管理与邀请码)

---

## Task 6.1: 认证体系

### Part A — 设计与解释

#### 问题陈述

Prism 是自托管产品，注册入口通过邀请码控制。认证采用 JWT access token（短期）+ refresh token（长期、HttpOnly cookie）双 token 模式。DOC-02 Task 2.1 已经在 `app/core/security.py` 中实现了 JWT 工具函数骨架，本 Task 补完完整的认证链路：注册、登录、刷新、登出、获取当前用户。

#### 设计决策

- **ADR-025**: `ENCRYPTION_KEY` 独立于 `JWT_SECRET`
  - `JWT_SECRET`：用于 JWT 签名（HMAC-SHA256），轮换时只影响已签发的 token（用户重新登录即可）
  - `ENCRYPTION_KEY`：用于 AES-256-GCM 加密 Provider API Key，轮换时需要重新加密所有已存储的 key（高成本操作）
  - 两者必须是不同的随机值，不可从一个派生另一个
  - `ENCRYPTION_KEY` 在 `.env` 中配置，`config.py` 中声明

- **ADR-026**: Refresh token 存储在 HttpOnly cookie 中，不存储在 DB
  - Refresh token 本身是 JWT（含 user_id + exp），签名验证即可确认有效性
  - 登出通过前端删除 cookie + 可选的 token blacklist（Phase 1 不实现 blacklist，接受"登出后 refresh token 在 exp 前仍有效"的 trade-off）

#### Harness 层交互

认证模块不直接与 Harness Runtime 交互（Harness 运行在 CLI 子进程中，认证运行在 Backend 进程中）。但认证产生的 `user_id` 会传递到 Run 配置中，Harness 的数据隔离护栏（铁律 4）依赖 `user_id` 做 WHERE 过滤。

#### 验收标准

- 注册需要有效邀请码，邀请码用完后不可重复使用
- 登录返回 access_token + 设置 refresh_token cookie
- access_token 过期后可通过 refresh_token 刷新
- 所有受保护端点在无 token / token 过期 / token 无效时返回 401
- 密码使用 bcrypt（cost factor 12）存储
- 首次启动时自动创建 admin 用户（从 ADMIN_EMAIL + ADMIN_PASSWORD 环境变量）

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的认证体系。DOC-02 Task 2.1 已完成项目骨架，`app/core/security.py` 中有 JWT 工具函数骨架，`app/models/user.py` 和 `app/models/audit.py` 已有 ORM 定义。本 Task 实现完整的注册/登录/刷新/登出链路。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

1. DOC-02 Task 2.1 完成，14 张表已迁移
2. `app/core/security.py` 已有 hash_password / verify_password / create_access_token / create_refresh_token / decode_token 骨架

## 要创建/修改的文件

```
backend/app/
├── core/
│   ├── config.py              # 修改：新增 ENCRYPTION_KEY 配置项
│   └── security.py            # 修改：补完实现 + 新增 encrypt_value / decrypt_value
├── schemas/
│   └── auth.py                # 认证请求/响应 Schema
├── services/
│   ├── auth_service.py        # 认证业务逻辑
│   └── user_service.py        # 用户查询/创建
└── api/v1/
    └── auth.py                # 认证 API 端点
```

## 实现规范

### 1. app/core/config.py 修改

新增配置项：
```python
ENCRYPTION_KEY: str            # AES-256 加密 Provider API Key 的密钥（64 hex chars = 32 bytes）
```

在 `.env.example` 中同步新增：
```bash
ENCRYPTION_KEY=<random-64-hex-chars>    # 用于加密 Provider API Key，必须与 JWT_SECRET 不同
```

### 2. app/core/security.py 修改

补完已有骨架的实现，新增加密函数：

```python
"""
安全工具模块

JWT 签名：使用 JWT_SECRET（HMAC-SHA256）
数据加密：使用 ENCRYPTION_KEY（AES-256-GCM）

⚠️ 这两个 key 必须独立，不可相同或从一个派生另一个（ADR-025）
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# === JWT 函数（已有骨架，补完实现）===

def hash_password(password: str) -> str:
    """bcrypt hash，cost factor 12"""
    ...

def verify_password(plain: str, hashed: str) -> bool:
    ...

def create_access_token(user_id: str, secret: str, expire_minutes: int = 15) -> str:
    """
    PyJWT 签发 access token。
    payload: {"sub": user_id, "type": "access", "exp": now + expire_minutes, "iat": now}
    """
    ...

def create_refresh_token(user_id: str, secret: str, expire_days: int = 7) -> str:
    """
    PyJWT 签发 refresh token。
    payload: {"sub": user_id, "type": "refresh", "exp": now + expire_days, "iat": now}
    """
    ...

def decode_token(token: str, secret: str) -> dict:
    """
    验证并解码 JWT。
    失败时抛出 jose.ExpiredSignatureError 或 jose.JWTError。
    """
    ...

# === 数据加密函数（新增）===

def encrypt_value(plaintext: str, encryption_key: str) -> str:
    """
    AES-256-GCM 加密。
    
    encryption_key: 64 hex chars (32 bytes)
    返回: base64 编码的 nonce+ciphertext 字符串
    """
    key = bytes.fromhex(encryption_key)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    import base64
    return base64.b64encode(nonce + ciphertext).decode()

def decrypt_value(encrypted: str, encryption_key: str) -> str:
    """
    AES-256-GCM 解密。
    """
    key = bytes.fromhex(encryption_key)
    import base64
    data = base64.b64decode(encrypted)
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

在 `requirements.txt` 中新增 `cryptography>=42.0.0`（如果尚未存在）。

### 3. app/schemas/auth.py

```python
"""认证请求/响应 Schema"""

class RegisterRequest(BaseModel):
    email: str                    # 邮箱格式校验
    username: str                 # 3-50 字符
    password: str                 # 最少 8 字符
    invite_code: str              # 邀请码

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int               # 秒

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    avatar_url: str | None
    last_login_at: datetime | None
    created_at: datetime

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
```

### 4. app/services/auth_service.py

```python
"""
认证业务逻辑

职责：
- 注册（校验邀请码 → 创建用户 → 消耗邀请码 → 签发 token）
- 登录（校验密码 → 签发 token → 更新 last_login_at）
- 刷新（验证 refresh token → 签发新 access token）
- 初始化 admin（首次启动时创建）
"""

class AuthService:
    def __init__(self, db: Session, settings):
        self._db = db
        self._settings = settings
    
    def register(self, data: RegisterRequest) -> tuple[User, str, str]:
        """
        注册新用户。
        
        返回: (user, access_token, refresh_token)
        
        流程：
        1. 校验邮箱格式和唯一性
        2. 校验用户名唯一性
        3. 校验邀请码有效性（存在 + 未过期 + used_count < max_uses）
        4. 创建用户（密码 bcrypt hash）
        5. 邀请码 used_count += 1
        6. 签发 access_token + refresh_token
        7. 写审计日志（action: "user.register"）
        """
        ...
    
    def login(self, data: LoginRequest) -> tuple[User, str, str]:
        """
        登录。
        
        返回: (user, access_token, refresh_token)
        
        流程：
        1. 按 email 查找用户
        2. 验证密码
        3. 更新 last_login_at
        4. 签发 token
        5. 写审计日志（action: "user.login"）
        
        失败时抛出 HTTPException(401)，错误消息统一为 "邮箱或密码错误"（不区分"用户不存在"和"密码错误"）
        """
        ...
    
    def refresh(self, refresh_token: str) -> str:
        """
        刷新 access token。
        
        返回: 新的 access_token
        
        流程：
        1. decode_token 验证 refresh_token 签名和过期
        2. 校验 token type == "refresh"
        3. 校验 user 仍存在
        4. 签发新 access_token
        """
        ...
    
    def ensure_admin(self) -> None:
        """
        首次启动时创建 admin 用户。
        
        如果 ADMIN_EMAIL 对应的用户已存在 → 跳过
        如果不存在 → 创建（role='admin'，不需要邀请码）
        
        在 app/main.py 的 lifespan 中调用。
        """
        ...
```

### 5. app/services/user_service.py

```python
"""
用户查询服务

职责：
- 按 ID 查询用户
- 按 email 查询用户
- 更新用户信息（头像等）
"""

class UserService:
    def __init__(self, db: Session):
        self._db = db
    
    def get_by_id(self, user_id: str) -> User | None:
        ...
    
    def get_by_email(self, email: str) -> User | None:
        ...
    
    def update(self, user_id: str, **kwargs) -> User:
        ...
```

### 6. app/api/v1/auth.py

按 DOC-01 v3 §6.1 的路由表实现全部 5 个端点：

```python
"""
认证 API 端点

POST /auth/register  — 注册（需邀请码）[public]
POST /auth/login     — 登录 [public]
POST /auth/refresh   — 刷新 token [cookie]
POST /auth/logout    — 登出 [bearer]
GET  /auth/me        — 当前用户信息 [bearer]
"""

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=ApiResponse[TokenResponse])
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """
    注册新用户。
    
    成功：返回 access_token，设置 refresh_token HttpOnly cookie。
    失败：邀请码无效 → 400，邮箱已存在 → 409
    """
    ...

@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    登录。
    
    成功：返回 access_token，设置 refresh_token HttpOnly cookie。
    Cookie 设置：
    - key: "refresh_token"
    - httponly: True
    - secure: True（生产环境）
    - samesite: "lax"
    - max_age: 7 * 24 * 3600
    - path: "/api/v1/auth"（限制 cookie 发送范围）
    """
    ...

@router.post("/refresh", response_model=ApiResponse[RefreshResponse])
def refresh(request: Request, db: Session = Depends(get_db)):
    """
    刷新 access token。
    
    从 cookie 中读取 refresh_token。
    cookie 不存在或无效 → 401
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")
    ...

@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    """
    登出。
    
    删除 refresh_token cookie。
    Phase 1 不实现 token blacklist。
    """
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    return ApiResponse(data={"message": "logged out"})

@router.get("/me", response_model=ApiResponse[UserResponse])
def me(user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return ApiResponse(data=UserResponse.model_validate(user))
```

### 7. app/core/dependencies.py 修改

补完 `get_current_user` 的完整实现：

```python
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    从 JWT 解析 user_id，查询 DB 返回 User。
    
    token 无效/过期 → 401
    用户不存在 → 401
    """
    try:
        payload = decode_token(token, settings.JWT_SECRET)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user = UserService(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user
```

### 8. app/main.py 修改

在 lifespan 中添加 admin 初始化：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    with SessionLocal() as db:
        AuthService(db, settings).ensure_admin()
        db.commit()
    yield
    # 关闭
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/core/security.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/auth.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/auth_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/user_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/auth.py

# 2. 加密函数测试
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.core.security import encrypt_value, decrypt_value
import os

key = os.urandom(32).hex()  # 64 hex chars
plaintext = 'sk-test-api-key-12345'
encrypted = encrypt_value(plaintext, key)
decrypted = decrypt_value(encrypted, key)
assert decrypted == plaintext, f'Decrypt mismatch: {decrypted}'
assert encrypted != plaintext, 'Encryption did not transform'
print(f'Encrypt/Decrypt: PASS (encrypted length: {len(encrypted)})')

# 验证不同 key 无法解密
wrong_key = os.urandom(32).hex()
try:
    decrypt_value(encrypted, wrong_key)
    assert False, 'Should have failed with wrong key'
except Exception:
    print('Wrong key rejected: PASS')
"

# 3. Admin 自动创建
docker compose -f docker-compose.dev.yml restart backend
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.core.database import SessionLocal
from app.models.user import User
from app.core.config import get_settings

settings = get_settings()
with SessionLocal() as db:
    admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
    assert admin is not None, 'Admin not created'
    assert admin.role == 'admin'
    print(f'Admin created: {admin.email} / {admin.role}')
"

# 4. API 端到端测试
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
echo "Access token: $TOKEN"

# 获取当前用户
curl -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN" | python -m json.tool
# 期望：返回 admin 用户信息

# 无 token → 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/auth/me
# 期望：401

# 错误密码 → 401
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"wrong"}'
# 期望：401

# 5. Refresh token cookie 验证
curl -s -c cookies.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
grep refresh_token cookies.txt
# 期望：cookie 存在，httponly 标记

curl -s -b cookies.txt -X POST http://localhost:8000/api/v1/auth/refresh | python -m json.tool
# 期望：返回新的 access_token
rm cookies.txt
```

## 完成后

1. 更新 PROGRESS.md
2. 更新 DECISIONS.md：记录 ADR-025（ENCRYPTION_KEY 与 JWT_SECRET 分离）、ADR-026（Refresh token in HttpOnly cookie, no DB storage）
3. 更新 `.env.example`：新增 `ENCRYPTION_KEY`
4. **修改 DOC-02 Task 2.3 的 ProviderService**：将 `encrypt/decrypt` 调用从 JWT_SECRET 派生改为使用 `settings.ENCRYPTION_KEY`
5. 加载 Simplify skill 审查
6. 加载 PJR skill 验证
7. `git add -A && git commit -m "feat: JWT auth + registration with invite codes + ENCRYPTION_KEY separation"`
```

---

## Task 6.2: 用户管理与邀请码

### Part A — 设计与解释

#### 问题陈述

Admin 需要能管理用户（查看列表、修改角色）和邀请码（生成、查看、撤销）。普通用户需要通过邀请码注册。这些功能需要完整的 Admin API。

#### 验收标准

- Admin 可以生成邀请码（指定 max_uses 和 expires_at）
- Admin 可以查看所有邀请码及其使用状态
- Admin 可以撤销邀请码
- Admin 可以查看用户列表
- Admin 可以修改用户角色（admin ↔ user）
- 普通用户调用 Admin API → 403
- 邀请码过期后不可使用
- 邀请码用完（used_count >= max_uses）后不可使用

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的用户管理和邀请码功能。Task 6.1 的认证体系已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 6.1 已完成，登录/注册/JWT 刷新链路可用

## 要创建的文件

```
backend/app/
├── schemas/
│   ├── user.py                # 用户管理 Schema
│   └── invite.py              # 邀请码 Schema
├── services/
│   └── invite_service.py      # 邀请码业务逻辑
└── api/v1/
    └── admin.py               # Admin API 端点
```

## 实现规范

### 1. app/schemas/invite.py

```python
class CreateInviteCodeRequest(BaseModel):
    max_uses: int = 1               # 最大使用次数，默认 1
    expires_at: datetime | None = None  # 过期时间，None = 永不过期

class InviteCodeResponse(BaseModel):
    id: str
    code: str                       # 明文显示（PRISM-XXXXXXXX 格式）
    created_by: str                 # 创建者 user_id
    max_uses: int
    used_count: int
    expires_at: datetime | None
    is_valid: bool                  # 计算字段：未过期 AND used_count < max_uses
    created_at: datetime
```

### 2. app/schemas/user.py

```python
class UserListResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    last_login_at: datetime | None
    created_at: datetime

class UpdateUserRoleRequest(BaseModel):
    role: Literal["admin", "user"]
```

### 3. app/services/invite_service.py

```python
"""
邀请码业务逻辑

邀请码格式：前缀 "PRISM-" + 8 位大写字母数字（如 "PRISM-A3B7C9D2"）。
"""

import secrets
import string

class InviteService:
    def __init__(self, db: Session):
        self._db = db
    
    def generate_code(self) -> str:
        """生成 8 位随机码，前缀 PRISM-"""
        chars = string.ascii_uppercase + string.digits
        code = "".join(secrets.choice(chars) for _ in range(8))
        return f"PRISM-{code}"
    
    def create(self, created_by: str, data: CreateInviteCodeRequest) -> InviteCode:
        """创建邀请码"""
        code = self.generate_code()
        while self._db.query(InviteCode).filter(InviteCode.code == code).first():
            code = self.generate_code()
        invite = InviteCode(
            code=code,
            created_by=created_by,
            max_uses=data.max_uses,
            expires_at=data.expires_at,
        )
        self._db.add(invite)
        self._db.flush()
        return invite
    
    def validate(self, code: str) -> InviteCode:
        """
        校验邀请码有效性。无效时抛出 HTTPException(400)。
        
        检查：存在 + 未过期 + 未用完
        """
        ...
    
    def consume(self, invite: InviteCode) -> None:
        """消耗一次使用次数"""
        invite.used_count += 1
        self._db.flush()
    
    def list_all(self) -> list[InviteCode]:
        return self._db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    
    def revoke(self, invite_id: str) -> None:
        """撤销：将 max_uses 设为 used_count"""
        ...
```

### 4. app/api/v1/admin.py

按 DOC-01 v3 §6.9 的路由表实现全部 7 个端点：

```python
"""
Admin API 端点 — 所有端点需要 admin 角色

GET    /admin/users              — 用户列表
PATCH  /admin/users/{id}         — 更新用户角色
POST   /admin/invite-codes       — 生成邀请码
GET    /admin/invite-codes       — 邀请码列表
DELETE /admin/invite-codes/{id}  — 撤销邀请码
GET    /admin/usage              — 全局用量统计
GET    /admin/audit-logs         — 审计日志查询
"""

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

@router.get("/users", response_model=ApiResponse[list[UserListResponse]])
def list_users(db: Session = Depends(get_db)):
    ...

@router.patch("/users/{user_id}", response_model=ApiResponse[UserListResponse])
def update_user_role(user_id: str, data: UpdateUserRoleRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    更新用户角色。
    不能修改自己的角色（防止 admin 把自己降级后无人管理）。
    """
    ...

@router.post("/invite-codes", response_model=ApiResponse[InviteCodeResponse])
def create_invite_code(data: CreateInviteCodeRequest, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ...

@router.get("/invite-codes", response_model=ApiResponse[list[InviteCodeResponse]])
def list_invite_codes(db: Session = Depends(get_db)):
    ...

@router.delete("/invite-codes/{invite_id}")
def revoke_invite_code(invite_id: str, db: Session = Depends(get_db)):
    ...

@router.get("/usage", response_model=ApiResponse[dict])
def get_usage(db: Session = Depends(get_db)):
    """
    全局用量统计。
    
    从 runs 表聚合：
    - 总 runs 数、总 input_tokens / output_tokens、总 cost_usd
    - 按 Provider 分组的用量
    - 按日/周/月的趋势（最近 30 天）
    """
    ...

@router.get("/audit-logs", response_model=ApiResponse[PagedResponse[dict]])
def get_audit_logs(
    action: str | None = None,     # 前缀筛选，如 "harness." 筛选所有 Harness 事件
    user_id: str | None = None,
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
):
    """审计日志查询。支持 action 前缀 LIKE 筛选。"""
    ...
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/invite.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/schemas/user.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/invite_service.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/admin.py

# 2. 端到端测试
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# 生成邀请码
INVITE=$(curl -s -X POST http://localhost:8000/api/v1/admin/invite-codes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_uses": 2}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['code'])")
echo "Invite code: $INVITE"

# 邀请码列表
curl -s http://localhost:8000/api/v1/admin/invite-codes -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 使用邀请码注册（第 1 次）
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test@example.com\",\"username\":\"testuser\",\"password\":\"testpass123\",\"invite_code\":\"$INVITE\"}"

# 使用邀请码注册（第 2 次，max_uses=2）
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test2@example.com\",\"username\":\"testuser2\",\"password\":\"testpass123\",\"invite_code\":\"$INVITE\"}"

# 第 3 次 → 400（已用完）
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"test3@example.com\",\"username\":\"testuser3\",\"password\":\"testpass123\",\"invite_code\":\"$INVITE\"}"
# 期望：400

# 用户列表（3 个用户）
curl -s http://localhost:8000/api/v1/admin/users -H "Authorization: Bearer $TOKEN" | python -m json.tool

# 普通用户 → 403
USER_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/admin/users -H "Authorization: Bearer $USER_TOKEN"
# 期望：403

# 审计日志
curl -s "http://localhost:8000/api/v1/admin/audit-logs?action=user.&page=1&per_page=10" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: user management + invite codes + admin API + usage stats"`
```

---

> **文档维护说明**：本文档的 2 个 Task 完成后，Prism v2 将拥有完整的认证和用户管理能力：JWT 双 token 认证 + bcrypt 密码存储 + AES-256-GCM 数据加密（ENCRYPTION_KEY 独立于 JWT_SECRET）+ 邀请码注册控制 + Admin 用户/邀请码/用量/审计管理。这是 DOC-07（Session/Run/Task）和 DOC-09（MCP/Provider/Admin）的前置依赖。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-07 Backend Session/Run/Task
