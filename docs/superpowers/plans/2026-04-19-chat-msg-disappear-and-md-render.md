# Chat User Message Disappearance + Markdown Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two visible Prism v2 chat UI bugs — (1) user message bubble disappears after `run_complete` and (2) assistant markdown renders as raw text — with Playwright double-viewport verification and full downstream skill chain before merge.

**Architecture:** Zero-build inline React in `frontend/Prism.html` + `frontend/styles.css`. Bug 1: evidence-gated fix, either parser bottom-out (A) or run_complete merge (B), decided by a Playwright reproduction. Bug 2: `marked@12` + `DOMPurify@3` via jsdelivr CDN `<script>` tags, new `MarkdownBody` component, `.content.md` typography scoped to existing tokens. No backend/executor/schema changes.

**Tech Stack:** JavaScript (inline React + Babel standalone), Playwright (desktop-chromium + mobile-safari), Docker Compose (already running), marked@12 + DOMPurify@3 via jsdelivr CDN.

**Spec:** `docs/superpowers/specs/2026-04-19-chat-msg-disappear-and-md-render-design.md` (commit `1763119`)

**Context reminders:**
- Session 1 of parallel execution plan. Sessions 2a/2b (Exa competitive research) completed in background; their output at `docs/research/2026-04-19-skills-plugins-im-competitive.md` and `docs/research/2026-04-19-distributed-task-decomposition.md` is consumed by Session 3 (Bug 3 architecture ADR), not by this plan.
- Docker stack already running (`prismv3-backend-1` healthy, `prismv3-nginx-1` running — nginx healthcheck is noisy but serving traffic). Do not restart.
- Admin login: `admin@prism.dev` / `PrismAdmin!2026`.
- Repo currently on `master`. No `develop` branch exists yet — Task 11 creates it.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `frontend/Prism.html` | Modify | Two regions: (a) add CDN `<script>` tags for marked+DOMPurify in `<head>`, (b) add `MarkdownBody` component + call it from `Msg` (line 436), (c) fix Bug 1 in `run_complete` handler (line 772-802) OR parser (line 780-796) based on Task 3 evidence. |
| `frontend/styles.css` | Modify | Add `.content.md` block at file tail with typography rules reusing existing tokens. Add `--mono` to `:root` only if not present. |
| `e2e/tests/chat-msg-render.spec.ts` | Create | Two Playwright tests — Bug 1 (user bubble persists) and Bug 2 (markdown renders as HTML). Runs on `desktop-chromium` and `mobile-safari`. |
| `docs/superpowers/plans/2026-04-19-chat-msg-disappear-and-md-render.md` | (this file) | Source of truth. |
| `HANDOFF-LOG.md` | Modify at Task 12 | Append Session 1 completion record; remove/archive the 🔴 red block at top. |

Existing e2e pattern: fixtures in `e2e/fixtures/auth.ts`, tests in `e2e/tests/*.spec.ts` (e.g., `chat.spec.ts`). Reuse `auth.ts` fixture.

---

## Task 1: Worktree setup

**Files:**
- Create: git worktree at adjacent dir
- Branch: `fix/chat-msg-disappear-and-md-render` off `master`

- [ ] **Step 1: Load worktree skill**

Invoke Skill tool with `superpowers:using-git-worktrees`. Follow its guidance on worktree placement. Recommended placement: sibling dir `../PrismV3-fix-chat-md/` to keep CLAUDE.md-described project working tree clean.

- [ ] **Step 2: Verify main tree clean baseline**

Run in main tree:
```bash
git status --short
```
Expected output includes `M HANDOFF-LOG.md` and `?? .claude/settings.json` (these are untouched by this work). Confirm no other unexpected files. Do NOT stage or commit these.

- [ ] **Step 3: Create worktree**

```bash
cd "E:/Agent program/PrismV3"
git worktree add ../PrismV3-fix-chat-md -b fix/chat-msg-disappear-and-md-render master
```
Expected: "Preparing worktree (new branch 'fix/chat-msg-disappear-and-md-render')" and new dir `../PrismV3-fix-chat-md` populated.

- [ ] **Step 4: Change working directory into worktree for all remaining tasks**

```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
git branch --show-current
```
Expected output: `fix/chat-msg-disappear-and-md-render`. All subsequent tool calls reference paths relative to this worktree.

- [ ] **Step 5: Commit checkpoint**

No files changed yet; skip commit this step. Proceed to Task 2.

---

## Task 2: Write failing E2E tests (TDD red phase)

**Files:**
- Create: `e2e/tests/chat-msg-render.spec.ts`

**Purpose:** Two Playwright tests that MUST fail before any implementation — Bug 1 (user bubble persists) and Bug 2 (markdown renders). After both fixes land they MUST pass on `desktop-chromium` and `mobile-safari`.

- [ ] **Step 1: Inspect existing test pattern for auth fixture usage**

```bash
cat e2e/tests/chat.spec.ts | head -60
cat e2e/fixtures/auth.ts
```
Note: how `loggedInPage` fixture is named/imported. Use the identical import style for the new file.

- [ ] **Step 2: Create the spec file**

Write `e2e/tests/chat-msg-render.spec.ts` with two tests:

```typescript
import { test, expect } from '../fixtures/auth';

// Helper: start a new chat session and return its ID from the URL after first send
async function openFreshChat(page: any): Promise<string> {
  await page.goto('/');
  // Click "新建对话" or the equivalent affordance in Prism.html
  const newChatBtn = page.locator('[data-testid="new-chat"], button:has-text("新建对话"), button:has-text("新建")').first();
  if (await newChatBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await newChatBtn.click();
  }
  // Wait for composer to be focusable
  await expect(page.locator('textarea').first()).toBeVisible({ timeout: 10_000 });
  return page.url();
}

test.describe('Chat message rendering fixes (Session 1)', () => {
  test('Bug 1: user bubble persists after run_complete', async ({ loggedInPage: page }) => {
    await openFreshChat(page);
    const token = `TEST-BUG1-${Date.now()}`;
    const composer = page.locator('textarea').first();
    await composer.fill(token);
    await composer.press('Enter');

    // Wait for SSE run to complete — detect by agent message appearing without streaming caret
    await expect(page.locator('.agent-msg .content').first()).toBeVisible({ timeout: 30_000 });
    // Additional wait: no streaming caret present (end of stream)
    await expect(page.locator('.agent-msg .caret')).toHaveCount(0, { timeout: 15_000 });
    // Small settle wait for run_complete history refresh
    await page.waitForTimeout(1500);

    // Assertion: the token the user typed MUST still be visible somewhere in a user bubble
    const userBubbleWithToken = page.locator('.user-msg .bubble', { hasText: token });
    await expect(userBubbleWithToken).toBeVisible();
    await expect(userBubbleWithToken).toContainText(token);
  });

  test('Bug 2: markdown renders as formatted HTML in assistant reply', async ({ loggedInPage: page }) => {
    await openFreshChat(page);
    const prompt = [
      '请用 markdown 回复以下内容原样结构（不要翻译、不要总结、不要加前缀）:',
      '',
      '## 标题 H2',
      '',
      '- 列表项 A',
      '- 列表项 B',
      '- **粗体文本** 和 `inline code`',
      '',
      '```python',
      'def hello():',
      '    print("hi")',
      '```',
      '',
      '> 引用段落',
      '',
      '| 列 A | 列 B |',
      '|---|---|',
      '| 1 | 2 |',
    ].join('\n');
    const composer = page.locator('textarea').first();
    await composer.fill(prompt);
    await composer.press('Enter');

    await expect(page.locator('.agent-msg .content').first()).toBeVisible({ timeout: 60_000 });
    await expect(page.locator('.agent-msg .caret')).toHaveCount(0, { timeout: 30_000 });
    await page.waitForTimeout(1000);

    const mdRoot = page.locator('.agent-msg .content.md').first();
    // Structural assertions — every markdown element must become an HTML element, not text
    await expect(mdRoot.locator('h2', { hasText: '标题 H2' })).toBeVisible();
    await expect(mdRoot.locator('ul li')).toHaveCount(3);
    await expect(mdRoot.locator('strong', { hasText: '粗体文本' })).toBeVisible();
    await expect(mdRoot.locator('code', { hasText: 'inline code' })).toBeVisible();
    await expect(mdRoot.locator('pre code')).toContainText('def hello');
    await expect(mdRoot.locator('blockquote')).toContainText('引用段落');
    await expect(mdRoot.locator('table thead th')).toHaveCount(2);
    await expect(mdRoot.locator('table tbody tr')).toHaveCount(1);

    // Screenshot evidence for manual review
    await page.locator('.agent-msg').last().screenshot({ path: `test-results/md-${test.info().project.name}.png` });
  });
});
```

- [ ] **Step 3: Run the spec on desktop-chromium and confirm FAIL**

```bash
cd e2e
npx playwright test chat-msg-render.spec.ts --project=desktop-chromium
```
Expected: both tests FAIL (Bug 1 expects user bubble with token → currently disappears; Bug 2 expects `.content.md` → currently `.content` has no md class and no `<h2>/<ul>/...` inside).

- [ ] **Step 4: Run on mobile-safari and confirm FAIL**

```bash
cd e2e
npx playwright test chat-msg-render.spec.ts --project=mobile-safari
```
Expected: both tests FAIL.

- [ ] **Step 5: Commit red phase**

```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
git add e2e/tests/chat-msg-render.spec.ts
git commit -m "$(cat <<'EOF'
test(e2e): add failing E2E for chat user-bubble persistence + markdown render

- Bug 1: assert user bubble with unique token still visible after run_complete
- Bug 2: assert .content.md contains real h2/ul/strong/code/pre/blockquote/table

Both tests currently FAIL — red phase of TDD for Session 1 fixes.
EOF
)"
```

---

## Task 3: Bug 1 reproduction — decide root cause A vs B

**Files:**
- (diagnostic only — no commits)

**Purpose:** Before picking A or B in Task 4, capture the real shape of `m.content` for a user message via Playwright interception. One fix only.

- [ ] **Step 1: Load systematic-debugging skill**

Invoke Skill tool with `superpowers:systematic-debugging`. Follow its root-cause-first discipline — no speculative fixes until Task 3 produces evidence.

- [ ] **Step 2: Create a temporary diagnostic test**

Create `e2e/tests/_diagnostic-bug1.spec.ts` (underscore prefix — we delete it after Task 3):

```typescript
import { test } from '../fixtures/auth';

test('diagnostic: capture user message shape on run_complete', async ({ loggedInPage: page }) => {
  const captured: any[] = [];
  await page.route('**/api/v1/sessions/*/messages**', async (route) => {
    const resp = await route.fetch();
    const body = await resp.text();
    captured.push({ url: route.request().url(), body });
    await route.fulfill({ response: resp, body });
  });

  await page.goto('/');
  const newBtn = page.locator('[data-testid="new-chat"], button:has-text("新建对话"), button:has-text("新建")').first();
  if (await newBtn.isVisible({ timeout: 2000 }).catch(() => false)) await newBtn.click();
  const composer = page.locator('textarea').first();
  const token = `DIAG-${Date.now()}`;
  await composer.fill(token);
  await composer.press('Enter');
  await page.waitForTimeout(20_000); // generous wait for run_complete + history refresh

  console.log('=== DIAGNOSTIC CAPTURE ===');
  console.log(`Captured ${captured.length} /messages calls`);
  for (const c of captured) {
    console.log('URL:', c.url);
    console.log('BODY:', c.body.slice(0, 3000));
    console.log('---');
  }
  console.log('=== SEARCH TOKEN:', token);
});
```

- [ ] **Step 3: Run diagnostic and inspect output**

```bash
cd e2e
npx playwright test _diagnostic-bug1.spec.ts --project=desktop-chromium --reporter=list
```

Inspect the captured `/messages` bodies for the user row (the row where `role === "user"`). Look at two things:
1. Is there a row with `role === "user"` and `text_preview` containing `DIAG-...`? If NO → Case B (race / row missing).
2. If YES, what is `m.content`? Array of `{type:"text", text:"..."}`? Array of other block types? A raw string? If NOT a `{type:"text"}` array → Case A (parser starvation).

- [ ] **Step 4: Record the decision inline in the plan (edit this file)**

Edit this plan, in Task 4's header, insert one line: `**Decision: Case <A | B> because <one-sentence evidence>.**` Commit this edit before Task 4 starts:

```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
git add docs/superpowers/plans/2026-04-19-chat-msg-disappear-and-md-render.md
git commit -m "docs(plan): record Bug 1 root cause decision from Task 3 reproduction"
```

- [ ] **Step 5: Delete the diagnostic spec**

```bash
rm e2e/tests/_diagnostic-bug1.spec.ts
git add e2e/tests/_diagnostic-bug1.spec.ts
git commit -m "chore(e2e): drop Bug 1 diagnostic spec after root cause confirmed"
```

---

## Task 4: Bug 1 fix — apply Case A OR Case B (never both)

**Decision:** (filled in at Task 3 Step 4)

**Files:**
- Modify: `frontend/Prism.html:780-796` (Case A) OR `frontend/Prism.html:795-800` (Case B)

- [ ] **Step 1: If decision = Case A — apply parser bottom-out**

Read `frontend/Prism.html` lines 770-805 to confirm exact surrounding context. Then replace the parser block:

Old (lines 782-796):
```javascript
            while (i < rawMsgs.length) {
              const m = rawMsgs[i];
              if (m.role === "user") {
                const textBlocks = (m.content || []).filter(b => b.type === "text");
                displayMsgs.push({ role: "user", at: formatTime(m.created_at), content: textBlocks.map(b => b.text).join("\n") || m.text_preview || "" });
                i++;
              } else if (m.role === "assistant") {
                let toolResults = [];
                if (i + 1 < rawMsgs.length && rawMsgs[i + 1].role === "tool_result") { toolResults = rawMsgs[i + 1].content || []; }
                const { text, tools } = renderContentBlocks(m.content, toolResults);
                displayMsgs.push({ role: "agent", at: formatTime(m.created_at), content: text || m.text_preview || "", tools, streaming: false });
                i++;
                if (toolResults.length > 0) i++;
              } else { i++; }
            }
```

New:
```javascript
            while (i < rawMsgs.length) {
              const m = rawMsgs[i];
              if (m.role === "user") {
                let text = "";
                if (Array.isArray(m.content)) {
                  const textBlocks = m.content.filter(b => b && b.type === "text");
                  text = textBlocks.map(b => b.text).join("\n");
                  if (!text) {
                    text = m.content.map(b => (b && typeof b.text === "string") ? b.text : "").filter(Boolean).join("\n");
                  }
                } else if (typeof m.content === "string") {
                  text = m.content;
                }
                if (!text) text = m.text_preview || "[空消息]";
                displayMsgs.push({ role: "user", at: formatTime(m.created_at), content: text });
                i++;
              } else if (m.role === "assistant") {
                let toolResults = [];
                if (i + 1 < rawMsgs.length && rawMsgs[i + 1].role === "tool_result") { toolResults = rawMsgs[i + 1].content || []; }
                const { text, tools } = renderContentBlocks(m.content, toolResults);
                displayMsgs.push({ role: "agent", at: formatTime(m.created_at), content: text || m.text_preview || "", tools, streaming: false });
                i++;
                if (toolResults.length > 0) i++;
              } else { i++; }
            }
```

- [ ] **Step 2: If decision = Case B — apply merge strategy**

Read `frontend/Prism.html` lines 772-802 to confirm. Then change the body of the `.then(historyRes => {...})` handler:

Old (lines 797-799):
```javascript
            setMsgs(displayMsgs);
            streamBuf.current = {};
            scrollToBottom();
```

New:
```javascript
            setMsgs(prev => {
              const dbContentKeys = new Set(
                displayMsgs.filter(m => m.role === "user").map(m => (m.content || "").trim())
              );
              const optimisticTail = prev.filter(m => m.role === "user" && m.at === "now" && !dbContentKeys.has((m.content || "").trim()));
              return [...displayMsgs, ...optimisticTail];
            });
            streamBuf.current = {};
            scrollToBottom();
```

Rationale for content-trim key (not `at`): optimistic msgs have `at:"now"`, DB msgs have a formatted time — keys can't match directly. Dedup by trimmed content is sufficient for the 5-second race window (user won't send the same 100%-identical prompt in that window).

- [ ] **Step 3: Run Bug 1 test — must now PASS on both viewports**

```bash
cd e2e
npx playwright test chat-msg-render.spec.ts -g "Bug 1" --project=desktop-chromium
npx playwright test chat-msg-render.spec.ts -g "Bug 1" --project=mobile-safari
```
Expected: both runs PASS (1 passed).

- [ ] **Step 4: Commit Bug 1 fix**

```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
git add frontend/Prism.html
git commit -m "$(cat <<'EOF'
fix(frontend): user message bubble persists after run_complete (Bug 1)

Root cause: <A parser starvation | B race/wipe on setMsgs> — see plan Task 3.

<A: parser bottom-out — non-text-typed content blocks, raw-string content, and missing text_preview all fall through to "[空消息]" placeholder; no more empty bubble>
<B: run_complete no longer wipes optimistic user msgs not yet reflected in DB history>

Verified: Bug 1 Playwright test passes on desktop-chromium + mobile-safari.
EOF
)"
```

(Delete the non-applicable branch from the commit message body.)

---

## Task 5: Bug 2 step 1 — add marked + DOMPurify CDN scripts

**Files:**
- Modify: `frontend/Prism.html` `<head>` section

- [ ] **Step 1: Locate the CDN block in Prism.html**

Search the file for existing CDN `<script src="https://cdn.jsdelivr.net/...">` lines (React/ReactDOM/Babel are already loaded this way). Place the new scripts in the same block.

```bash
grep -n "jsdelivr" frontend/Prism.html | head -20
```

- [ ] **Step 2: Add pinned marked@12 + DOMPurify@3 script tags**

Insert after the existing React/Babel CDN lines:

```html
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.0.11/dist/purify.min.js"></script>
```

- [ ] **Step 3: Verify globals load**

Reload `http://localhost:8080/` in a browser. In devtools console:
```javascript
typeof window.marked   // "object"
typeof window.DOMPurify // "object"
window.marked.parse("# hi").trim() // "<h1>hi</h1>"
```

- [ ] **Step 4: Commit**

```bash
git add frontend/Prism.html
git commit -m "feat(frontend): add marked@12 + DOMPurify@3 CDN scripts for md rendering"
```

---

## Task 6: Bug 2 step 2 — MarkdownBody component + Msg integration

**Files:**
- Modify: `frontend/Prism.html` — new component near `Msg` (around line 410-450), call site at line 436

- [ ] **Step 1: Insert MarkdownBody component definition**

Read `frontend/Prism.html:405-420` to find the empty line before `function Msg(...)`. Insert:

```jsx
function MarkdownBody({ content, streaming }) {
  const html = React.useMemo(() => {
    if (!content) return "";
    try {
      return window.DOMPurify.sanitize(window.marked.parse(content, {
        gfm: true, breaks: false, headerIds: false, mangle: false,
      }));
    } catch (e) {
      return "";
    }
  }, [content]);
  return (
    <div className="content md">
      <div dangerouslySetInnerHTML={{ __html: html }} />
      {streaming && <span className="caret"/>}
    </div>
  );
}
```

- [ ] **Step 2: Replace the assistant content render call site at line 436**

Old (around line 436):
```jsx
          ) : (
            <div className="content">{m.content}{m.streaming && <span className="caret"/>}</div>
          )}
```

New:
```jsx
          ) : (
            <MarkdownBody content={m.content} streaming={m.streaming}/>
          )}
```

- [ ] **Step 3: Smoke check in browser (pre-typography)**

Reload app, send a prompt with markdown (e.g. `## Hi\n\n- one\n- two`). The assistant reply should now contain `<h2>` and `<ul>` in DOM but with no specific styling — raw browser defaults are acceptable at this step. `document.querySelectorAll('.agent-msg .content.md h2').length` in devtools should be `≥ 1`.

- [ ] **Step 4: Commit**

```bash
git add frontend/Prism.html
git commit -m "feat(frontend): MarkdownBody component renders assistant content as sanitized HTML"
```

---

## Task 7: Bug 2 step 3 — typography styles

**Files:**
- Modify: `frontend/styles.css`

- [ ] **Step 1: Verify existing token palette**

```bash
grep -E "^\s*--(serif|ink|bg|line|accent|mono)" frontend/styles.css | head -20
```
Note which tokens exist. If `--mono` is absent, include its definition in Step 2.

- [ ] **Step 2: Append `.content.md` typography block to styles.css**

Append at end of `frontend/styles.css` (add `--mono` in `:root` only if not present):

```css
/* ---- Markdown rendering in assistant messages ---- */

/* If --mono is not defined elsewhere, uncomment and place in :root */
/* :root { --mono: ui-monospace, "Cascadia Code", "SF Mono", Menlo, Consolas, monospace; } */

.content.md h1,
.content.md h2,
.content.md h3,
.content.md h4 {
  font-family: var(--serif);
  color: var(--ink);
  font-weight: 500;
  letter-spacing: -0.01em;
  line-height: 1.25;
  margin: 20px 0 10px;
}
.content.md h1 { font-size: 1.55em; }
.content.md h2 { font-size: 1.3em; }
.content.md h3 { font-size: 1.12em; }
.content.md h4 { font-size: 1em; color: var(--ink-2, var(--ink)); }

.content.md p { margin: 0 0 14px; line-height: 1.7; }
.content.md p:last-child { margin-bottom: 0; }

.content.md ul,
.content.md ol { margin: 8px 0 14px; padding-left: 22px; }
.content.md li { margin: 4px 0; line-height: 1.6; }
.content.md ul li::marker { color: var(--ink-3, var(--ink)); }

.content.md code {
  font-family: var(--mono, ui-monospace, Menlo, Consolas, monospace);
  font-size: 0.9em;
  background: var(--bg-2, rgba(255,255,255,0.06));
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--ink);
}
.content.md pre {
  background: var(--bg-3, rgba(255,255,255,0.04));
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
  margin: 12px 0;
  overflow-x: auto;
  font-family: var(--mono, ui-monospace, Menlo, Consolas, monospace);
  font-size: 0.9em;
  line-height: 1.55;
}
.content.md pre code { background: transparent; padding: 0; border-radius: 0; }

.content.md blockquote {
  border-left: 3px solid var(--accent);
  padding: 4px 14px;
  margin: 12px 0;
  color: var(--ink-2, var(--ink));
  background: transparent;
}

.content.md table {
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 0.95em;
  width: 100%;
}
.content.md th,
.content.md td {
  border: 1px solid var(--line);
  padding: 6px 10px;
  text-align: left;
}
.content.md th { font-weight: 600; background: var(--bg-2, rgba(255,255,255,0.06)); }

.content.md a {
  color: var(--accent);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.15s;
}
.content.md a:hover { border-bottom-color: var(--accent); }

.content.md hr {
  border: none;
  border-top: 1px solid var(--line);
  margin: 18px 0;
}

.content.md strong { font-weight: 600; color: var(--ink); }
.content.md em { font-style: italic; }
```

Note: fallback values in `var(--foo, fallback)` are defensive — if a token is missing the rule still renders sanely. They mirror the dark-neutral palette already used by Prism but are approximations; if the token exists in styles.css the fallback is ignored.

- [ ] **Step 3: If --mono token missing, add it**

From Step 1 output: if `--mono` is not defined, append to the existing `:root {}` block in styles.css (find via `grep -n "^:root" frontend/styles.css`):
```css
--mono: ui-monospace, "Cascadia Code", "SF Mono", Menlo, Consolas, monospace;
```

- [ ] **Step 4: Run Bug 2 test — must now PASS on both viewports**

```bash
cd e2e
npx playwright test chat-msg-render.spec.ts -g "Bug 2" --project=desktop-chromium
npx playwright test chat-msg-render.spec.ts -g "Bug 2" --project=mobile-safari
```
Expected: both PASS. Screenshots land in `e2e/test-results/md-desktop-chromium.png` and `md-mobile-safari.png`.

- [ ] **Step 5: Load UI-UX skills and self-check typography**

Invoke Skill tool with `ui-ux-pro-max:ui-ux-pro-max` and `taste-skill`. Briefly inspect screenshots — do headings feel serif-editorial? Does inline code sit as a capsule, not a block? Does blockquote read as a rail, not a fill? Adjust pixel values if obviously off. Do NOT change colors outside the palette.

- [ ] **Step 6: Commit typography**

```bash
git add frontend/styles.css
git commit -m "style(frontend): .content.md typography for marked output (serif heads, capsule code, rail quote)"
```

---

## Task 8: Full Playwright sweep + human-sim walkthrough

**Purpose:** Beyond the two targeted tests — run full e2e suite on both viewports + Playwright MCP-driven human walkthrough per user's standing instruction ("完全模拟人的走一遍").

- [ ] **Step 1: Run full e2e suite on desktop-chromium**

```bash
cd e2e
npx playwright test --project=desktop-chromium
```
Expected: all previously-passing tests still pass. No regressions. `chat-msg-render.spec.ts` × 2 passes counted.

- [ ] **Step 2: Run full e2e suite on mobile-safari**

```bash
npx playwright test --project=mobile-safari
```
Expected: same — no regressions.

- [ ] **Step 3: Playwright MCP human-sim walkthrough — desktop**

Use `playwright-mcp` MCP tool (`browser_navigate`, `browser_click`, etc.) to perform, on desktop viewport:
1. Login → dashboard → session list → click each sidebar nav item → confirm page renders with no console error (check devtools console via `browser_evaluate`).
2. Create new chat → send markdown prompt → verify formatted output → click copy / retry / fork buttons → confirm they don't throw.
3. Skills page → open SkillsPage → click each of 3 install tabs → confirm switch works.
4. Plugins page → open → confirm builder pane renders.
5. Logout → login again → confirm state restored.

Take a screenshot at each major step and collect them under `e2e/test-results/human-sim-desktop/`.

- [ ] **Step 4: Playwright MCP human-sim walkthrough — mobile (iPhone 13 viewport)**

Repeat Step 3 on mobile viewport (`browser_resize` to 390×844 or use a new Playwright context with `devices['iPhone 13']`). Pay attention to composer pinning, sidebar drawer collapse, markdown reflow.

Collect screenshots under `e2e/test-results/human-sim-mobile/`.

- [ ] **Step 5: Verify no console errors regression**

For each page visited, `browser_evaluate("() => window.__errors__ || []")` if Prism exposes such a collector; otherwise inspect devtools console via the Playwright MCP console log retrieval tool. Document any non-benign errors in the commit message.

- [ ] **Step 6: Commit screenshots + verification log**

Only commit the summary log (not all screenshots — they go in test-results which is already in .gitignore if present; verify).

```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
cat e2e/.gitignore 2>/dev/null | grep -E "test-results|playwright-report"
# If both are gitignored, skip committing artifacts; just note the paths in the commit body.
```

No commit needed for this task if artifacts are gitignored. Proceed to Task 9.

---

## Task 9: Skill chain — simplify + verification-before-completion + react-code-review

**Purpose:** Run three review skills sequentially over the diff. Address any findings with follow-up commits.

- [ ] **Step 1: Load simplify skill and review diff**

Invoke Skill tool with `simplify`. Feed it the full diff:
```bash
git diff master...HEAD -- frontend/Prism.html frontend/styles.css e2e/tests/chat-msg-render.spec.ts
```
Apply its findings (DRY, dead-code removal, clarity). If it recommends changes, make them as a dedicated commit:
```bash
git add -p  # stage only relevant hunks
git commit -m "refactor(simplify): <one-line summary of simplify findings>"
```

- [ ] **Step 2: Load verification-before-completion skill**

Invoke Skill tool with `superpowers:verification-before-completion`. It will drive a checklist — do NOT claim completion without running its mandated commands. Evidence-based only.

- [ ] **Step 3: Load react-code-review for frontend-specific review**

Invoke Skill tool with `react-code-review:react-code-review`. Review `frontend/Prism.html` changes (new `MarkdownBody` component, parser fix, optional merge strategy) against its React 2024-2025 best practice checklist.

Expected findings to double-check against:
- `React.useMemo` correctness on `html` derivation
- `dangerouslySetInnerHTML` is sanitized (yes — DOMPurify wraps output)
- No dependency loops in Msg component hooks
- Keys on mapped elements (harness notices, tools)

Apply findings, commit as `refactor(frontend): react-code-review feedback — <summary>`.

- [ ] **Step 4: Re-run full e2e suite after simplify/review changes**

```bash
cd e2e
npx playwright test --project=desktop-chromium
npx playwright test --project=mobile-safari
```
Both must still pass. If anything regresses, revert the offending commit and re-evaluate.

---

## Task 10: PJR — project-review

**Purpose:** Full lint + build + workspace state check before merge. Per CLAUDE.md, this is mandatory.

- [ ] **Step 1: Load project-review:pjr skill**

Invoke Skill tool with `project-review:pjr`. Follow its full checklist.

- [ ] **Step 2: Frontend lint (if project has one)**

Prism frontend is zero-build inline React — there may not be a dedicated linter. Check for one:
```bash
ls frontend/ | grep -iE "eslint|prettier|tsconfig|package.json"
cat frontend/package.json 2>/dev/null | head -30
```
If an npm linter exists, run it. Otherwise, validate `frontend/Prism.html` parses by loading it in a browser and checking console for syntax errors.

- [ ] **Step 3: Backend lint (even though we didn't touch backend)**

Per PJR guidance — run the backend lint to confirm no accidental cross-file changes:
```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
# Adjust to the actual backend lint command. If unsure, find it:
cat backend/pyproject.toml 2>/dev/null | grep -E "ruff|flake8|black|mypy" -A 2
# Common pattern:
docker compose exec backend ruff check app/ 2>&1 | tail -20  # if ruff configured
```
Expected: no new findings over main. If untouched files show findings, it's pre-existing — flag in commit, do not fix in this PR.

- [ ] **Step 4: Backend build / smoke**

```bash
bash scripts/final-ops-smoke.sh
```
Expected: all 9 phases PASS per HANDOFF baseline. Screenshots / logs under project root.

- [ ] **Step 5: Workspace state check**

```bash
git status
```
Expected: clean tree. No dangling untracked files except known ones from main (.claude/settings.json — leave alone; it's from main, not worktree).

- [ ] **Step 6: Commit PJR artifacts if any were produced**

If PJR produced a PR-checklist file or report, commit it. Otherwise no commit.

---

## Task 11: Merge to develop

**Purpose:** Rebase + merge per git-merge-to-develop skill. First create `develop` branch since it doesn't yet exist.

- [ ] **Step 1: Load git-merge-to-develop skill**

Invoke Skill tool with `git-merge-to-develop:git-merge-to-develop`.

- [ ] **Step 2: Create develop branch from master HEAD (in main working tree, not worktree)**

```bash
cd "E:/Agent program/PrismV3"
git fetch origin
git branch develop master
git push -u origin develop 2>/dev/null || echo "no remote or push skipped — local only"
cd "E:/Agent program/PrismV3-fix-chat-md"
```
(If a remote exists and push fails due to permissions, proceed local-only. Skill will guide.)

- [ ] **Step 3: Rebase fix branch onto develop**

```bash
cd "E:/Agent program/PrismV3-fix-chat-md"
git fetch "E:/Agent program/PrismV3" develop
git rebase develop
```
Expected: clean rebase (master → develop has zero commit delta since we just branched). If conflicts appear, resolve per skill guidance.

- [ ] **Step 4: Merge into develop in main tree**

```bash
cd "E:/Agent program/PrismV3"
git checkout develop
git merge --no-ff fix/chat-msg-disappear-and-md-render -m "Merge fix/chat-msg-disappear-and-md-render into develop (Session 1 fixes)"
```

- [ ] **Step 5: Verify merge**

```bash
git log --oneline -10
```
Expected: merge commit at top, followed by the fix commits.

- [ ] **Step 6: Remove worktree (cleanup)**

```bash
git worktree remove "E:/Agent program/PrismV3-fix-chat-md"
# If blocked because worktree dirty, cd to it, reset, then retry
```

---

## Task 12: Independent code review + HANDOFF log update

**Purpose:** Final independent review via `requesting-code-review`, then update `HANDOFF-LOG.md` with Session 1 completion record. No more code changes after this task without a new session.

- [ ] **Step 1: Load requesting-code-review skill**

Invoke Skill tool with `superpowers:requesting-code-review`. Follow its subagent-driven review process.

- [ ] **Step 2: Dispatch code-reviewer agent on the merge commit**

Follow the skill's Agent dispatch pattern. Scope: the diff between `master` and `develop` HEAD (the merge commit's parent range). Frame: `frontend/Prism.html` + `frontend/styles.css` + `e2e/tests/chat-msg-render.spec.ts`.

Review criteria (brief for the agent):
- Spec compliance: does the diff match `docs/superpowers/specs/2026-04-19-chat-msg-disappear-and-md-render-design.md`?
- Security: DOMPurify configured correctly, no XSS vector opened?
- Performance: `useMemo` dep array correct?
- Scope creep: any file outside the declared scope touched?

- [ ] **Step 3: Address any agent findings**

For each P0/P1 finding from the reviewer, create a follow-up commit on `develop`:
```bash
cd "E:/Agent program/PrismV3"
git checkout develop
# edit files...
git add <files>
git commit -m "fix(frontend): address code-reviewer finding — <summary>"
```
P2 findings: note in HANDOFF-LOG, defer to next session. Do not open-ended expand scope.

- [ ] **Step 4: Update HANDOFF-LOG.md**

Remove the 🔴 red block at the top (or move it under a 🟢 "archived Session 1 handoff" heading). Add new top entry:

```markdown
## 2026-04-19 <HH:MM> — Session 1 Bug 1+2 fix COMPLETED ✅

### Done
- Bug 1: user message bubble persists after run_complete. Root cause: <A parser starvation | B race-on-setMsgs>. Fix: <one-line>.
- Bug 2: markdown renders as formatted HTML. Added marked@12 + DOMPurify@3 CDN, MarkdownBody component, .content.md typography scoped to existing token palette.
- Parallel: Session 2a (skills market / plugin builder / IM integration) + 2b (Manus distributed task decomposition) research docs landed at docs/research/2026-04-19-*.md, ready for Session 3 consumption.

### Verification
- Playwright chat-msg-render.spec.ts: PASS on desktop-chromium + mobile-safari.
- Full e2e suite: no regressions.
- Human-sim walkthrough: desktop + mobile, screenshots at e2e/test-results/human-sim-{desktop,mobile}/.
- PJR 9-phase: GREEN.
- requesting-code-review: <N> findings, all P0/P1 fixed inline, P2 deferred (list).

### Commits (on develop after merge)
- <commit hash sequence>

### Session 3 pointers
- Bug 3 (plugin download/enable/chat linkage) is architecture-level per HANDOFF; treat as ADR.
- Research inputs ready:
  - `docs/research/2026-04-19-skills-plugins-im-competitive.md` (10 prioritized recs — R1 marketplace abstraction P0, R2 typed plugin taxonomy P0, R4 Slack+Discord adapters P1)
  - `docs/research/2026-04-19-distributed-task-decomposition.md` (Planner-Executor recommended; dispatch_subtasks tool + child executor subprocess; schema impact flagged — needs ADR)
- Dev branch created from master HEAD during this session — future work should branch off develop.

### Remaining risk
- (list any P2 findings from reviewer, any test flakes observed)
```

- [ ] **Step 5: Commit HANDOFF update**

```bash
cd "E:/Agent program/PrismV3"
git add HANDOFF-LOG.md
git commit -m "docs(handoff): Session 1 completion — Bug 1+2 fixed, Session 2a/2b research landed"
```

- [ ] **Step 6: Final state verification**

```bash
git log --oneline -15
git status
git branch -a
```
Expected:
- Latest commit on develop: handoff update.
- Branches: master, develop, fix/chat-msg-disappear-and-md-render (can be deleted after Task 11; if kept, document in HANDOFF).
- Clean status in main tree.

---

## Post-plan self-review checklist (already applied during writing)

1. **Spec coverage**: every spec section maps to a task —
   - Bug 1 root cause / procedure → Task 3, Task 4
   - Bug 2 library / component / typography → Tasks 5, 6, 7
   - Verification plan → Tasks 2 (red), 4/7 (green per bug), 8 (sweep + human-sim)
   - Constraints → Task 1 (scope), Task 10 (PJR workspace), Task 11 (merge)
   - Acceptance → Task 12
2. **Placeholder scan**: no `TBD` / `TODO` / `...` — the `[空消息]` string is a user-facing placeholder and is the correct literal.
3. **Type consistency**: `MarkdownBody` takes `{ content, streaming }` throughout. `loggedInPage` fixture naming matches existing `e2e/fixtures/auth.ts` style (confirm during Task 2 Step 1).
4. **Out-of-order readability**: every task includes its files, its code, its verify command — no "see Task N".

---

## Execution notes

- Sessions 2a/2b research docs already landed; **do not read them during this plan** — they're inputs for Session 3 (separate session), not this plan.
- If Bug 1 reproduction in Task 3 produces ambiguous evidence (e.g., content is `[{type:"text", text:""}]` — an empty text block exists but yields empty string), treat as Case A (parser issue) and apply Case A fix — the bottom-out logic handles it gracefully.
- If during Task 9 simplify skill suggests removing the `[空消息]` placeholder in favor of hiding the bubble entirely, resist — the placeholder is a diagnostic signal that a content-shape regression happened upstream. Keep it.
