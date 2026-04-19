# Session 3 Design: Skills Marketplace + Plugin Taxonomy + IM Integration Expansion

**Date**: 2026-04-20
**Branches planned**: `redesign/doc-sk` (Phase 1) + `redesign/doc-im2` (Phase 2) off `develop`
**DOC assignment (new)**: DOC-SK = Skills/Plugins redesign; DOC-IM2 = IM adapter expansion
**ADR allocation (available slots 086–089 between DOC-09 and DOC-10)**:
- ADR-086 — Skills Marketplace Registry
- ADR-087 — Typed Plugin Manifest + Permissions
- ADR-088 — IM Interactive Cards + Multi-Channel (Slack/Discord)
- ADR-089 — (reserved for Progressive-Disclosure Skills, deferred P2)

---

## 1. Source of truth

Primary design brief: `docs/research/2026-04-20-session3-design-brief.md` (WebFetched 2026-04-20, 32-source competitive + all official docs verified).

Competitive research: `docs/research/2026-04-19-skills-plugins-im-competitive.md` Parts 1/3/4 (10 recs).

This spec **overlays decisions on top of the brief**; the brief is authoritative for endpoint shapes, signature algorithms, env-var names.

---

## 2. Scope — Phase 1 (DOC-SK)

**In scope:**
- **S1. Skills Marketplace abstraction** (R1, P0) — new `marketplace_registry` table, 4th install tab in SkillsPage, catalog-driven discovery, one-click install.
- **S2. Typed plugin manifest** (R2, P0) — `plugin.yaml` gets required `type: tool | agent_strategy | extension | trigger`; PluginBuilder branches per type; migration backfills existing rows to `type='tool'`.
- **S3. Plugin permissions declaration** (R5, P0 bundled with S2) — `permissions: { allowed_tools, allowed_models, storage_scope }` block in manifest; install-time consent screen in PluginsPage.

**Deferred (logged, not built):**
- R3 Progressive-disclosure skills (injects only `{name, description}` at session start + `load_skill(name)` tool) — needs ADR-089 on prompt budget; touches executor skill registry; can ship independently later. *Not in Phase 1.*
- R6/R7/R9/R10 — assorted lower-priority recs, deferred.

## 3. Scope — Phase 2 (DOC-IM2)

**In scope:**
- **I1. Feishu card callback signature fix** (bugfix, bundled) — add second `verify_card_signature()` using SHA-1 + verification_token + nonce. Fix pre-existing docstring drift ("HMAC-SHA256" → actual "plain SHA-256").
- **I2. Slack adapter** (R4, P1) — new `im_slack.py`, Events API default, Socket Mode opt-in via `IM_SLACK_MODE=socket`. HMAC-SHA256 signature verify.
- **I3. Discord adapter** (R4, P1) — new `im_discord.py`, HTTP Interactions + Ed25519 signature. Dependency: `PyNaCl`.
- **I4. IM credential storage migration** — move Feishu from env-vars-only to `im_channel_configs.config` JSONB (AES-encrypted, multi-tenant ready). Env vars become dev override only.
- **I5. IMOutgoingCard abstraction** (R8, bundled with I2/I3) — provider-neutral card dataclass; per-adapter translator (Feishu card / Slack blocks / Discord embed).

**Deferred:**
- DingTalk adapter (R4 P2).
- WeChat Work adapter (existing `im_wecom.py` unchanged this DOC).
- Telegram adapter polish (already exists, not touched).

---

## 4. Decisions (auto-executed, embedded here per user directive "auto decide")

| # | Decision point | Choice | Rationale |
|---|---|---|---|
| D1 | Marketplace — new table vs extend `skill_installs.source` | **New `marketplace_registry` table** | Single-responsibility; clean FK; no string-prefix hackery |
| D2 | Plugin `type` backfill | **Migration `DEFAULT 'tool'` for existing rows** | 最简代码; zero user action; CLAUDE.md 不做向后兼容 in NEW code — but DB migration still backfills to avoid NOT NULL crash |
| D3 | IM credential storage | **`im_channel_configs.config` JSONB, AES-encrypted** (same pattern as providers) | Multi-tenant ready; envvar stays as dev fallback only |
| D4 | IM depth (Slack/Discord) | **Full bidirectional (send + receive + cards)** | User's explicit "IM接入功能" directive; half-implementation fails KISS litmus ("需要解释就是太复杂") |
| D5 | Deployment readiness — do we have test tenants? | **No** — E2E mocks the external HTTP, prod users supply real credentials via Admin panel after adapter config | Doesn't block development |
| D6 | Feishu card signature fix — now or Session 4? | **Bundle with DOC-IM2 (Phase 2)** | Same domain; fixing earlier creates cross-DOC commit (CLAUDE.md 不可做 #6) |
| D7 | Slack mode default | **Events API (HTTP)** | Standard, Marketplace-listable (future), simpler for self-hosted |
| D8 | Progressive-disclosure skills (R3) | **Deferred to ADR-089 standalone** | Orthogonal to marketplace; prompt-budget implications need own ADR; don't block this DOC |

### Additional cross-cutting decisions

- **D9. Phase ordering** — DOC-SK first (smaller scope, sets marketplace/plugin pattern). DOC-IM2 second (larger adapter surface, depends on IM credential refactor).
- **D10. Schema authorization** — user's reiterated dev principle "不做向后兼容,宁愿破坏性更新" + explicit redesign directive = implicit authorization for additive schema changes. Migrations remain reversible (down_revision).
- **D11. Backward-compat shims** — none. Per user principle, no legacy format support. Clean break.
- **D12. Test layers** — unit for signature algos; integration for adapter flows; E2E for UI (mock external HTTP at network level).

---

## 5. Architecture

### 5.1 Skills Marketplace (DOC-SK S1)

**Data flow**:
1. Admin registers marketplace URL via `POST /marketplaces` (must be a git-repo URL or tarball URL serving a `marketplace.json` manifest).
2. Backend fetches `marketplace.json` → caches `catalog_json`, updates `last_fetched_at`.
3. User opens SkillsPage → "Marketplace" tab → browses catalogs → picks a skill → clicks Install.
4. Frontend calls `POST /skills/install {source: "marketplace", marketplace_id, skill_name}` → backend finds skill in cached catalog → downloads SKILL.md → writes to `skill_installs` row with `marketplace_id` FK.

**`marketplace.json` format** (contract):
```json
{
  "name": "anthropic-skills",
  "version": "1",
  "skills": [
    {"name": "pdf-reader", "description": "...", "download_url": "https://.../skill.md", "author": "..."},
    ...
  ]
}
```

**Endpoints** (all under `/api/v1/marketplaces`):
- `GET /` — list registered marketplaces + catalog summary (skill count, last_fetched)
- `POST /` — register new marketplace (body: `{url, name}`)
- `DELETE /{id}` — remove marketplace (cascades `skill_installs.marketplace_id → NULL` via `ON DELETE SET NULL`)
- `POST /{id}/sync` — force refresh catalog from URL

### 5.2 Typed Plugin Manifest (DOC-SK S2+S3)

**`plugin.yaml` schema** (new contract):
```yaml
name: my-plugin
version: 1.0.0
type: tool                    # REQUIRED — enum: tool | agent_strategy | extension | trigger
description: ...
permissions:                  # REQUIRED for type != 'tool'; optional for 'tool'
  allowed_tools: ["fetch", "mcp.*"]
  allowed_models: ["claude-*"]
  storage_scope: "session"    # enum: session | user | global
  network_access: false
# ... type-specific fields below ...
```

**Type-specific sub-schemas**:
- `type: tool` — current behavior (OpenAPI-like tool definition)
- `type: agent_strategy` — `reasoning_pattern: react|plan-and-execute|debate`, `max_turns: int`
- `type: extension` — `hook: pre_turn|post_turn|post_tool_use`, `middleware_class_path: str`
- `type: trigger` — `event_source: cron|webhook|file_watch`, `config: dict`

**PluginBuilder UX**:
- First question (new): "What kind of plugin? [tool / agent-strategy / extension / trigger]"
- Branches prompt per type → generates corresponding YAML skeleton
- Install screen shows consent dialog: "Allow this plugin to access: [tool list] / [model list] / [storage scope]"

### 5.3 IM Adapter Expansion (DOC-IM2)

**Unified `IMAdapter` contract** (extended):
```python
class IMAdapter(ABC):
    channel: str          # "feishu" | "wecom" | "slack" | "discord" | "telegram"
    
    async def verify_and_parse_event(self, headers: dict, raw_body: bytes) -> IMIncomingMessage | None
    async def send_text(self, target: IMTarget, text: str) -> None
    async def send_card(self, target: IMTarget, card: IMOutgoingCard) -> None  # NEW
```

**`IMOutgoingCard` dataclass** (new, `im_adapter.py`):
```python
@dataclass
class IMOutgoingCard:
    title: str
    body_markdown: str
    actions: list[IMCardAction]  # [{label, action_id, style: primary|secondary}]
    footer: str | None = None
```

Each adapter translates this to its native card format (Feishu card JSON / Slack blocks / Discord embed + components). Telegram uses plain-text fallback with inline-keyboard approximation.

**New routes** in `backend/app/api/v1/im.py`:
- `POST /im/webhook/slack` — Events API (signature verify → dedup → dispatch)
- `POST /im/webhook/discord` — Interactions (Ed25519 verify → PING ack or dispatch)
- (existing `/webhook/feishu`, `/webhook/wecom` unchanged for inbound path)

### 5.4 Feishu card signature fix (DOC-IM2 I1)

Current `im_feishu.py:verify_signature` only implements event-subscription SHA-256 path. Add:

```python
def verify_card_signature(self, headers: dict, body: bytes) -> bool:
    ts = headers.get("X-Lark-Request-Timestamp", "")
    nonce = headers.get("X-Lark-Request-Nonce", "")
    sig = headers.get("X-Lark-Signature", "")
    expected = hashlib.sha1((ts + nonce + self._verification_token + body.decode()).encode()).hexdigest()
    return hmac.compare_digest(expected, sig)
```

Different algorithm, different key (`verification_token` not `encrypt_key`), three headers instead of two.

Fix docstring drift on `verify_signature`: not HMAC, just plain SHA-256.

---

## 6. Schema changes

### Migration M1 (DOC-SK): `marketplace_registry`

```python
# alembic/versions/xxx_marketplace_registry.py
def upgrade():
    op.create_table("marketplace_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(500), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("catalog_json", postgresql.JSONB, nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.add_column("skill_installs",
        sa.Column("marketplace_id", sa.String(36), sa.ForeignKey("marketplace_registry.id", ondelete="SET NULL"), nullable=True)
    )
```

### Migration M2 (DOC-SK): `plugins_library` typed columns

```python
def upgrade():
    op.add_column("plugins_library",
        sa.Column("plugin_type", sa.String(30), nullable=False, server_default="tool")
    )
    op.add_column("plugins_library",
        sa.Column("permissions_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    )
    # Remove server_default after backfill (migration runs once, data is backfilled)
    op.alter_column("plugins_library", "plugin_type", server_default=None)
    op.alter_column("plugins_library", "permissions_json", server_default=None)
```

### Migration M3 (DOC-IM2): no new table — reuses `im_channel_configs`

No DDL. Just extend enum of valid `channel` values in application code to include `slack`, `discord`.

---

## 7. Environment variables

### New vars (add to `.env.example` + `config.py`)

```
# Slack
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=          # xoxb-...
SLACK_APP_TOKEN=          # xapp-... (only if IM_SLACK_MODE=socket)
IM_SLACK_MODE=events      # events | socket

# Discord
DISCORD_PUBLIC_KEY=       # hex Ed25519 pubkey
DISCORD_APP_ID=
DISCORD_BOT_TOKEN=

# Existing Feishu vars move from env-only to DB-primary (env = dev fallback)
# FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_ENCRYPT_KEY, FEISHU_VERIFICATION_TOKEN — unchanged
```

### New dependency

`PyNaCl>=1.5` in `backend/requirements.txt` for Ed25519 verification. (slack-sdk optional; prefer direct HTTP to keep surface minimal.)

---

## 8. Verification plan (high level — detailed in plan doc)

**Unit (pytest)**:
- `tests/test_marketplace_service.py` — fetch+cache catalog, sync, delete
- `tests/test_plugin_schema.py` — typed YAML validation, permissions parsing
- `tests/test_im_slack_signature.py` — HMAC-SHA256 v0: prefix, timestamp window
- `tests/test_im_discord_signature.py` — Ed25519 with known keypair fixture
- `tests/test_im_feishu_card_sig.py` — SHA-1 + verification_token path

**Integration**:
- Marketplace sync → skill install → list shows installed-from-marketplace
- Plugin builder `type: tool` end-to-end generates valid YAML that validates
- Slack Events API URL verification handshake
- Discord PING → PONG handshake
- Feishu card callback signature verification

**E2E (Playwright, desktop + mobile)**:
- SkillsPage new Marketplace tab — add marketplace URL, list shows, install one skill, verify appears in "Installed"
- PluginsPage type picker first step — select "tool" → builder YAML is typed
- Admin IM config panel — add Slack channel config, enter creds, test-send a message (mocked externally)

**Human-sim**:
- Every button on new UI (Marketplace tab add/delete/sync, Plugin type picker, IM config CRUD) click-tested
- Desktop + mobile viewport both

---

## 9. Out of scope (hard)

- PRD v4 document modifications (ADR numbers allocated here are in available gap slots, documented in DECISIONS.md at landing)
- CLAUDE.md modifications
- Any backend endpoint outside `/marketplaces`, `/skills`, `/plugins`, `/im`, `/admin`
- Any frontend page outside `SkillsPage`, `PluginsPage`, `Admin → IM Channels` config section
- Session 2b's distributed task decomposition research (separate concern)
- Progressive-disclosure skills (ADR-089, future session)
- Migration rollback testing beyond `alembic downgrade` smoke
- LLM-dependent E2E (we mock at network boundary per D5)

---

## 10. Acceptance

Phase 1 (DOC-SK) acceptance:
- All 3 migrations applied cleanly (forward + rollback)
- Unit tests for marketplace_service + plugin_schema pass (new tests)
- E2E Marketplace tab flow passes on desktop + mobile
- E2E Plugin type picker flow passes on desktop + mobile
- Full skill chain: simplify → verification → react-code-review → pjr → git-merge-to-develop → requesting-code-review

Phase 2 (DOC-IM2) acceptance:
- Feishu event webhook still works + new card callback path unit-tested with known-good payload
- Slack URL verification handshake passes against Slack's real probe (or signed fixture)
- Discord PING ack passes against signed fixture with test Ed25519 keypair
- E2E IM Channels admin UI passes on desktop + mobile
- Full skill chain

Both phases merge to `develop` via `git-merge-to-develop`. Final merge to `main` is a separate (future) session decision.

---

## 11. Risks + blocker candidates (pre-registered)

| # | Risk | Mitigation |
|---|---|---|
| R1 | User does NOT authorize the 3 migrations before Phase 1 starts | Write new `blocker.md` + halt per CLAUDE.md 六原则 #1 |
| R2 | `marketplace.json` spec turns out to conflict with Claude Code's official format | Phase 1 Task 1 = confirm format by examining `anthropic/claude-code-marketplace` or similar real repo before coding |
| R3 | Slack Socket Mode dependency (`slack-sdk`) is heavier than expected | Keep Socket Mode as opt-in; default Events API needs only HMAC + requests |
| R4 | Discord Ed25519 verify latency during probe floods | Prefer async verify; PyNaCl's `VerifyKey.verify` is fast (<1ms) |
| R5 | Existing `im_channel_configs` row shape doesn't accommodate Slack's bot-token format | Migration M3 no-op asserts this; if it breaks, extend JSONB with new key and document |
| R6 | Phase 2 credential migration breaks prod Feishu configs | Dual-read (envvar + DB) for 1 release; HANDOFF flags deprecation window |

---

*End of spec — word count ≈ 2100.*
