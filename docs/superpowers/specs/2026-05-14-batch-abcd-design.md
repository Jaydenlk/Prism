# Batch A-D Design Spec — Bug Fixes + UX + IM + Features

> Date: 2026-05-14
> Scope: 10 items across 4 batches (team architecture excluded, separate iteration)

---

## Batch A: Critical Bugs (parallel)

### A1: User messages disappear on refresh
**Root cause:** User prompt stored only in `runs.prompt`, not in `messages` table. On refresh, history loads from `messages` — only assistant messages exist.
**Fix:** Backend `_handle_message_complete` or task submission should persist user prompt as a `role=user` Message record when creating the Run.
**Files:** `backend/app/services/task_service.py` or `backend/app/services/callback_service.py`

### A2: Skills Market GitHub stars missing
**Root cause:** Skills search API previously returned star counts from GitHub source. Need to check if the search response schema still includes `stars` field and if the frontend renders it.
**Files:** `backend/app/api/v1/skills.py`, `frontend/Prism.html` (SkillsPage)

### A3: Feishu IM messages not being read
**Root cause:** `FEISHU_ENCRYPT_KEY` and `FEISHU_VERIFICATION_TOKEN` were just configured. Backend needs restart to pick up. Also verify the webhook endpoint receives and processes messages correctly.
**Files:** `backend/app/services/im_feishu.py`, `backend/app/api/v1/im.py`

---

## Batch B: UX Design (sequential: color → dark theme → file preview)

### B1: Warm color tone adjustment — brighten
**Current:** `--paper: #F5F1EA`, `--bg: #EDE6D6` — too warm/yellow
**Target:** Lighter, cleaner warmth. Shift toward cream-white.
**Approach:** Adjust 4 core CSS variables in `frontend/styles.css`

### B2: Dark theme
**Approach:** CSS `[data-theme="dark"]` selector overriding all CSS variables. Toggle in settings or header.
**Files:** `frontend/styles.css`, `frontend/Prism.html` (theme toggle button)

### B3: File preview
**Scope:** After uploading a text file, show its content in a scrollable preview panel above the input.
**Approach:** Expand the existing attachment chip into a preview card with syntax-highlighted content.
**Files:** `frontend/Prism.html` (Composer component)

---

## Batch C: IM Experience (depends on A3)

### C1: Feishu emoji read receipt
**Flow:**
1. Receive message → react with 👀 emoji on the Feishu message
2. Start processing → emoji stays
3. Run complete → remove 👀 emoji, send reply text
4. On Prism platform: show `[飞书] 👀 正在处理` → `[飞书] 处理完成`
**Files:** `backend/app/services/im_feishu.py`, `backend/app/services/callback_service.py`

### C2: IM messages page
**Design:** New sidebar nav item "消息" or integrate into existing "会话" page with IM filter.
**Layout:** 3 channel tabs (飞书/企微/Telegram), each shows conversation history.
**Data source:** Sessions with `im_channel` field set, messages from those sessions.
**Files:** `frontend/Prism.html` (new IMPage component), `frontend/apiClient.js`

---

## Batch D: Big Features

### D1: OAuth login (Google + GitHub)
**Backend:** Add OAuth endpoints using `authlib`. Store OAuth tokens in `users` table.
**Frontend:** OAuth buttons on login page.
**Files:** `backend/app/api/v1/auth.py`, `frontend/Prism.html` (LoginPage)

### D2: Plugin Builder test — Financial Info + KYC
**Financial Info Plugin:**
- Research free/paid financial data channels
- Design plugin with timeliness weighting, cost-benefit display
- Check existing open-source options

**KYC Plugin:**
- Find Anthropic's recent KYC template on GitHub
- Evaluate and recommend integration approach
- Build via Plugin Builder UI

**Test both paths:** Plugin Builder UI creation + code-based definition + agent execution verification
