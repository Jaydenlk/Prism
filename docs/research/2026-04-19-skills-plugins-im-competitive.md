# Skills, Plugins & IM Integrations — Competitive Research for Prism v2

> Date: 2026-04-19
> Audience: Prism v2 product + engineering
> Scope: Skills marketplaces, conversational plugin authoring, IM channel architecture
> Method: Exa web search + fetch; grounding in Prism source files at `backend/app/services/` and `frontend/Prism.html`

---

## TL;DR

| Area | Winning pattern | Who does it best | Prism gap |
|---|---|---|---|
| Skills packaging | Single `SKILL.md` + YAML frontmatter + progressive disclosure | Claude Code (Agent Skills open standard) [1][3][6] | Already partial — file layout fine, but no progressive-disclosure loading |
| Skill discovery | Git-hosted marketplace catalogs (`owner/repo`) separated from install | Claude Code `/plugin marketplace add` [13][14][15] | Missing: no marketplace concept, only per-skill install |
| Plugin authoring | Typed CLI scaffold + hot reload + remote-debug token | Dify `dify plugin init` / remote daemon [11][12] | Prism has conversational builder — complementary, not redundant |
| Plugin taxonomy | Separate Tool / Model / Extension / Agent-Strategy / Data-Source / Trigger | Dify [2][9][10] | Prism has only "Plugin" (monolithic) |
| IM transport | Dual-mode (WebSocket stream + HTTP webhook) per channel | DingTalk / Slack / Feishu all offer both [16][17][18][20] | Prism has Feishu WS + WeCom webhook, but no Slack/Discord/DingTalk |
| IM security | Per-platform AES + signature + idempotent msg_id dedup | WeCom (AES-256-CBC + HMAC-SHA1) / Feishu (SHA256 signature) [19][20][21] | Prism has dedup + signature; fine |
| Unified adapter | Standard `IMIncomingMessage` dataclass, handler callback | Bot Framework activity handler / NextBridge [23][26] | Prism already has it (`im_adapter.py`) — keep and extend |
| Monetization | Usage-based revenue share, OpenAI model | GPT Store [4][5] | Not applicable for self-hosted, but enterprise billing relevant |

---

## Part 1 — Skills Market (Behavior Packs)

### 1.1 Claude Code Agent Skills

**Structure** ([1][3][6]):

```text
my-skill/
├── SKILL.md           # required, YAML frontmatter + markdown
├── scripts/           # optional — zero-context execution
├── references/        # optional — loaded on-demand
└── assets/            # optional — templates, binaries
```

Frontmatter fields ([3][6]):

| Field | Required | Purpose |
|---|---|---|
| `name` | no (falls back to dir) | Slash-command name, lowercase/hyphens, ≤64 chars |
| `description` | **yes** (de facto) | Up to 1024 chars — **this is what drives auto-activation** |
| `user-invocable` | no (default `true`) | Whether user can type `/skill-name` directly |
| `disable-model-invocation` | no | Prevent Claude auto-triggering |
| `allowed-tools` | no | Whitelist, e.g. `Read Grep Bash(pdftotext:*)` — removes permission prompts |
| `agent` | no (default `claude-code`) | Execution agent type |

**Activation model** — "progressive disclosure" ([3]):

1. At startup, only `name` + `description` (~100–200 tokens each) are in context
2. When a user request semantically matches a skill's description, Claude asks permission (or auto-loads if allowed)
3. Full `SKILL.md` body loads only after activation
4. Supporting files (`scripts/`, `references/`) load on-demand when referenced by the SKILL.md

Activation is **LLM-reasoning based, not keyword matching**. Community empirical data: strong trigger descriptions → ~80%+ activation reliability vs ~50% baseline [3].

**Distribution** — two layers ([13][14][15]):

- **Marketplaces** are git repos with `.claude-plugin/marketplace.json` catalog
- **Plugins** bundle skills, slash-commands, agents, hooks, MCP servers
- User flow: `/plugin marketplace add anthropics/claude-code` → `/plugin install github@claude-plugins-official`
- Three scopes: **user** (all projects), **project** (`.claude/settings.json`), **local** (single repo)
- Auto-update on startup; hot-reload via `/reload-plugins` after edit; directory watcher picks up `~/.claude/skills/` changes without restart [1]

### 1.2 Dify — Plugin Taxonomy (Skills ≈ "Agent Strategies" + "Extensions")

Dify deliberately avoids "skill" as a term; they split capability packs into **6 distinct plugin types** [2][9][10][12]:

| Type | Purpose | Analog in Claude Code |
|---|---|---|
| **Tool** | Third-party API/service (Google Search, Stable Diffusion) | MCP server |
| **Model** | LLM/embedding/rerank/TTS provider | (no direct analog) |
| **Extension** | Simple HTTP endpoint (Ingress-like) | Hook / webhook |
| **Agent Strategy** | Reasoning logic (ReAct, Function Calling, CoT) | Subagent / skill |
| **Data Source** | Knowledge-pipeline source | (via MCP) |
| **Trigger** | Third-party event → workflow execution | Hook on event |

Each plugin is a folder with `manifest.yaml` + Python implementation under `strategies/` or `tools/`. Permission system explicit at init: `Backwards Invocation` toggles (Tools, Models, Moderation, Apps, Storage) [2][12].

**Distribution**: Dify Marketplace (hosted), GitHub URL, or local `.difypkg` file [9]. Marketplace supports **Bundles** (curated plugin collections) — equivalent to Claude Code's "plugin".

### 1.3 Coze / 扣子

Plugin = tool collection callable by the agent [7][27]. Three practical categories:

1. **Code plugins** — hosted in Coze IDE, Node.js or Python, 50 QPS/plugin, 250MB dep limit, 100 tools/plugin [7]
2. **No-auth plugins** — direct HTTP, no OAuth/token, for public APIs
3. **Authorized plugins** — OAuth/API-key wrapped

Bot-centric UX: user assembles an agent from workflows + plugins + knowledge bases. Distribution mostly **internal to Coze Studio** (no open marketplace like Dify/Claude Code). Chinese ecosystem specifics: tight integration with 豆包 / 飞书 as delivery channels; sensitive-data review required before publish.

### 1.4 ChatGPT GPTs Store

Content + monetization model, not developer packaging:

- **No file format** — "Build a GPT" is a form-based chat builder; no YAML/JSON manifest exposed to creators [4]
- **Moderation**: automated + human review; users can report; brand-guideline compliance; domain verification + Builder Profile required for store listing [4][5]
- **Monetization** (as of 2026): usage-based revenue share from Plus/Team/Enterprise subscription pool; "Value Contribution" algo weights session depth + task completion + retention (not raw click count); Native Actions allow ~4% transaction fee on in-chat commerce; US-only initially [4][5]
- **Discovery**: leaderboard + category taxonomy (DALL·E, writing, research, programming, education, lifestyle); featured list curated by OpenAI [4]

### 1.5 Comparison — Skills / Behavior Packs

| Axis | Claude Code Skills | Dify Plugins | Coze Plugins | GPTs |
|---|---|---|---|---|
| Package format | Dir + `SKILL.md` (YAML+MD) | Dir + `manifest.yaml` + Python | IDE-hosted + schema | Opaque (form-config) |
| Install UX | `/plugin install name@market` | UI upload / marketplace / GitHub / .difypkg | Bot-builder UI | ChatGPT Store UI |
| Discovery | Git-repo marketplaces (decentralized) | Hosted Marketplace (centralized) | Inside Coze Studio | GPT Store (centralized) |
| Versioning | Git tag + marketplace.json | manifest `version` field | Plugin version published | Implicit (editor state) |
| Enable/disable | `/plugin enable/disable`, per-scope | Toggle in workspace | Bind/unbind to bot | N/A (public or private) |
| Sandboxing | `allowed-tools` whitelist; scripts = subprocess | Plugin daemon process isolation | Hosted sandbox (Deno+Pyodide for Coze Studio workflows) [7][28] | OpenAI server-side only |
| Progressive load | Yes (metadata only until matched) | No (full manifest parsed) | No | N/A |
| Open standard | Agent Skills open standard [6] | Dify-specific | Coze-specific | Proprietary |

**Key insight**: Claude Code's progressive-disclosure + decentralized marketplace is the model most aligned with Prism's self-hosted ethos. Dify's 6-type taxonomy is the most mature for production AI platforms. Coze's bot-binding UX is worth copying for end-user simplicity. GPTs' lessons are mostly about moderation + monetization, not packaging.

---

## Part 2 — Plugin Builder (Conversational Plugin Authoring)

### 2.1 Claude Code `/plugin` — marketplace-first, not builder-first

Claude Code's philosophy: **plugins are data, not code**. Authoring = create a directory with `commands/`, `skills/`, `agents/`, `hooks/`, push to GitHub, run `/plugin marketplace add your-org/my-plugin` [13][14][15]. There is **no conversational builder** — building a plugin "takes under 5 minutes, no build step, no toolchain, no approval" [14].

### 2.2 Dify — CLI + hot-reload + remote daemon

`dify plugin init` scaffolds a Python project [11][12]:

```text
my-plugin/
├── manifest.yaml           # plugin metadata + permission requests
├── main.py                 # entry point
├── strategies/ or tools/   # implementation
├── _assets/icon.svg
├── README.md / PRIVACY.md / GUIDE.md
└── .env                    # INSTALL_METHOD=remote + REMOTE_INSTALL_HOST
```

Development loop [11]:

1. `dify plugin init` — pick type (tool / agent-strategy / llm / etc.)
2. `python -m main` — starts local daemon
3. `.env` has a debug token from Dify workspace → daemon connects to running Dify instance
4. File changes → hot reload (`PLUGIN_HOT_RELOAD=true` env var) [11]
5. Test in Dify UI immediately
6. `dify plugin package ./my-plugin` → `.difypkg` → upload or submit to Marketplace

Notable: permission prompts at init (Backwards Invocation: Tools/Models/Moderation/Apps/Storage), forcing developer to declare scope up-front.

### 2.3 Coze — IDE-first, no local dev

Coze has a **web IDE** where you write Python/Node.js directly, define in/out schema via form, and click "Publish" [7]. No local CLI. Tradeoff: lower barrier (no tooling setup) but vendor lock-in — you cannot `git clone` a plugin.

### 2.4 Cursor — VSCode extensions (unchanged)

Cursor inherits VSCode's extension model: `package.json` manifest, `.vsix` package, Extensions Marketplace. Plugin builder is manual TypeScript coding. Relevant pattern for Prism: **extension manifest enumerating contributes.commands + activationEvents**.

### 2.5 Zapier — CLI + Web Builder (dual path)

Zapier's Platform has **two authoring modes** [24][25]:

- **Platform CLI** (`zapier-platform-cli`) — `zapier init`, Node.js App object, `zapier push`, `zapier promote`
- **Platform UI** (Web Builder) — form-based, for non-coders; can `zapier convert 1234 my-app` to CLI but not reverse

Authentication schemes baked into manifest (Basic / Digest / Session / OAuth2 / Custom), Zapier auto-stores auth response tokens in `bundle.authData`. Key lesson for Prism: **auth as a first-class manifest field** with declarative schemas, not ad-hoc.

### 2.6 Comparison — Plugin Authoring

| Axis | Claude Code | Dify | Coze | Cursor / VSCode | Zapier |
|---|---|---|---|---|---|
| Authoring mode | File + git | CLI + local daemon | Web IDE only | Local TS + SDK | CLI + Web Builder (dual) |
| Manifest format | `plugin.json` + `SKILL.md` YAML | `manifest.yaml` (YAML) | Form-captured JSON schema | `package.json` | JS App object (no file) |
| Hot reload | Directory watch | Yes (`PLUGIN_HOT_RELOAD`) [11] | N/A (cloud-only) | VSCode dev host | `zapier invoke` local mode |
| In-platform testing | `claude --plugin-dir ./p` | Remote daemon via debug token | Inline in IDE | Extension dev host (F5) | `zapier test` + `zapier invoke` |
| Publication flow | Push to GitHub, register marketplace | `.difypkg` → upload or Marketplace submit | Publish button (moderation) | `vsce publish` | `zapier push` → `promote` |
| Conversational builder | ❌ | ❌ | ❌ (form-based, not chat) | ❌ | ❌ |

**Nobody has a production conversational plugin builder.** Prism's chat-driven PluginBuilder (seen at `frontend/Prism.html:1643 PluginsPage`, SSE-streamed) is an actual differentiator. Lesson: pair it with a conventional YAML export + permission prompts (Dify-style) so power users can graduate from chat to file editing.

---

## Part 3 — IM Integration (Bot / Agent Channels)

### 3.1 Slack

Two transports [16][17][18]:

| | HTTP (Events API) | Socket Mode (WebSocket) |
|---|---|---|
| Direction | Slack → your server | Your server → Slack |
| Protocol | Stateless request-response | Stateful bi-directional, 1 of ≤10 concurrent |
| Public URL | Required (HTTPS) | Not needed (firewall-friendly) |
| Retries | 3× auto-retry | Dropped events gone on disconnect |
| Scaling | Horizontal via LB | Single connection bottleneck |
| Marketplace listing | **Required** | Not allowed for Slack Marketplace apps |
| Best fit | Production, interactive (modals, buttons) | Dev/local, on-prem firewall |

Signing verification: `X-Slack-Signature` (`v0=HMAC-SHA256(signing_secret, "v0:timestamp:body")`) + 5-minute timestamp freshness check. Slash commands + Interactive components use a separate Request URL and `response_url` (bypasses channel posting perms, valid 30 min) [18].

### 3.2 Feishu / 飞书 (Lark)

Two transports [19][20][21][22]:

- **Webhook mode**: Public HTTPS endpoint; URL verification challenge (type=`url_verification`, echo `challenge` back within 1s) [20]; signature `SHA256(timestamp + nonce + encrypt_key + body)` compared to `X-Lark-Signature` (timing-safe) [20]
- **WebSocket / long-connection mode**: Outbound to Feishu, SDK handles signature; no public endpoint needed

Critical gotcha surfaced by OpenClaw bug report [19]: Feishu's **initial** URL-verification ping sends an encrypted body **without** the `X-Lark-Signature` header. Servers must accept the verification request without signature but reject all subsequent requests lacking signature. Many implementations get this wrong.

Message cards: interactive with **separate callback URL** configured in developer console (may be same endpoint, but must be declared) [20]. Card responses include `X-Refresh-Token` for idempotency [20].

### 3.3 WeChat Work / 企业微信

Encrypted callback model [19][29][30]:

- URL verification: GET with `msg_signature` + `timestamp` + `nonce` + `echostr`; verify `sha1(sort([token,ts,nonce,echostr]))` == `msg_signature`; AES-decrypt `echostr` and return plaintext
- Event: POST XML `<Encrypt>...</Encrypt>`; verify same HMAC-SHA1 signature, AES-256-CBC decrypt with `EncodingAESKey` (43-char Base64 → 256-bit key); IV = first 16 bytes of key; PKCS#7 padding to 32-byte block
- Two channel flavors: **应用消息** (app messages, requires enterprise app + agent_id) vs **群机器人** (group bot, webhook key only, no AES required)
- AI Bot (智能机器人) API mode (2025/12 spec): supports streaming responses, requires `msgid`-based dedup (retry delivery possible) [30]

### 3.4 DingTalk / 钉钉

Two transports [16][17]:

- **Stream mode** (recommended): Outbound WebSocket via `clientId` (AppKey) + `clientSecret` (AppSecret); SDK auto-refreshes access token; subscribes to topics (`/v1.0/im/bot/messages/get` for bot messages, `/v1.0/card/instances/callback` for card callbacks, `*` for events) [17]
- **Callback mode**: Public HTTPS webhook, similar signature pattern to WeCom

Stream protocol: ACK required within 15s or retry triggers; `specVersion: 1.0`, types `SYSTEM` / `EVENT` / `CALLBACK`; keep-alive via `ping` [17]. Group @mention detection uses `isInAtList` flag (no entity parsing).

### 3.5 Discord

Two transports, mutually exclusive per app [31][32]:

- **Gateway** (WebSocket): Bot identifies with token + intents; receives `INTERACTION_CREATE` alongside all other events (messages, reactions); requires privileged intents for message content/member data
- **HTTP Interactions Endpoint**: Configure URL; Discord signs requests with Ed25519 (`X-Signature-Ed25519` + `X-Signature-Timestamp`); must respond to `PING` (type 1) handshake; token valid 15 min for follow-up messages

Slash commands and components always flow through interactions, regardless of transport. Webhooks (one-way, no bot user, just an unguessable URL) are separate from Interactions and ideal for notifications only [31].

### 3.6 Microsoft Teams

Bot Framework v4 SDK [23][26]:

- Single endpoint `/api/messages` receives all `Activity` objects
- Activities routed by `ActivityHandler` (base) or `TeamsActivityHandler` (Teams-specific events like `OnTeamsChannelCreatedAsync`, `OnInvokeActivityAsync`)
- Middleware pattern: `context.Next()` chains handlers [26]
- Azure Bot Service fronts delivery — bot registers `botId` in `manifest.json`; `validDomains` must include endpoint domain + `token.botframework.com` for OAuth
- 15-second processing SLA — retry after [23]
- Same bot can serve Teams, Skype, Webchat, etc. (cross-channel unified)

### 3.7 Architecture pattern — how mature platforms unify IM channels

Common shape across Dify, Coze, Bot Framework, NextBridge [23][26]:

```
┌──────────────────┐  adapter-specific signature+decrypt
│ IM Webhook / WS  │ ──────────────────────┐
└──────────────────┘                       │
     per-platform                          ▼
                             ┌────────────────────────────┐
                             │ Adapter layer              │
                             │  - Normalize → UnifiedMsg  │
                             │  - Dedup by platform_msgid │
                             │  - Auth (bind platform_uid │
                             │    → internal user)        │
                             └────────────┬───────────────┘
                                          ▼
                             ┌────────────────────────────┐
                             │ Handler / Turn / Router    │
                             │  - Slash command           │
                             │  - Agent invocation        │
                             │  - Interactive response    │
                             └────────────┬───────────────┘
                                          ▼
                             ┌────────────────────────────┐
                             │ Adapter.send(UnifiedMsg)   │
                             │  - Split long messages     │
                             │  - Platform markdown dialect│
                             │  - Card rendering          │
                             └────────────────────────────┘
```

Prism already implements this shape in `backend/app/services/im_adapter.py` (`IMAdapter` ABC, `IMIncomingMessage` / `IMOutgoingMessage` dataclasses) — see [Part 4](#part-4--recommendations-for-prism-v2).

### 3.8 Security & operational table

| Platform | URL verify | Signature | Payload encryption | Idempotency | Msg length cap |
|---|---|---|---|---|---|
| Slack | (none, just signing) | HMAC-SHA256(signing_secret) + 5-min ts | HTTPS only | Event dedup on `event_id` | 4000 chars/text block |
| Feishu webhook | `url_verification` echo challenge in 1s [20] | `SHA256(ts+nonce+key+body)` → `X-Lark-Signature` [21] | Optional AES-256 (if encrypt_key set) [21] | `msg_id` field | 4000 chars [Prism adapter] |
| Feishu WS | via SDK (internal) | SDK-managed | SDK-managed | `msg_id` | same |
| WeCom webhook | GET with echostr AES-encrypted [29][30] | HMAC-SHA1 `msg_signature` | **Required** AES-256-CBC + PKCS#7 | `msgid` per bot [30] | 2048 chars |
| DingTalk stream | N/A (SDK) | SDK-managed via app token | SDK-managed | Event dedup + ACK within 15s | ~3800 chars (split) [17] |
| Discord HTTP | `PING` type-1 handshake | Ed25519 (`X-Signature-Ed25519`) [31] | HTTPS only | `interaction_id`, 15-min token | 2000 chars |
| Discord Gateway | via bot token + intents | Token + intents declaration | WSS | `sequence_number` + resume | same |
| Teams | Azure Bot Service fronts | JWT from Azure AD in Authorization | HTTPS | `activity.id` | 28 KB payload |
| Telegram | (long poll) | bot token in URL | HTTPS | `update_id` monotonic | 4096 chars |

---

## Part 4 — Recommendations for Prism v2

**Prism grounding (files actually inspected):**

- `backend/app/services/skill_install_service.py` (275 lines) — INSERT/UPSERT into `skill_installs` table, Redis cache key `skill_install:status:{user_id}:{skill_name}`, TTL 600s. **Flat install API, no marketplace abstraction.**
- `backend/app/services/im_adapter.py` (157 lines) — Clean `IMAdapter` ABC; `IMIncomingMessage` has `channel`, `platform_user_id`, `platform_chat_id`, `text`, `msg_id`, `raw`. Already handles dedup intent via `msg_id` (ADR-070 ref). **Only 3 channels declared: feishu / wecom / telegram.**
- `backend/app/services/` IM implementations: `im_feishu.py` (494 lines), `im_wecom.py`, `im_telegram.py`, `im_gateway.py` (459 lines), `im_binding_service.py`, `im_dedup.py`. No Slack/Discord/DingTalk/Teams.
- `backend/app/api/v1/im.py` (441 lines) — Has `/im/webhook/feishu`, `/im/webhook/wecom` (GET+POST), `/im/bindings`, `/im/channels`. No Slack/Discord/DingTalk routes.
- `backend/app/api/v1/plugins.py` (593 lines) — `/plugins/load`, `/plugins/export-cc`, `/plugins/validate`. Single "Plugin" type with `plugin.yaml` + Pydantic validation (ADR-055); CC-compat export (ADR-054). **No taxonomy split (tool vs agent-strategy vs extension).**
- `frontend/Prism.html:1245` `SkillsPage` — install tabs `local_file` / `github` / `custom_md` (three paths, already implemented, tests exist per data-testid). `frontend/Prism.html:1643` `PluginsPage` — conversational builder with SSE stream (`openStream`, `builderRunning` state).

**Now the recommendations, ordered by priority:**

### R1 — Introduce Marketplace abstraction for Skills (P0)

**Pattern**: Git-repo-as-catalog (Claude Code model)

**Current state**: `SkillInstallService.install()` takes `source` ∈ {local_file, github, custom_md} as a flat string. No grouping of skills by publisher, no "add marketplace" vs "install skill" separation, no catalog metadata.

**Proposed change**: Add `marketplace_registry` table (url, name, last_fetched_at, catalog_json) + `POST /skills/marketplaces` to register a git URL containing a `.prism-plugin/marketplace.json` catalog. UI: 4th tab "Marketplace" in `SkillsPage` showing registered catalogs + their skill lists. Install still writes to `skill_installs`, but `source` gets a new value `marketplace:{name}` and `marketplace_id` FK. Rationale: lets users subscribe to curated lists (e.g. "Prism official", "team internal") without one-by-one GitHub URL entry.

### R2 — Split Plugin into typed taxonomy (P0)

**Pattern**: Dify 6-type split (Tool / Model / Extension / Agent-Strategy / Data-Source / Trigger)

**Current state**: `plugins.py` treats every plugin uniformly; `plugin.yaml` schema (ADR-055) has one shape. Prism's `PluginsPage` conversational builder generates one kind of artifact.

**Proposed change**: Extend `plugin.yaml` with a required `type:` field (enum: `tool | agent_strategy | extension | trigger`), and make the Pydantic validator dispatch to type-specific sub-schemas. PluginBuilder chat should ask "what kind?" as first question, then tailor follow-up prompts (tool asks for OpenAPI schema, agent_strategy asks for reasoning pattern, trigger asks for event source). This matches Dify's mental model and lets the `plugins_library` table filter by capability. Backward compat: untyped plugins default to `type: tool`.

### R3 — Add progressive-disclosure loading for Skills (P1)

**Pattern**: Claude Code metadata-only startup + on-match body load

**Current state**: `skill_install_service.py` only records install metadata in DB; skill body loading strategy not visible in this file, but executor-side `skills_registry` is imported. Likely all installed skills' markdown is injected into system prompt at session start.

**Proposed change**: In the executor's skills_registry, at session start inject only the `{name, description}` pair for each installed skill (~100–200 tokens each). Add a `load_skill(name)` tool to the agent; when description matches user intent, model calls `load_skill` → full `SKILL.md` body streamed into next turn. Saves context at 50+ installed skills. Requires ADR on the load-skill tool surface and caching of parsed frontmatter in Redis.

### R4 — Add Slack + Discord adapters (P1)

**Pattern**: `IMAdapter` subclass, same as existing Feishu/WeCom/Telegram

**Current state**: `im_adapter.py` declares only feishu/wecom/telegram channels. No Slack/Discord code in `backend/app/services/`. Prism's architecture (clean ABC, handler callback) makes adding channels straightforward.

**Proposed change**: Implement `im_slack.py` (Socket Mode for dev + Events API for prod, choose via env `IM_SLACK_MODE`) and `im_discord.py` (HTTP Interactions endpoint with Ed25519 signature verification). Reuse `im_dedup.py` (event_id / interaction_id). Add routes `/im/webhook/slack`, `/im/webhook/discord` to `api/v1/im.py`. Priority: Slack first (broader enterprise reach), Discord second (dev/community relevance).

### R5 — Permission declaration in plugin manifest (P1)

**Pattern**: Dify's `Backwards Invocation` toggles at plugin init (Tools/Models/Moderation/Apps/Storage) [2][12]

**Current state**: Prism's `plugin.yaml` does not require explicit permission declaration. Executor's plugin host presumably grants all capabilities the plugin asks for at runtime.

**Proposed change**: Add `permissions:` block to `plugin.yaml` (allowed_tools, allowed_models, can_call_other_plugins, can_write_sessions, storage_scope). Validator rejects calls outside declared scope. PluginBuilder should ask "what permissions does this plugin need?" and surface a consent screen to the installer showing the declared capabilities. This aligns with Claude Code's `allowed-tools` frontmatter on skills.

### R6 — Add `plugin dev` CLI with hot reload (P1)

**Pattern**: Dify `dify plugin init` + `PLUGIN_HOT_RELOAD=true`

**Current state**: PluginsPage is chat-based; developers writing complex plugins need file-based workflow. Prism exposes `POST /plugins/load` (takes `plugin_dir` absolute path) — good primitive but no local-dev loop.

**Proposed change**: Ship a `prism-cli` (Python) with `prism plugin init`, `prism plugin dev` (watches dir, re-calls `/plugins/load` on change, connects to running Prism instance via API token matching the PluginBuilder's debug surface), `prism plugin package` (zips + generates `plugin.yaml` checksum). Keep conversational builder as the on-ramp — graduate power users to CLI. Reuse `POST /plugins/validate` for pre-flight.

### R7 — Add DingTalk adapter (P2)

**Pattern**: DingTalk stream mode via WebSocket, same shape as Feishu WS

**Current state**: No DingTalk code. Some Chinese-market Prism users likely need this.

**Proposed change**: `im_dingtalk.py` using `dingtalk-stream-sdk-python` (or manual WS per [17]); topics `/v1.0/im/bot/messages/get` + `/v1.0/card/instances/callback`; ACK within 15s; auto-refresh access token. Config: AppKey + AppSecret in `im_channel_configs`. Markdown dialect differs from Feishu — add per-adapter `format_markdown()` helper to `im_adapter.py` base class.

### R8 — Message-card / interactive-component unified abstraction (P2)

**Pattern**: Block Kit (Slack) / Adaptive Cards (Teams) / Message Card (Feishu) / Template Card (WeCom) — each platform has its own rich-message spec

**Current state**: `IMOutgoingMessage` has only `text` field + `reply_to_message_id`. No structured-message support.

**Proposed change**: Add `IMOutgoingCard` dataclass with a provider-neutral schema (title, body, buttons, fields) and let each adapter translate to its native card format. Start with a minimal subset (header + body + 1–3 buttons) that all 5+ platforms support. Lets agents emit richer responses (e.g. "Approve / Deny" buttons for ask-permission flows, ADR-028).

### R9 — Skill/Plugin discovery page + search (P2)

**Pattern**: GPT Store categories + Dify Marketplace tags + Claude Code `/plugin` Discover tab

**Current state**: `SkillsPage` only lists currently-installed skills. No browse/discover surface.

**Proposed change**: Add `DiscoverPage` route that queries registered marketplaces' catalogs (R1) and shows tag-filtered browseable cards. Server-side: small FTS index (Postgres `tsvector` on name+description) over catalog_json. Low priority until multiple marketplaces exist.

### R10 — Idempotent delivery + retries at the adapter layer (P2)

**Pattern**: Slack's 3× retry w/ X-Slack-Retry-Num; DingTalk's ACK-or-retry; WeCom's `msgid` dedup [17][29][30]

**Current state**: `im_dedup.py` exists (per file listing), so dedup is implemented — but outbound retry semantics not visible. Adapters may swallow send failures (`im_adapter.py` contract says "log error but don't throw").

**Proposed change**: Add exponential-backoff retry wrapper around `IMAdapter.send()` (3 attempts, 1s/2s/4s) with terminal-state tracking in Redis `im_send:{msg_id}` (status + attempts). Emit `im_send_failed` event after terminal failure so the coordinator can decide fallback (e.g. email alert). Matches best-in-class reliability patterns without requiring adapter-specific code.

---

## Citations

[1] Extend Claude with skills — https://code.claude.com/docs/en/skills.md
[2] Dify Plugin — https://docs.dify.ai/plugins
[3] Claude Code Agent Skills (progressive disclosure) — https://prg.sh/notes/Claude-Code-Agent-Skills
[4] Introducing the GPT Store — https://openai.com/blog/introducing-the-gpt-store
[5] How the GPT Store Revenue Program Works (2026 Guide) — https://gptstorerevenueprogram.com/how-the-gpt-store-revenue-program-works-in-2026/
[6] Use Custom Agent Skills — https://nikiforovall.github.io/claude-code-rules/fundamentals/agent-skills/
[7] Coze plugin guide (CSDN) — https://devpress.csdn.net/v1/article/detail/157581703
[8] Coze plugin docs — https://www.coze.com/open/docs/guides/agent_plugin
[9] Dify plugin introduction (legacy docs) — https://legacy-docs.dify.ai/plugins
[10] Dify Agent Strategy Plugin — https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/agent-strategy-plugin
[11] Dify Plugin Development Setup (DeepWiki) — https://deepwiki.com/langgenius/dify-docs/9.2-plugin-development-setup
[12] Dify CLI — https://docs.dify.ai/en/develop-plugin/getting-started/cli
[13] Discover and install prebuilt plugins (Claude Code) — https://code.claude.com/docs/en/discover-plugins.md
[14] Claude Code Plugins guide (Morph) — https://www.morphllm.com/claude-code-plugins
[15] Customize Claude Code with plugins (Anthropic) — https://www.claude.com/blog/claude-code-plugins
[16] Comparing HTTP & Socket Mode (Slack) — https://docs.slack.dev/apis/events-api/comparing-http-socket-mode
[17] DingTalk Stream 协议描述 — https://open-dingtalk.github.io/developerpedia/docs/learn/stream/protocol
[18] Slack Socket Mode + slash commands — http://docs.slack.dev/apis/events-api/using-socket-mode
[19] Feishu URL verification bug (OpenClaw) — https://github.com/openclaw/openclaw/issues/58905
[20] Feishu message card security verification — https://open.larksuite.com/document/common-capabilities/message-card/getting-started/message-card-security-verification
[21] Feishu / Lark (Hermes Agent docs, signature formula) — https://hermes-agent.nousresearch.com/docs/user-guide/messaging/feishu
[22] go-lark SDK (URL challenge + middleware) — https://pkg.go.dev/github.com/go-lark/lark/v2
[23] Activity Handlers and Bot Logic (Teams) — https://learn.microsoft.com/en-us/microsoftteams/platform/bots/bot-concepts
[24] Zapier Platform CLI reference — https://github.com/zapier/zapier-platform/blob/main/packages/cli/docs/cli.md
[25] zapier-platform-cli README — https://github.com/zapier/zapier-platform-cli
[26] Teams Bot Framework Architecture (DeepWiki) — https://deepwiki.com/solution8-com/S8-Microsoft-Teams-Automations-Bots/3.2-bot-framework-architecture
[27] Coze Use Plugins — https://www.coze.com/open/docs/guides/agent_plugin
[28] Coze Studio Workflows (Oreate) — https://www.oreateai.com/blog/building-workflows-in-coze-studio-a-deep-dive-from-principles-to-implementation/e5afcf8ec9fb03830fbe5407e95f1e09
[29] 企业微信 ipad 协议加解密 — https://juejin.cn/post/7605542907118141492
[30] WeCom bot API (go-sphere/wecom-bot-api) — https://github.com/go-sphere/wecom-bot-api
[31] Discord Interactions Overview — https://docs.discord.com/developers/platform/interactions
[32] Discord Receiving & Responding — https://docs.discord.com/developers/interactions/receiving-and-responding

---

*End of document. Word count target 2500–4000; this doc ≈ 3200 words.*
