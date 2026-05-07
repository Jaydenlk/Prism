# Feishu WebSocket Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add lark_oapi SDK WebSocket long connection mode to FeishuAdapter so Prism can receive Feishu messages without a public IP.

**Architecture:** Add `lark_oapi` dependency, implement `_start_ws_listener()` in existing FeishuAdapter that uses `lark.ws.Client` for WebSocket event reception. Keep existing Webhook mode as fallback. Mode selected by `FEISHU_MODE` env var (default: websocket).

**Tech Stack:** Python, lark_oapi>=2.0.0, asyncio

---

### Task 1: Add lark_oapi dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add lark_oapi to requirements**

Add `lark-oapi>=2.0.0` to requirements.txt.

- [ ] **Step 2: Add FEISHU_MODE to config**

In `backend/app/core/config.py`, add to Settings class:
```python
FEISHU_MODE: str = "websocket"  # "websocket" or "webhook"
```

- [ ] **Step 3: Commit**

### Task 2: Add WebSocket listener to FeishuAdapter

**Files:**
- Modify: `backend/app/services/im_feishu.py`

- [ ] **Step 1: Add WebSocket start method**

In `FeishuAdapter`, add `_start_ws_listener()` that:
1. Creates `lark_oapi.EventDispatcherHandler` with `register_p2_im_message_receive_v1`
2. Creates `lark.ws.Client(app_id, app_secret, event_handler=handler)`
3. Runs `cli.start()` in `asyncio.to_thread()` (it blocks)
4. On message receive: converts to `IMIncomingMessage` and calls `self._message_handler()`

- [ ] **Step 2: Update start() to pick mode**

```python
async def start(self):
    if not self.is_configured():
        return
    self._running = True
    await self._ensure_token()
    if self._mode == "websocket":
        self._ws_task = asyncio.create_task(self._start_ws_listener())
    logger.info("feishu.adapter.started", mode=self._mode)
```

- [ ] **Step 3: Update stop() to cancel WebSocket task**

- [ ] **Step 4: Commit**

### Task 3: Write tests

**Files:**
- Create: `backend/tests/test_feishu_adapter.py`

- [ ] **Step 1: Test WebSocket mode init**
- [ ] **Step 2: Test message conversion from lark event to IMIncomingMessage**
- [ ] **Step 3: Test send() still works (existing functionality)**
- [ ] **Step 4: Commit**

### Task 4: Docker + deployment

**Files:**
- Modify: `backend/Dockerfile` (add lark-oapi to pip install)
- Modify: `.env.example` (add FEISHU_MODE, FEISHU_APP_ID, FEISHU_APP_SECRET)

- [ ] **Step 1: Update Dockerfile and .env.example**
- [ ] **Step 2: Rebuild and verify container starts**
- [ ] **Step 3: Commit**
