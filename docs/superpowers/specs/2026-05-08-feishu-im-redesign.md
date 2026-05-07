# 飞书 IM 真实对接 — 设计文档

> **日期**: 2026-05-08
> **触发**: 用户反馈"飞书的 IM 模块和飞书机器人没关系"
> **文档置信度**: 已通过 exa 搜索官方文档 + WebFetch 验证 Python SDK 用法 + 发送消息 API

---

## 0. 调研结论（基于飞书官方文档）

### 飞书机器人两种事件接收方式

| 方式 | 优势 | 要求 |
|---|---|---|
| **长连接（WebSocket）** | 无需公网 IP、SDK 自动鉴权、5 分钟接入 | `lark_oapi` SDK、仅企业自建应用 |
| **Webhook（HTTP POST）** | 传统方式 | 公网 IP、手动签名验证 + AES 解密 |

**决策：同时支持两种模式**，长连接为默认（自托管场景通常无公网 IP），Webhook 为 fallback。

### 核心 API

- **发送消息**: `POST /open-apis/im/v1/messages?receive_id_type=chat_id`
  - 需要 `tenant_access_token`（应用身份）
  - 支持 text / post / interactive(卡片) 等消息类型
  - 限频: 5 QPS/用户, 5 QPS/群

- **接收消息事件**: `im.message.receive_v1`
  - 权限: `im:message.p2p_msg:readonly` 或 `im:message.group_at_msg:readonly`
  - 事件数据含: sender.open_id, message.chat_id, message.content, message.message_type

- **获取 tenant_access_token**: `POST /open-apis/auth/v3/tenant_access_token/internal`
  - 参数: app_id + app_secret
  - 有效期 2 小时，需缓存和自动续期

### Python SDK 用法（`lark_oapi`）

```python
import lark_oapi as lark

# 长连接模式
event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(on_message) \
    .build()

cli = lark.ws.Client(APP_ID, APP_SECRET, event_handler=event_handler)
cli.start()  # 阻塞，建议放在 asyncio.to_thread

# 发送消息
client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()
request = lark.im.v1.CreateMessageRequest.builder() \
    .receive_id_type("chat_id") \
    .request_body(lark.im.v1.CreateMessageRequestBody.builder()
        .receive_id(chat_id)
        .msg_type("text")
        .content('{"text":"hello"}')
        .build()) \
    .build()
response = client.im.v1.message.create(request)
```

---

## 1. 现状问题

`backend/app/services/im_feishu.py`（440+ 行）：
- ✅ 手写了签名验证 + AES-CBC 解密 + challenge 响应
- ❌ 没有用 `lark_oapi` 官方 SDK
- ❌ 没有发送消息能力（只有被动接收）
- ❌ 没有长连接模式
- ❌ 没有 `tenant_access_token` 管理

---

## 2. 设计方案

### 2.1 依赖

- 添加 `lark_oapi>=2.0.0` 到 `requirements.txt`（官方 Python SDK）
- 添加 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 到 `.env`

### 2.2 FeishuAdapter 重写

**保留**现有 Webhook 路由（`/im/webhook/feishu`）作为 fallback。
**新增**：
1. `FeishuClient`：封装 `lark_oapi.Client`，管理 token 刷新和消息发送
2. `FeishuWSListener`：长连接事件监听，作为 Backend lifespan 的 background task
3. `send()` 方法：调用发送消息 API，支持 text/interactive 消息类型

### 2.3 消息流

```
飞书用户发消息
  ↓
[长连接] lark.ws.Client 接收 im.message.receive_v1
  OR
[Webhook] POST /im/webhook/feishu → 签名验证 → 解密
  ↓
FeishuAdapter.receive() → 标准化为 IMMessage
  ↓
IMGateway.route() → 查 im_binding → TaskService.submit()
  ↓
Agent 处理 → run_complete 回调
  ↓
FeishuAdapter.send(chat_id, content) → lark.im.v1.message.create
  ↓
飞书用户收到回复
```

### 2.4 环境变量

```env
FEISHU_APP_ID=cli_xxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxx
FEISHU_MODE=websocket  # 或 webhook
FEISHU_ENCRYPT_KEY=    # webhook 模式才需要
FEISHU_VERIFICATION_TOKEN=  # webhook 模式才需要
```

### 2.5 前端 IM 设置页

- 显示飞书连接状态（长连接 online/offline）
- 配对码生成和绑定流程
- 测试发送按钮

---

## 3. 成功标准

- [ ] `lark_oapi` SDK 集成，长连接模式能建立 WebSocket 连接
- [ ] 能接收飞书单聊/群聊消息并路由到 Prism Agent
- [ ] Agent 回复能通过飞书 API 发回给用户
- [ ] 配对码绑定流程：用户发配对码 → 绑定 Prism 账户 → 后续消息自动路由
- [ ] 前端 IM 设置页显示连接状态
- [ ] 单元测试覆盖消息收发 + 绑定逻辑
- [ ] E2E: 前端 IM 配置页可操作（配对码生成、解绑等）

---

## 4. 前置条件（需要用户操作）

1. 在飞书开发者后台创建企业自建应用
2. 开启机器人能力
3. 申请权限：`im:message.p2p_msg:readonly` + `im:message:send_as_bot`
4. 配置事件订阅：`im.message.receive_v1`
5. 提供 App ID + App Secret 配到 `.env`
