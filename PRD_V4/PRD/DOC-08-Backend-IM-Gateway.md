# Prism 棱镜 v2 — Backend IM Gateway (DOC-08)

> **文档编号**: DOC-08  
> **版本**: 3.1  
> **日期**: 2026-04-02  
> **性质**: 实现文档 — IM 网关：飞书/企业微信/Telegram 接入，消息路由，用户绑定  
> **前置依赖**: DOC-01 v3（Schema: im_bindings + im_channel_configs）, DOC-07（TaskService + SessionService）  
> **Phase**: 2（后端功能模块）  
> **Task 数**: 3  
> **审计关注点**:  
> - **与 Web 端同优先级设计**：IM 消息不是"降级入口"，走完全相同的 TaskService.submit() → RunLifecycle → Harness Runtime → Agent 链路。IM 和 Web 唯一的区别是入口格式化和结果回传渠道，中间全部共享  
> - **三平台共用消息路由和 session 管理抽象层**：不为每个 IM 平台写独立的完整链路，而是抽象出 `IMAdapter` 接口（接收/发送/绑定），三个平台实现该接口，消息路由和 session 查找/创建逻辑在 `IMGateway` 中统一处理

---

## 目录

1. [Task 8.1: IMAdapter 抽象层与消息路由](#task-81-imadapter-抽象层与消息路由)
2. [Task 8.2: 飞书 + 企业微信 + Telegram 适配器](#task-82-飞书--企业微信--telegram-适配器)
3. [Task 8.3: 用户绑定与配对流程](#task-83-用户绑定与配对流程)

---

## Task 8.1: IMAdapter 抽象层与消息路由

### Part A — 设计与解释

#### 问题陈述

Prism 的 IM 接入不是附属功能，而是与 Web 端并列的一级入口（DOC-00 §2.5）。三个 IM 平台（飞书/企业微信/Telegram）的接入协议各不相同（WebSocket / Webhook / Long Polling），但它们的核心行为完全一致：收到用户消息 → 找到 Prism 用户 → 提交任务 → 等结果 → 回传。

如果为每个平台写独立的完整链路，会产生大量重复代码。正确做法是抽象出 `IMAdapter` 接口和 `IMGateway` 路由层。

#### 架构

```
飞书 WebSocket ──→ FeishuAdapter.receive() ─┐
企微 Webhook ────→ WeComAdapter.receive()  ──┤
Telegram Polling ─→ TelegramAdapter.receive()┘
                                              │
                                              ▼
                                    IMGateway.route()
                                    ├─ 查找 im_binding → 获取 user_id
                                    ├─ 查找/创建 Session（im_channel + im_chat_id）
                                    ├─ TaskService.submit()  ← 与 Web 端完全相同
                                    └─ 注册结果回调 → adapter.send()
```

#### 验收标准

- `IMAdapter` 接口定义了 `receive()`、`send()`、`start()`、`stop()` 四个方法
- `IMGateway.route()` 能将标准化消息路由到 TaskService
- IM 消息走 TaskService.submit() 的完全相同链路（含排队、Harness 治理）
- 未绑定用户发消息时回复绑定引导
- Session 按 `(user_id, im_channel, im_chat_id)` 查找或创建

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 IM 网关抽象层。DOC-07 的 TaskService 已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

DOC-07 全部完成，TaskService.submit() 可用

## 要创建的文件

```
backend/app/
├── services/
│   ├── im_gateway.py          # IM 网关统一路由
│   └── im_adapter.py          # IMAdapter 抽象接口
└── schemas/
    └── im.py                  # IM 相关 Schema
```

## 实现规范

### 1. app/services/im_adapter.py

```python
"""
IM 适配器抽象接口

每个 IM 平台实现此接口。
IMGateway 通过此接口与具体平台解耦。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class IMIncomingMessage:
    """标准化的收到消息"""
    channel: str                     # "feishu" | "wecom" | "telegram"
    platform_user_id: str            # IM 平台的用户标识
    platform_chat_id: str            # IM 平台的会话标识
    text: str                        # 消息文本
    raw: dict                        # 原始消息体（调试用）

@dataclass
class IMOutgoingMessage:
    """标准化的发送消息"""
    channel: str
    platform_chat_id: str
    text: str
    reply_to_message_id: str | None = None  # 回复特定消息（如支持）

class IMAdapter(ABC):
    """IM 平台适配器抽象基类"""
    
    @property
    @abstractmethod
    def channel_name(self) -> str:
        """平台标识：'feishu' | 'wecom' | 'telegram'"""
        ...
    
    @abstractmethod
    async def start(self) -> None:
        """启动适配器（WebSocket 连接 / Long Polling 启动等）"""
        ...
    
    @abstractmethod
    async def stop(self) -> None:
        """停止适配器"""
        ...
    
    @abstractmethod
    async def send(self, message: IMOutgoingMessage) -> bool:
        """发送消息到 IM 平台。返回是否成功。"""
        ...
    
    def set_message_handler(self, handler) -> None:
        """设置消息处理回调。适配器收到消息后调用此 handler。"""
        self._message_handler = handler
```

### 2. app/services/im_gateway.py

```python
"""
IM 网关 — 统一消息路由

⚠️ 审计关注点：IM 消息走与 Web 端完全相同的 TaskService.submit() 链路。
不存在"IM 简化版"的处理路径。

职责：
1. 注册和管理所有 IM 适配器
2. 收到消息 → 查找绑定 → 查找/创建 Session → TaskService.submit()
3. Run 完成 → 通过对应适配器回传结果
"""

class IMGateway:
    def __init__(self, db_factory, task_service_factory, settings):
        self._db_factory = db_factory
        self._task_service_factory = task_service_factory
        self._settings = settings
        self._adapters: dict[str, IMAdapter] = {}
    
    def register_adapter(self, adapter: IMAdapter) -> None:
        """注册 IM 适配器"""
        adapter.set_message_handler(self._handle_message)
        self._adapters[adapter.channel_name] = adapter
    
    async def start_all(self) -> None:
        """启动所有已注册且已启用的适配器"""
        for channel, adapter in self._adapters.items():
            # 检查 im_channel_configs 中是否启用
            ...
            await adapter.start()
    
    async def stop_all(self) -> None:
        for adapter in self._adapters.values():
            await adapter.stop()
    
    async def _handle_message(self, msg: IMIncomingMessage) -> None:
        """
        统一消息处理。
        
        这是所有 IM 消息的唯一入口。
        """
        with self._db_factory() as db:
            # 1. 查找绑定
            binding = db.query(IMBinding).filter(
                IMBinding.channel == msg.channel,
                IMBinding.platform_user_id == msg.platform_user_id,
                IMBinding.paired_at.isnot(None),  # 已完成绑定
            ).first()
            
            if binding is None:
                # 未绑定 → 回复绑定引导
                await self._send_binding_guide(msg)
                return
            
            user_id = binding.user_id
            
            # 2. 查找/创建 Session
            session = self._find_or_create_session(db, user_id, msg.channel, msg.platform_chat_id)
            
            # 3. 提交任务（与 Web 端完全相同的链路）
            task_service = self._task_service_factory(db)
            result = task_service.submit(user_id, SubmitTaskRequest(
                session_id=session.id,
                prompt=msg.text,
            ))
            db.commit()
            
            # 4. 如果立即执行，启动子进程
            if result.accepted_type == "immediate" and result.run_id:
                _start_agent_subprocess(result.run_id)
            
            # 5. 回复确认
            if result.accepted_type == "queued_query":
                adapter = self._adapters[msg.channel]
                await adapter.send(IMOutgoingMessage(
                    channel=msg.channel,
                    platform_chat_id=msg.platform_chat_id,
                    text=f"✅ 消息已收到，当前排队第 {result.queue_position} 位",
                ))
    
    def _find_or_create_session(self, db, user_id: str, channel: str, chat_id: str):
        """
        按 (user_id, im_channel, im_chat_id) 查找 Session。
        不存在则创建。IM 会话的 Session 与 Web 会话独立。
        """
        session = db.query(SessionModel).filter(
            SessionModel.user_id == user_id,
            SessionModel.im_channel == channel,
            SessionModel.im_chat_id == chat_id,
        ).first()
        
        if session is None:
            session = SessionModel(
                user_id=user_id,
                im_channel=channel,
                im_chat_id=chat_id,
            )
            db.add(session)
            db.flush()
        
        return session
    
    async def _send_binding_guide(self, msg: IMIncomingMessage) -> None:
        """发送绑定引导消息"""
        adapter = self._adapters.get(msg.channel)
        if adapter:
            await adapter.send(IMOutgoingMessage(
                channel=msg.channel,
                platform_chat_id=msg.platform_chat_id,
                text="👋 你好！请先在 Prism Web 端生成配对码，然后回复配对码完成绑定。",
            ))
    
    async def send_run_result(self, session_id: str, text: str) -> None:
        """
        Run 完成后回传结果到 IM。

        由 CallbackService 在 run_complete 时调用。
        查找 session 的 im_channel + im_chat_id，通过对应适配器发送。
        """
        ...

> **send_run_result() 实现 (P1)**：Run 完成时，从 Run 结果中提取最终文本消息，格式化为 IM 消息格式（纯文本 + 可选 Markdown），调用对应 adapter.send() 发送到 IM 渠道。实现要点：
> 1. 从 `run.messages` 中提取最后一条 `role=assistant` 的文本内容
> 2. 如果文本超过 IM 平台消息长度限制（飞书 4000 字、企微 2048 字、Telegram 4096 字），截断并附加"完整结果请在 Web 端查看"
> 3. 如果 Run 状态为 `failed`，发送格式化的错误信息
> 4. 调用 `adapter.send(chat_id=session.im_chat_id, content=formatted_message)`
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/im_adapter.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/im_gateway.py

# 2. 路由逻辑测试（mock adapter）
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.services.im_adapter import IMAdapter, IMIncomingMessage, IMOutgoingMessage

class MockAdapter(IMAdapter):
    @property
    def channel_name(self): return 'test'
    async def start(self): pass
    async def stop(self): pass
    async def send(self, msg):
        print(f'Mock send: {msg.text[:50]}')
        return True

adapter = MockAdapter()
assert adapter.channel_name == 'test'
print('IMAdapter interface: PASS')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: IM Gateway abstraction layer + unified message routing"`
```

---

## Task 8.2: 飞书 + 企业微信 + Telegram 适配器

### Part A — 设计与解释

#### 问题陈述

三个 IM 平台的接入协议完全不同，但都实现 Task 8.1 定义的 `IMAdapter` 接口。

| 平台 | 接入方式 | 消息接收 | 消息发送 |
|------|---------|---------|---------|
| 飞书 | WebSocket 长连接 | ws message → 解析 JSON | POST 消息 API |
| 企业微信 | Webhook 回调 | POST /im/webhook/wecom → 解析 XML/JSON | POST 消息 API |
| Telegram | Bot API Long Polling | getUpdates 循环 | sendMessage API |

#### 文档置信度说明

三个平台的 API 文档链接：
- 飞书：https://open.feishu.cn/document
- 企业微信：https://developer.work.weixin.qq.com/document
- Telegram：https://core.telegram.org/bots/api

⚠️ 各平台 API 可能随时变更。实现时必须参考最新官方文档，不可基于本文档中的 API 细节推测。本文档只定义接口契约和集成架构，具体的 API 调用参数以官方文档为准。如果官方文档与本文档描述冲突，以官方文档为准并在 DECISIONS.md 中记录偏差。

#### 验收标准

- 三个适配器分别实现 IMAdapter 接口
- 飞书：WebSocket 连接、消息接收、消息回复
- 企业微信：Webhook 回调验证、消息解析、消息回复
- Telegram：Long Polling 启动、消息接收、消息回复
- 未启用的适配器 start() 时 graceful 跳过
- 平台 API 调用失败时不影响其他平台

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的三个 IM 平台适配器。Task 8.1 的 IMAdapter 接口和 IMGateway 已完成。

⚠️ 文档置信度原则：三个平台的具体 API 调用参数必须参考最新官方文档。实现前请先确认以下官方文档的当前内容：
- 飞书 Bot WebSocket：https://open.feishu.cn/document
- 企业微信自建应用：https://developer.work.weixin.qq.com/document
- Telegram Bot API：https://core.telegram.org/bots/api

如果无法访问官方文档或文档内容与预期不符，立即停止并告知我。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 8.1 已完成

## 要创建的文件

```
backend/app/
├── services/
│   ├── im_feishu.py           # 飞书适配器
│   ├── im_wecom.py            # 企业微信适配器
│   └── im_telegram.py         # Telegram 适配器
└── api/v1/
    └── im.py                  # IM Webhook 端点（企业微信回调）
```

## 实现规范

### 每个适配器的共同要求：

1. 实现 `IMAdapter` 接口的全部方法
2. 配置从 `im_channel_configs` 表读取（`config` JSONB 字段）
3. API 调用异常时 log error 但不抛异常（不影响其他平台）
4. 消息长度超过平台限制时自动截断并追加 "[消息已截断]"

### 飞书适配器（im_feishu.py）

- 使用 WebSocket 长连接接收消息
- 消息发送通过 REST API（需要 access_token，app_id + app_secret 获取）
- access_token 缓存并在过期前自动刷新

### 企业微信适配器（im_wecom.py）

- 消息接收通过 Webhook 回调（POST /im/webhook/wecom）
- 需要实现回调验证（URL 验证 + 消息解密）
- 消息发送通过 REST API（需要 corp_id + agent_id + secret 获取 access_token）

### Telegram 适配器（im_telegram.py）

- 消息接收通过 Long Polling（getUpdates，在后台线程中循环）
- 消息发送通过 sendMessage API
- 只需要 bot_token

### app/api/v1/im.py

```python
"""
IM API 端点

GET    /im/channels              — 已配置的 IM 渠道列表
PATCH  /im/channels/{channel}    — 更新渠道配置（admin only）
POST   /im/webhook/feishu        — 飞书事件回调（public，平台验证）
POST   /im/webhook/wecom         — 企业微信事件回调（public，平台验证）
"""

# Webhook 端点是 public 的（IM 平台直接调用），但需要平台级验证
# 飞书：验证 X-Lark-Signature
# 企业微信：验证 msg_signature
```

## 验证步骤

每个平台需要实际的平台应用配置才能完整测试。本 Task 验收重点是代码结构和接口实现，集成测试由部署环境确认。

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/im_feishu.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/im_wecom.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/im_telegram.py
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/api/v1/im.py

# 2. 接口实现验证
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.services.im_feishu import FeishuAdapter
from app.services.im_wecom import WeComAdapter
from app.services.im_telegram import TelegramAdapter
from app.services.im_adapter import IMAdapter

# 验证三个适配器都实现了 IMAdapter 接口
for cls in [FeishuAdapter, WeComAdapter, TelegramAdapter]:
    assert issubclass(cls, IMAdapter), f'{cls.__name__} does not implement IMAdapter'
    print(f'{cls.__name__}: implements IMAdapter ✓')

print('\nAll adapters: PASS')
"
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: Feishu + WeCom + Telegram IM adapters"`
```

---

## Task 8.3: 用户绑定与配对流程

### Part A — 设计与解释

#### 问题陈述

IM 用户需要将 IM 账号绑定到 Prism 账号才能使用。绑定流程通过配对码实现：用户在 Web 端生成配对码 → 在 IM 中发送配对码 → 系统完成绑定。

#### 配对流程

```
Web 端:
  POST /im/bindings/pair → 生成 6 位配对码（有效期 5 分钟）→ 显示给用户

IM 端:
  用户发送配对码 → IMGateway 识别为绑定请求
  → 查找 im_bindings 中 pairing_code 匹配的记录
  → 填入 platform_user_id + paired_at → 绑定完成
  → 回复 "绑定成功！现在可以直接发消息了"
```

> **配对码改进 (P1)**：
> 1. **碰撞重试**：配对码生成时检查是否已存在相同有效码，存在则重新生成（最多 3 次重试）
> 2. **触发方式**：改用前缀命令 `/pair 123456` 触发配对，避免 6 位纯数字在正常对话中误触发。配对码仍为 6 位数字，但必须通过 `/pair` 命令提交。

#### 验收标准

- Web 端可以生成配对码（6 位随机码，5 分钟过期）
- IM 端发送配对码后完成绑定
- 同一个 IM 用户不能绑定到多个 Prism 账号
- 已绑定的 IM 用户可以解除绑定
- 配对码过期后不可使用
- 配对码使用后不可重复使用

---

### Part B — Claude Code 执行 Prompt

```markdown
# 以下为 Claude Code 的 Prompt

## 上下文

你正在构建 Prism v2 的 IM 用户绑定功能。Task 8.1 和 8.2 已完成。

请先加载以下 Skill（如果找不到任何一个，立即停止并告知我）：
- using-superpowers

## 前置条件

Task 8.1 和 8.2 已完成

## 要创建/修改的文件

```
backend/app/
├── services/
│   └── im_binding_service.py  # 绑定业务逻辑
└── api/v1/
    └── im.py                  # 修改：新增 /bindings 端点
```

## 实现规范

### 1. app/services/im_binding_service.py

```python
"""
IM 用户绑定服务

配对码格式：6 位数字（如 "382947"），有效期 5 分钟。
"""

import secrets

class IMBindingService:
    PAIRING_CODE_LENGTH = 6
    PAIRING_CODE_TTL_MINUTES = 5
    
    def __init__(self, db: Session):
        self._db = db
    
    def generate_pairing_code(self, user_id: str, channel: str) -> str:
        """
        生成配对码。
        
        在 im_bindings 表创建记录：
        - user_id = 当前用户
        - channel = 指定平台
        - pairing_code = 6 位随机数字
        - paired_at = None（未完成绑定）
        - platform_user_id 暂时为空（IM 端绑定时填入）
        
        如果该用户已有未完成的配对记录 → 覆盖旧配对码
        """
        code = "".join([str(secrets.randbelow(10)) for _ in range(self.PAIRING_CODE_LENGTH)])
        ...
        return code
    
    def pair(self, channel: str, platform_user_id: str, code: str) -> bool:
        """
        完成配对。
        
        由 IMGateway 在收到疑似配对码的消息时调用。
        
        流程：
        1. 查找 im_bindings 中 channel + pairing_code 匹配的记录
        2. 校验未过期（created_at + TTL > now）
        3. 校验 paired_at is None（未使用）
        4. 校验 platform_user_id 未被其他用户绑定
        5. 填入 platform_user_id + display_name + paired_at
        6. 清除 pairing_code
        
        返回: 是否成功
        """
        ...
    
    def list_bindings(self, user_id: str) -> list["IMBinding"]:
        """列出当前用户的所有绑定"""
        ...
    
    def unbind(self, user_id: str, binding_id: str) -> None:
        """解除绑定（物理删除）"""
        ...
```

### 2. IMGateway 修改

在 `_handle_message` 中增加配对码识别：

```python
async def _handle_message(self, msg: IMIncomingMessage) -> None:
    # 检查是否是配对码（纯数字，6 位）
    if msg.text.strip().isdigit() and len(msg.text.strip()) == 6:
        success = IMBindingService(db).pair(
            channel=msg.channel,
            platform_user_id=msg.platform_user_id,
            code=msg.text.strip(),
        )
        if success:
            await adapter.send(IMOutgoingMessage(
                channel=msg.channel,
                platform_chat_id=msg.platform_chat_id,
                text="✅ 绑定成功！现在可以直接发消息了。",
            ))
        else:
            await adapter.send(IMOutgoingMessage(
                channel=msg.channel,
                platform_chat_id=msg.platform_chat_id,
                text="❌ 配对码无效或已过期，请在 Web 端重新生成。",
            ))
        return
    
    # 正常消息处理（已有逻辑）...
```

### 3. app/api/v1/im.py 补充端点

```python
# 新增绑定相关端点

@router.get("/bindings", response_model=ApiResponse[list[IMBindingResponse]])
def list_bindings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...

@router.post("/bindings/pair", response_model=ApiResponse[PairingCodeResponse])
def generate_pairing_code(
    channel: str,  # query param: "feishu" | "wecom" | "telegram"
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成配对码，返回码值和过期时间"""
    ...

@router.delete("/bindings/{binding_id}", status_code=204)
def unbind(binding_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ...
```

## 验证步骤

```bash
# 1. 编译检查
docker compose -f docker-compose.dev.yml exec backend python -m py_compile app/services/im_binding_service.py

# 2. 配对流程测试
TOKEN="..."

# 生成配对码
curl -s -X POST "http://localhost:8000/api/v1/im/bindings/pair?channel=telegram" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
# 期望：返回 6 位数字配对码 + 过期时间

# 列出绑定（应为空或包含刚创建的未完成绑定）
curl -s http://localhost:8000/api/v1/im/bindings -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

## 完成后

1. 更新 PROGRESS.md
2. 加载 Simplify skill 审查
3. 加载 PJR skill 验证
4. `git add -A && git commit -m "feat: IM user binding with pairing code flow"`
```

---

> **文档维护说明**：本文档的 3 个 Task 完成后，Prism v2 将拥有完整的 IM 接入能力：IMAdapter 抽象接口 + IMGateway 统一路由（与 Web 端共享 TaskService 链路）+ 飞书/企业微信/Telegram 三平台适配器 + 配对码用户绑定。IM 消息走与 Web 完全相同的 Harness → Agent 链路。  
> **最后更新**: 2026-04-02 | **下一步**: DOC-09 Backend MCP/Provider/Admin
