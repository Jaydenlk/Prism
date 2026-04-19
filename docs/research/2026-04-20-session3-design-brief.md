# Session 3 Design Brief — Skills Market + Plugin Builder + IM

> Date: 2026-04-20
> Scope: Redesign Skills Market, Plugin Builder, and IM channel support for Prism v2
> Inputs: `docs/research/2026-04-19-skills-plugins-im-competitive.md` (Parts 1/3/4), WebFetched official docs (2026-04-20)
> Word target: <1500

---

## 1. Feishu Bot (critical path)

### URLs (canonical, WebFetched 2026-04-20)

| Purpose | URL | Status |
|---|---|---|
| Self-built app registration | https://open.feishu.cn/document/home/introduction-to-custom-app-development/self-built-application | Title-only render; use open.feishu.cn/app portal directly |
| tenant/app access token (internal) | https://open.feishu.cn/document/server-docs/authentication-management/access-token/app_access_token_internal | OK |
| Send message API (v1) | https://open.feishu.cn/document/server-docs/im-v1/message/create | OK |
| Event subscription URL verify + signature | https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case | Title-only; algorithm corroborated via encrypt-key doc + Prism code |
| Encrypt-key AES spec | https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/encrypt-key-encryption-configuration-case | OK |
| Message card (interactive) | https://open.feishu.cn/document/server-docs/im-v1/message-card/send-message-cards-with-various-layouts | Title-only; use send-message endpoint with `msg_type=interactive` |
| Message-card security verify (Lark — **different algo!**) | https://open.larksuite.com/document/common-capabilities/message-card/getting-started/message-card-security-verification | OK |

### Auth model

- **tenant_access_token** via `POST /open-apis/auth/v3/tenant_access_token/internal` with `{app_id, app_secret}` → returns `tenant_access_token` + `expire` (typically 7200s). Refresh ≤30 min before expiry.
- All IM API calls use `Authorization: Bearer {tenant_access_token}`.
- Prism already implements this in `im_feishu.py:_ensure_token` (Redis key `feishu:tenant_token`, TTL cap 7000s).

### Signature verification — **two separate algorithms** (surprising finding)

| Context | Header | Algorithm | Key material |
|---|---|---|---|
| Event subscription webhook | `X-Lark-Signature` | `SHA256(timestamp + encrypt_key + body).hexdigest()` | `encrypt_key` |
| Interactive card callback | `X-Lark-Signature` + `X-Lark-Request-Timestamp` + `X-Lark-Request-Nonce` | `SHA1(timestamp + nonce + verification_token + body).hexdigest()` | **`verification_token`** (NOT encrypt_key) |

Prism's current `im_feishu.py:verify_signature` (lines 254-280) uses SHA-256 with encrypt_key and concatenates `timestamp + encrypt_key + body`. This matches event webhook **but will reject card callbacks** once we ship cards. Docstring also says "HMAC-SHA256" but implementation is plain SHA-256 — docstring/code drift.

### AES encryption (encrypt_key mode)

- Mode: `AES-256-CBC`, key = `SHA256(encrypt_key).digest()` (32 bytes)
- IV: first 16 bytes of `base64_decode(encrypted_payload)`; ciphertext = rest
- Padding: PKCS#7 (stripped after decrypt)
- Prism `im_feishu.py:decrypt_message` (lines 282-310) implements this correctly.

### URL verification handshake

- Incoming: `{"type": "url_verification", "challenge": "...", "token": "..."}`
- Respond: `{"challenge": "..."}` within 1 second
- **Gotcha** (per research [19]): initial ping may arrive without `X-Lark-Signature` header — server must accept it unsigned but reject subsequent unsigned events. Prism's handler (line 332) echoes challenge but does not have this bypass — verify before enforcing signature for all requests.

### Endpoints we'll call

| Endpoint | Method | Purpose |
|---|---|---|
| `/open-apis/im/v1/messages?receive_id_type={chat_id\|open_id\|union_id\|user_id\|email}` | POST | Send text/card; body `{receive_id, msg_type, content(JSON-string), uuid?}` |
| `/open-apis/im/v1/messages/{message_id}/reply` | POST | Reply to message |
| `/open-apis/auth/v3/tenant_access_token/internal` | POST | Refresh token |

Message types: `text`, `interactive` (card), `image`, `file`, `audio`, `media`, `post`, `share_chat`, `share_user`, `sticker`, `system`.

### Configuration needed (env vars already exist per `im_feishu.py`)

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_ENCRYPT_KEY` / `FEISHU_VERIFICATION_TOKEN`
- Webhook URL shape: `https://{prism-host}/api/v1/im/webhook/feishu` (already routed per `api/v1/im.py`)
- User registers in feishu developer console: create self-built app → "事件与回调" tab → paste URL → enable "接收消息 v2.0" permission

---

## 2. Slack Bot

### URLs (WebFetched 2026-04-20 — note api.slack.com → docs.slack.dev redirects)

| Purpose | URL |
|---|---|
| Events API overview | https://docs.slack.dev/apis/events-api/ |
| url_verification handshake | https://docs.slack.dev/reference/events/url_verification |
| Request signing | https://docs.slack.dev/authentication/verifying-requests-from-slack |
| Socket Mode | https://docs.slack.dev/apis/events-api/using-socket-mode |
| chat.postMessage | https://docs.slack.dev/reference/methods/chat.postMessage |
| Interactive components | https://api.slack.com/messaging/interactivity |

### Auth / signature

- **Signing secret** (from app admin → Basic Info); basestring = `v0:{X-Slack-Request-Timestamp}:{raw_body}`; sig = `v0=` + `HMAC-SHA256(signing_secret, basestring).hexdigest()`; compare against `X-Slack-Signature` header; reject if timestamp ±5 minutes from now.
- **Bot OAuth token** (`xoxb-…`) with scope `chat:write` for sending; **App-level token** (`xapp-…`) for Socket Mode only.

### URL verification handshake

- Incoming: `{"type": "url_verification", "challenge": "...", "token": "..."}`
- Respond 200 with one of: `text/plain` (echo challenge), `application/x-www-form-urlencoded` (`challenge=<value>`), or `application/json` (`{"challenge":"..."}`)

### Endpoints

- `POST https://slack.com/api/chat.postMessage` — body `{channel, text, blocks?, thread_ts?}`, auth `Authorization: Bearer xoxb-…`. Rate limit ~1 msg/sec/channel.
- `POST https://slack.com/api/apps.connections.open` (with xapp- token) → returns `wss://…` URL for Socket Mode.
- Event retries: 0s → 1m → 5m, each carrying `x-slack-retry-num` + `x-slack-retry-reason`. 3-sec ACK SLA.
- Socket Mode envelope types: `events_api` / `interactive` / `slash_commands`; ack = `{"envelope_id": "...", "payload": {}?}`. Max 10 concurrent WS; **not allowed for Marketplace-listed apps**.

### Config needed (new env vars)

- `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN` (`xoxb-…`)
- `SLACK_APP_TOKEN` (`xapp-…`, only if `IM_SLACK_MODE=socket`)
- `IM_SLACK_MODE=events|socket` (default `events`)

---

## 3. Discord Bot

### URLs

| Purpose | URL |
|---|---|
| Interactions receiving/responding | https://docs.discord.com/developers/interactions/receiving-and-responding |
| Interactions overview + endpoint setup | https://docs.discord.com/developers/interactions/overview |

### Auth / signature

- **Ed25519** signature (NOT HMAC). Signed blob = `{X-Signature-Timestamp}{raw_body}`. Verify using app's Ed25519 public key from Developer Portal → app General Info. Invalid sig → return 401 (Discord actively probes with bad sigs).
- Bot token (`Bot <token>`) for REST API calls; not needed for interactions endpoint validation.

### Handshake

- First interaction Discord sends = type 1 `PING`. Respond 200 with `{"type": 1}` (PONG).
- **Must send initial response within 3 seconds**; interaction token valid 15 minutes for follow-up messages.

### Response types (integer enum)

| Type | Name | Use |
|---|---|---|
| 1 | PONG | PING ack |
| 4 | CHANNEL_MESSAGE_WITH_SOURCE | Immediate message |
| 5 | DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE | "Bot is thinking…" (streaming friendly) |
| 6 | DEFERRED_UPDATE_MESSAGE | Defer component update |
| 7 | UPDATE_MESSAGE | Edit original |
| 8 | APPLICATION_COMMAND_AUTOCOMPLETE_RESULT | Autocomplete |
| 9 | MODAL | Popup modal |

### Config needed (new env vars)

- `DISCORD_PUBLIC_KEY` (hex Ed25519 pubkey), `DISCORD_APP_ID`, `DISCORD_BOT_TOKEN`
- Webhook URL: `https://{prism-host}/api/v1/im/webhook/discord` entered in Developer Portal → Interactive Endpoint URL

Dependency: `PyNaCl` (Ed25519 verify) — add to `requirements.txt`.

---

## 4. Skills Market redesign

### Current state (Prism)

- `frontend/Prism.html:1278` `SkillsPage`: 3 install tabs — `local_file` / `github` / `custom_md` + search + installed-skills list with enable/disable/view/uninstall
- `backend/app/services/skill_install_service.py`: flat `source` enum, writes `skill_installs` row, Redis cache `skill_install:status:{user_id}:{skill_name}` TTL 600s
- No marketplace concept; install is per-skill

### Target state (from research R1 + R3)

- **Add marketplace abstraction** (Claude Code model): git-repo-as-catalog with `.prism-plugin/marketplace.json`
- **Add 4th tab "Marketplace"** in SkillsPage — list registered catalogs, browseable skill cards, one-click install
- **Progressive disclosure** (R3, P1): executor injects only `{name, description}` at session start; add `load_skill(name)` agent tool

### Files to change

| File | Change |
|---|---|
| `backend/app/models/skill.py` | **New** `marketplace_registry` model (needs ADR, §7) |
| `backend/alembic/versions/<new>_marketplace_registry.py` | **New migration** |
| `backend/app/services/marketplace_service.py` | **New**: fetch + cache catalog JSON, sync job |
| `backend/app/services/skill_install_service.py` | Add `source="marketplace:{name}"` + FK `marketplace_id` |
| `backend/app/api/v1/marketplaces.py` | **New**: CRUD for marketplace URLs + `/sync` |
| `backend/app/api/v1/skills.py` | Add filter `?marketplace_id=…` for discovery |
| `frontend/Prism.html` SkillsPage | 4th tab "Marketplace" + catalog browser UI |
| `executor/app/skills_registry.py` (locate) | Progressive-disclosure loader (R3) |

---

## 5. Plugin Builder redesign

### Current state

- `frontend/Prism.html:1676` `PluginsPage`: conversational SSE builder (left pane) + library CRUD (right pane) + manual YAML-save modal fallback
- `backend/app/api/v1/plugins.py`: 3 endpoints (`/load`, `/export-cc`, `/validate`); single plugin shape per ADR-055
- No typed taxonomy; CC-compat export via ADR-054

### Target state (from research R2 + R5)

- **Typed manifest** (Dify model): `plugin.yaml` gets required `type: tool | agent_strategy | extension | trigger`
- **PluginBuilder branches by type** (first question: "what kind?"); per-type YAML sub-schemas (tool = OpenAPI schema; agent_strategy = reasoning pattern; trigger = event source)
- **Permission declaration block** `permissions: {allowed_tools, allowed_models, storage_scope, …}` (R5) — consent screen at install
- **Backward compat**: untyped plugins default to `type: tool`

### Files to change

| File | Change |
|---|---|
| `backend/app/schemas/plugin.py` | Add `type:` + `permissions:` fields + type dispatch in Pydantic validator (needs ADR — extends ADR-055) |
| `backend/app/api/v1/plugins.py` | `validate` handles dispatch; `load` records type |
| `backend/app/services/plugin_builder.py` (locate/create) | Typed prompt branches |
| `backend/app/models/plugin.py` | Add `plugin_type`, `permissions_json` columns (migration) |
| `frontend/Prism.html` PluginsPage | Type picker as first builder step; consent screen |

Research finding: nobody has a conversational builder → Prism's chat builder is a differentiator; keep, but pair with Dify-style typed manifest.

---

## 6. IM integration redesign

### Current state

- `backend/app/services/im_adapter.py`: clean `IMAdapter` ABC; channels declared `feishu | wecom | telegram`
- `backend/app/services/im_feishu.py`: webhook mode, token cache, URL verify, AES decrypt, text send (494 lines); **signature algorithm mismatch risk** vs card callbacks (§1)
- `backend/app/services/im_gateway.py`: ADR-070 dedup → binding lookup → TaskService.submit()
- `backend/app/api/v1/im.py`: routes `/webhook/feishu`, `/webhook/wecom` (GET+POST) only

### Target state (from research R4 + R7 + R8)

- **Fix Feishu card signature path** (SHA-1 + verification_token branch)
- **Add Slack adapter** — Events API default; Socket Mode opt-in
- **Add Discord adapter** — HTTP Interactions + Ed25519
- **(Deferred P2)** DingTalk adapter (stream mode); provider-neutral `IMOutgoingCard` dataclass

### Files to change

| File | Change |
|---|---|
| `backend/app/services/im_adapter.py` | Add `slack`, `discord` to channel enum; optional `IMOutgoingCard` dataclass (R8) |
| `backend/app/services/im_slack.py` | **New** — Events API + optional Socket Mode |
| `backend/app/services/im_discord.py` | **New** — Ed25519 verify + Interactions response |
| `backend/app/services/im_feishu.py` | Add second `verify_card_signature()` path (SHA-1 + verification_token); fix docstring drift |
| `backend/app/api/v1/im.py` | Add `POST /im/webhook/slack`, `POST /im/webhook/discord` |
| `backend/app/core/config.py` | New env vars (§2, §3) |
| `backend/requirements.txt` | Add `PyNaCl`, `slack-sdk` (optional) |
| `backend/app/services/im_gateway.py` | Add `slack` / `discord` to `_PLATFORM_MAX_LENGTH` (4000 / 2000) |

---

## 7. Schema changes — flagged for user authorization (CLAUDE.md six-principle #1)

| # | Change | Proposed ADR |
|---|---|---|
| S1 | New `marketplace_registry` table (id, url, name, last_fetched_at, catalog_json, created_by) | ADR-080 Skills Marketplace |
| S2 | `skill_installs.marketplace_id` FK + extend `source` enum value `marketplace:{name}` | ADR-080 (same) |
| S3 | `plugins_library.plugin_type` (enum) + `permissions_json` (JSONB) | ADR-081 Plugin Taxonomy (extends ADR-055) |
| S4 | `im_channel_configs` values for `slack` / `discord` (schema already JSONB-flexible; no DDL — just seed rows) | No new ADR (data only) |
| S5 (optional R8) | `IMOutgoingCard` schema + per-adapter card translators | ADR-082 IM Interactive Cards |
| S6 (optional R3) | Executor-side progressive-disclosure cache — Redis only, no DB | No ADR (cache layer) |

---

## 8. Blocker candidates for user brainstorm

1. **Marketplace scope** — new `marketplace_registry` table vs extend `skill_installs.source`? Former cleaner; the latter dodges migration. Decision gates ADR-080.
2. **Plugin type enum migration** — backfill `type='tool'` for existing rows? Or require re-save? Affects UX of users with existing plugin library.
3. **IM credential storage** — env vars (current Feishu pattern) vs DB `im_channel_configs.config` JSONB (AES-encrypted, per existing `ImChannelConfig` model) vs per-tenant `providers` pattern? Multi-tenant readiness differs dramatically.
4. **IM depth** — full bidirectional bot (send + receive + cards + slash commands) or just inbound webhook? Feishu already full; Slack/Discord scope is the open question.
5. **Deployment readiness** — does user have (a) Feishu tenant/app already? (b) Slack workspace with admin? (c) Discord app/server? Without these, E2E tests can only mock.
6. **Feishu card signature fix** — ship alongside R4, or standalone bugfix in current session (risk of cross-DOC refactor violation, CLAUDE.md unforbidden list #6)?
7. **Socket Mode vs Events API default** — Socket Mode dev-friendly but blocks Marketplace listing. Position Prism as self-hosted-only OK, but locks future hosted tier.
8. **Progressive-disclosure tool surface** — `load_skill(name)` as a new tool requires ADR on prompt injection budget at session start.

---

## 9. Canonical URLs for spec footnotes

**Feishu**: self-built app intro · tenant_access_token/internal · im/v1/messages · message-card cards · event-subscription URL-config · encrypt-key config · Lark message-card security (URL list under §1).

**Slack**: events-api · url_verification · verifying-requests (HMAC-SHA256 v0:) · socket-mode · chat.postMessage · interactivity (§2).

**Discord**: interactions/receiving-and-responding · interactions/overview (§3).

**Prism source**: `backend/app/services/im_feishu.py`, `im_adapter.py`, `im_gateway.py`, `api/v1/im.py`, `api/v1/plugins.py`, `services/skill_install_service.py`, `frontend/Prism.html` (SkillsPage L1278, PluginsPage L1676).

---

## 10. Estimated scope per subsystem

| Subsystem | Files touched | New LOC (rough) | ADRs | Days (sonnet-session-equiv) |
|---|---|---|---|---|
| Skills Marketplace (R1) | ~7 (backend 4, frontend 1, migration 1, model 1) | 400-600 | ADR-080 | 1-2 |
| Progressive disclosure (R3) | ~3 (executor skills_registry + tool + Redis cache) | 150-250 | Sub-ADR | 0.5-1 |
| Plugin taxonomy (R2) | ~5 (schema/model/migration/API/frontend) | 300-500 | ADR-081 | 1-2 |
| Plugin permissions (R5) | ~3 (schema + frontend consent + runtime enforce) | 200-300 | Extend ADR-081 | 0.5 |
| IM Slack adapter | ~4 (service + routes + config + test) | 500-700 | none | 1 |
| IM Discord adapter | ~4 (service + routes + config + test) | 350-500 | none | 0.5-1 |
| Feishu card sig fix | 1 (`im_feishu.py`) | 30-50 | none | 0.25 |
| IM interactive card abstraction (R8) | ~5 | 400-600 | ADR-082 | 1-2 |

**Total session-3 scope**: 6-10 sonnet-equivalents. Recommend split into two DOCs: DOC-SK (Skills+Plugins, R1/R2/R3/R5) and DOC-IM2 (R4 Slack+Discord+Feishu fix), each one PR per CLAUDE.md.

---

*End of brief — word count ≈ 1460.*
