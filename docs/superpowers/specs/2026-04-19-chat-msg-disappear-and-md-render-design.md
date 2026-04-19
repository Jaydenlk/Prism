# Fix: Chat User Message Disappearance + Markdown Rendering

**Date**: 2026-04-19
**Branch (planned)**: `fix/chat-msg-disappear-and-md-render`
**Scope**: `frontend/Prism.html` + `frontend/styles.css` only
**Session**: Prism v2 Session 1 (parallel with Exa research subagents 2a/2b)

---

## Context

Prism v2 is a self-hosted AI Agent platform. The chat UI is a zero-build inline React app loaded from a single `frontend/Prism.html`. Users reported two visible bugs in the chat page (ChatPage `Prism.html:591-1073`):

1. **Bug 1** — Send a prompt, the assistant replies, then the user's own message bubble disappears from the UI (only the assistant reply remains).
2. **Bug 2** — Markdown in assistant replies (headings, lists, code fences, bold) renders as a single unformatted paragraph of raw text instead of as formatted HTML.

Bug 3 (plugin download/enable/chat linkage) and Bug 4 (competitive research) are explicitly out of scope for this fix — they belong to Session 3 (architecture ADR) and are being handled by background research subagents.

---

## Bug 1 — User message disappears after `run_complete`

### Symptom

- `handleSend` (`Prism.html:992-1023`) optimistically pushes the user message to `msgs` state. Bubble appears.
- Assistant streams reply. Appears.
- On `run_complete` event (`Prism.html:772-802`), frontend re-fetches history via `PrismAPI.sessions.listMessages(sid, {limit:50})` and calls `setMsgs(displayMsgs)`.
- **The optimistic user bubble vanishes.** Only the assistant reply is visible.

### Root cause — two candidates

| ID | Candidate | Evidence required to confirm |
|---|---|---|
| A | **Parser starvation.** `Prism.html:785` filters `m.content` to blocks where `b.type === "text"`. If DB persists user content as a raw string, or as `[{type:"user_text",…}]`, the filter returns `[]`. Fallback chain `textBlocks.map(b=>b.text).join("\n") \|\| m.text_preview \|\| ""` bottoms out to empty string. Bubble renders but is visually empty. | Playwright intercepts `GET /api/v1/sessions/{sid}/messages`, inspects actual user message `content` shape |
| B | **Race / wholesale replace.** `run_complete` fires before user message is persisted to DB (or before DB query sees it). `rawMsgs` lacks the user row. `setMsgs(displayMsgs)` unconditionally replaces, wiping the optimistic entry. | Same interception — check whether the user row is present in the response at all |

### Evidence-gated decision procedure

Before writing any fix, run this Playwright reproduction:

1. Login, open chat, send a prompt containing one clear token (e.g. `TEST-<uuid>`).
2. Intercept `GET /api/v1/sessions/*/messages` response via `page.route`. Log the raw JSON to the test report.
3. Assert the user bubble is visible before `run_complete` (by streamed token presence), then assert again after.
4. Inspect the captured JSON:
   - If the user row exists but `content` does not have `type:"text"` blocks → **Case A**.
   - If the user row is missing entirely → **Case B**.

Implement exactly one fix. Never ship both.

### Fix A — parser bottom-out

Replace the parser block at `Prism.html:780-796`:

```js
while (i < rawMsgs.length) {
  const m = rawMsgs[i];
  if (m.role === "user") {
    let text = "";
    if (Array.isArray(m.content)) {
      const textBlocks = m.content.filter(b => b && b.type === "text");
      text = textBlocks.map(b => b.text).join("\n");
      if (!text) {
        // Bottom out through non-text blocks (e.g., future user_text, tool_result)
        text = m.content.map(b => (b && typeof b.text === "string") ? b.text : "").filter(Boolean).join("\n");
      }
    } else if (typeof m.content === "string") {
      text = m.content;
    }
    if (!text) text = m.text_preview || "[空消息]";
    displayMsgs.push({ role: "user", at: formatTime(m.created_at), content: text });
    i++;
  } else if (m.role === "assistant") { /* unchanged */ }
  else { i++; }
}
```

Behavior: every `role==="user"` row produces a bubble. Empty content shows `[空消息]` placeholder — this is a last-resort indicator; if it ever appears in production, it signals a schema issue worth fixing upstream, not a UI bug.

### Fix B — merge instead of replace

At `Prism.html:797`, do not call `setMsgs(displayMsgs)` unconditionally. Instead:

```js
setMsgs(prev => {
  // Index prev by (role, content, at) hash; drop prev entries that DB confirms; keep prev-only optimistic entries.
  const dbKeys = new Set(displayMsgs.map(m => `${m.role}|${m.at}`));
  const optimisticTail = prev.filter(m => m.role === "user" && !dbKeys.has(`${m.role}|${m.at}`));
  return [...displayMsgs, ...optimisticTail];
});
```

Behavior: DB response is authoritative for confirmed messages; optimistic user messages not yet in DB are preserved so the bubble never blinks. If the next `run_complete` refresh picks up the user row, the duplicate would need dedupe — the `at` field (formatted with seconds) is a good enough key for the 5-second race window. Stream buffer reset (`streamBuf.current = {}`) and `scrollToBottom()` remain unchanged.

---

## Bug 2 — No markdown rendering in assistant messages

### Symptom

`Prism.html:436` renders assistant content as `{m.content}` — a text node. Any `# heading`, `**bold**`, ``` `inline` ```, ```` ```fenced``` ```` appears as literal characters.

### Library choice

- **Constraint**: Prism.html is a zero-build inline React — no webpack, no Vite, no import bundler. Loaded via `<script type="text/babel">` through Babel standalone.
- **Choice**: `marked@12` (markdown → HTML) + `DOMPurify@3` (sanitize HTML) — both available as global `<script>` tags from jsdelivr CDN.
- **Not chosen**: `react-markdown` via esm.sh — works but pulls larger graph of dependencies across the zero-build boundary; marked+DOMPurify is ~60KB combined, directly global-scoped, simpler to pin.
- **Pinning**: pin exact versions (`marked@12.0.x`, `dompurify@3.0.x`) via jsdelivr URL with SRI hash. CDN outage mitigation is out of scope for this fix.

### Component design

New component `MarkdownBody` inside `Prism.html`, consumed by `Msg` at line 436:

```jsx
function MarkdownBody({ content, streaming }) {
  const html = React.useMemo(() => {
    if (!content) return "";
    try {
      return window.DOMPurify.sanitize(window.marked.parse(content, { gfm: true, breaks: false }));
    } catch (e) {
      console.warn("[MarkdownBody] parse/sanitize failed, escaping as text", e);
      const div = document.createElement("div");
      div.textContent = content;
      return div.innerHTML;
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

In `Msg` (line 436), replace `<div className="content">{m.content}{m.streaming && <span className="caret"/>}</div>` with `<MarkdownBody content={m.content} streaming={m.streaming}/>`. User bubbles (`isUser === true`) remain plain text — do not wrap them.

**Streaming consideration**: During streaming, `content` arrives incrementally. `marked.parse` is idempotent on partial markdown — worst case an unclosed fence renders as plain text until the closing fence arrives, then snaps to a code block. Acceptable; matches ChatGPT UX.

**Error handling rationale**: `marked.parse` can throw on malformed input (regex edge cases, null-byte content). The catch branch escapes `content` via `document.createElement('div').textContent = content; return div.innerHTML;` — this returns HTML-safe text, never raw user-controlled HTML into `dangerouslySetInnerHTML`. Returning raw `content` would be an XSS vector; returning `""` would silently eat the message. Escape-and-render is the only safe + observable option.

### E2E test mount path (renderer decoupling)

The LLM cannot be relied on to echo markdown verbatim for E2E assertions — preambles, rephrasing, and skipped table rows would flake the test. Add a test-only mount helper inside `Prism.html`, guarded by a query flag, that mounts `MarkdownBody` directly with fixture input:

```js
if (window.location.search.includes('__e2e=1')) {
  window.__e2e_mountMarkdown = (content) => {
    let root = document.getElementById('e2e-md-root');
    if (!root) { root = document.createElement('div'); root.id = 'e2e-md-root'; document.body.appendChild(root); }
    if (!window.__e2e_root) window.__e2e_root = ReactDOM.createRoot(root);
    window.__e2e_root.render(<MarkdownBody content={content} streaming={false}/>);
  };
}
```

Placement: inline in the same `<script type="text/babel">` block that mounts the app, AFTER the `ReactDOM.createRoot(document.getElementById(...)).render(<App/>)` call. Guard prevents the helper from being exposed in production (`/?__e2e=1` is never passed by real users). Playwright tests navigate to `/?__e2e=1`, await `window.__e2e_mountMarkdown` existence, then call it with a fixed markdown string and assert on `#e2e-md-root .content.md`. This tests MarkdownBody rendering, not LLM fidelity.

The two E2E tests become:
- Bug 1 test: real chat flow (user bubble persists) — still uses live LLM since the bug is in the chat page lifecycle, not renderer.
- Bug 2 test: mount helper + fixed markdown + DOM assertions + XSS regression (`<script>` tag in input must NOT execute).

### Typography spec

New CSS block in `frontend/styles.css`, scoped under `.content.md` to avoid leaking to non-markdown contexts. All values reuse existing tokens from the current `styles.css` palette (`--serif`, `--ink`, `--ink-2`, `--ink-3`, `--bg`, `--bg-2`, `--bg-3`, `--line`, `--accent`, `--mono` if present; add `--mono: ui-monospace, "Cascadia Code", "SF Mono", Menlo, monospace;` if missing).

```css
.content.md h1, .content.md h2, .content.md h3, .content.md h4 {
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
.content.md h4 { font-size: 1em; color: var(--ink-2); }
.content.md p { margin: 0 0 14px; line-height: 1.7; }
.content.md p:last-child { margin-bottom: 0; }

.content.md ul, .content.md ol { margin: 8px 0 14px; padding-left: 22px; }
.content.md li { margin: 4px 0; line-height: 1.6; }
.content.md ul li::marker { color: var(--ink-3); }

.content.md code {
  font-family: var(--mono);
  font-size: 0.9em;
  background: var(--bg-2);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--ink);
}
.content.md pre {
  background: var(--bg-3);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 14px;
  margin: 12px 0;
  overflow-x: auto;
  font-family: var(--mono);
  font-size: 0.9em;
  line-height: 1.55;
}
.content.md pre code { background: transparent; padding: 0; border-radius: 0; }

.content.md blockquote {
  border-left: 3px solid var(--accent);
  padding: 4px 14px;
  margin: 12px 0;
  color: var(--ink-2);
  background: transparent;
}

.content.md table {
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 0.95em;
  width: 100%;
}
.content.md th, .content.md td {
  border: 1px solid var(--line);
  padding: 6px 10px;
  text-align: left;
}
.content.md th { font-weight: 600; background: var(--bg-2); }

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

Design intent (high-end editorial feel, consistent with existing tokens):
- Serif titles + sans body = agency-grade hierarchy
- Subtle bg for inline code and pre, not loud boxes
- Blockquote as rail (not block fill) — premium restraint
- Tables readable without chrome — `--line` borders only
- Links underline on hover, not persistent — less noise

### Sanitization

`DOMPurify.sanitize()` with default config:
- Strips `<script>`, `<iframe>`, `on*` attributes.
- Allows `<a>`, `<img>`, `<code>`, `<pre>`, `<table>` — the full markdown element set.
- Does not allow raw HTML to pass through unchecked (defense in depth against prompt-injection markdown bombs).
- No `USE_PROFILES: {svg: true, mathMl: true}` — not needed, keeps surface small.

### Token additions (if missing)

If `styles.css` does not already define `--mono`, add to `:root` alongside `--serif`:
```css
--mono: ui-monospace, "Cascadia Code", "SF Mono", Menlo, Consolas, monospace;
```

No other token additions. All other variables are expected to exist (they are used elsewhere in the current styles.css — verify during implementation, if any is missing the fix is to wire it from the existing palette, not to invent colors).

---

## Verification plan

Playwright E2E, in `e2e/`, both projects `desktop-chromium` and `mobile-chrome`:

### Test 1 — Bug 1 user bubble persists

1. `page.route('**/api/v1/sessions/*/messages', handler)` to snapshot response.
2. Login, open a session, `fillAndSubmit('TEST-BUG1-<ts>')`.
3. Wait for `run_complete` event (SSE close or `.agent-msg:not(.streaming)` visible).
4. Assert `.user-msg .bubble` containing `TEST-BUG1-<ts>` is still present in DOM.
5. Screenshot.

### Test 2 — Bug 2 markdown renders

Prompt content:
```
请用 markdown 演示：

## 标题 H2

- 列表项 A
- 列表项 B
- **粗体** 和 `inline code`

```python
def hello():
    print("hi")
```

> 引用段落

| 列 A | 列 B |
|---|---|
| 1 | 2 |
```

1. Submit, wait for `run_complete`.
2. Assert selectors exist in `.agent-msg .content.md`:
   - `h2` with text "标题 H2"
   - `ul > li` count ≥ 3
   - `strong` element
   - `code` element (inline)
   - `pre > code` (fenced block)
   - `blockquote` element
   - `table thead th` count === 2 and `tbody tr` count === 1
3. Screenshot both desktop and mobile.

### Full human-sim walkthrough

Per user's standing instruction ("完全模拟人的走一遍"):
- Nav: every sidebar item click → page renders, no console error.
- Composer: type, Enter, Shift+Enter (newline), paste.
- Message actions: copy, retry, fork buttons clickable.
- Session list: create, switch, delete.
- Logout → login again → state preserved.
- Mobile viewport (390×844): composer pinned, sidebar collapses to drawer.

No assertion = no pass. Screenshots required for both viewports.

---

## Constraints

1. **File scope**: only `frontend/Prism.html` and `frontend/styles.css`. No backend, no executor, no PRD, no schema, no ADR edits.
2. **Branch strategy**: worktree `fix/chat-msg-disappear-and-md-render` off `master`. Repo currently has no `develop` branch; the git-merge-to-develop skill phase will create `develop` from `master` HEAD before the rebase-merge. Alternative (merge to `master` directly) is rejected — the skill enforces a develop gate, and creating `develop` is cheaper than bypassing the skill.
3. **Worktree isolation**: all edits inside the worktree. Main repo working tree (currently has uncommitted `HANDOFF-LOG.md` + untracked `.claude/settings.json`) is not touched.
4. **No cross-session scope creep**: do not touch Bug 3 plugin flow, do not touch Task 4a/4b research files (those are under `docs/research/` and owned by background subagents — file paths disjoint from this worktree).
5. **Zero-build preservation**: do not introduce webpack/vite/rollup. CDN scripts only. Pin versions.
6. **No new environment variables, no new DB migration, no new backend endpoint.**

---

## Out of scope (explicit)

- Bug 3 — plugin download / enable / chat linkage. Session 3 ADR.
- Task 4a / 4b — skills market + IM integration + Manus competitive research. Handled by two background Exa subagents writing to `docs/research/*.md`.
- CDN fallback / self-hosting of marked+DOMPurify. If jsdelivr is blocked in deploy, that's a follow-up.
- Markdown-in-user-bubble support. User messages stay plain text — simpler, and the bug report concerns assistant output only.
- Syntax highlighting inside fenced code blocks. marked emits `<pre><code class="language-xxx">` which DOMPurify preserves; if needed later, drop in highlight.js or Prism.js CDN. Not in this fix.
- Copy-button on code blocks. Nice-to-have; defer.
- Streaming-aware partial markdown rendering. Baseline is "re-parse whole string on every render" — already fast enough for the 50-message visible window.

---

## Acceptance

- Both Playwright tests (Bug 1, Bug 2) pass on desktop-chromium and mobile-chrome.
- Human-sim walkthrough: zero console errors, every button clickable, markdown renders as real HTML in screenshots.
- Skill chain passes: simplify → verification-before-completion → react-code-review → pjr (lint+build green) → git-merge-to-develop (rebase clean, merged to develop) → requesting-code-review (independent agent sign-off).
- Commit on `fix/chat-msg-disappear-and-md-render`, merged to `develop`.
- HANDOFF-LOG entry appended with Session 1 completion record + pointer to background subagent research outputs.
