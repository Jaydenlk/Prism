# DOC-SK + DOC-IM2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Prism v2 Session 3 redesign — Skills Marketplace (R1), Typed Plugin Manifest (R2+R5), then Slack/Discord IM adapters + Feishu card signature fix (R4+R8+I1).

**Architecture:** Phase 1 DOC-SK (marketplace + plugin taxonomy) → Phase 2 DOC-IM2 (IM expansion). Each phase = separate feature branch off `develop`, separate merge commit.

**Tech Stack:** FastAPI + SQLAlchemy + alembic + Pydantic; Postgres JSONB + Redis cache; zero-build React (Prism.html); Playwright e2e; PyNaCl for Ed25519.

**Spec:** `docs/superpowers/specs/2026-04-20-session3-sk-im2-redesign-design.md`
**Brief:** `docs/research/2026-04-20-session3-design-brief.md`
**Research:** `docs/research/2026-04-19-skills-plugins-im-competitive.md`

**ADR allocations:**
- ADR-086 Skills Marketplace (DOC-SK M1)
- ADR-087 Typed Plugin Manifest + Permissions (DOC-SK M2)
- ADR-088 IM Interactive Cards + Multi-Channel (DOC-IM2 I2/I3/I5)

---

## File Structure

### Phase 1 (DOC-SK)

| File | Action |
|---|---|
| `backend/app/models/marketplace.py` | Create (new `MarketplaceRegistry` ORM) |
| `backend/app/models/skill.py` | Modify (add `marketplace_id` FK) |
| `backend/app/models/plugin.py` | Modify (add `plugin_type`, `permissions_json`) |
| `backend/app/schemas/marketplace.py` | Create (Pydantic: `MarketplaceCreate`, `MarketplaceResponse`) |
| `backend/app/schemas/plugin.py` | Modify (add `type`, `permissions`) |
| `backend/app/services/marketplace_service.py` | Create (fetch+cache+CRUD) |
| `backend/app/services/plugin_builder_service.py` | Modify (branch prompt by type) |
| `backend/app/services/skill_install_service.py` | Modify (source=marketplace path) |
| `backend/app/api/v1/marketplaces.py` | Create (4 endpoints) |
| `backend/app/api/v1/skills.py` | Modify (filter `?marketplace_id=`) |
| `backend/app/api/v1/plugins.py` | Modify (typed validate) |
| `backend/alembic/versions/<M1>_marketplace_registry.py` | Create |
| `backend/alembic/versions/<M2>_plugin_typed_columns.py` | Create |
| `frontend/Prism.html` | Modify (SkillsPage 4th tab; PluginsPage type picker + consent) |
| `e2e/tests/marketplace.spec.ts` | Create |
| `e2e/tests/plugin-typed-builder.spec.ts` | Create |
| `DECISIONS.md` | Append ADR-086, ADR-087 |

### Phase 2 (DOC-IM2)

| File | Action |
|---|---|
| `backend/app/services/im_adapter.py` | Modify (add `IMOutgoingCard`, extend channel enum) |
| `backend/app/services/im_feishu.py` | Modify (add `verify_card_signature`; fix docstring drift) |
| `backend/app/services/im_slack.py` | Create |
| `backend/app/services/im_discord.py` | Create |
| `backend/app/api/v1/im.py` | Modify (add Slack + Discord webhook routes) |
| `backend/app/core/config.py` | Modify (new env vars) |
| `backend/requirements.txt` | Modify (add `PyNaCl>=1.5`) |
| `.env.example` | Modify |
| `frontend/Prism.html` | Modify (Admin IM Channels config section) |
| `e2e/tests/im-channels.spec.ts` | Create |
| `backend/tests/test_im_slack_signature.py` | Create |
| `backend/tests/test_im_discord_signature.py` | Create |
| `backend/tests/test_im_feishu_card_sig.py` | Create |
| `DECISIONS.md` | Append ADR-088 |

---

## Phase 1 (DOC-SK) — Skills Marketplace + Plugin Taxonomy

### Task 1: Create worktree + baseline

- [ ] **Step 1**: Load `superpowers:using-git-worktrees` skill. Create worktree at `.worktrees/redesign-doc-sk` on new branch `redesign/doc-sk` off `develop`.
  ```bash
  cd "E:/Agent program/PrismV3"
  git worktree add .worktrees/redesign-doc-sk -b redesign/doc-sk develop
  cd .worktrees/redesign-doc-sk
  ```
- [ ] **Step 2**: Set up e2e node_modules via PowerShell junction to main tree's e2e/node_modules (pattern from Session 1):
  ```bash
  powershell -NoProfile -Command "New-Item -ItemType Junction -Path '.worktrees/redesign-doc-sk/e2e/node_modules' -Target 'E:\Agent program\PrismV3\e2e\node_modules'"
  ```
- [ ] **Step 3**: Copy `.env` from main tree to worktree (backend needs it at runtime):
  ```bash
  cp "E:/Agent program/PrismV3/.env" ".worktrees/redesign-doc-sk/.env"
  ```
- [ ] **Step 4**: Verify baseline tests pass (from worktree e2e/):
  ```bash
  cd e2e && npx playwright test --project=desktop-chromium --reporter=list --retries=0
  ```
  Expect: 14 pass / 4 skip / 0 fail (same as develop baseline).

### Task 2: Write failing E2E tests (TDD red phase)

- [ ] **Step 1**: Create `e2e/tests/marketplace.spec.ts` with two tests:
  - "admin can register a marketplace URL and see catalog" — needs new Marketplace tab + `POST /api/v1/marketplaces` endpoint
  - "installed skill from marketplace shows marketplace badge" — needs skill install flow with marketplace_id
- [ ] **Step 2**: Create `e2e/tests/plugin-typed-builder.spec.ts` with:
  - "plugin builder first step asks type" — needs type picker UI
  - "saving untyped manifest adds type: tool default" — backend accepts, stores type
- [ ] **Step 3**: Run new tests. Expect ALL FAIL (no impl yet).
  ```bash
  npx playwright test marketplace.spec.ts plugin-typed-builder.spec.ts --project=desktop-chromium --reporter=list
  ```
- [ ] **Step 4**: Commit red phase.
  ```bash
  git add e2e/tests/marketplace.spec.ts e2e/tests/plugin-typed-builder.spec.ts
  git commit -m "test(e2e): RED phase for marketplace + typed plugin builder"
  ```

### Task 3: Backend — `MarketplaceRegistry` model + migration M1

- [ ] **Step 1**: Create `backend/app/models/marketplace.py`:
  ```python
  from sqlalchemy import Column, String, DateTime, ForeignKey
  from sqlalchemy.dialects.postgresql import JSONB
  from sqlalchemy.orm import relationship
  from app.models.base import Base, generate_uuid
  from datetime import datetime

  class MarketplaceRegistry(Base):
      __tablename__ = "marketplace_registry"
      id = Column(String(36), primary_key=True, default=generate_uuid)
      url = Column(String(500), unique=True, nullable=False)
      name = Column(String(200), nullable=False)
      catalog_json = Column(JSONB, nullable=True)
      last_fetched_at = Column(DateTime(timezone=True), nullable=True)
      created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
      created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
      creator = relationship("User")
  ```
- [ ] **Step 2**: Modify `backend/app/models/skill.py` (skill_installs model) — add `marketplace_id` optional FK:
  ```python
  marketplace_id = Column(String(36), ForeignKey("marketplace_registry.id", ondelete="SET NULL"), nullable=True)
  marketplace = relationship("MarketplaceRegistry")
  ```
- [ ] **Step 3**: Generate alembic migration M1.
  ```bash
  docker compose exec backend alembic revision --autogenerate -m "marketplace_registry"
  ```
  Review generated file in `backend/alembic/versions/` — ensure `down_revision` points to current head.
- [ ] **Step 4**: Apply and verify.
  ```bash
  docker compose exec backend alembic upgrade head
  docker compose exec postgres psql -U prism -d prism -c "\\d marketplace_registry"
  ```
- [ ] **Step 5**: Commit.
  ```bash
  git add backend/app/models/marketplace.py backend/app/models/skill.py backend/alembic/versions/*marketplace_registry.py
  git commit -m "feat(db): marketplace_registry table + skill_installs.marketplace_id FK (M1, ADR-086)"
  ```

### Task 4: Backend — marketplace service + endpoints

- [ ] **Step 1**: Create `backend/app/schemas/marketplace.py` (Pydantic).
- [ ] **Step 2**: Create `backend/app/services/marketplace_service.py`:
  - `create_marketplace(user_id, url, name) → MarketplaceResponse` — stores row, triggers initial sync.
  - `sync_marketplace(id) → MarketplaceResponse` — HTTP GET url, parse `marketplace.json`, validate, store in `catalog_json`, stamp `last_fetched_at`.
  - `list_marketplaces(user_id) → list[MarketplaceResponse]`.
  - `delete_marketplace(id, user_id) → None`.
- [ ] **Step 3**: Create `backend/app/api/v1/marketplaces.py` (4 endpoints per spec §5.1). Add router to `main.py`.
- [ ] **Step 4**: Modify `skill_install_service.py` — accept `source="marketplace"` + `marketplace_id` + `skill_name`; look up in cached catalog; fetch `download_url`; install.
- [ ] **Step 5**: Curl-test each endpoint after backend reload.
- [ ] **Step 6**: Commit.
  ```bash
  git add backend/app/schemas/marketplace.py backend/app/services/marketplace_service.py backend/app/api/v1/marketplaces.py backend/app/services/skill_install_service.py backend/app/main.py
  git commit -m "feat(api): marketplace service + 4 endpoints + marketplace-source skill install"
  ```

### Task 5: Backend — typed plugin manifest + migration M2

- [ ] **Step 1**: Modify `backend/app/models/plugin.py` — add columns `plugin_type: String(30) NOT NULL DEFAULT 'tool'`, `permissions_json: JSONB NOT NULL DEFAULT '{}'`.
- [ ] **Step 2**: Modify `backend/app/schemas/plugin.py` Pydantic — add `type: Literal["tool", "agent_strategy", "extension", "trigger"]` + `permissions: PluginPermissions` nested model.
- [ ] **Step 3**: Generate migration M2.
  ```bash
  docker compose exec backend alembic revision --autogenerate -m "plugin_typed_columns"
  ```
  Review — ensure `server_default='tool'` on `plugin_type` column, `server_default="'{}'::jsonb"` on `permissions_json` (backfill existing rows).
- [ ] **Step 4**: Apply + verify existing `plugins_library` rows have `plugin_type='tool'`.
- [ ] **Step 5**: Modify `backend/app/api/v1/plugins.py` `/validate` endpoint — dispatch on `type`; each type's sub-schema checked.
- [ ] **Step 6**: Commit.
  ```bash
  git add backend/app/models/plugin.py backend/app/schemas/plugin.py backend/alembic/versions/*plugin_typed_columns.py backend/app/api/v1/plugins.py
  git commit -m "feat(db): plugin_type + permissions_json columns (M2, ADR-087)"
  ```

### Task 6: Frontend — Marketplace tab + Plugin type picker

Load `frontend-design` + `ui-ux-pro-max` skills before UI edits.

- [ ] **Step 1**: In `frontend/Prism.html` SkillsPage, add 4th install tab `marketplace` alongside existing `local_file / github / custom_md`. Content:
  - "Add marketplace" form (URL + name) → `POST /api/v1/marketplaces`
  - List of registered marketplaces (name, skill count, last-synced timestamp, sync button, delete button)
  - Click marketplace → shows catalog skills → click "Install" on a skill → `POST /skills/install` with `source="marketplace"` + `marketplace_id` + `skill_name`
- [ ] **Step 2**: In SkillsPage installed list, show marketplace badge if `marketplace_id` present.
- [ ] **Step 3**: In PluginsPage builder, first bot message asks: "What kind of plugin? [tool / agent_strategy / extension / trigger]" — user's answer becomes the `type` field. Subsequent prompts branch per type.
- [ ] **Step 4**: Install modal shows consent screen with `permissions.allowed_tools`, `allowed_models`, `storage_scope`, `network_access` before confirming install.
- [ ] **Step 5**: CSS: reuse `.content.md` palette; new `.marketplace-card`, `.plugin-type-chip`, `.consent-dialog` classes using `--paper / --panel / --amber / --line` tokens only.
- [ ] **Step 6**: Run Playwright RED tests → now GREEN.
  ```bash
  npx playwright test marketplace.spec.ts plugin-typed-builder.spec.ts --project=desktop-chromium --project=mobile-safari --reporter=list --retries=0
  ```
- [ ] **Step 7**: Commit.
  ```bash
  git add frontend/Prism.html frontend/styles.css
  git commit -m "feat(frontend): SkillsPage marketplace tab + PluginsPage type picker + consent screen"
  ```

### Task 7: DECISIONS.md entries for ADR-086 + ADR-087

- [ ] **Step 1**: Append two ADR entries to `DECISIONS.md` using template from file.
- [ ] **Step 2**: Commit.
  ```bash
  git add DECISIONS.md
  git commit -m "docs(adr): ADR-086 Skills Marketplace + ADR-087 Typed Plugin Manifest"
  ```

### Task 8: Full suite + skill chain Phase 1

- [ ] **Step 1**: Full Playwright sweep both viewports. Expect all pass + new tests pass.
- [ ] **Step 2**: Load `simplify` skill → 3 agents → fix findings.
- [ ] **Step 3**: Load `superpowers:verification-before-completion` → run all verify cmds, document.
- [ ] **Step 4**: Load `react-code-review:react-code-review` → review frontend changes.
- [ ] **Step 5**: Load `project-review:pjr` → lint + build + workspace state.
- [ ] **Step 6**: Load `git-merge-to-develop:git-merge-to-develop` → rebase onto develop → merge DOC-SK into develop.
- [ ] **Step 7**: Load `superpowers:requesting-code-review` → dispatch code-reviewer → triage findings.

---

## Phase 2 (DOC-IM2) — Slack + Discord + Feishu Card Fix

### Task 9: Worktree + baseline for Phase 2

- [ ] **Step 1**: From main tree on `develop` (now includes DOC-SK merge), create new worktree.
  ```bash
  git worktree add .worktrees/redesign-doc-im2 -b redesign/doc-im2 develop
  ```
- [ ] **Step 2**: Node junction + `.env` copy (same pattern).
- [ ] **Step 3**: Verify baseline.

### Task 10: RED tests for IM expansion

- [ ] **Step 1**: Create `backend/tests/test_im_feishu_card_sig.py` — known-good card callback payload + signature; assert verify returns True. Assert the OLD event-sig path still verifies its own payload.
- [ ] **Step 2**: Create `backend/tests/test_im_slack_signature.py` — HMAC-SHA256 `v0:{ts}:{body}` fixture; assert verify + timestamp window reject.
- [ ] **Step 3**: Create `backend/tests/test_im_discord_signature.py` — generate Ed25519 keypair, sign fixture, verify against pubkey. Assert reject on tampered body.
- [ ] **Step 4**: Create `e2e/tests/im-channels.spec.ts` — admin UI: list existing channels, add Slack channel config (mocked backend), test-send returns mocked success.
- [ ] **Step 5**: Run all — expect FAIL (no impl).
- [ ] **Step 6**: Commit RED.

### Task 11: Feishu card signature fix + docstring drift

- [ ] **Step 1**: In `backend/app/services/im_feishu.py`, add `verify_card_signature(headers, body) → bool` using SHA-1 + `verification_token` + timestamp + nonce. Spec §5.4 for exact code.
- [ ] **Step 2**: Fix `verify_signature` docstring — remove "HMAC-SHA256" wording; replace with "plain SHA-256 (timestamp + encrypt_key + body)" per official doc.
- [ ] **Step 3**: Run `test_im_feishu_card_sig.py` → GREEN.
- [ ] **Step 4**: Commit.
  ```bash
  git commit -m "fix(im_feishu): add verify_card_signature SHA-1 path + fix HMAC docstring drift (I1)"
  ```

### Task 12: Slack adapter

- [ ] **Step 1**: Create `backend/app/services/im_slack.py` extending `IMAdapter`:
  - `verify_and_parse_event` — HMAC-SHA256 sig + timestamp window + handle `type:url_verification` + `type:event_callback`.
  - `send_text` — `POST https://slack.com/api/chat.postMessage` with `Bearer xoxb-…`.
  - `send_card` — translate `IMOutgoingCard` → Slack `blocks` format.
- [ ] **Step 2**: Modify `backend/app/api/v1/im.py` — add `POST /im/webhook/slack`. 3s ACK budget (async handoff to TaskService).
- [ ] **Step 3**: Modify `backend/app/core/config.py` — add `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `IM_SLACK_MODE` settings.
- [ ] **Step 4**: Run signature unit test → GREEN. Smoke test webhook endpoint.
- [ ] **Step 5**: Commit.

### Task 13: Discord adapter

- [ ] **Step 1**: Add `PyNaCl>=1.5` to `backend/requirements.txt`. Rebuild backend image.
- [ ] **Step 2**: Create `backend/app/services/im_discord.py`:
  - `verify_and_parse_event` — Ed25519 verify via `PyNaCl.VerifyKey`; on PING (type=1) return PONG (type=1); else parse as interaction.
  - `send_text` + `send_card` (card → Discord embed + components).
- [ ] **Step 3**: Add `POST /im/webhook/discord` route. Return non-200 for invalid sig (per Discord docs).
- [ ] **Step 4**: Add `DISCORD_PUBLIC_KEY`, `DISCORD_APP_ID`, `DISCORD_BOT_TOKEN` to config.
- [ ] **Step 5**: Run unit tests → GREEN.
- [ ] **Step 6**: Commit.

### Task 14: IMOutgoingCard abstraction + IM channel enum

- [ ] **Step 1**: In `backend/app/services/im_adapter.py`, add `IMOutgoingCard` dataclass + `IMCardAction`. Extend channel enum to include `slack`, `discord`.
- [ ] **Step 2**: Update `backend/app/services/im_feishu.py` — implement `send_card` (translate to native interactive card).
- [ ] **Step 3**: `im_slack.py` + `im_discord.py` already implement `send_card` per their Task.
- [ ] **Step 4**: Commit.

### Task 15: Frontend — Admin IM Channels config UI

Load `frontend-design` + `ui-ux-pro-max`.

- [ ] **Step 1**: In `admin.html` (admin-only page) — add IM Channels section: list configured channels, per-row edit (creds JSONB encrypted), test-send button.
- [ ] **Step 2**: Run E2E `im-channels.spec.ts` → GREEN (admin login → add Slack → test).
- [ ] **Step 3**: Commit.

### Task 16: Skill chain Phase 2 (same as Task 8)

- [ ] simplify → verification → react-code-review → pjr → git-merge-to-develop → requesting-code-review
- [ ] DECISIONS.md append ADR-088.
- [ ] Final HANDOFF update marking Session 3 complete + next-session pointers.

---

## Self-Review Checklist (applied when writing this plan)

1. **Spec coverage**: every spec §5/§6/§7/§10 requirement maps to a task (verified).
2. **Placeholders**: zero TBD/TODO (verified).
3. **Type consistency**: `plugin_type` column name matches Pydantic field `type` (distinct, intentional — `type` is Python builtin so DB column renamed).
4. **ADR numbers**: 086 / 087 / 088 are in documented gap slots (CLAUDE.md + DECISIONS.md index verified).

---

## Execution notes

- Phase 1 + Phase 2 are separate branches + merges; do NOT mix commits. This preserves CLAUDE.md "1 DOC = 1 PR".
- Whenever a task requires running Docker commands, the stack must be up (`docker compose up -d` from worktree with `--env-file` pointing to `.env`). Feishu credential test-path relies on `.env` values.
- If Task 3 or Task 5 migration autogeneration pulls in unrelated model changes (stale autoregen cache), run `alembic upgrade head` on a fresh checkout first to sync state.
- If at any task a CLAUDE.md 六原则 violation is detected (schema change not covered by ADR-086/087/088, backward-compat shim creeping in, cross-DOC refactor), write `blocker.md` and halt per skill discipline.
- **Session budget**: Phase 1 estimated 2-4 sonnet-session-equiv; Phase 2 estimated 2-3. Total: 4-7 sessions. Phase boundary is a natural /clear point.
