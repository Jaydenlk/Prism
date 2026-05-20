# IM Gateway 修复设计

> **日期**: 2026-05-16
> **目标**: 让飞书和企微 IM 功能在国内部署环境下正常工作
> **调研来源**: 飞书开放平台官方文档 + 企业微信开发者中心官方文档
> **优先级**: 飞书 > 企微 > Telegram（国内部署场景）

---

## 一、问题清单

### CRITICAL: 适配器未注册
- `backend/app/main.py` 行 191-254 的 lifespan 中，只注册了 Feishu/Slack/Discord
- **WeComAdapter 和 TelegramAdapter 从未被实例化**，导致：
  - `/webhook/wecom` 端点收到请求后找不到对应 adapter
  - Telegram long polling 从未启动

### HIGH: 企微缺 ENV 配置
- `backend/app/core/config.py` 无 WECOM_* 环境变量
- 当前只能通过 DB（im_channel_configs 表）配置，但首次部署时 DB 为空
- 需要：WECOM_CORP_ID、WECOM_TOKEN、WECOM_ENCODING_AES_KEY、WECOM_AGENT_ID、WECOM_SECRET

### HIGH: 企微签名 fail-open
- `im_wecom.py:224-225` 当 token/encoding_aes_key 为空时 `return True`
- 官方要求：SHA1(sort(token, timestamp, nonce, encrypt)) 必须验证
- 线上部署必须 fail-closed

### MEDIUM: 企微缺 is_configured()
- 其他 4 个 adapter 都有 `is_configured()` 方法
- WeCom 缺失导致 test_send 端点行为不一致

---

## 二、飞书现状（基本可用）

### 连接模式
- **WebSocket（推荐）**: SDK 自动鉴权，明文数据，无需解密验签
  - .env: `FEISHU_MODE=websocket`
  - 使用 `lark_oapi` SDK 建立长连接
  - 优势：无需公网 IP、5 分钟接入、开发阶段不需要内网穿透
  
- **Webhook**: 传统模式，需要公网 URL
  - 事件订阅：SHA256(timestamp + encrypt_key + body)
  - 卡片回调：SHA1(timestamp + nonce + verification_token + body)
  - AES-CBC-256 加密消息体

### 已有配置（.env）
```
FEISHU_APP_ID=cli_a7...
FEISHU_APP_SECRET=pHaIOI16...
FEISHU_ENCRYPT_KEY=...
FEISHU_VERIFICATION_TOKEN=...
```

### 需要验证
1. WebSocket 模式是否能正常建连
2. 消息接收 → Gateway → TaskService → 回复 是否完整跑通
3. Token 缓存（Redis + 内存双层）是否有竞态

---

## 三、企微修复方案

### 3.1 config.py 新增 ENV 变量
```python
# WeCom / 企业微信
WECOM_CORP_ID: str = ""
WECOM_TOKEN: str = ""
WECOM_ENCODING_AES_KEY: str = ""
WECOM_AGENT_ID: str = ""
WECOM_SECRET: str = ""
```

### 3.2 main.py 注册适配器
在 lifespan 的适配器注册段落中加入：
```python
# WeCom
if wecom_config or settings.WECOM_CORP_ID:
    from app.services.im_wecom import WeComAdapter
    wecom = WeComAdapter(config=wecom_config or {
        "corp_id": settings.WECOM_CORP_ID,
        "token": settings.WECOM_TOKEN,
        "encoding_aes_key": settings.WECOM_ENCODING_AES_KEY,
        "agent_id": settings.WECOM_AGENT_ID,
        "secret": settings.WECOM_SECRET,
    })
    gateway.register_adapter("wecom", wecom)
```

### 3.3 签名验证 fail-closed
```python
# im_wecom.py 修改
def _verify_signature(self, ...):
    if not self._token or not self._encoding_aes_key:
        logger.warning("wecom.signature_skip_no_credentials")
        return False  # fail-closed, not True
```

### 3.4 添加 is_configured()
```python
def is_configured(self) -> bool:
    return bool(self._corp_id and self._token and self._encoding_aes_key)
```

### 3.5 Webhook 流程（官方文档）

**GET 验证**:
1. 收到 msg_signature, timestamp, nonce, echostr 参数
2. SHA1(sort(token, timestamp, nonce, echostr)) == msg_signature
3. AES 解密 echostr 得到明文
4. 1 秒内返回明文（不带引号/BOM/换行）

**POST 消息**:
1. 验证 msg_signature
2. 解密 Encrypt 字段（AES-CBC-256）
3. 解析 XML：ToUserName, AgentID, MsgType, Content 等
4. 异步处理，立即返回空串或 "success"

---

## 四、Telegram 修复方案（次优先）

### 注册适配器
```python
# main.py
if telegram_config:
    from app.services.im_telegram import TelegramAdapter
    tg = TelegramAdapter(config=telegram_config)
    gateway.register_adapter("telegram", tg)
```

### 添加 is_configured() 和 ENV 变量
```python
# config.py
TELEGRAM_BOT_TOKEN: str = ""
```

---

## 五、实施顺序

1. **main.py 注册 WeComAdapter + TelegramAdapter**（10 分钟）
2. **config.py 新增 WECOM_*/TELEGRAM_* ENV**（5 分钟）
3. **im_wecom.py 签名 fail-closed + is_configured()**（10 分钟）
4. **.env.example 更新模板**（2 分钟）
5. **飞书 E2E 验证**：WebSocket 建连 → 发消息 → 收回复（需要真实飞书应用）
6. **企微 E2E 验证**：配置回调 URL → GET 验证 → POST 消息（需要企微管理后台）

---

## 六、测试约束

IM 功能的 E2E 测试需要真实的第三方应用配置：
- 飞书：需要飞书开放平台应用（用户已配置 APP_ID/SECRET）
- 企微：需要企业微信管理后台配置回调 URL
- Telegram：需要 BotFather 创建的 bot token

**本地测试方案**：
- 飞书 WebSocket 模式可以本地直接测（无需公网 IP）
- 企微/飞书 Webhook 模式需要 ngrok 或公网 IP
- 单元测试覆盖签名验证和加解密逻辑
