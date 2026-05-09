# Frontend Core Experience (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pages users actually see and interact with — Auth, Chat with streaming, Content Renderer with HTML display + Markdown export. This is where Prism competes with Manus.

**Architecture:** Pages built on the Phase 1+2 foundation (components, API client, hooks, contexts, layout shell). Chat page uses useSSE for streaming, ContentRenderer for rich display. Auth pages are standalone (outside AppLayout).

**Tech Stack:** React 18, TypeScript, marked, DOMPurify, Prism.js (syntax highlighting), Turndown.js (MD export)

**Design Language:** Luxury/refined + Editorial aesthetic. Source Serif 4 headings, warm amber/paper palette, minimal border-radius (10px buttons, 16px cards), generous whitespace. Touch targets ≥44px. 4.5:1 contrast.

**Spec:** `docs/superpowers/specs/2026-05-09-frontend-react-migration-design.md` §Phase 3

---

## Dependencies to Install

```bash
cd frontend-react
npm install marked dompurify prismjs turndown
npm install -D @types/dompurify @types/prismjs @types/turndown
```

---

## Task 1: Auth Pages (Login + Register)

**Files:**
- Create: `src/pages/Auth/LoginPage.tsx`
- Create: `src/pages/Auth/LoginPage.module.css`
- Create: `src/pages/Auth/RegisterPage.tsx`
- Create: `src/pages/Auth/RegisterPage.module.css`
- Create: `src/pages/Auth/AuthLayout.tsx`
- Create: `src/pages/Auth/AuthLayout.module.css`
- Modify: `src/App.tsx` — wire auth routes

### AuthLayout.tsx — Shared layout for login/register

Full-page centered layout with Prism branding. Two-column on desktop (left: branding + tagline, right: form), single column stacked on mobile.

**Left panel (desktop only):**
- PrismGlyph centered
- Brand: "Prism 棱镜"
- Tagline: "让大模型变得可靠、可治理、可扩展"
- Background: var(--bg), full height

**Right panel / main (mobile: full width):**
- White/paper card with form content
- Children slot for form

### LoginPage.tsx

**Form fields:**
- Email input (type="email", autocomplete="email")
- Password input (type="password", autocomplete="current-password", show/hide toggle)
- "登录" primary button (full width, loading state during API call)
- Error display below form (inline, near the action)
- Link to register page

**Behaviors:**
- Enter key submits form
- On success: useAuth().login() → redirect to "/"
- On error: show error message (from API), don't clear password
- Loading: button shows spinner, disabled during request

**Reference:** Read `frontend/Prism.html` LoginScreen component for the original flow, including magic link and Google OAuth buttons. Include:
- "或者" divider
- Magic link section: email input → "发送登录链接" button
- Google OAuth button (if auth providers API returns google enabled)

### RegisterPage.tsx

**Form fields:**
- Username input
- Email input (type="email")
- Password input (min 8 chars, show/hide toggle)
- Invite code input (optional — check if registration requires it)
- "创建账号" primary button (full width, loading)
- Error display
- Link to login page

**Behaviors:**
- Client-side validation: email format, password ≥8 chars
- On success: show success message, redirect to login
- On error: show error inline

### CSS Design Notes (from frontend-design + ui-ux-pro-max):

- Form inputs: height 44px (touch target), border 1px solid var(--line), border-radius 10px, padding 10px 14px, font-family var(--serif), font-size 15px. Focus: border-color var(--amber), box-shadow 0 0 0 2px var(--amber-soft)
- Labels: font-size 13px, font-weight 500, color var(--ink-2), margin-bottom 6px, visible (NOT placeholder-only)
- Error text: color var(--danger), font-size 13px, margin-top 4px
- Card: max-width 400px, padding 32px, border-radius 16px, background var(--paper), shadow-3

- [ ] Step 1: Install no new deps needed (marked etc. not needed for auth)
- [ ] Step 2: Create AuthLayout (shared branding layout)
- [ ] Step 3: Create LoginPage with email/password + magic link + Google OAuth
- [ ] Step 4: Create RegisterPage with invite code
- [ ] Step 5: Update App.tsx routes: `/login` → LoginPage, `/register` → RegisterPage
- [ ] Step 6: Verify `npx tsc --noEmit` zero errors
- [ ] Step 7: Commit

```bash
git add frontend-react/src/pages/Auth/ frontend-react/src/App.tsx
git commit -m "feat(frontend): auth pages — login, register, magic link, Google OAuth"
```

---

## Task 2: Chat Page — Message List + Composer + Streaming

**Files:**
- Create: `src/pages/Chat/ChatPage.tsx`
- Create: `src/pages/Chat/ChatPage.module.css`
- Create: `src/pages/Chat/MessageList.tsx`
- Create: `src/pages/Chat/MessageList.module.css`
- Create: `src/pages/Chat/MessageBubble.tsx`
- Create: `src/pages/Chat/MessageBubble.module.css`
- Create: `src/pages/Chat/Composer.tsx`
- Create: `src/pages/Chat/Composer.module.css`
- Create: `src/pages/Chat/EmptyState.tsx`
- Modify: `src/App.tsx` — wire chat route

### ChatPage.tsx — Main orchestrator

State management:
- `messages: Message[]` — loaded from API on session change
- `streamingText: string` — accumulates text_delta events during streaming
- `streamingTools: ToolState[]` — tracks tool calls in progress
- `isRunning: boolean` — true while a Run is active
- `permissionRequest: PermissionAsk | null` — when permission_ask event arrives

Uses `useSSE` hook for streaming. Event handlers:
- `text_delta` → append to streamingText (RAF throttle via useRef)
- `tool_start` → add to streamingTools
- `tool_end` → update tool status
- `message_complete` → flush streamingText into messages, clear streaming state
- `run_complete` → set isRunning false, refresh session list
- `run_error` / `run_crashed` → show error toast, set isRunning false
- `permission_ask` → set permissionRequest
- `session_title` → update sidebar session title
- `coordinator_plan_update` → update plan state

Layout: flex column, full height. MessageList takes flex-1, Composer fixed at bottom.

### MessageList.tsx

Scrollable message container. Auto-scrolls to bottom on new message (unless user has scrolled up).

Renders:
- Messages from API (loaded on mount / session change)
- Streaming message (if streamingText or streamingTools is non-empty)
- Empty state when no messages and no streaming

Each message → MessageBubble component.

### MessageBubble.tsx

**User messages:** Right-aligned, dark background (var(--ink)), light text, border-radius var(--bubble-radius) = 18px 18px 6px 18px.

**Assistant messages:** Left-aligned, transparent/subtle background, full width. Contains:
- ContentRenderer for text (Task 3)
- ToolCard for each tool_use block (inline, expandable)
- Thinking block (collapsible, muted)

For now (before ContentRenderer in Task 3), render text as plain text with basic markdown via `dangerouslySetInnerHTML` + marked. Task 3 will upgrade this.

### Composer.tsx

**Input area:**
- Textarea (auto-growing, max 200px height)
- Send button (Icon name="send", amber color, disabled when empty or isRunning)
- Keyboard: Enter sends (unless Shift held), Shift+Enter newline

**Behaviors:**
- On send: call `api.tasks.submit({ session_id, prompt })`
- If no current session: create one first via `api.sessions.create()`
- While running: show "停止" button instead of send (calls `api.runs.cancel()`)
- Queue toast when task is queued (queue_update event)

**CSS:**
- Bottom-fixed, padding 12px 16px, border-top 1px solid var(--line), background var(--paper)
- Textarea: border none, background transparent, resize none, font-family var(--serif), 15px
- Send button: 36px circle, background var(--amber), color white, border-radius 50%

### EmptyState.tsx

Shown when no messages. Center content:
- PrismGlyph (size 120)
- Title: "随便聊点什么。" (serif, 20px)
- Subtitle: "我会把你的问题分派给对的 Agent" (ink-3, 14px)
- Example prompts (4 items from I18N, clickable → fills composer)

**Reference:** Read `frontend/Prism.html` for the exact empty state content and example prompts.

- [ ] Step 1: Create EmptyState component
- [ ] Step 2: Create Composer with auto-grow textarea + send/stop
- [ ] Step 3: Create MessageBubble (user + assistant variants)
- [ ] Step 4: Create MessageList with auto-scroll
- [ ] Step 5: Create ChatPage orchestrator with SSE event handling
- [ ] Step 6: Wire in App.tsx: `<Route index element={<ChatPage />} />`
- [ ] Step 7: Verify `npx tsc --noEmit` zero errors
- [ ] Step 8: Commit

```bash
git add frontend-react/src/pages/Chat/ frontend-react/src/App.tsx
git commit -m "feat(frontend): chat page — messages, composer, SSE streaming"
```

---

## Task 3: Content Renderer (Markdown → Rich HTML)

**Files:**
- Create: `src/pages/Chat/ContentRenderer.tsx`
- Create: `src/pages/Chat/ContentRenderer.module.css`
- Create: `src/pages/Chat/CodeBlock.tsx`
- Create: `src/pages/Chat/CodeBlock.module.css`
- Create: `src/pages/Chat/ToolCard.tsx`
- Create: `src/pages/Chat/ToolCard.module.css`
- Create: `src/pages/Chat/ThinkingBlock.tsx`
- Create: `src/utils/markdown.ts`

### Install dependencies first

```bash
cd frontend-react
npm install marked dompurify prismjs turndown
npm install -D @types/dompurify @types/prismjs @types/turndown
```

### ContentRenderer.tsx

The core rendering pipeline:

```
Input (markdown string)
  → marked.parse() → raw HTML
  → DOMPurify.sanitize() → safe HTML
  → React dangerouslySetInnerHTML
  → CSS styles for rendered elements
```

Props:
```typescript
interface ContentRendererProps {
  content: string;
  className?: string;
}
```

Configure marked:
- GFM tables enabled
- Line breaks enabled
- Custom renderer for code blocks → wrap in `<pre data-lang="..."><code>` for Prism.js

After render, use `useEffect` to run Prism.highlightAllUnder(ref) for syntax highlighting.

### ContentRenderer.module.css — Prose styles

Style all rendered HTML elements within the renderer:
- `p`: margin-bottom 12px, line-height 1.6
- `h1-h6`: font-family var(--serif), font-weight 600, margin-top 20px, margin-bottom 8px
- `ul, ol`: padding-left 24px, margin-bottom 12px
- `li`: margin-bottom 4px
- `blockquote`: border-left 3px solid var(--amber), padding-left 16px, color var(--ink-2), font-style italic
- `table`: width 100%, border-collapse collapse, border 1px solid var(--line)
- `th`: background var(--bg), padding 8px 12px, text-align left, font-weight 500
- `td`: padding 8px 12px, border-top 1px solid var(--line)
- `a`: color var(--amber), text-decoration underline on hover
- `code` (inline): background var(--amber-soft), padding 2px 6px, border-radius 4px, font-family var(--mono), font-size 13px
- `pre`: see CodeBlock
- `img`: max-width 100%, border-radius 8px

### CodeBlock.tsx

Syntax-highlighted code block with copy button and language label.

Replace `<pre><code>` in rendered HTML with React component via post-processing:
- Actually, simpler: configure marked custom renderer to output `<pre data-lang="python"><code class="language-python">...</code></pre>`
- Then Prism.js highlights it
- Add copy button overlay (top-right, ghost style, Icon name="copy")
- Add language label (top-left, badge style)

CSS:
- Background: var(--ink) for dark code blocks (or var(--bg) for light — match existing Prism.html style)
- Border-radius: 10px
- Padding: 16px
- Font: var(--mono), 13px
- Overflow-x: auto
- Position relative (for copy button overlay)

### ToolCard.tsx

Displays a tool invocation inline in the message. Expandable card.

Props:
```typescript
interface ToolCardProps {
  name: string;
  status: 'running' | 'ok' | 'error';
  input?: string;
  output?: string;
  duration?: number;
  isError?: boolean;
}
```

Structure:
- Header row: tool icon (terminal), tool name, status badge (running=amber spinner, ok=teal check, error=rust alert), duration
- Collapsed by default (click to expand)
- Expanded: input JSON block + output text block (both scrollable, max-height 300px)

CSS:
- Border: 1px solid var(--line), border-radius 10px
- Background: var(--panel)
- Margin: 8px 0
- Header: flex, padding 8px 12px, cursor pointer
- Hover: background var(--bg)

### ThinkingBlock.tsx

Collapsible thinking content. Muted styling.

Props:
```typescript
interface ThinkingBlockProps {
  content: string;
}
```

- Collapsed by default, shows "[思考过程]" label
- Click to expand: shows thinking text in muted color
- CSS: border-left 2px solid var(--ink-4), padding-left 12px, color var(--ink-3), font-size 13px

### markdown.ts — Utility functions

```typescript
export function renderMarkdown(text: string): string {
  // marked.parse() + DOMPurify.sanitize()
}
```

- [ ] Step 1: Install marked, dompurify, prismjs, turndown + types
- [ ] Step 2: Create markdown.ts utility
- [ ] Step 3: Create ContentRenderer with prose styles
- [ ] Step 4: Create CodeBlock with copy button + language label + Prism.js highlighting
- [ ] Step 5: Create ToolCard (expandable, 3 status states)
- [ ] Step 6: Create ThinkingBlock (collapsible)
- [ ] Step 7: Update MessageBubble to use ContentRenderer + ToolCard + ThinkingBlock
- [ ] Step 8: Verify `npx tsc --noEmit` zero errors
- [ ] Step 9: Commit

```bash
git add frontend-react/src/pages/Chat/ frontend-react/src/utils/markdown.ts frontend-react/package*.json
git commit -m "feat(frontend): content renderer — markdown, code highlighting, tool cards"
```

---

## Task 4: Permission Modal + Plan Panel

**Files:**
- Create: `src/pages/Chat/PermissionModal.tsx`
- Create: `src/pages/Chat/PermissionModal.module.css`
- Create: `src/pages/Chat/PlanPanel.tsx`
- Create: `src/pages/Chat/PlanPanel.module.css`
- Modify: `src/pages/Chat/ChatPage.tsx` — integrate both

### PermissionModal.tsx

When Agent needs user permission, shows an overlay modal.

Props:
```typescript
interface PermissionModalProps {
  request: {
    request_id: string;
    tool_name: string;
    description: string;
    input_preview: string;
  };
  onAllow: () => void;
  onDeny: () => void;
}
```

**Structure:**
- Title: "这一步需要你点头" (serif)
- Description: what the tool wants to do
- Input preview (code block, scrollable)
- Countdown timer (5 minutes → auto-deny)
- Two buttons: "允许" (primary), "拒绝" (danger)

**Countdown:** useEffect with setInterval, updates every second. Shows MM:SS remaining. On timeout: auto-call onDeny.

**Behavior:** On allow/deny → call `api.sessions.permissionAnswer(sessionId, { request_id, decision })`.

### PlanPanel.tsx

Shows Coordinator step progress. Slides in from right side of chat area.

Props:
```typescript
interface PlanPanelProps {
  plan: {
    steps: Array<{
      title: string;
      status: 'pending' | 'running' | 'completed' | 'failed';
    }>;
    current_step: number;
  } | null;
}
```

**Structure:**
- Header: "这次的计划" (serif)
- Step list: numbered steps, each with status icon (pending=circle, running=spinner, completed=check, failed=alert)
- Current step highlighted
- Collapse/expand toggle

CSS: background var(--panel), border-left 1px solid var(--line), width 280px on desktop, full overlay on mobile.

### ChatPage integration

- On `permission_ask` SSE event → set permissionRequest state → render PermissionModal
- On `coordinator_plan_update` SSE event → set plan state → render PlanPanel
- On allow/deny → clear permissionRequest, call API

- [ ] Step 1: Create PermissionModal with countdown timer
- [ ] Step 2: Create PlanPanel with step progress
- [ ] Step 3: Integrate both into ChatPage via SSE events
- [ ] Step 4: Verify `npx tsc --noEmit` zero errors
- [ ] Step 5: Commit

```bash
git add frontend-react/src/pages/Chat/
git commit -m "feat(frontend): permission modal + coordinator plan panel"
```

---

## Task 5: Markdown Export

**Files:**
- Create: `src/utils/export.ts`
- Modify: `src/pages/Chat/MessageBubble.tsx` — add export button

### export.ts

```typescript
import TurndownService from 'turndown';

const turndown = new TurndownService({
  headingStyle: 'atx',
  codeBlockStyle: 'fenced',
});

// Custom rules for Prism-specific elements
turndown.addRule('toolCard', {
  filter: (node) => node.classList?.contains('tool-card'),
  replacement: (content, node) => {
    const name = node.getAttribute('data-tool-name') || 'tool';
    return `\n\`\`\`tool: ${name}\n${content}\n\`\`\`\n`;
  },
});

turndown.addRule('thinkingBlock', {
  filter: (node) => node.classList?.contains('thinking-block'),
  replacement: (content) => `\n> [思考] ${content}\n`,
});

export function htmlToMarkdown(html: string): string {
  return turndown.turndown(html);
}

export function downloadMarkdown(markdown: string, filename: string): void {
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
}

export function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}
```

### MessageBubble update

Add a hover-revealed action bar on assistant messages:
- Copy button (copies rendered text as Markdown)
- Download button (downloads as .md file)

Both use the export utilities.

- [ ] Step 1: Install turndown + types (already done in Task 3 deps)
- [ ] Step 2: Create export.ts with Turndown + custom rules
- [ ] Step 3: Update MessageBubble with copy/download actions
- [ ] Step 4: Verify `npx tsc --noEmit` zero errors
- [ ] Step 5: Commit

```bash
git add frontend-react/src/utils/export.ts frontend-react/src/pages/Chat/MessageBubble.*
git commit -m "feat(frontend): markdown export — copy + download with custom turndown rules"
```

---

## Final Verification

- [ ] `npx tsc --noEmit` — zero errors
- [ ] `npx vite build` — build succeeds
- [ ] Visual check: Auth pages render with Prism design language
- [ ] Visual check: Chat page shows messages, composer works
- [ ] Visual check: Content renderer handles markdown, code blocks, tables
- [ ] Visual check: Tool cards expand/collapse
- [ ] Visual check: Mobile responsive (390px width)
