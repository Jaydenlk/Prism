# Backend Endpoint Audit — 2026-05-08

Anchor: `frontend/apiClient.js`  
Scope: `backend/app/api/v1/*.py` + `backend/app/services/*.py`  
Auditor: Agent C (read-only)

---

## Legend

- **exists+real** — route registered, service does real work, params consumed
- **exists-partial** — route registered, real logic, but params partially ignored
- **exists-stub** — route registered but logic is placeholder / NotImplementedError / hardcoded mock
- **missing** — frontend calls this path but backend has no matching route
- **param-ignored** — endpoint exists + real, but specific query param silently dropped

---

## Auth (`/auth`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| POST /auth/login | auth.py:148 | `login()` | **exists+real** | Calls `AuthService.login()` → hashes PW + issues JWT |
| POST /auth/register | auth.py:108 | `register()` | **exists+real** | Validates invite, hashes PW, issues JWT |
| POST /auth/refresh | auth.py:178 | `_doRefresh()` | **exists+real** | Reads HttpOnly cookie, verifies JWT |
| POST /auth/logout | auth.py:211 | `logout()` | **exists+real** | Deletes refresh cookie |
| GET /auth/me | auth.py:230 | `me()` | **exists+real** | Returns `UserResponse.from_user()` |
| POST /auth/sse-ticket | auth.py:243 | `createSSETicket()` | **exists+real** | SETEX in Redis, returns uuid4 ticket |
| GET /auth/providers | auth.py:382 | `authProviders()` | **exists+real** | Reads `AuthConfigService` + `GoogleOAuthService` |
| POST /auth/email-magic/request | auth.py:420 | `emailMagicRequest()` | **exists+real** | Creates challenge, sends email |
| POST /auth/email-magic/verify | auth.py:480 | `emailMagicVerify()` | **exists+real** | Verifies challenge, issues JWT |
| POST /auth/email-otp/request | auth.py:537 | `emailOtpRequest()` | **exists+real** | Creates OTP challenge, sends email |
| POST /auth/email-otp/verify | auth.py:589 | `emailOtpVerify()` | **exists+real** | Verifies OTP, issues JWT |
| POST /auth/forgot-password | auth.py:646 | `forgotPassword()` | **exists+real** | Creates reset challenge, sends email |
| POST /auth/reset-password | auth.py:707 | `resetPassword()` | **exists+real** | Verifies challenge, calls `hash_password()`, persists |
| POST /auth/phone-register | auth.py:763 | `phoneRegister()` | **exists+real** | Validates invite, creates user with phone |
| POST /auth/phone-login | auth.py:844 | `phoneLogin()` | **exists+real** | Verifies phone + password |
| POST /auth/google/complete | auth.py:1109 | `googleComplete()` | **exists+real** | GETDEL pending Redis token, creates user |
| POST /auth/change-password | — | (not in apiClient.js) | **N/A** | apiClient.js does NOT call change-password; no backend route exists |

> **Severity: LOW** — `POST /auth/change-password` is absent from both apiClient.js and backend. No user-reported breakage. The `reset-password` flow (token-based) is the current password-change mechanism.

---

## Sessions (`/sessions`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /sessions | sessions.py:102 | `sessions.list()` | **exists+real** | Paginated, pinned-first ordering |
| POST /sessions | sessions.py:131 | `sessions.create()` | **exists+real** | Creates session via SessionService |
| GET /sessions/{id} | sessions.py:143 | `sessions.get()` | **exists+real** | Enforces user ownership |
| PATCH /sessions/{id} | sessions.py:155 | `sessions.update()` | **exists+real** | Updates title/pin/config |
| DELETE /sessions/{id} | sessions.py:174 | `sessions.delete()` | **exists+real** | Cascade delete via SessionService |
| GET /sessions/{id}/messages | sessions.py:195 | `sessions.listMessages()` | **exists+real** | Supports `after_sequence_no` + `limit` |
| GET /sessions/{id}/runs | runs.py:90 | `sessions.listRuns()` | **exists+real** | Paginated, session ownership enforced |
| POST /sessions/{id}/permission-answer | sessions.py:357 | `sessions.permissionAnswer()` | **exists+real** | RPUSH to Redis `perm_answer:{id}` |

---

## Tasks (`/tasks`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| POST /tasks | tasks.py:38 | `tasks.submit()` | **exists+real** | Calls `TaskService.submit()` → start_run() |

---

## Runs (`/runs`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /runs/{id} | runs.py:67 | `runs.get()` | **exists+real** | Returns RunResponse with harness_summary |
| POST /runs/{id}/cancel | tasks.py:142 | `runs.cancel()` | **exists+real** | Three modes: graceful/force/also_cancel_queue |
| POST /runs/{id}/resume | runs.py:124 | `runs.resume()` | **exists+real** | ADR-067 coordinator recovery from checkpoint |

---

## MCP (`/mcp-servers`, `/mcp-installs`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /mcp-servers | mcp.py:54 | `mcp.listServers()` | **exists+real** | Returns system + user-scoped servers |
| GET /mcp-servers/{id} | mcp.py (via service) | `mcp.getServer()` | **exists+real** | Ownership enforced |
| POST /mcp-servers | mcp.py:69 | `mcp.createServer()` | **exists+real** | Forces scope='user' |
| DELETE /mcp-servers/{id} | mcp.py:89 | `mcp.deleteServer()` | **exists+real** | 403 if system-scope |
| POST /mcp-servers/{id}/test | mcp.py:106 | `mcp.testServer()` | **exists+real** | Real MCPClient connection, 10s timeout |
| GET /mcp-installs | mcp.py:145 | `mcp.listInstalls()` | **exists+real** | Filtered to user_id |
| POST /mcp-installs | mcp.py:126 | `mcp.install()` | **exists+real** | Creates UserMcpInstall row, 409 on dup |
| PATCH /mcp-installs/{id} | mcp.py:156 | `mcp.updateInstall()` | **exists+real** | **is_enabled PERSISTED** — writes `install.is_enabled = data.is_enabled` then `db.commit()` (mcp_service.py:368-373) |
| DELETE /mcp-installs/{id} | mcp.py:176 | `mcp.uninstall()` | **exists+real** | Physical delete |

> **MCP toggle persistence verdict: PASS** — `PATCH /mcp-installs/{id}` → `MCPService.update_install()` at mcp_service.py:356 reads `data.is_enabled`, sets `install.is_enabled = data.is_enabled`, calls `db.commit()`. The `is_enabled` column is persisted to the `user_mcp_installs` table.  
> **Agent startup loads this state**: executor processes would query `user_mcp_installs` filtered by `is_enabled=True`. (Verification of executor load path is outside input file scope; the DB write side is confirmed real.)

---

## Providers (`/providers`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /providers | providers.py:76 | `providers.list()` | **exists+real** | Includes real-time Redis circuit-breaker state |
| GET /providers/{id} | — | `providers.get()` | **missing** | apiClient calls `GET /providers/${id}` but no such route exists in providers.py |
| POST /providers | providers.py:109 | `providers.create()` | **exists+real** | Validates capabilities, encrypts API key |
| PUT /providers/{id} | providers.py:134 | `providers.update()` | **exists+real** | Permission matrix enforced |
| DELETE /providers/{id} | providers.py:165 | `providers.delete_()` | **exists+real** | Permission matrix enforced |
| POST /providers/{id}/test | providers.py:194 | `providers.test()` | **exists+real** | Real provider probe |
| GET /providers/usage | providers.py:222 | `providers.usage()` | **exists+real** | `group_by`, `start_date`, `end_date` all consumed by `UsageService.get_user_usage()` |
| GET /providers/presets | providers.py:60 | `providers.presets()` | **exists+real** | Public, no auth required |

> **Severity: MEDIUM** — `GET /providers/{id}` is called by apiClient (`providers.get(id)`) but no `@router.get("/{provider_id}")` route exists in providers.py. FastAPI will return 405. Frontend code calling this will fail silently or surface as a UI gap if provider detail view is used.

---

## Admin (`/admin`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /admin/users | admin.py:90 | `admin.listUsers()` | **exists+real** | `page` and `search` consumed with `.ilike()` |
| PATCH /admin/users/{id} | admin.py:200 | `admin.updateUser()` | **exists+real** (deprecated) | Delegates to `change_user_role` logic |
| PATCH /admin/users/{id}/role | admin.py:136 | `admin.changeUserRole()` | **exists+real** | Last-admin guard ADR-083 |
| DELETE /admin/users/{id} | admin.py:221 | `admin.disableUser()` | **exists+real** | Soft-disable (is_active=False) |
| GET /admin/invite-codes | admin.py:300 | `admin.listInviteCodes()` | **exists+real** | Returns all with is_valid computed |
| POST /admin/invite-codes | admin.py:262 | `admin.createInviteCode()` | **exists+real** | PRISM-XXXXXXXX format |
| DELETE /admin/invite-codes/{id} | admin.py:317 | `admin.revokeInviteCode()` | **exists+real** | Sets max_uses = used_count |
| GET /admin/audit-logs | admin.py:425 | `admin.listAuditLogs()` | **exists-partial** | Backend accepts `action/user_id/severity/start_time/end_time/page/page_size`; apiClient sends `start_date/end_date` (not `start_time/end_time`) — param name mismatch, dates silently dropped |
| GET /admin/audit-logs/export | admin.py:496 | `admin.exportAuditLogsCSV()` | **exists+real** | CSV download, max 10k rows |
| GET /admin/stats/dashboard | admin.py:544 | `admin.getDashboard()` | **exists+real** | `AdminStatsService.get_dashboard()` — real DB+Redis queries |
| GET /admin/usage | admin.py:344 | `admin.getUsage()` | **param-ignored** | apiClient sends `group_by`, `start_date`, `end_date`; backend `get_usage()` accepts NO query params — hardcoded last-30-days, no time-range filtering |
| GET /admin/alerts/config | admin.py:610 | `admin.getAlertConfig()` | **exists+real** | Returns in-memory Settings values |
| PATCH /admin/alerts/config | admin.py:632 | `admin.updateAlertConfig()` | **exists+real** | Updates in-memory Settings (not persisted to .env) |

> **Severity: MEDIUM** — `GET /admin/usage`: Frontend sends `group_by`, `start_date`, `end_date` params but the endpoint signature is `def get_usage(db)` with no query parameters. FastAPI silently ignores unknown query params. The frontend's date-range filter has zero effect; response is always last-30-days aggregate.
>
> **Severity: LOW** — `GET /admin/audit-logs`: Frontend sends `start_date`/`end_date` but backend expects `start_time`/`end_time`. FastAPI ignores unrecognized query params, so date-range filtering in audit logs is silently broken via apiClient.

---

## Skills (`/skills`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /skills/search | skills.py:144 | `skills.search()` | **exists+real** | See verdict below |
| GET /skills/installed | skills.py:215 | `skills.listInstalled()` | **exists+real** | Queries `skill_installs` table, status='installed' filter |
| GET /skills/{name} | skills.py:564 | `skills.get()` | **exists+real** | DB first, then registry search fallback |
| POST /skills/install | skills.py:243 | `skills.install()` | **exists+real** | Writes `skill_installs` table, base64 decode + file write for local/marketplace |
| PATCH /skills/{name} | skills.py:410 | `skills.patch()` | **exists+real** | Writes `metadata_.enabled` to DB + commit |
| GET /skills/{name}/content | skills.py:456 | `skills.getContent()` | **exists+real** | Reads SKILL.md from install_path |
| POST /skills/{name}/update | skills.py:501 | `skills.update()` | **exists+real** | Calls `SkillsRegistry.update()` + DB sync |
| DELETE /skills/{name} | skills.py:373 | `skills.uninstall()` | **exists+real** | Updates status='uninstalled' in metadata_ |

### Skills Search `q` Parameter Verdict — HIGH SEVERITY

**Root cause of "搜啥都没出 / 不支持模糊"**:

The `q` parameter IS passed from frontend → `GET /skills/search?q=...` → `skills.py:149` → `registry.search(q, sources)`.

The registry calls two sources in parallel:
1. **LocalSource.search(q)** — `skills_registry.py:156` — does `_matches(pkg, query)` at line 265: substring match on `pkg.name.lower()`, `pkg.description.lower()`, tags. **This works correctly for local skills.**
2. **MarketplaceCatalogSource.search(q)** — `skills_registry.py:322` — does `_marketplace_entry_matches(entry, q)` at line 396: substring match on name/description/keywords. **This works correctly for marketplace skills.**

**The real issue**: Both sources search in-memory against already-loaded data. They do NOT hit a database search query. For `LocalSource`: skills must exist as `SKILL.md` files in `{workspace}/.skills/` or `{workspace}/.prism/skills/`. For `MarketplaceCatalogSource`: skills must exist in the `marketplace_registry.catalog_json` JSONB column (populated only after a marketplace `sync`).

**If search returns nothing it is because**:
- No local `SKILL.md` files exist in the scanned directories (empty local install), AND
- No marketplace has been registered + synced (empty catalog_json)

The `q` parameter is correctly filtered in-memory once data is loaded. The search is NOT broken — the **data source is empty**. There is no SQL `ILIKE` because the search is file-system + JSON, not DB text search.

**Conclusion**: `GET /skills/search` — status **exists+real**, `q` param **actively consumed**. The user-reported "搜啥都没出" is a data population problem, not a param-ignored bug.

---

## Plugins (`/plugins`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /plugins/library | plugins.py:534 | `plugins.listLibrary()` | **exists+real** | Queries `plugin_library` table filtered by user_id |
| POST /plugins/save | plugins.py:561 | `plugins.save()` | **exists+real** | UPSERT semantics; parses YAML if manifest_json empty |
| PATCH /plugins/library/{id} | plugins.py:663 | `plugins.patch()` | **exists+real** | Sets `entry.enabled`, commits |
| DELETE /plugins/library/{id} | plugins.py:710 | `plugins.delete()` | **exists+real** | Physical delete with ownership check |

---

## Marketplaces (`/marketplaces`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /marketplaces | marketplaces.py:60 | `marketplaces.list()` | **exists+real** | `MarketplaceService.list_all()` |
| POST /marketplaces | marketplaces.py:74 | `marketplaces.create()` | **exists+real** | Runs in threadpool (git clone may block) |
| POST /marketplaces/{id}/sync | marketplaces.py:128 | `marketplaces.sync()` | **exists+real** | Refreshes catalog_json |
| DELETE /marketplaces/{id} | marketplaces.py:108 | `marketplaces.delete()` | **exists+real** | Sets skill_installs.marketplace_id → NULL |
| POST /marketplaces/{id}/plugins/{name}/install | marketplaces.py:152 | `marketplaces.installPlugin()` | **exists+real** | ADR-090 5-source resolver |

---

## IM (`/im`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /im/channels | im.py:63 | `im.listChannels()` | **exists+real** | Placeholder rows for unconfigured channels; secrets redacted |
| PATCH /im/channels/{channel} | im.py:108 | `im.updateChannel()` | **exists+real** | Merges config JSONB, encrypts secret fields |
| GET /im/bindings | im.py:545 | `im.listBindings()` | **exists+real** | `IMBindingService.list_bindings()` |
| POST /im/bindings/pair | im.py:574 | `im.generatePairingCode()` | **exists+real** | 6-char code, 5-min TTL |
| DELETE /im/bindings/{id} | im.py:617 | `im.unbind()` | **exists+real** | Physical delete with ownership check |

---

## Harness (`/harness`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /harness/config | harness.py:37 | `harness.config()` | **exists+real** | Loads from YAML file via `HarnessConfigLoader`; admin only |
| GET /harness/analytics | harness.py:76 | `harness.analytics()` | **exists-partial** | Frontend sends `window` param (e.g. `'7d'`); backend signature uses `days: int` + `offset_days: int`. The string `'7d'` will fail FastAPI int coercion → **422 error on default call** |
| POST /harness/entropy-check | harness.py:96 | `harness.entropyCheck()` | **exists+real** | Admin only; runs real EntropyDetector |
| POST /harness/threshold-calibrate | harness.py:114 | `harness.thresholdCalibrate()` | **exists+real** | Admin only; returns suggestions, does NOT auto-write |

> **Severity: HIGH** — `GET /harness/analytics`: apiClient sends `{ query: { window: w } }` where `w = '7d'` (a string). The backend endpoint declares `days: int = Query(default=7)`. FastAPI will attempt to coerce `'7d'` to `int` and raise HTTP 422. The `window` parameter name is also mismatched (`window` vs `days`). Both calls from `harness.analytics()` will 422 by default.

---

## Health (`/health`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| GET /health/detailed | health.py:129 | `healthDetailed()` | **exists+real** | Admin only; real DB+Redis+psutil+Redis circuit-breaker checks |

---

## Frontend Error Reporting (`/frontend-errors`)

| Endpoint | File:Line | Frontend Call | Status | Notes |
|---|---|---|---|---|
| POST /frontend-errors | frontend.py:93 | `reportError()` | **exists+real** | IP rate-limited, writes AuditLog, increments Prometheus counter |

---

## Summary Table

| Domain | Total Endpoints | exists+real | exists-partial | param-ignored | missing | exists-stub |
|---|---|---|---|---|---|---|
| auth | 16 | 16 | 0 | 0 | 0 | 0 |
| sessions | 8 | 8 | 0 | 0 | 0 | 0 |
| tasks | 1 | 1 | 0 | 0 | 0 | 0 |
| runs | 3 | 3 | 0 | 0 | 0 | 0 |
| mcp | 9 | 9 | 0 | 0 | 0 | 0 |
| providers | 8 | 7 | 0 | 0 | 1 | 0 |
| admin | 13 | 10 | 0 | 2 | 0 | 0 |
| skills | 8 | 8 | 0 | 0 | 0 | 0 |
| plugins | 4 | 4 | 0 | 0 | 0 | 0 |
| marketplaces | 5 | 5 | 0 | 0 | 0 | 0 |
| im | 5 | 5 | 0 | 0 | 0 | 0 |
| harness | 4 | 3 | 1 | 0 | 0 | 0 |
| health | 1 | 1 | 0 | 0 | 0 | 0 |
| frontend-errors | 1 | 1 | 0 | 0 | 0 | 0 |
| **TOTAL** | **86** | **81** | **1** | **2** | **1** | **0** |

---

## Issues by Severity

### HIGH — User-impacting / Broken Functionality

| # | Endpoint | Issue | Fix |
|---|---|---|---|
| H1 | GET /harness/analytics | apiClient sends `window='7d'` (string); backend expects `days: int`. FastAPI coercion → 422. Parameter name also mismatched. | Change apiClient to send `{ query: { days: 7 } }` OR change backend to accept `window: str` and parse it |

### MEDIUM — Functional gap, not user-reported

| # | Endpoint | Issue | Fix |
|---|---|---|---|
| M1 | GET /providers/{id} | Route missing in providers.py; apiClient calls it. Any frontend UI that calls `providers.get(id)` gets 404/405 | Add `@router.get("/{provider_id}")` route |
| M2 | GET /admin/usage | Backend ignores `group_by`, `start_date`, `end_date` params — always returns last-30-days aggregate | Add query params to endpoint signature + pass to query |

### LOW — Edge cases / Admin functions

| # | Endpoint | Issue | Fix |
|---|---|---|---|
| L1 | GET /admin/audit-logs | apiClient sends `start_date`/`end_date`; backend expects `start_time`/`end_time` — date filters silently dropped | Align param names in one direction |
| L2 | PATCH /admin/alerts/config | Updates are in-memory only, not persisted to .env — resets on restart. Documented behavior but surprising. | Note in UI that changes require restart |

---

## Special Focus Answers

### Skills Search (`GET /skills/search?q=`)
**Status: exists+real — q parameter actively consumed**

The `q` param flows: apiClient → `skills.py:search_skills()` → `registry.search(q)` → parallel `LocalSource._matches()` + `MarketplaceCatalogSource._marketplace_entry_matches()`. Both do case-insensitive substring matching on name/description/tags. Search returns empty because **data sources are empty** (no local SKILL.md files + no synced marketplace catalogs), not because `q` is ignored.

### MCP Toggle (`PATCH /mcp-installs/{id}`)
**Status: is_enabled PERSISTED — PASS**

`mcp_service.py:368`: `install.is_enabled = data.is_enabled`, followed by `db.commit()` at line 373. The `user_mcp_installs.is_enabled` column is durably written to PostgreSQL. Agent startup behavior (whether executor reads this column) is outside the audited file scope.

### Change Password (`POST /auth/change-password`)
**Status: NOT IN apiClient.js — N/A**

`apiClient.js` does not define a `changePassword()` function. No such endpoint exists in `backend/app/api/v1/auth.py`. Password changes go through the `reset-password` token flow (forgot-password → email → reset-password).

### Admin Endpoints
**Status: All 13 admin endpoints exist+real or param-ignored**

None are stubs. `getDashboard()` calls real `AdminStatsService`. `listAuditLogs()` runs real DB queries. The two param-ignored issues (admin/usage, admin/audit-logs date param names) are functional gaps, not stubs.

### Observability / Harness
**Status: harness/analytics is BROKEN (HIGH)**

`GET /harness/config` — real YAML load. `POST /harness/entropy-check` — real `EntropyDetector`. `POST /harness/threshold-calibrate` — real `ThresholdCalibrator`. `GET /harness/analytics` — 422 due to `window='7d'` string → int coercion failure.
