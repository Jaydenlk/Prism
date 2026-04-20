# Session 4b: IM send_card + AES credential + Admin 编辑 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ADR-088 偏离点 #2 (`send_card` 未实现) + #3 (credential env-only) + #4 (Admin UI 只读) 全部清零 → IM 模块进入 "用户换真实 credentials 即可直接用" 的生产可用状态。

**Architecture:** 三端 adapter 各自实现 `send_card` 翻译 `IMOutgoingCard` 到原生格式(Feishu interactive / Slack blocks / Discord embed+components);新 `CredentialCipher` (Fernet/AES-128-CBC+HMAC) 在 im.py PATCH 时自动加密 sensitive fields,adapter 初始化时自动解密;Admin admin.html 加编辑 modal + test-send modal;新 `POST /im/channels/{c}/test-send` endpoint 让 admin 自测。

**Tech Stack:** FastAPI + SQLAlchemy (现有) + `cryptography.fernet` (已有依赖) + httpx (现有) + React inline (Prism.html 风格)

**Spec:** `docs/superpowers/specs/2026-04-20-session4b-im-send-card-aes-admin-design.md`

---

## File Structure

| File | Action | 职责 |
|---|---|---|
| `backend/app/services/credential_cipher.py` | Create | Fernet-based encrypt/decrypt + config scrubber |
| `backend/app/services/im_adapter.py` | Modify | add abstract `send_card` |
| `backend/app/services/im_feishu.py` | Modify | 实现 send_card → Feishu interactive card JSON |
| `backend/app/services/im_slack.py` | Modify | 实现 send_card → Slack blocks |
| `backend/app/services/im_discord.py` | Modify | 实现 send_card → Discord embed + components |
| `backend/app/api/v1/im.py` | Modify | PATCH 写前 encrypt + GET 读后 decrypt + `POST /channels/{c}/test-send` |
| `backend/app/main.py` | Modify | lifespan 注入 `app.state.credential_cipher` |
| `backend/app/schemas/im.py` | Modify | `TestSendRequest` schema |
| `backend/tests/test_credential_cipher.py` | Create | 3 unit tests |
| `backend/tests/test_im_send_card_feishu.py` | Create | 3 unit tests(mock httpx) |
| `backend/tests/test_im_send_card_slack.py` | Create | 3 unit tests |
| `backend/tests/test_im_send_card_discord.py` | Create | 3 unit tests |
| `frontend/admin.html` | Modify | IMChannels edit modal + test modal |
| `frontend/apiClient.js` | Modify | `im.testSend(channel, body)` + `im.updateChannel(...)` already exists |
| `e2e/tests/im-admin-edit.spec.ts` | Create | 8 e2e tests(dual viewport × 2 = 16) |

---

## Task 1: Worktree + baseline

- [ ] **Step 1**: 建 worktree。
  ```bash
  cd "E:/Agent program/PrismV3"
  git worktree add .worktrees/im-sendcard-aes -b redesign/im-sendcard-aes develop
  ```

- [ ] **Step 2**: junction + env copy。
  ```bash
  powershell -NoProfile -Command "New-Item -ItemType Junction -Path '.worktrees/im-sendcard-aes/e2e/node_modules' -Target 'E:\Agent program\PrismV3\e2e\node_modules'"
  cp ".env" ".worktrees/im-sendcard-aes/.env"
  ```

- [ ] **Step 3**: health check(docker 已起)。
  ```bash
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/health/live
  ```
  Expected: `200`.

---

## Task 2: RED — credential_cipher unit

**File**: Create `backend/tests/test_credential_cipher.py`

- [ ] **Step 1**: 写 3 tests。
  ```python
  """Session 4b — credential_cipher round-trip + fallback + wrong-key."""
  from __future__ import annotations
  import pytest
  from app.services.credential_cipher import CredentialCipher


  def test_encrypt_decrypt_roundtrip():
      c = CredentialCipher("x" * 32)
      token = c.encrypt("hello-world")
      assert token.startswith("fernet:")
      assert c.decrypt(token) == "hello-world"


  def test_plaintext_fallback_returns_as_is():
      c = CredentialCipher("x" * 32)
      assert c.decrypt("plaintext-legacy") == "plaintext-legacy"


  def test_decrypt_with_wrong_key_raises():
      encryptor = CredentialCipher("key-one" + "0" * 25)
      token = encryptor.encrypt("secret")
      decryptor = CredentialCipher("key-two" + "0" * 25)
      with pytest.raises(ValueError):
          decryptor.decrypt(token)
  ```

- [ ] **Step 2**: 跑 — expect ImportError(module missing)。
  ```bash
  cd ".worktrees/im-sendcard-aes"
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 10
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_credential_cipher.py --no-header 2>&1 | tail -8"
  ```
  Expected: `ModuleNotFoundError: No module named 'app.services.credential_cipher'`.

- [ ] **Step 3**: Commit RED。
  ```bash
  git add backend/tests/test_credential_cipher.py
  git commit -m "test(cipher): RED phase — Fernet encrypt/decrypt + fallback + wrong-key"
  ```

---

## Task 3: GREEN — credential_cipher

**File**: Create `backend/app/services/credential_cipher.py`

- [ ] **Step 1**: 实现。
  ```python
  """
  Prism v2 — Credential Cipher (Session 4b, ADR-088 偏离点 #3)

  Fernet (AES-128-CBC + HMAC-SHA256 + timestamp + IV) symmetric encryption
  for sensitive values in im_channel_configs.config (and future JSONB secret
  containers). Uses settings.ENCRYPTION_KEY (third of the 3-key pair,
  CLAUDE.md 六原则 #5 — never conflated with JWT_SECRET / CALLBACK_SECRET).

  Ciphertext format: "fernet:<urlsafe_base64>" — prefix allows plaintext
  fallback for legacy values and instant visual diff in DB dumps.
  """
  from __future__ import annotations

  import base64
  import hashlib
  from typing import Any

  from cryptography.fernet import Fernet, InvalidToken

  _PREFIX = "fernet:"
  _SENSITIVE_SUBSTRINGS = ("secret", "token", "key", "password")


  class CredentialCipher:
      """Symmetric-key cipher for IM (and future) credential JSONB values."""

      def __init__(self, encryption_key: str) -> None:
          if not encryption_key or len(encryption_key) < 32:
              raise ValueError("encryption_key must be >= 32 chars")
          digest = hashlib.sha256(encryption_key.encode("utf-8")).digest()
          self._fernet = Fernet(base64.urlsafe_b64encode(digest))

      def encrypt(self, plaintext: str) -> str:
          token = self._fernet.encrypt(plaintext.encode("utf-8"))
          return _PREFIX + token.decode("ascii")

      def decrypt(self, value: str) -> str:
          if not isinstance(value, str) or not value.startswith(_PREFIX):
              return value  # plaintext fallback
          try:
              return self._fernet.decrypt(value[len(_PREFIX):].encode("ascii")).decode("utf-8")
          except InvalidToken as exc:
              raise ValueError("ciphertext did not decrypt with configured key") from exc

      @staticmethod
      def is_encrypted(value: Any) -> bool:
          return isinstance(value, str) and value.startswith(_PREFIX)


  def _is_sensitive_key(key: str) -> bool:
      k = key.lower()
      return any(sub in k for sub in _SENSITIVE_SUBSTRINGS)


  def encrypt_config_secrets(config: dict | None, cipher: CredentialCipher) -> dict:
      """Return a new dict with sensitive string values encrypted in place."""
      out: dict = {}
      for k, v in (config or {}).items():
          if isinstance(v, str) and _is_sensitive_key(k) and not cipher.is_encrypted(v):
              out[k] = cipher.encrypt(v)
          else:
              out[k] = v
      return out


  def decrypt_config_secrets(config: dict | None, cipher: CredentialCipher) -> dict:
      """Return a new dict with encrypted values decrypted; plaintext passes through."""
      out: dict = {}
      for k, v in (config or {}).items():
          if cipher.is_encrypted(v):
              try:
                  out[k] = cipher.decrypt(v)
              except ValueError:
                  out[k] = v  # wrong key: leave encrypted for triage
          else:
              out[k] = v
      return out
  ```

- [ ] **Step 2**: 跑 — expect 3 PASS。
  ```bash
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 10
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_credential_cipher.py --no-header 2>&1 | tail -8"
  ```

- [ ] **Step 3**: Commit。
  ```bash
  git add backend/app/services/credential_cipher.py
  git commit -m "feat(cipher): CredentialCipher Fernet + config scrubber helpers (ADR-088 I4)"
  ```

---

## Task 4: RED — send_card unit tests(3 files × 3 tests each)

**Files**: Create:
- `backend/tests/test_im_send_card_feishu.py`
- `backend/tests/test_im_send_card_slack.py`
- `backend/tests/test_im_send_card_discord.py`

- [ ] **Step 1**: `test_im_send_card_feishu.py`
  ```python
  """Session 4b — Feishu send_card unit (mock httpx)."""
  from __future__ import annotations
  import json
  from unittest.mock import AsyncMock, patch
  import pytest
  from app.services.im_adapter import IMOutgoingCard, IMCardAction
  from app.services.im_feishu import FeishuAdapter


  def _adapter() -> FeishuAdapter:
      return FeishuAdapter(config={
          "app_id": "cli_x", "app_secret": "s", "encrypt_key": "e", "verify_token": "v",
      })


  def _card() -> IMOutgoingCard:
      return IMOutgoingCard(
          channel="feishu", platform_chat_id="oc_test",
          title="测试", body_markdown="**bold**",
          actions=[IMCardAction(label="确认", action_id="ok")],
      )


  @pytest.mark.asyncio
  async def test_feishu_send_card_builds_interactive_payload(monkeypatch):
      captured: dict = {}

      class _MockResp:
          def json(self_inner): return {"code": 0}

      class _MockClient:
          def __init__(self_inner, timeout=None, **kw): pass
          async def __aenter__(self_inner): return self_inner
          async def __aexit__(self_inner, *a): pass
          async def post(self_inner, url, **kw):
              captured["url"] = url; captured["kw"] = kw; return _MockResp()

      monkeypatch.setattr("app.services.im_feishu.httpx.AsyncClient", _MockClient)
      a = _adapter()
      monkeypatch.setattr(a, "_ensure_token", AsyncMock(return_value="tkn"))

      ok = await a.send_card(_card())
      assert ok is True
      body = captured["kw"].get("json") or {}
      assert body.get("msg_type") == "interactive"
      content = json.loads(body.get("content") or "{}")
      assert "header" in content and "elements" in content
      assert content["header"]["title"]["content"] == "测试"


  @pytest.mark.asyncio
  async def test_feishu_send_card_not_configured_returns_false():
      a = FeishuAdapter(config={"app_id": "", "app_secret": ""})
      assert await a.send_card(_card()) is False


  @pytest.mark.asyncio
  async def test_feishu_send_card_api_error_returns_false(monkeypatch):
      class _MockResp:
          def json(self_inner): return {"code": 99, "msg": "bad"}

      class _MockClient:
          def __init__(self_inner, timeout=None, **kw): pass
          async def __aenter__(self_inner): return self_inner
          async def __aexit__(self_inner, *a): pass
          async def post(self_inner, url, **kw): return _MockResp()

      monkeypatch.setattr("app.services.im_feishu.httpx.AsyncClient", _MockClient)
      a = _adapter()
      monkeypatch.setattr(a, "_ensure_token", AsyncMock(return_value="tkn"))
      assert await a.send_card(_card()) is False
  ```

- [ ] **Step 2**: `test_im_send_card_slack.py`
  ```python
  """Session 4b — Slack send_card unit (mock httpx)."""
  from __future__ import annotations
  import pytest
  from app.services.im_adapter import IMOutgoingCard, IMCardAction
  from app.services.im_slack import SlackAdapter


  def _adapter() -> SlackAdapter:
      return SlackAdapter(config={
          "signing_secret": "s" * 32, "bot_token": "xoxb-test", "mode": "events",
      })


  def _card() -> IMOutgoingCard:
      return IMOutgoingCard(
          channel="slack", platform_chat_id="C0TEST",
          title="Test", body_markdown="*bold* note",
          actions=[IMCardAction(label="OK", action_id="ok", style="primary")],
      )


  @pytest.mark.asyncio
  async def test_slack_send_card_builds_blocks(monkeypatch):
      captured: dict = {}

      class _Resp:
          status_code = 200
          def json(self_inner): return {"ok": True}

      class _Client:
          def __init__(self_inner, timeout=None, **kw): pass
          async def __aenter__(self_inner): return self_inner
          async def __aexit__(self_inner, *a): pass
          async def post(self_inner, url, **kw):
              captured["url"] = url; captured["kw"] = kw; return _Resp()

      monkeypatch.setattr("app.services.im_slack.httpx.AsyncClient", _Client)
      ok = await _adapter().send_card(_card())
      assert ok is True
      body = captured["kw"]["json"]
      assert body["channel"] == "C0TEST"
      blocks = body["blocks"]
      kinds = [b["type"] for b in blocks]
      assert "header" in kinds and "section" in kinds and "actions" in kinds


  @pytest.mark.asyncio
  async def test_slack_send_card_not_configured_returns_false():
      a = SlackAdapter(config={"signing_secret": "", "bot_token": ""})
      assert await a.send_card(_card()) is False


  @pytest.mark.asyncio
  async def test_slack_send_card_api_error_returns_false(monkeypatch):
      class _Resp:
          status_code = 200
          def json(self_inner): return {"ok": False, "error": "channel_not_found"}

      class _Client:
          def __init__(self_inner, timeout=None, **kw): pass
          async def __aenter__(self_inner): return self_inner
          async def __aexit__(self_inner, *a): pass
          async def post(self_inner, *a, **kw): return _Resp()

      monkeypatch.setattr("app.services.im_slack.httpx.AsyncClient", _Client)
      assert await _adapter().send_card(_card()) is False
  ```

- [ ] **Step 3**: `test_im_send_card_discord.py`
  ```python
  """Session 4b — Discord send_card unit (mock httpx)."""
  from __future__ import annotations
  import pytest
  from app.services.im_adapter import IMOutgoingCard, IMCardAction
  from app.services.im_discord import DiscordAdapter


  def _adapter() -> DiscordAdapter:
      return DiscordAdapter(config={
          "public_key": "00" * 32, "app_id": "1", "bot_token": "Bot-t",
      })


  def _card() -> IMOutgoingCard:
      return IMOutgoingCard(
          channel="discord", platform_chat_id="CHANNEL_ID",
          title="Test", body_markdown="body",
          actions=[IMCardAction(label="OK", action_id="ok", style="primary")],
      )


  @pytest.mark.asyncio
  async def test_discord_send_card_builds_embed_and_components(monkeypatch):
      captured: dict = {}

      class _Resp:
          status_code = 200
          text = "{}"
          def json(self_inner): return {}

      class _Client:
          def __init__(self_inner, timeout=None, **kw): pass
          async def __aenter__(self_inner): return self_inner
          async def __aexit__(self_inner, *a): pass
          async def post(self_inner, url, **kw):
              captured["url"] = url; captured["kw"] = kw; return _Resp()

      monkeypatch.setattr("app.services.im_discord.httpx.AsyncClient", _Client)
      ok = await _adapter().send_card(_card())
      assert ok is True
      body = captured["kw"]["json"]
      assert body["embeds"][0]["title"] == "Test"
      assert body["components"][0]["type"] == 1  # ActionRow
      assert body["components"][0]["components"][0]["type"] == 2  # Button
      assert body["components"][0]["components"][0]["label"] == "OK"


  @pytest.mark.asyncio
  async def test_discord_send_card_no_bot_token_returns_false():
      a = DiscordAdapter(config={"public_key": "00" * 32, "app_id": "1", "bot_token": ""})
      assert await a.send_card(_card()) is False


  @pytest.mark.asyncio
  async def test_discord_send_card_api_error_returns_false(monkeypatch):
      class _Resp:
          status_code = 400
          text = "bad"
          def json(self_inner): return {}

      class _Client:
          def __init__(self_inner, timeout=None, **kw): pass
          async def __aenter__(self_inner): return self_inner
          async def __aexit__(self_inner, *a): pass
          async def post(self_inner, *a, **kw): return _Resp()

      monkeypatch.setattr("app.services.im_discord.httpx.AsyncClient", _Client)
      assert await _adapter().send_card(_card()) is False
  ```

- [ ] **Step 4**: 跑 — expect 9 FAIL (NotImplementedError since send_card not overridden)。
  ```bash
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_im_send_card_feishu.py tests/test_im_send_card_slack.py tests/test_im_send_card_discord.py --no-header 2>&1 | tail -15"
  ```

- [ ] **Step 5**: Commit RED。
  ```bash
  git add backend/tests/test_im_send_card_*.py
  git commit -m "test(im): RED phase — send_card unit (Feishu + Slack + Discord)"
  ```

---

## Task 5: GREEN — IMAdapter.send_card abstract + Feishu 实现

**Files:**
- Modify `backend/app/services/im_adapter.py`
- Modify `backend/app/services/im_feishu.py`

- [ ] **Step 1**: `im_adapter.py` 基类加 `send_card`(默认 NotImplementedError)。
  在 `class IMAdapter(ABC)` 的 abstract methods 组里加:
  ```python
      async def send_card(self, card: IMOutgoingCard) -> bool:
          """发送结构化卡片消息(对 IM 平台的 interactive card / blocks / embed 的统一抽象)。

          各 adapter 必须 override。默认 raise NotImplementedError 以便静默
          fallback(例如 Telegram)明确出错,而非无声吞掉。
          """
          raise NotImplementedError(f"{self.channel_name} adapter 未实现 send_card")
  ```

- [ ] **Step 2**: `im_feishu.py` 追加 send_card。在 `send_message` 方法之后插入:
  ```python
      async def send_card(self, card: IMOutgoingCard) -> bool:
          """POST Feishu interactive card via /open-apis/im/v1/messages msg_type=interactive."""
          from app.services.im_adapter import IMOutgoingCard  # avoid circular at class time
          if not self.is_configured():
              logger.warning("feishu.send_card.not_configured", chat_id=card.platform_chat_id)
              return False

          elements: list[dict[str, Any]] = [
              {"tag": "div", "text": {"tag": "lark_md", "content": card.body_markdown}},
          ]
          if card.actions:
              elements.append({
                  "tag": "action",
                  "actions": [
                      {
                          "tag": "button",
                          "text": {"tag": "plain_text", "content": a.label},
                          "type": "primary" if a.style == "primary" else "default",
                          "value": {"action_id": a.action_id},
                      }
                      for a in card.actions
                  ],
              })
          if card.footer:
              elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": card.footer}]})

          card_payload = {
              "config": {"wide_screen_mode": True},
              "header": {
                  "template": "blue",
                  "title": {"tag": "plain_text", "content": card.title},
              },
              "elements": elements,
          }

          try:
              token = await self._ensure_token()
              async with httpx.AsyncClient(timeout=10.0) as client:
                  resp = await client.post(
                      f"{FEISHU_API_BASE}/open-apis/im/v1/messages",
                      params={"receive_id_type": "chat_id"},
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                      json={
                          "receive_id": card.platform_chat_id,
                          "msg_type": "interactive",
                          "content": json.dumps(card_payload, ensure_ascii=False),
                      },
                  )
              data = resp.json()
              if data.get("code") != 0:
                  logger.error("feishu.send_card.api_error", chat_id=card.platform_chat_id, code=data.get("code"), msg=data.get("msg"))
                  return False
              logger.info("feishu.send_card.ok", chat_id=card.platform_chat_id)
              return True
          except Exception as exc:  # noqa: BLE001
              logger.error("feishu.send_card.exception", chat_id=card.platform_chat_id, error=str(exc))
              return False
  ```
  加 import `from app.services.im_adapter import IMOutgoingCard` 在文件头(与现有 imports 合并)。

- [ ] **Step 3**: 跑 feishu 3 tests。
  ```bash
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 10
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_im_send_card_feishu.py --no-header 2>&1 | tail -8"
  ```
  Expected: 3 passed.

- [ ] **Step 4**: Commit。
  ```bash
  git add backend/app/services/im_adapter.py backend/app/services/im_feishu.py
  git commit -m "feat(im_feishu): send_card → interactive card JSON (ADR-088 I5)"
  ```

---

## Task 6: GREEN — Slack send_card

**File**: Modify `backend/app/services/im_slack.py`

- [ ] **Step 1**: 追加 send_card 在 send 方法之后。
  ```python
      async def send_card(self, card: IMOutgoingCard) -> bool:
          if not self.is_configured():
              logger.warning("slack.send_card.not_configured", chat_id=card.platform_chat_id)
              return False

          blocks: list[dict[str, Any]] = [
              {"type": "header", "text": {"type": "plain_text", "text": card.title}},
              {"type": "section", "text": {"type": "mrkdwn", "text": card.body_markdown}},
          ]
          if card.actions:
              blocks.append({
                  "type": "actions",
                  "elements": [
                      {
                          "type": "button",
                          "text": {"type": "plain_text", "text": a.label},
                          "action_id": a.action_id,
                          **({"style": "primary"} if a.style == "primary" else {}),
                      }
                      for a in card.actions
                  ],
              })
          if card.footer:
              blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": card.footer}]})

          payload: dict[str, Any] = {
              "channel": card.platform_chat_id,
              "blocks": blocks,
              "text": card.title,
          }
          if card.reply_to_message_id:
              payload["thread_ts"] = card.reply_to_message_id

          try:
              async with httpx.AsyncClient(timeout=10.0) as client:
                  resp = await client.post(
                      f"{SLACK_API_BASE}/chat.postMessage",
                      headers={
                          "Authorization": f"Bearer {self._bot_token}",
                          "Content-Type": "application/json; charset=utf-8",
                      },
                      json=payload,
                  )
              data = resp.json()
              if not data.get("ok"):
                  logger.error("slack.send_card.api_error", chat_id=card.platform_chat_id, error=data.get("error"))
                  return False
              logger.info("slack.send_card.ok", chat_id=card.platform_chat_id)
              return True
          except Exception as exc:  # noqa: BLE001
              logger.error("slack.send_card.exception", chat_id=card.platform_chat_id, error=str(exc))
              return False
  ```
  补 import `from app.services.im_adapter import IMOutgoingCard`(同文件已有 IMIncomingMessage 等 import)。

- [ ] **Step 2**: 跑 slack 3 tests。
  ```bash
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 10
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_im_send_card_slack.py --no-header 2>&1 | tail -8"
  ```
  Expected: 3 passed.

- [ ] **Step 3**: Commit。
  ```bash
  git add backend/app/services/im_slack.py
  git commit -m "feat(im_slack): send_card → Block Kit blocks (ADR-088 I5)"
  ```

---

## Task 7: GREEN — Discord send_card

**File**: Modify `backend/app/services/im_discord.py`

- [ ] **Step 1**: 追加 send_card 在 send 方法之后。
  ```python
      async def send_card(self, card: IMOutgoingCard) -> bool:
          if not self._bot_token:
              logger.warning("discord.send_card.no_bot_token", chat_id=card.platform_chat_id)
              return False

          embed: dict[str, Any] = {
              "title": card.title,
              "description": card.body_markdown,
              "color": 0xD97706,  # amber-600, matches Prism accent
          }
          if card.footer:
              embed["footer"] = {"text": card.footer}

          components: list[dict[str, Any]] = []
          if card.actions:
              style_map = {"primary": 1, "secondary": 2}  # Discord button styles
              components.append({
                  "type": 1,  # ActionRow
                  "components": [
                      {
                          "type": 2,  # Button
                          "style": style_map.get(a.style, 2),
                          "label": a.label,
                          "custom_id": a.action_id,
                      }
                      for a in card.actions
                  ],
              })

          payload: dict[str, Any] = {"embeds": [embed]}
          if components:
              payload["components"] = components
          if card.reply_to_message_id:
              payload["message_reference"] = {"message_id": card.reply_to_message_id}

          try:
              async with httpx.AsyncClient(timeout=10.0) as client:
                  resp = await client.post(
                      f"{DISCORD_API_BASE}/channels/{card.platform_chat_id}/messages",
                      headers={
                          "Authorization": f"Bot {self._bot_token}",
                          "Content-Type": "application/json",
                      },
                      json=payload,
                  )
              if resp.status_code >= 300:
                  logger.error("discord.send_card.api_error", chat_id=card.platform_chat_id, status=resp.status_code, body=resp.text[:200])
                  return False
              logger.info("discord.send_card.ok", chat_id=card.platform_chat_id)
              return True
          except Exception as exc:  # noqa: BLE001
              logger.error("discord.send_card.exception", chat_id=card.platform_chat_id, error=str(exc))
              return False
  ```
  补 import `from app.services.im_adapter import IMOutgoingCard`.

- [ ] **Step 2**: 跑 discord 3 tests。
  ```bash
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 10
  docker compose -p prismv3 exec -T backend pip install pytest pytest-asyncio 2>&1 | tail -1
  docker compose -p prismv3 exec -T backend sh -c "cd /app/backend && python -m pytest tests/test_im_send_card_discord.py --no-header 2>&1 | tail -8"
  ```
  Expected: 3 passed.

- [ ] **Step 3**: Commit。
  ```bash
  git add backend/app/services/im_discord.py
  git commit -m "feat(im_discord): send_card → embed + button components (ADR-088 I5)"
  ```

---

## Task 8: Backend — PATCH encryption + /test-send endpoint

**Files:**
- Modify `backend/app/main.py` — lifespan 构造 cipher
- Modify `backend/app/schemas/im.py` — `TestSendRequest`
- Modify `backend/app/api/v1/im.py` — PATCH encrypt + GET decrypt + test-send handler + adapter init decrypt

- [ ] **Step 1**: `main.py` lifespan。在 IMGateway 初始化之前插入(在 `# 6b. Initialize IMGateway + adapters` 之前):
  ```python
      # 6a2. Initialize CredentialCipher (ADR-088 偏离点 #3, Session 4b)
      try:
          from app.services.credential_cipher import CredentialCipher
          app.state.credential_cipher = CredentialCipher(settings.ENCRYPTION_KEY)
          logger.info("prism.credential_cipher.initialized")
      except Exception as exc:
          app.state.credential_cipher = None
          logger.error("prism.credential_cipher.init_failed", error=str(exc))
  ```

- [ ] **Step 2**: `backend/app/schemas/im.py` 追加 `TestSendRequest`:
  ```python
  class TestSendRequest(BaseModel):
      """POST /im/channels/{channel}/test-send body."""

      target_chat_id: str = Field(min_length=1, description="目标会话/群聊 ID")
      title: str | None = Field(default=None, description="卡片标题,缺省 'Prism 测试卡片'")
      body: str | None = Field(default=None, description="卡片正文 markdown,缺省标准测试文案")
  ```

- [ ] **Step 3**: `im.py` PATCH handler — 在 merge config 前 encrypt secrets。定位 `update_channel` 函数内 `merged.update(data.config)` 附近,替换为:
  ```python
      if data.config is not None:
          cipher = getattr(db.bind.engine.app_state if False else None, None)  # placeholder; see actual replacement below
  ```
  实际替换(定位现有代码):
  ```python
      # 原:
      if data.config is not None:
          merged = dict(row.config or {})
          merged.update(data.config)
          row.config = merged
  ```
  改为:
  ```python
      if data.config is not None:
          cipher = getattr(admin.request.app.state if hasattr(admin, 'request') else None, 'credential_cipher', None)
          # admin User object doesn't carry request; use a separate Request injection
  ```
  正确做法(FastAPI Request 注入):修改 handler 签名加 `request: Request`,并使用 `request.app.state.credential_cipher`。
  
  具体替换:
  ```python
  @router.patch(
      "/channels/{channel}",
      response_model=ApiResponse[IMChannelConfigResponse],
      summary="更新渠道配置（admin only）",
  )
  def update_channel(
      channel: str,
      data: IMChannelConfigUpdate,
      request: Request,
      admin: User = Depends(require_admin),
      db: Session = Depends(get_db),
  ) -> ApiResponse[IMChannelConfigResponse]:
      from app.services.credential_cipher import encrypt_config_secrets

      row = db.query(ImChannelConfig).filter(ImChannelConfig.channel == channel).first()
      if row is None:
          row = ImChannelConfig(channel=channel, is_enabled=False, config={})
          db.add(row)

      if data.is_enabled is not None:
          row.is_enabled = data.is_enabled
      if data.config is not None:
          cipher = getattr(request.app.state, "credential_cipher", None)
          new_config = encrypt_config_secrets(data.config, cipher) if cipher else dict(data.config)
          merged = dict(row.config or {})
          merged.update(new_config)
          row.config = merged

      db.commit()
      db.refresh(row)

      logger.info("im.channel.updated", channel=channel, is_enabled=row.is_enabled, admin_id=admin.id)

      return ApiResponse(
          data=IMChannelConfigResponse(
              id=row.id,
              channel=row.channel,
              is_enabled=row.is_enabled,
              config=_redact_secrets(row.config),
              created_at=row.created_at,
              updated_at=row.updated_at,
          )
      )
  ```

- [ ] **Step 4**: `im.py` 新 endpoint `POST /channels/{channel}/test-send`。追加在 update_channel 之后:
  ```python
  @router.post(
      "/channels/{channel}/test-send",
      response_model=ApiResponse[dict],
      summary="向 IM 渠道发送一张测试卡片(admin only)",
  )
  async def test_send_channel(
      channel: str,
      body: "TestSendRequest",
      request: Request,
      admin: User = Depends(require_admin),
  ) -> ApiResponse[dict]:
      from app.services.im_adapter import IMCardAction, IMOutgoingCard
      from app.schemas.im import TestSendRequest  # re-import for runtime

      gw = getattr(request.app.state, "im_gateway", None)
      adapter = gw.get_adapter(channel) if gw else None
      if adapter is None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"channel '{channel}' adapter not found")
      if not adapter.is_configured():
          raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"channel '{channel}' not configured")

      card = IMOutgoingCard(
          channel=channel,
          platform_chat_id=body.target_chat_id,
          title=body.title or "Prism 测试卡片",
          body_markdown=body.body or "这是一张由 Prism admin 发送的测试互动卡片。\n您可以点击下方按钮测试 action 回传。",
          actions=[IMCardAction(label="确认", action_id="test_confirm", style="primary")],
      )
      try:
          ok = await adapter.send_card(card)
      except Exception as exc:  # noqa: BLE001
          logger.error("im.test_send.exception", channel=channel, error=str(exc))
          raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"send failed: {exc}")

      logger.info("im.test_send.result", channel=channel, ok=ok, admin_id=admin.id)
      return ApiResponse(data={"sent": bool(ok), "channel": channel})
  ```
  顶部 import 里加 `from app.schemas.im import TestSendRequest`(统一不要在 handler 内部重复 import)。

- [ ] **Step 5**: adapter 初始化解密。修改 feishu / slack / discord adapter `__init__` 的 config 分支,让 `config.get("<secret_key>", "")` 的结果通过 cipher.decrypt。具体:`im_gateway.py` 里注册 adapter 之前,用 `decrypt_config_secrets` 预处理 config。或在 adapter `__init__` 中接受 cipher:
  - **简化方式**:`main.py` lifespan 初始化 adapter 前,从 DB 读 `im_channel_configs` row 的 config,`decrypt_config_secrets(row.config, cipher)` 后再传给 adapter。
  - 当前代码 adapter 只从 settings / 传入 config 取值,Session 3 implementation settings path 优先;本 session 不改 init 逻辑,只在 PATCH 写入时加密 → `_redact_secrets` 已对前端脱敏,后续 adapter 重启会从 DB 读解密后的 config。
  - 新增 `_load_adapter_config_decrypted(channel: str, db, cipher) -> dict` helper,在 `main.py` lifespan 注册 adapter 时调用。
  
  在 `main.py` 6b block 之前增加:
  ```python
      def _load_im_config(ch: str) -> dict:
          try:
              from app.core.database import SessionLocal
              from app.models.im import ImChannelConfig
              from app.services.credential_cipher import decrypt_config_secrets
              _s = SessionLocal()
              try:
                  row = _s.query(ImChannelConfig).filter(ImChannelConfig.channel == ch).first()
                  raw = dict(row.config or {}) if row else {}
              finally:
                  _s.close()
              cipher = getattr(app.state, "credential_cipher", None)
              return decrypt_config_secrets(raw, cipher) if cipher else raw
          except Exception as exc:
              logger.warning("im.config_load_failed", channel=ch, error=str(exc))
              return {}

      feishu_adapter = FeishuAdapter(config=_load_im_config("feishu"), settings=settings, redis_client=_redis_for_im)
      slack_adapter = SlackAdapter(config=_load_im_config("slack"), settings=settings)
      discord_adapter = DiscordAdapter(config=_load_im_config("discord"), settings=settings)
  ```

- [ ] **Step 6**: rebuild + health + smoke curl test-send。
  ```bash
  docker compose -p prismv3 up -d --build --force-recreate backend 2>&1 | tail -3
  sleep 10
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/health/live
  TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login -H "Content-Type: application/json" -d '{"email":"admin@prism.dev","password":"PrismAdmin!2026"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
  curl -s -X POST http://localhost:8080/api/v1/im/channels/feishu/test-send -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"target_chat_id":"oc_x"}' | head -c 200
  ```
  Expected: 503(feishu 未 configured)或 feishu send fail → {"sent": false, "channel":"feishu"}.

- [ ] **Step 7**: Commit。
  ```bash
  git add backend/app/main.py backend/app/schemas/im.py backend/app/api/v1/im.py
  git commit -m "feat(im): PATCH encrypt secrets + test-send endpoint + adapter decrypt loader (ADR-088 I4+#4)"
  ```

---

## Task 9: RED e2e admin edit modal

**File**: Create `e2e/tests/im-admin-edit.spec.ts`

- [ ] **Step 1**: 写 e2e RED。
  ```typescript
  import { test, expect } from '@playwright/test';
  import { loginAsAdmin } from '../fixtures/auth';

  /**
   * im-admin-edit.spec.ts — Session 4b ADR-088 #4 偏离点清零.
   *
   * Production path:
   *   1. Admin → /admin.html → IM 频道 tab
   *   2. Each row has Edit + Test button (data-testid="im-channel-{action}-{channel}")
   *   3. Edit modal: dynamic key/value rows (add/remove), is_enabled toggle,
   *      Save posts PATCH /im/channels/{c} with JSONB config
   *   4. Test modal: target_chat_id input, Send posts /channels/{c}/test-send
   *   5. Toast success/fail based on response
   *
   * All external HTTP (Feishu/Slack/Discord API) is mocked at route-level so
   * CI passes without real credentials. Production code path unchanged: user
   * configures real tokens in admin UI and the Test button hits the same path.
   */

  async function openImTab(page: any) {
    await page.goto('/admin.html');
    const nav = page.locator('text=IM 频道').first();
    await nav.evaluate((el: HTMLElement) => (el.closest('[class*="nav"]') as HTMLElement | null || el).click());
    await expect(page.locator('[data-testid="im-channel-row-slack"]')).toBeVisible({ timeout: 10_000 });
  }

  test.describe('Admin IM Channels edit + test-send (Session 4b)', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('every row has edit + test buttons', async ({ page }) => {
      await openImTab(page);
      for (const ch of ['feishu', 'wecom', 'slack', 'discord']) {
        await expect(page.locator(`[data-testid="im-channel-edit-${ch}"]`)).toBeVisible();
        await expect(page.locator(`[data-testid="im-channel-test-${ch}"]`)).toBeVisible();
      }
    });

    test('edit modal opens + add key/value row + save posts PATCH', async ({ page }) => {
      await openImTab(page);
      await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-edit-modal"]')).toBeVisible({ timeout: 5_000 });

      // add a config key/value
      await page.locator('[data-testid="im-channel-edit-add-row"]').evaluate((el: HTMLButtonElement) => el.click());
      const lastKey = page.locator('[data-testid^="im-channel-edit-row-key-"]').last();
      const lastValue = page.locator('[data-testid^="im-channel-edit-row-value-"]').last();
      await lastKey.fill('bot_token');
      await lastValue.fill('xoxb-test-live-token');

      let patchSent: any = null;
      await page.route('**/api/v1/im/channels/slack', async (route) => {
        if (route.request().method() === 'PATCH') {
          patchSent = await route.request().postDataJSON();
        }
        await route.continue();
      });

      await page.locator('[data-testid="im-channel-edit-save"]').evaluate((el: HTMLButtonElement) => el.click());
      await page.waitForTimeout(1200);

      expect(patchSent).toBeTruthy();
      expect(patchSent.config?.bot_token).toBe('xoxb-test-live-token');
      await expect(page.locator('[data-testid="im-channel-edit-modal"]')).not.toBeVisible();
    });

    test('edit modal cancel closes without posting', async ({ page }) => {
      await openImTab(page);
      await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-edit-modal"]')).toBeVisible();

      let patchCalled = false;
      await page.route('**/api/v1/im/channels/slack', async (route) => {
        if (route.request().method() === 'PATCH') patchCalled = true;
        await route.continue();
      });

      await page.locator('[data-testid="im-channel-edit-cancel"]').evaluate((el: HTMLButtonElement) => el.click());
      await page.waitForTimeout(500);
      expect(patchCalled).toBe(false);
      await expect(page.locator('[data-testid="im-channel-edit-modal"]')).not.toBeVisible();
    });

    test('test-send happy path posts chat_id and shows success toast', async ({ page }) => {
      await openImTab(page);
      await page.locator('[data-testid="im-channel-test-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-test-modal"]')).toBeVisible();

      await page.locator('[data-testid="im-channel-test-chat-id"]').fill('C0TEST_MOCKED');

      await page.route('**/api/v1/im/channels/slack/test-send', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: { sent: true, channel: 'slack' }, error: null }),
        });
      });

      await page.locator('[data-testid="im-channel-test-send"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('.toast.success, .toast').filter({ hasText: /成功|sent/i }).first()).toBeVisible({ timeout: 5_000 });
    });

    test('test-send 503 shows failure toast', async ({ page }) => {
      await openImTab(page);
      await page.locator('[data-testid="im-channel-test-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-test-modal"]')).toBeVisible();

      await page.locator('[data-testid="im-channel-test-chat-id"]').fill('C0X');

      await page.route('**/api/v1/im/channels/slack/test-send', async (route) => {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: "channel 'slack' not configured" }),
        });
      });

      await page.locator('[data-testid="im-channel-test-send"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('.toast').filter({ hasText: /失败|not configured/i }).first()).toBeVisible({ timeout: 5_000 });
    });

    test('test-send cancel closes modal without posting', async ({ page }) => {
      await openImTab(page);
      await page.locator('[data-testid="im-channel-test-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-test-modal"]')).toBeVisible();

      let sendCalled = false;
      await page.route('**/api/v1/im/channels/slack/test-send', async (route) => {
        sendCalled = true;
        await route.continue();
      });

      await page.locator('[data-testid="im-channel-test-cancel"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-test-modal"]')).not.toBeVisible();
      expect(sendCalled).toBe(false);
    });

    test('sensitive key value is rendered as password input', async ({ page }) => {
      await openImTab(page);
      await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await page.locator('[data-testid="im-channel-edit-add-row"]').evaluate((el: HTMLButtonElement) => el.click());
      const lastKey = page.locator('[data-testid^="im-channel-edit-row-key-"]').last();
      await lastKey.fill('bot_token');
      // After blur / on change the value input should get type=password
      const lastValue = page.locator('[data-testid^="im-channel-edit-row-value-"]').last();
      await lastKey.blur();
      await expect(lastValue).toHaveAttribute('type', 'password');
    });

    test('mobile viewport stacks edit modal buttons vertically', async ({ page, viewport }) => {
      if (!viewport || viewport.width >= 500) {
        test.skip(true, 'only mobile');
      }
      await openImTab(page);
      await page.locator('[data-testid="im-channel-edit-slack"]').evaluate((el: HTMLButtonElement) => el.click());
      await expect(page.locator('[data-testid="im-channel-edit-modal"]')).toBeVisible();
      const save = await page.locator('[data-testid="im-channel-edit-save"]').boundingBox();
      const cancel = await page.locator('[data-testid="im-channel-edit-cancel"]').boundingBox();
      expect(save && cancel).toBeTruthy();
      expect(Math.abs(save!.y - cancel!.y)).toBeGreaterThan(5);
    });
  });
  ```

- [ ] **Step 2**: 跑 — expect 全 FAIL(UI 不存在)。
  ```bash
  cd .worktrees/im-sendcard-aes
  docker compose -p prismv3 up -d --force-recreate nginx 2>&1 | tail -3
  sleep 2
  cd e2e
  npx playwright test im-admin-edit.spec.ts --project=desktop-chromium --reporter=line --retries=0 2>&1 | tail -10
  ```
  Expected: 7-8 FAIL.

- [ ] **Step 3**: Commit RED。
  ```bash
  cd ../  # back to worktree root
  git add e2e/tests/im-admin-edit.spec.ts
  git commit -m "test(e2e): RED phase — admin IM edit modal + test-send"
  ```

---

## Task 10: GREEN — Frontend Admin edit & test modals

**File**: Modify `frontend/admin.html`

- [ ] **Step 1**: `IMChannels` 组件增强。找到 `function IMChannels()` 定义,在 `const [channels, setChannels] = useState([])` 之后加 state:
  ```jsx
  const [editModal, setEditModal] = useState(null);  // { channel, is_enabled, rows: [{key, value}] }
  const [testModal, setTestModal] = useState(null);  // { channel, chat_id }
  const [actionBusy, setActionBusy] = useState(false);
  ```

- [ ] **Step 2**: row 按钮。找到 table row 的 `<td className="mono" …>{configured ? '已配置' : '未配置'}</td>` 之后、`</tr>` 之前,加新 td:
  ```jsx
  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
    <button data-testid={`im-channel-edit-${ch}`} className="btn ghost sm" style={{ marginRight: 6 }} onClick={() => setEditModal({
      channel: ch,
      is_enabled: !!(c.enabled || c.is_enabled),
      rows: Object.entries(c.config || {}).map(([k, v]) => ({ key: k, value: String(v) })),
    })}>编辑</button>
    <button data-testid={`im-channel-test-${ch}`} className="btn ghost sm" onClick={() => setTestModal({ channel: ch, chat_id: "" })}>测试</button>
  </td>
  ```
  同时扩展表头:
  ```jsx
  <thead><tr><th>频道</th><th>平台</th><th>状态</th><th>配置</th><th>操作</th></tr></thead>
  ```

- [ ] **Step 3**: 编辑 Modal JSX。在 IMChannels return 的最外层 div 内部顶部(在 sidebar 外、table 内容外)加:
  ```jsx
  {editModal && (
    <div data-testid="im-channel-edit-modal" style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.4)", zIndex:500, display:"flex", alignItems:"center", justifyContent:"center", padding:16 }} onClick={() => setEditModal(null)}>
      <div style={{ background:"var(--paper)", borderRadius:14, padding:24, maxWidth:600, width:"100%", maxHeight:"85vh", overflow:"auto", display:"flex", flexDirection:"column", gap:16, boxShadow:"0 20px 60px rgba(0,0,0,0.15)" }} onClick={e => e.stopPropagation()}>
        <div style={{ fontFamily:"var(--serif)", fontSize:18, fontWeight:500, color:"var(--ink)" }}>编辑 IM 渠道:{editModal.channel}</div>

        <label style={{ display:"flex", alignItems:"center", gap:10, fontSize:13 }}>
          <input type="checkbox" data-testid="im-channel-edit-enabled" checked={editModal.is_enabled} onChange={e => setEditModal({ ...editModal, is_enabled: e.target.checked })}/>
          <span>启用此渠道</span>
        </label>

        <div>
          <div style={{ fontSize:12, color:"var(--ink-3)", marginBottom:8 }}>配置字段(key / value)</div>
          <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
            {editModal.rows.map((r, i) => {
              const sensitive = /secret|token|key|password/i.test(r.key);
              return (
                <div key={i} style={{ display:"flex", gap:6, alignItems:"center" }}>
                  <input data-testid={`im-channel-edit-row-key-${i}`} className="input" style={{ flex:"0 0 180px", fontFamily:"var(--mono)", fontSize:12 }} placeholder="key" value={r.key} onChange={e => { const rows=[...editModal.rows]; rows[i]={...rows[i], key:e.target.value}; setEditModal({...editModal, rows}); }}/>
                  <input data-testid={`im-channel-edit-row-value-${i}`} type={sensitive ? "password" : "text"} className="input" style={{ flex:1, fontFamily:"var(--mono)", fontSize:12 }} placeholder="value" value={r.value} onChange={e => { const rows=[...editModal.rows]; rows[i]={...rows[i], value:e.target.value}; setEditModal({...editModal, rows}); }}/>
                  <button className="btn ghost sm" style={{ flex:"0 0 auto" }} onClick={() => { const rows=editModal.rows.filter((_,idx)=>idx!==i); setEditModal({...editModal, rows}); }}>✕</button>
                </div>
              );
            })}
            <button data-testid="im-channel-edit-add-row" className="btn ghost sm" style={{ alignSelf:"flex-start", marginTop:6 }} onClick={() => setEditModal({ ...editModal, rows:[...editModal.rows, { key:"", value:"" }] })}>+ 添加字段</button>
          </div>
        </div>

        <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
          <button data-testid="im-channel-edit-save" className="btn primary" style={{ width:"100%", justifyContent:"center", minHeight:44 }} disabled={actionBusy} onClick={async () => {
            setActionBusy(true);
            try {
              const config = {};
              for (const r of editModal.rows) {
                if (r.key) config[r.key] = r.value;
              }
              await PrismAPI.request('PATCH', `/im/channels/${editModal.channel}`, { json: { is_enabled: editModal.is_enabled, config } });
              toast(`${editModal.channel} 配置已保存`, 'ok');
              setEditModal(null);
              // reload channels
              const resp = await PrismAPI.request('GET', '/im/channels');
              setChannels(Array.isArray(resp.data) ? resp.data : []);
            } catch (e) {
              toast('保存失败: ' + e.message, 'err');
            }
            setActionBusy(false);
          }}>保存</button>
          <button data-testid="im-channel-edit-cancel" className="btn ghost" style={{ width:"100%", justifyContent:"center", minHeight:44 }} onClick={() => setEditModal(null)}>取消</button>
        </div>
      </div>
    </div>
  )}

  {testModal && (
    <div data-testid="im-channel-test-modal" style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.4)", zIndex:500, display:"flex", alignItems:"center", justifyContent:"center", padding:16 }} onClick={() => setTestModal(null)}>
      <div style={{ background:"var(--paper)", borderRadius:14, padding:24, maxWidth:440, width:"100%", display:"flex", flexDirection:"column", gap:14 }} onClick={e => e.stopPropagation()}>
        <div style={{ fontFamily:"var(--serif)", fontSize:17, fontWeight:500 }}>向 {testModal.channel} 发送测试卡片</div>
        <label style={{ display:"flex", flexDirection:"column", gap:6 }}>
          <span style={{ fontSize:11.5, color:"var(--ink-3)" }}>目标 chat_id</span>
          <input data-testid="im-channel-test-chat-id" className="input" value={testModal.chat_id} onChange={e => setTestModal({ ...testModal, chat_id: e.target.value })} placeholder="oc_xxxx / C0XXX / channel_id"/>
        </label>
        <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
          <button data-testid="im-channel-test-send" className="btn primary" style={{ width:"100%", justifyContent:"center", minHeight:44 }} disabled={actionBusy || !testModal.chat_id} onClick={async () => {
            setActionBusy(true);
            try {
              const r = await PrismAPI.request('POST', `/im/channels/${testModal.channel}/test-send`, { json: { target_chat_id: testModal.chat_id } });
              const sent = r?.data?.sent;
              if (sent) toast(`${testModal.channel} 发送成功`, 'ok');
              else toast(`${testModal.channel} 发送失败`, 'err');
              setTestModal(null);
            } catch (e) {
              toast('发送失败: ' + (e.message || e), 'err');
            }
            setActionBusy(false);
          }}>发送</button>
          <button data-testid="im-channel-test-cancel" className="btn ghost" style={{ width:"100%", justifyContent:"center", minHeight:44 }} onClick={() => setTestModal(null)}>取消</button>
        </div>
      </div>
    </div>
  )}
  ```

- [ ] **Step 4**: recreate nginx + 跑 e2e。
  ```bash
  cd ..  # worktree root
  docker compose -p prismv3 up -d --force-recreate nginx 2>&1 | tail -3
  sleep 2
  cd e2e
  npx playwright test im-admin-edit.spec.ts --reporter=line --retries=0 2>&1 | tail -8
  ```
  Expected: 8 pass desktop + 8 pass mobile = **16 passed**.

- [ ] **Step 5**: Commit。
  ```bash
  cd ..
  git add frontend/admin.html
  git commit -m "feat(admin): IM 渠道 edit + test-send modals (ADR-088 #4)"
  ```

---

## Task 11: Simplify + PJR

- [ ] **Step 1**: Load Simplify skill。3 subagent 并行(reuse/quality/efficiency)get diff `git diff develop..HEAD`。应用 findings。
- [ ] **Step 2**: PJR checks。
  ```bash
  docker compose -p prismv3 exec -T backend python -c "
  import ast, os
  files = [
      'app/services/credential_cipher.py',
      'app/services/im_adapter.py',
      'app/services/im_feishu.py',
      'app/services/im_slack.py',
      'app/services/im_discord.py',
      'app/api/v1/im.py',
      'app/main.py',
      'app/schemas/im.py',
  ]
  ok, fail = [], []
  for f in files:
      p = os.path.join('/app/backend', f)
      try:
          with open(p) as fh: ast.parse(fh.read(), filename=p); ok.append(f)
      except SyntaxError as e: fail.append((f, str(e)))
  print(f'AST OK: {len(ok)}, FAIL: {len(fail)}')
  for f,e in fail: print(f'FAIL {f}: {e}')
  from app.services.credential_cipher import CredentialCipher, encrypt_config_secrets, decrypt_config_secrets
  from app.services.im_feishu import FeishuAdapter
  from app.services.im_slack import SlackAdapter
  from app.services.im_discord import DiscordAdapter
  print('all imports OK')
  "
  ```
- [ ] **Step 3**: Commit Simplify fixes(如有)。

---

## Task 12: Merge + full regression + HANDOFF

- [ ] **Step 1**: Merge local no-ff。
  ```bash
  cd "E:/Agent program/PrismV3"
  git checkout develop
  git merge --no-ff redesign/im-sendcard-aes -m "Merge Session 4b: IM send_card + AES credential + Admin edit UI (ADR-088 偏离点清零)"
  ```
- [ ] **Step 2**: Full Playwright dual viewport。预期 ≥70 pass(现有 55 + 16 新 im-admin-edit - 已知 flaky 2)。
  ```bash
  docker compose -p prismv3 up -d --force-recreate nginx 2>&1 | tail -3
  cd e2e && npx playwright test --reporter=line --retries=0 2>&1 | tail -6
  ```
- [ ] **Step 3**: 更新 `DECISIONS.md` ADR-088 偏离点:标记 #2 send_card ✅ / I4 credential ✅ / #4 Admin UI ✅ 全部清零。
- [ ] **Step 4**: 更新 `HANDOFF-LOG.md` 新 Session 4b entry;明确列出用户自主真实账号测试步骤:
  - 飞书:/admin.html → IM 频道 → Feishu row → 编辑 → 填 `app_id / app_secret / encrypt_key / verification_token` → 保存 → 测试 → 输入 `oc_xxxx` chat_id → 发送;期望真实飞书群收到测试卡片
  - Slack:同上,填 `bot_token:xoxb-...` / `signing_secret:...`;测试时 `C0XXXXXX`
  - Discord:同上,填 `bot_token:...` / `public_key:<64hex>`;测试时 channel_id
- [ ] **Step 5**: Final commit。
  ```bash
  git add DECISIONS.md HANDOFF-LOG.md
  git commit -m "docs(handoff): Session 4b complete — ADR-088 偏离点 #2/#3/#4 清零"
  ```

---

## Self-Review(plan)

1. **Spec coverage**:spec §2 R1/R2/R3 对应 tasks 5-7 / 3 / 8 + 10 ✓;§7.1 12 unit → tasks 2+4 覆盖 ✓;§7.2 8 e2e → task 9 ✓
2. **Placeholders**:0 TBD/TODO,每步含代码
3. **Type consistency**:`CredentialCipher` / `IMOutgoingCard` / `IMCardAction` 签名从 Session 3 + Session 4a 沿用 ✓
4. **ADR-088 偏离点映射**:#2 → T5/T6/T7 send_card impl ✓ / #3 (I4) → T3 cipher + T8 PATCH encrypt ✓ / #4 → T10 Admin modal ✓

---

## Execution notes

- 单 session 完整执行估 3-4h context。中途可跳过 simplify 第 3 subagent 的 micro 建议,只取 actionable
- Playwright 外部 HTTP mock **仅为** CI 确定性;production 代码路径与 user 真实账号路径完全一致
- 用户在 /admin.html 填真 credentials → 点"测试"即生产路径(route intercept 只在 CI 自动化里生效,用户浏览器不受影响)
- 一旦 detect scope creep(比如想顺手给 telegram 加 send_card)→ halt + blocker.md
