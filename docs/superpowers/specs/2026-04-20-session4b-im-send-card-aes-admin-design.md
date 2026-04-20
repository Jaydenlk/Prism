# Session 4b Design: IM send_card 三端 + AES credential + Admin 编辑 UI

**Date**: 2026-04-20
**Branch planned**: `redesign/im-sendcard-aes` off `develop`
**DOC assignment**: DOC-IM2b (续 DOC-IM2 的 ADR-088 偏离点清零)
**Parent ADR**: ADR-088 (IM Interactive Cards + Multi-Channel) — 补完偏离点 #2、I4 credential migration、#4 Admin UI

---

## 1. Source of truth

- ADR-088 偏离点 #2: "send_card 三端均未实现" — 未做
- ADR-088 偏离点 #3: "IM credential 仍 env-only" (spec §3 I4) — 未做
- ADR-088 偏离点 #4: "Admin UI 只读,没有编辑 button / test-send 按钮" — 未做
- 官方文档(WebFetched during Phase 2):
  - Feishu 卡片: https://open.feishu.cn/document/uAjLw4CM/uAjLw4CO/card/send-message-cards/overview
  - Slack Block Kit: https://docs.slack.dev/block-kit
  - Discord Embeds + Components: https://discord.com/developers/docs/resources/channel#embed-object / https://discord.com/developers/docs/interactions/message-components

User directive (2026-04-20): "真正生产可用,不 mock,桌面 + 移动双端 Playwright 人工模拟每按钮"。

---

## 2. Scope

### In scope

#### R1. `send_card` 三端 adapter 实现
- `IMAdapter` 抽象基类添加 `async def send_card(card: IMOutgoingCard) -> bool`,默认 `raise NotImplementedError`;三个具体 adapter(Feishu / Slack / Discord)override。
- **Feishu**(`im_feishu.py`):
  - `send_card` 翻译 `IMOutgoingCard` → Feishu interactive card JSON: `{config, header:{title}, elements:[{tag:"div", text:{tag:"lark_md", content:body_markdown}}], i18n_elements:{}, card_action_triggers:[]}` + actions → `{tag:"action", actions:[{tag:"button", text:{tag:"plain_text", content:label}, type:"primary|default", value:{action_id}}]}`
  - POST `/open-apis/im/v1/messages?receive_id_type=chat_id` Bearer tenant_access_token,`msg_type:"interactive"`,`content: json.dumps(card)`
  - 失败处理:返回 False + structlog error
- **Slack**(`im_slack.py`):
  - `send_card` 翻译 `IMOutgoingCard` → blocks: `[{type:"header", text:{type:"plain_text", text:title}}, {type:"section", text:{type:"mrkdwn", text:body_markdown}}, {type:"actions", elements:[{type:"button", text:{type:"plain_text", text:label}, action_id, style:"primary|null"}]}]`
  - 若 footer 存在:加 context block
  - POST `chat.postMessage` with `{channel, blocks, text:title}`
- **Discord**(`im_discord.py`):
  - `send_card` 翻译 → `embeds: [{title, description:body_markdown, footer:{text:footer}, color}]` + `components: [{type:1, components:[{type:2, label, style:primary|secondary, custom_id:action_id}]}]`
  - POST `channels/{chat_id}/messages` with Bot token
- **Telegram**(`im_telegram.py`):**不动**(已有自己 send_text,cards 不是本 session 范围)

#### R2. AES credential cipher + 自动加密/解密
- 新文件 `backend/app/services/credential_cipher.py`:
  - `CredentialCipher(key: bytes)` class,method `encrypt(plaintext: str) -> str`(返回 `fernet:<base64>` 前缀形式),`decrypt(value: str) -> str`(识别前缀,无则返回原值 plaintext backward-compat OK 因为"不做向后兼容"仅对新写入值,读取旧 plaintext 不报错)
  - `is_encrypted(value: str) -> bool` 前缀判断
  - 派生 Fernet key: `hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()[:32] → base64 urlsafe`
  - Fernet 内置 HMAC-SHA256 + 128-bit AES-CBC + timestamp + IV,符合生产要求
- `backend/app/api/v1/im.py` PATCH `/im/channels/{channel}` handler:
  - 在 merge config 前,扫描 `data.config` 值,凡 key 含 `secret / token / key / password` 的,用 cipher.encrypt 转换;写入 DB
  - GET `/im/channels` 脱敏逻辑不变(仍全部 redact)
- Adapter 初始化 fallback order 保持 Session 3 D3:`settings > config dict`,其中从 `config dict` 读出的加密值先通过 cipher.decrypt;plaintext 值直接使用(平滑迁移)

#### R3. Admin 编辑 UI + test-send
- `frontend/admin.html` `IMChannels` 组件:
  - 每个 row 追加两个按钮:"编辑"(data-testid="im-channel-edit-{channel}")+ "测试"(data-testid="im-channel-test-{channel}")
  - 编辑按钮 → 弹 modal(`data-testid="im-channel-edit-modal"`):
    - is_enabled toggle
    - JSONB key/value 动态表单(list of `{key, value}` row,add/remove)
    - 保存按钮 → PATCH /im/channels/{channel} + 关闭 modal + reload channels
    - 取消按钮 → 关闭
  - 测试按钮 → 弹简单 modal(`data-testid="im-channel-test-modal"`)要求填 chat_id → 发送 → toast 成功/失败
- 新 endpoint `POST /api/v1/im/channels/{channel}/test-send`:
  - admin-only
  - body: `{target_chat_id: str, title?: str, body?: str}`
  - 用 `app.state.im_gateway.get_adapter(channel)` 拿 adapter
  - 构造 `IMOutgoingCard(channel, target_chat_id, title="Prism 测试卡片", body_markdown="这是一张由 Prism admin 发送的测试互动卡片。")`
  - 调 `adapter.send_card(card)`,返回 `{sent: bool, channel}`;not_configured → 503;adapter 不存在 → 404;send 失败 → 502

### Out of scope (hard)
- 真实账号 live 发送(Playwright mock HTTP)
- Slack Socket Mode
- send_card 的 Markdown → native 自动转换优化
- 分布式任务拆解 / Skills Market / Plugin runtime enforcement(独立 session)

---

## 3. 决策(auto-decide)

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | Fernet vs AES-GCM vs cryptography lowlevel | Fernet | 标准、内置 HMAC+IV+timestamp,官方推荐用于对称加密 |
| D2 | 加密标识 | 前缀 `fernet:` | 明示加密状态,读取时区分 plaintext fallback |
| D3 | 哪些 key 自动加密 | name 含 `secret/token/key/password` | 保守黑名单足够覆盖 IM secret 类字段;`_id` / `encrypt_key`(飞书配置)全命中 |
| D4 | test-send card 内容 | hard-coded 中文文本 + 1 action button(label="确认") | 生产触发方便验证,不泄露任何真实业务数据 |
| D5 | test-send 失败时 HTTP code | adapter missing 404 / not_configured 503 / send 异常 502 | 区分运维错误(503)vs 平台错误(502) |
| D6 | Admin 编辑 UI JSONB 表单 | key/value row 列表(动态 add/remove)而非自由 textarea | 降低输错 JSON 风险,UX 清晰 |
| D7 | Plaintext 存量兼容 | cipher.decrypt 对无前缀值直接返回 | "不做向后兼容"仅对新代码写入;读取旧 plaintext 不 break;环境变量仍 plaintext |
| D8 | 验证测试 | unit + e2e 双层,e2e mock 外部 HTTP(不测真账号) | 符合 user directive "不测真账号但生产可跑" |

---

## 4. Architecture

### 4.1 credential_cipher.py(新文件,单一职责)

```python
from cryptography.fernet import Fernet, InvalidToken
import base64, hashlib

_PREFIX = "fernet:"

class CredentialCipher:
    def __init__(self, encryption_key: str) -> None:
        digest = hashlib.sha256(encryption_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))
    
    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return _PREFIX + token.decode("ascii")
    
    def decrypt(self, value: str) -> str:
        if not value.startswith(_PREFIX):
            return value  # plaintext fallback
        try:
            return self._fernet.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("ciphertext did not decrypt with configured key") from exc
    
    @staticmethod
    def is_encrypted(value: str) -> bool:
        return isinstance(value, str) and value.startswith(_PREFIX)

_SENSITIVE_KEYS = ("secret", "token", "key", "password")

def encrypt_config_secrets(config: dict, cipher: "CredentialCipher") -> dict:
    out = {}
    for k, v in config.items():
        if isinstance(v, str) and any(s in k.lower() for s in _SENSITIVE_KEYS) and not cipher.is_encrypted(v):
            out[k] = cipher.encrypt(v)
        else:
            out[k] = v
    return out

def decrypt_config_secrets(config: dict, cipher: "CredentialCipher") -> dict:
    out = {}
    for k, v in (config or {}).items():
        if isinstance(v, str) and cipher.is_encrypted(v):
            try:
                out[k] = cipher.decrypt(v)
            except ValueError:
                out[k] = v  # wrong key: surface encrypted for triage
        else:
            out[k] = v
    return out
```

### 4.2 IMAdapter.send_card abstract

```python
# im_adapter.py
async def send_card(self, card: IMOutgoingCard) -> bool:
    raise NotImplementedError(f"{self.channel_name} adapter 未实现 send_card")
```

每个具体 adapter override。v1 接受 single header + body + 可选 footer + actions list。不同平台差异吸收在 translator 内。

### 4.3 test-send endpoint

```python
# im.py
@router.post("/channels/{channel}/test-send")
async def test_send_channel_card(
    channel: str,
    body: TestSendRequest,
    admin: User = Depends(require_admin),
) -> ApiResponse[dict]:
    gw = getattr(request.app.state, "im_gateway", None)
    adapter = gw.get_adapter(channel) if gw else None
    if adapter is None:
        raise HTTPException(404, f"channel '{channel}' adapter not found")
    if not adapter.is_configured():
        raise HTTPException(503, f"channel '{channel}' not configured")
    
    card = IMOutgoingCard(
        channel=channel,
        platform_chat_id=body.target_chat_id,
        title=body.title or "Prism 测试卡片",
        body_markdown=body.body or "这是一张由 Prism admin 发送的测试互动卡片。",
        actions=[IMCardAction(label="确认", action_id="test_confirm", style="primary")],
    )
    try:
        ok = await adapter.send_card(card)
    except Exception as exc:
        raise HTTPException(502, f"send failed: {exc}")
    return ApiResponse(data={"sent": ok, "channel": channel})
```

### 4.4 Admin UI 编辑 modal(frontend-design + ui-ux-pro-max 原则)

- Luxury-refined(一致于 Session 4a consent):serif header + amber accents + framed body + vertically stacked buttons(mobile)
- JSONB 表单用 dynamic row list:
  - 每行 `[key input | value input | 🗑 删除 btn]`
  - 底部 `+ 添加字段` btn
  - value input 对 sensitive keys(名含 secret/token/key)自动改 `type="password"`

---

## 5. Schema changes

**无 migration**。`im_channel_configs.config` JSONB 已存在(Session 3 既有),本 session 只在应用层读写时 encrypt/decrypt。

---

## 6. Environment / dependencies

**无新 env var**。`cryptography>=42.0.0` 在 requirements.txt 已有(AES-CBC-256 for Feishu decrypt 用过)。`cryptography.fernet` 是 `cryptography` 子模块。

---

## 7. 验证方案

### 7.1 Python unit(~12 tests)

`backend/tests/test_credential_cipher.py`(3):
- encrypt → decrypt round-trip
- decrypt plaintext value(无前缀)returns value as-is
- decrypt ciphertext with different key raises ValueError

`backend/tests/test_im_send_card_feishu.py`(3 via mocked httpx):
- send_card happy → POST body 含 `msg_type:"interactive"` + card JSON 符合 Feishu 结构
- send_card 无 bot_token → return False(not configured skip)
- send_card API 非 2xx → return False + log error

`backend/tests/test_im_send_card_slack.py`(3):
- send_card → POST body 含 `blocks:[header, section, actions]`
- send_card 非 2xx return False
- blocks 格式符合 Slack schema

`backend/tests/test_im_send_card_discord.py`(3):
- send_card → POST body 含 `embeds` + `components:[ActionRow]`
- 非 2xx return False
- card formatted correctly

### 7.2 Playwright e2e(8 × 2 viewport = 16)

`e2e/tests/im-admin-edit.spec.ts`:
- Admin 导航到 IM 频道 tab → 每个 row 有 edit + test button(`im-channel-edit-{c}` + `im-channel-test-{c}`)
- 点 Slack edit button → edit modal 打开(`im-channel-edit-modal`)
- 填 key/value pair(如 `bot_token: xoxb-test`)→ 保存 → PATCH 请求发出 + modal 关闭
- 编辑后的 config 重新打开时 secret 字段仍脱敏(`***`)
- 点 test button → test modal → 输入 chat_id → 发送 → 拦截 POST 返回 mock success → toast 成功
- test button 当 adapter 未配置 → mock 503 → toast 失败提示
- mobile viewport 按钮垂直堆叠

### 7.3 手动 sim(Playwright 自动化覆盖;无需真账号)

---

## 8. Out of scope (hard)

- 真实账号 E2E live 测试
- Slack Socket Mode / Discord Gateway / Telegram chat 集成
- Markdown 转 native 自动化
- IM 消息模板库(本 session 只发简单 card)
- Permission runtime enforcement

---

## 9. Acceptance

- 12 Python unit + 16 e2e(8 × 双端)全绿
- Simplify 3 subagent + 修 findings
- PJR:Python AST + in-container import + frontend node --check
- git-merge-to-develop 本地 no-ff
- HANDOFF 写 Session 4b 完成 + ADR-088 偏离点 #2/#3/#4 清零 + Session 4c/4d roadmap

---

*End of spec — word count ≈ 1500.*
