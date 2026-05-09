# Frontend Foundation (Phase 1+2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a working React + TypeScript + Vite application skeleton with design system, core components, typed API client, SSE streaming, routing, and global state — ready for page development in Phase 3+.

**Architecture:** Vite SPA with React 18 + TypeScript strict. CSS Modules for component scoping, CSS Variables for design tokens (ported from existing `frontend/styles.css`). API client ported from `frontend/apiClient.js` to typed module. SSE streaming via custom hook. React Context for auth/theme/session state.

**Tech Stack:** Vite 6, React 18, TypeScript 5 (strict), React Router 6, CSS Modules, marked, DOMPurify, Prism.js

**Spec:** `docs/superpowers/specs/2026-05-09-frontend-react-migration-design.md`

**Reference files (read these before starting):**
- `frontend/styles.css` — design tokens (lines 11-49), all CSS patterns
- `frontend/apiClient.js` — complete API surface (707 lines), SSE events, auth flow
- `frontend/Prism.html` — component implementations (4500+ lines), icon paths (lines 34-76)

---

## File Structure

```
frontend-react/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── .gitignore
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── vite-env.d.ts
    ├── theme/
    │   ├── tokens.ts
    │   ├── global.css
    │   └── fonts.css
    ├── api/
    │   ├── client.ts
    │   └── types.ts
    ├── hooks/
    │   ├── useAuth.ts
    │   ├── useSSE.ts
    │   ├── useTheme.ts
    │   └── useSessions.ts
    ├── context/
    │   ├── AuthContext.tsx
    │   ├── ThemeContext.tsx
    │   └── SessionContext.tsx
    ├── components/
    │   ├── Icon/
    │   │   ├── Icon.tsx
    │   │   └── Icon.module.css
    │   ├── Button/
    │   │   ├── Button.tsx
    │   │   └── Button.module.css
    │   ├── Modal/
    │   │   ├── Modal.tsx
    │   │   └── Modal.module.css
    │   ├── Toast/
    │   │   ├── Toast.tsx
    │   │   ├── Toast.module.css
    │   │   └── ToastContext.tsx
    │   ├── Badge/
    │   │   └── Badge.tsx
    │   ├── Spinner/
    │   │   └── Spinner.tsx
    │   ├── Dropdown/
    │   │   ├── Dropdown.tsx
    │   │   └── Dropdown.module.css
    │   └── Layout/
    │       ├── AppLayout.tsx
    │       ├── AppLayout.module.css
    │       ├── Sidebar.tsx
    │       ├── Sidebar.module.css
    │       ├── Topbar.tsx
    │       └── Topbar.module.css
    ├── pages/
    │   └── Placeholder.tsx
    └── utils/
        ├── time.ts
        └── cn.ts
```

---

## Task 1: Vite + React + TypeScript Project Scaffolding

**Files:**
- Create: `frontend-react/package.json`
- Create: `frontend-react/tsconfig.json`
- Create: `frontend-react/tsconfig.node.json`
- Create: `frontend-react/vite.config.ts`
- Create: `frontend-react/index.html`
- Create: `frontend-react/.gitignore`
- Create: `frontend-react/src/main.tsx`
- Create: `frontend-react/src/App.tsx`
- Create: `frontend-react/src/vite-env.d.ts`

- [ ] **Step 1: Initialize project with npm**

```bash
cd "E:/Agent program/PrismV3"
mkdir -p frontend-react/src frontend-react/public
cd frontend-react
npm init -y
npm install react@18 react-dom@18 react-router-dom@6
npm install -D vite@6 @vitejs/plugin-react typescript @types/react @types/react-dom
```

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create tsconfig.node.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
```

- [ ] **Step 5: Create index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN" data-theme="light" data-density="comfortable">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Prism · Agent Operating System</title>
  <script>
    try {
      var t = localStorage.getItem('prism_theme');
      if (t === 'dark' || t === 'light') {
        document.documentElement.setAttribute('data-theme', t);
      }
    } catch (e) {}
  </script>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

- [ ] **Step 6: Create src/vite-env.d.ts**

```typescript
/// <reference types="vite/client" />
```

- [ ] **Step 7: Create src/main.tsx**

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 8: Create src/App.tsx (placeholder)**

```tsx
export function App() {
  return <div style={{ padding: 40, fontFamily: 'serif' }}>Prism — React scaffold running</div>;
}
```

- [ ] **Step 9: Create .gitignore**

```
node_modules/
dist/
*.local
.env
```

- [ ] **Step 10: Verify dev server starts**

Run: `cd frontend-react && npx vite --host`
Expected: Server starts at http://localhost:3000, page shows "Prism — React scaffold running"

- [ ] **Step 11: Verify TypeScript compiles**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 12: Commit**

```bash
git add frontend-react/
git commit -m "feat(frontend): Vite + React 18 + TypeScript project scaffold"
```

---

## Task 2: Design System (Tokens + Global CSS)

**Files:**
- Create: `frontend-react/src/theme/tokens.ts`
- Create: `frontend-react/src/theme/global.css`
- Create: `frontend-react/src/theme/fonts.css`
- Modify: `frontend-react/src/main.tsx` — import global CSS

**Reference:** Read `frontend/styles.css` lines 1-50 for all design tokens.

- [ ] **Step 1: Create src/theme/tokens.ts**

Port all CSS custom properties from `frontend/styles.css :root` to TypeScript constants. These are the source of truth — global.css reads from these via CSS variables.

```typescript
export const palette = {
  paper: '#F5F1EA',
  bg: '#EDE6D6',
  ink: '#1C1B18',
  ink2: '#3A3832',
  ink3: '#6B675E',
  ink4: '#9C9890',
  line: 'rgba(28,27,24,0.10)',
  lineStrong: 'rgba(28,27,24,0.18)',
  amber: '#B8803A',
  amberSoft: '#F5EDDC',
  rust: '#9B4A35',
  rustSoft: '#F3E1DA',
  teal: '#4E7C6E',
  tealSoft: '#DAE9E4',
  plum: '#7A4E58',
  danger: '#9B4A35',
  panel: '#EEEAE0',
} as const;

export const typography = {
  serif: "'Source Serif 4', 'Noto Serif SC', Georgia, serif",
  mono: "'JetBrains Mono', 'Consolas', 'Courier New', monospace",
} as const;

export const shadows = {
  sm: '0 2px 8px rgba(28,27,24,0.10), 0 1px 2px rgba(28,27,24,0.07)',
  md: '0 4px 18px rgba(28,27,24,0.12), 0 2px 4px rgba(28,27,24,0.08)',
} as const;

export const layout = {
  sidebarWidth: 240,
  topbarHeight: 48,
  statusbarHeight: 32,
  bubbleRadius: '18px 18px 6px 18px',
  mobileBreakpoint: 640,
} as const;

export type PaletteKey = keyof typeof palette;
```

- [ ] **Step 2: Create src/theme/fonts.css**

```css
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,500;0,600;1,400;1,500&family=JetBrains+Mono:wght@400;500&display=swap');
```

- [ ] **Step 3: Create src/theme/global.css**

Port the full reset + CSS variables + base styles from `frontend/styles.css`. Key requirements:
- `:root` block with ALL variables matching `tokens.ts` values
- `[data-theme="dark"]` override block (dark mode tokens)
- Reset (`*, *::before, *::after { box-sizing: border-box; }`)
- Body base styles (font-family, font-size 14px, line-height 1.5, color var(--ink), background var(--paper))
- Scrollbar styling
- Selection color
- `[data-density="comfortable"]` / `[data-density="compact"]` / `[data-density="spacious"]` overrides

Read `frontend/styles.css` lines 1-100 for exact values. Port all CSS variables. Add dark mode tokens:

```css
[data-theme="dark"] {
  --paper: #1C1B18;
  --bg: #2A2824;
  --ink: #E8E4DC;
  --ink-2: #C8C4BC;
  --ink-3: #9C9890;
  --ink-4: #6B675E;
  --line: rgba(232,228,220,0.10);
  --line-strong: rgba(232,228,220,0.18);
  --amber-soft: #3A2E1C;
  --rust-soft: #3A2420;
  --teal-soft: #1C2E28;
  --panel: #242220;
}
```

- [ ] **Step 4: Update src/main.tsx to import CSS**

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme/fonts.css';
import './theme/global.css';
import { App } from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 5: Verify design tokens render**

Update App.tsx temporarily to show a card with the design language (serif font, amber accent, paper background). Verify in browser.

- [ ] **Step 6: Verify TypeScript compiles**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add frontend-react/src/theme/
git commit -m "feat(frontend): design system — tokens, global CSS, fonts, dark mode"
```

---

## Task 3: Icon System

**Files:**
- Create: `frontend-react/src/components/Icon/Icon.tsx`
- Create: `frontend-react/src/components/Icon/Icon.module.css`

**Reference:** Read `frontend/Prism.html` lines 34-76 for all 35 icon SVG paths.

- [ ] **Step 1: Create Icon.tsx**

Port all 35 icon paths from `Prism.html` lines 34-76. The component accepts `name` as a union type literal of all icon names.

```tsx
import type { CSSProperties } from 'react';
import styles from './Icon.module.css';

const paths: Record<IconName, JSX.Element> = {
  search: <><circle cx="7" cy="7" r="5"/><path d="M11 11l4 4"/></>,
  plus: <><path d="M8 3v10M3 8h10"/></>,
  // ... port ALL 35 icons from Prism.html lines 37-76
  // IMPORTANT: copy every icon path exactly, do not skip any
};

export type IconName = 'search' | 'plus' | 'chat' | 'sessions' | 'settings' | 'usage' |
  'skills' | 'plugin' | 'admin' | 'chevron' | 'close' | 'check' | 'attach' | 'shield' |
  'alert' | 'info' | 'clock' | 'book' | 'terminal' | 'folder' | 'pin' | 'globe' |
  'copy' | 'fork' | 'refresh' | 'arrowUp' | 'arrowRight' | 'more' | 'layers' |
  'send' | 'eye' | 'download' | 'upload' | 'filter' | 'flask' | 'flow' | 'link' |
  'menu' | 'sparkle';

interface IconProps {
  name: IconName;
  size?: number;
  stroke?: number;
  className?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 16, stroke = 1.5, className, style }: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
    >
      {paths[name]}
    </svg>
  );
}
```

Also port `PrismMark` and `PrismGlyph` from Prism.html lines 80-105 as named exports.

- [ ] **Step 2: Create Icon.module.css**

Minimal — just a display: inline-block wrapper if needed.

- [ ] **Step 3: Verify all icons render**

Create a temporary page in App.tsx that maps over all IconName values and renders each icon with its name label. Verify all 35+ icons are visible.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/src/components/Icon/
git commit -m "feat(frontend): icon system — 35+ typed SVG icons"
```

---

## Task 4: Core Components — Button, Badge, Spinner

**Files:**
- Create: `frontend-react/src/components/Button/Button.tsx`
- Create: `frontend-react/src/components/Button/Button.module.css`
- Create: `frontend-react/src/components/Badge/Badge.tsx`
- Create: `frontend-react/src/components/Spinner/Spinner.tsx`
- Create: `frontend-react/src/utils/cn.ts`

- [ ] **Step 1: Create utils/cn.ts** — classname join utility

```typescript
export function cn(...classes: (string | undefined | false | null)[]): string {
  return classes.filter(Boolean).join(' ');
}
```

- [ ] **Step 2: Create Button.tsx**

Three variants: `primary` (amber bg), `ghost` (transparent), `danger` (rust). Sizes: `sm`, `md`. Supports `icon` prop (renders Icon), `loading` prop (shows Spinner).

```tsx
import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/utils/cn';
import { Icon, type IconName } from '@/components/Icon/Icon';
import styles from './Button.module.css';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  icon?: IconName;
  loading?: boolean;
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading,
  children,
  className,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(styles.btn, styles[variant], styles[size], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <span className={styles.spinner} /> : icon ? <Icon name={icon} size={size === 'sm' ? 14 : 16} /> : null}
      {children && <span>{children}</span>}
    </button>
  );
}
```

- [ ] **Step 3: Create Button.module.css**

Reference `frontend/styles.css` for button styles. Key: border-radius 10px, padding 8px 16px (md) / 6px 12px (sm), transitions, hover/active states. Use CSS variables for colors.

- [ ] **Step 4: Create Badge.tsx**

```tsx
import { cn } from '@/utils/cn';

type BadgeVariant = 'amber' | 'teal' | 'rust' | 'plum' | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = 'neutral', children, className }: BadgeProps) {
  const colors: Record<BadgeVariant, string> = {
    amber: 'var(--amber)',
    teal: 'var(--teal)',
    rust: 'var(--rust)',
    plum: 'var(--plum)',
    neutral: 'var(--ink-3)',
  };
  const bgs: Record<BadgeVariant, string> = {
    amber: 'var(--amber-soft)',
    teal: 'var(--teal-soft)',
    rust: 'var(--rust-soft)',
    plum: 'var(--plum)',
    neutral: 'var(--line)',
  };
  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        color: colors[variant],
        backgroundColor: bgs[variant],
      }}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 5: Create Spinner.tsx**

```tsx
interface SpinnerProps {
  size?: number;
}

export function Spinner({ size = 16 }: SpinnerProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      style={{ animation: 'spin 0.8s linear infinite' }}
    >
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M8 2a6 6 0 014.5 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
```

Add `@keyframes spin` to global.css: `@keyframes spin { to { transform: rotate(360deg); } }`

- [ ] **Step 6: Verify components render**

Show Button (3 variants), Badge (5 variants), Spinner in App.tsx. Verify styles match existing Prism design language.

- [ ] **Step 7: Commit**

```bash
git add frontend-react/src/components/Button/ frontend-react/src/components/Badge/ frontend-react/src/components/Spinner/ frontend-react/src/utils/
git commit -m "feat(frontend): core components — Button, Badge, Spinner"
```

---

## Task 5: Modal Component

**Files:**
- Create: `frontend-react/src/components/Modal/Modal.tsx`
- Create: `frontend-react/src/components/Modal/Modal.module.css`

- [ ] **Step 1: Create Modal.tsx**

Portal-based modal with backdrop, focus trap, Escape to close, animation.

```tsx
import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '@/components/Icon/Icon';
import styles from './Modal.module.css';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  width?: number;
}

export function Modal({ open, onClose, title, children, width = 480 }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    ref.current?.focus();
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className={styles.backdrop} onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        className={styles.dialog}
        style={{ maxWidth: width }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {title && (
          <div className={styles.header}>
            <h3>{title}</h3>
            <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
              <Icon name="close" size={14} />
            </button>
          </div>
        )}
        <div className={styles.body}>{children}</div>
      </div>
    </div>,
    document.body,
  );
}
```

- [ ] **Step 2: Create Modal.module.css**

Backdrop: fixed inset-0, bg rgba(28,27,24,0.4), flex center. Dialog: bg var(--paper), border-radius 16px, shadow-3, max-height 80vh, overflow-y auto. Header: flex between, padding 16px 20px, border-bottom. Close button: ghost style.

- [ ] **Step 3: Verify modal opens and closes**

Add a button to App.tsx that opens a sample modal. Verify backdrop click closes, Escape closes, body scroll locks.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/src/components/Modal/
git commit -m "feat(frontend): Modal component with portal, focus trap, Escape"
```

---

## Task 6: Toast System

**Files:**
- Create: `frontend-react/src/components/Toast/Toast.tsx`
- Create: `frontend-react/src/components/Toast/Toast.module.css`
- Create: `frontend-react/src/components/Toast/ToastContext.tsx`

- [ ] **Step 1: Create ToastContext.tsx**

```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

export interface ToastItem {
  id: string;
  message: string;
  variant: 'info' | 'success' | 'error';
}

interface ToastContextValue {
  toasts: ToastItem[];
  addToast: (message: string, variant?: ToastItem['variant']) => void;
  removeToast: (id: string) => void;
}

const Ctx = createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useToast must be inside ToastProvider');
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((message: string, variant: ToastItem['variant'] = 'info') => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return <Ctx.Provider value={{ toasts, addToast, removeToast }}>{children}</Ctx.Provider>;
}
```

- [ ] **Step 2: Create Toast.tsx**

Renders toast stack in bottom-right corner using portal. Each toast has icon, message, close button, auto-dismiss animation.

- [ ] **Step 3: Create Toast.module.css**

Position: fixed bottom-right (right 20px, bottom 20px). Stack gap 8px. Toast: bg var(--paper), shadow-2, border-radius 10px, border-left 3px solid (amber=info, teal=success, rust=error). Slide-in animation.

- [ ] **Step 4: Wire ToastProvider into App.tsx**

Wrap `<App>` content in `<ToastProvider>`. Render `<ToastContainer />` inside provider.

- [ ] **Step 5: Verify toasts appear and auto-dismiss**

Add buttons in App.tsx: "Info Toast", "Success Toast", "Error Toast". Each calls `addToast()`. Verify 6s auto-dismiss and close button.

- [ ] **Step 6: Commit**

```bash
git add frontend-react/src/components/Toast/
git commit -m "feat(frontend): Toast system with context, auto-dismiss, 3 variants"
```

---

## Task 7: Dropdown Component

**Files:**
- Create: `frontend-react/src/components/Dropdown/Dropdown.tsx`
- Create: `frontend-react/src/components/Dropdown/Dropdown.module.css`

- [ ] **Step 1: Create Dropdown.tsx**

Click-to-open dropdown menu. Uses `useRef` + click-outside to close. Renders items with optional icons.

```tsx
import { useState, useRef, useEffect, type ReactNode } from 'react';
import styles from './Dropdown.module.css';

interface DropdownItem {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  danger?: boolean;
}

interface DropdownProps {
  trigger: ReactNode;
  items: DropdownItem[];
  align?: 'left' | 'right';
}

export function Dropdown({ trigger, items, align = 'left' }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div ref={ref} className={styles.wrapper}>
      <div onClick={() => setOpen(!open)}>{trigger}</div>
      {open && (
        <div className={`${styles.menu} ${styles[align]}`}>
          {items.map((item) => (
            <button
              key={item.label}
              className={`${styles.item} ${item.danger ? styles.danger : ''}`}
              onClick={() => { item.onClick(); setOpen(false); }}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create Dropdown.module.css**

Menu: absolute, bg var(--paper), shadow-3, border-radius 10px, border 1px solid var(--line), min-width 160px, z-index 100. Items: full width, text-align left, padding 8px 12px, hover bg var(--bg). Danger: color var(--danger).

- [ ] **Step 3: Commit**

```bash
git add frontend-react/src/components/Dropdown/
git commit -m "feat(frontend): Dropdown component with click-outside close"
```

---

## Task 8: API Client (Typed)

**Files:**
- Create: `frontend-react/src/api/types.ts`
- Create: `frontend-react/src/api/client.ts`

**Reference:** Port `frontend/apiClient.js` (707 lines) to TypeScript. Exact same auth flow, same API surface, but fully typed.

- [ ] **Step 1: Create api/types.ts**

Define all API response types based on `backend/app/schemas/`. Key types:

```typescript
export interface ApiEnvelope<T> {
  data: T;
  error: null | { code: string; message: string };
}

export interface PagedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface User {
  id: string;
  email: string;
  username: string;
  role: 'admin' | 'user';
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Session {
  id: string;
  title: string | null;
  user_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content_blocks: ContentBlock[];
  tool_results: ToolResult[];
  sequence_no: number;
  run_id: string | null;
  created_at: string;
}

export interface ContentBlock {
  type: 'text' | 'tool_use' | 'thinking';
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  input?: Record<string, unknown>;
}

export interface ToolResult {
  type: 'tool_result';
  tool_use_id: string;
  content: string;
  is_error: boolean;
}

export interface Run {
  id: string;
  session_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'crashed';
  agent_type: string;
  created_at: string;
  completed_at: string | null;
  harness_summary: Record<string, unknown> | null;
}

export interface Provider {
  id: string;
  name: string;
  protocol: 'anthropic' | 'openai';
  base_url: string;
  model_id: string;
  scope: 'system' | 'user';
  is_active: boolean;
  capabilities: Record<string, boolean>;
}

export interface SkillSearchResult {
  name: string;
  description: string;
  source: string;
  source_url: string | null;
  score: number;
  installed: boolean;
}

export interface SSEEvent {
  type: SSEEventType;
  [key: string]: unknown;
}

export type SSEEventType =
  | 'text_delta' | 'tool_use_delta'
  | 'tool_start' | 'tool_end'
  | 'message_complete'
  | 'run_complete' | 'run_error' | 'run_crashed'
  | 'permission_ask'
  | 'harness_event'
  | 'coordinator_plan_update'
  | 'session_title'
  | 'queue_update'
  | 'compaction';
```

Add more types as needed from the backend schemas. Cover every API endpoint's request/response.

- [ ] **Step 2: Create api/client.ts**

Port `frontend/apiClient.js` to TypeScript module exports. Exact same auth flow (singleton refresh promise, 401 auto-retry, `prism:unauthorized` event). Replace `window.PrismAPI` with named exports.

Key differences from the JS version:
- `export` instead of `window.PrismAPI`
- All functions typed (params and return types)
- Session/token storage functions are internal (not exported)
- `request<T>()` is generic
- SSE event types are typed

Structure:

```typescript
const API_BASE = '/api/v1';
const TOKEN_KEY = 'prism_access_token';
const USER_KEY = 'prism_current_user';

// Internal token storage — same as apiClient.js
function storeToken(token: string | null) { ... }
function storeUser(user: User | null) { ... }
export function getToken(): string | null { ... }
export function isAuthenticated(): boolean { ... }
export function currentUser(): User | null { ... }

// Base fetch with 401 auto-refresh — port from apiClient.js lines 49-94
async function fetchRaw(method: string, path: string, opts?: RequestOpts): Promise<Response> { ... }

// Generic request with envelope unwrapping — port from apiClient.js lines 122-150
export async function request<T>(method: string, path: string, opts?: RequestOpts): Promise<T> { ... }

// Auth — port from apiClient.js lines 175-263
export async function login(email: string, password: string): Promise<{ user: User; access_token: string }> { ... }
export async function register(params: RegisterParams): Promise<TokenResponse> { ... }
export async function logout(): Promise<void> { ... }
export async function me(): Promise<User> { ... }
// ... all other auth functions

// SSE — port from apiClient.js lines 280-347
export async function openStream(sessionId: string, handlers: SSEHandlers): Promise<EventSource> { ... }

// Domain modules — port each namespace from apiClient.js
export const sessions = { ... };  // lines 350-375
export const tasks = { ... };     // lines 378-383
export const runs = { ... };      // lines 386-396
export const admin = { ... };     // lines 399-457
export const providers = { ... }; // lines 460-485
export const mcp = { ... };       // lines 488-518
export const skills = { ... };    // lines 521-550
export const plugins = { ... };   // lines 553-566
export const marketplaces = { ... }; // lines 569-589
export const im = { ... };        // lines 592-609
export const harness = { ... };   // lines 612-625
export const auth = { ... };      // lines 688-702
export function reportError(params: ErrorReport): Promise<void> { ... } // lines 628-649
```

IMPORTANT: Port every single function and namespace from apiClient.js. Do not skip any. The function bodies are the same logic, just with types added.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend-react/src/api/
git commit -m "feat(frontend): typed API client — full port from apiClient.js"
```

---

## Task 9: useSSE Hook

**Files:**
- Create: `frontend-react/src/hooks/useSSE.ts`

- [ ] **Step 1: Create useSSE.ts**

Custom hook that manages SSE connection lifecycle. Wraps `api.openStream()`.

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';
import { openStream, type SSEEvent, type SSEEventType } from '@/api/client';

type SSEStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

interface UseSSEOptions {
  sessionId: string | null;
  onEvent: (event: SSEEvent) => void;
  enabled?: boolean;
}

export function useSSE({ sessionId, onEvent, enabled = true }: UseSSEOptions) {
  const [status, setStatus] = useState<SSEStatus>('disconnected');
  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  useEffect(() => {
    if (!sessionId || !enabled) {
      disconnect();
      return;
    }

    let cancelled = false;
    setStatus('connecting');

    openStream(sessionId, {
      onEvent: (evt) => {
        if (cancelled) return;
        setStatus('connected');
        onEventRef.current(evt);
      },
      onError: () => {
        if (cancelled) return;
        setStatus('error');
      },
      onClose: () => {
        if (cancelled) return;
        setStatus('disconnected');
      },
    }).then((es) => {
      if (cancelled) {
        es.close();
        return;
      }
      esRef.current = es;
    }).catch(() => {
      if (!cancelled) setStatus('error');
    });

    return () => {
      cancelled = true;
      disconnect();
    };
  }, [sessionId, enabled, disconnect]);

  return { status, disconnect };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend-react/src/hooks/useSSE.ts
git commit -m "feat(frontend): useSSE hook with connection lifecycle"
```

---

## Task 10: Auth Context + Theme Context + Session Context

**Files:**
- Create: `frontend-react/src/context/AuthContext.tsx`
- Create: `frontend-react/src/context/ThemeContext.tsx`
- Create: `frontend-react/src/context/SessionContext.tsx`
- Create: `frontend-react/src/hooks/useAuth.ts`
- Create: `frontend-react/src/hooks/useTheme.ts`
- Create: `frontend-react/src/hooks/useSessions.ts`

- [ ] **Step 1: Create AuthContext.tsx**

```tsx
import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react';
import * as api from '@/api/client';
import type { User } from '@/api/types';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (params: { email: string; username: string; password: string; invite_code?: string }) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(api.currentUser());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (api.isAuthenticated()) {
      api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
    const handler = () => { setUser(null); setLoading(false); };
    window.addEventListener('prism:unauthorized', handler);
    return () => window.removeEventListener('prism:unauthorized', handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { user } = await api.login(email, password);
    setUser(user);
  }, []);

  const register = useCallback(async (params: { email: string; username: string; password: string; invite_code?: string }) => {
    await api.register(params);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
```

- [ ] **Step 2: Create hooks/useAuth.ts**

```typescript
import { useContext } from 'react';
import { AuthContext } from '@/context/AuthContext';

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside AuthProvider');
  return ctx;
}
```

- [ ] **Step 3: Create ThemeContext.tsx**

```tsx
import { createContext, useCallback, useState, useEffect, type ReactNode } from 'react';

type Theme = 'light' | 'dark';
type Density = 'comfortable' | 'compact' | 'spacious';

interface ThemeState {
  theme: Theme;
  density: Density;
  setTheme: (t: Theme) => void;
  setDensity: (d: Density) => void;
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeState | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem('prism_theme') as Theme) || 'light'
  );
  const [density, setDensityState] = useState<Density>(
    () => (localStorage.getItem('prism_density') as Density) || 'comfortable'
  );

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem('prism_theme', t);
    document.documentElement.setAttribute('data-theme', t);
  }, []);

  const setDensity = useCallback((d: Density) => {
    setDensityState(d);
    localStorage.setItem('prism_density', d);
    document.documentElement.setAttribute('data-density', d);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === 'light' ? 'dark' : 'light');
  }, [theme, setTheme]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-density', density);
  }, [theme, density]);

  return (
    <ThemeContext.Provider value={{ theme, density, setTheme, setDensity, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

- [ ] **Step 4: Create hooks/useTheme.ts**

```typescript
import { useContext } from 'react';
import { ThemeContext } from '@/context/ThemeContext';

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be inside ThemeProvider');
  return ctx;
}
```

- [ ] **Step 5: Create SessionContext.tsx**

```tsx
import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react';
import * as api from '@/api/client';
import type { Session } from '@/api/types';
import { useAuth } from '@/hooks/useAuth';

interface SessionState {
  sessions: Session[];
  currentSessionId: string | null;
  loading: boolean;
  setCurrentSessionId: (id: string | null) => void;
  createSession: () => Promise<Session>;
  deleteSession: (id: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
}

export const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshSessions = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const data = await api.sessions.list({});
      setSessions(Array.isArray(data) ? data : data?.items ?? []);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) refreshSessions();
  }, [user, refreshSessions]);

  const createSession = useCallback(async () => {
    const session = await api.sessions.create({});
    setSessions((prev) => [session, ...prev]);
    setCurrentSessionId(session.id);
    return session;
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    await api.sessions.delete(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (currentSessionId === id) setCurrentSessionId(null);
  }, [currentSessionId]);

  return (
    <SessionContext.Provider value={{
      sessions, currentSessionId, loading,
      setCurrentSessionId, createSession, deleteSession, refreshSessions,
    }}>
      {children}
    </SessionContext.Provider>
  );
}
```

- [ ] **Step 6: Create hooks/useSessions.ts**

```typescript
import { useContext } from 'react';
import { SessionContext } from '@/context/SessionContext';

export function useSessions() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSessions must be inside SessionProvider');
  return ctx;
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend-react/src/context/ frontend-react/src/hooks/
git commit -m "feat(frontend): Auth, Theme, Session contexts + hooks"
```

---

## Task 11: Layout Shell — AppLayout + Sidebar + Topbar

**Files:**
- Create: `frontend-react/src/components/Layout/AppLayout.tsx`
- Create: `frontend-react/src/components/Layout/AppLayout.module.css`
- Create: `frontend-react/src/components/Layout/Sidebar.tsx`
- Create: `frontend-react/src/components/Layout/Sidebar.module.css`
- Create: `frontend-react/src/components/Layout/Topbar.tsx`
- Create: `frontend-react/src/components/Layout/Topbar.module.css`
- Create: `frontend-react/src/utils/time.ts`

**Reference:** `frontend/Prism.html` lines 200-400 for sidebar/layout structure, `frontend/styles.css` for layout CSS.

- [ ] **Step 1: Create utils/time.ts**

Port `groupByTime()` and `formatTime()` from Prism.html lines 139-166.

```typescript
import type { Session } from '@/api/types';

interface TimeGroups {
  today: Session[];
  yesterday: Session[];
  thisWeek: Session[];
  earlier: Session[];
}

export function groupByTime(sessions: Session[]): TimeGroups {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  const startOfWeek = new Date(startOfToday.getTime() - (now.getDay() || 7) * 86400000);

  const groups: TimeGroups = { today: [], yesterday: [], thisWeek: [], earlier: [] };
  const sorted = [...sessions].sort((a, b) =>
    new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
  );

  for (const s of sorted) {
    const d = new Date(s.updated_at);
    if (d >= startOfToday) groups.today.push(s);
    else if (d >= startOfYesterday) groups.yesterday.push(s);
    else if (d >= startOfWeek) groups.thisWeek.push(s);
    else groups.earlier.push(s);
  }
  return groups;
}

export function formatTime(isoStr: string | null): string {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  if (d >= startOfToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (d >= startOfYesterday) return '昨天';
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}
```

- [ ] **Step 2: Create Sidebar.tsx**

Session list with time grouping, search input, new chat button. Mobile: overlay mode.

Reference `Prism.html` lines 200-340 for structure. Key elements:
- PrismMark logo + brand text at top
- New chat button
- Search input (debounce 300ms)
- Session groups (Today / Yesterday / This Week / Earlier)
- Each session item: title, time, active highlight
- Nav items at bottom: Chat, Sessions, Settings, Usage, Skills, Plugins, Admin, Observability
- Nav items with icons from Icon system

Props:
```typescript
interface SidebarProps {
  open: boolean;
  onClose: () => void;
  currentPage: string;
  onNavigate: (page: string) => void;
}
```

- [ ] **Step 3: Create Sidebar.module.css**

Width: 240px (var(--sidebar-w)). Background: var(--bg). Border-right: 1px solid var(--line). Mobile (@media max-width 640px): position fixed, inset-0, z-index 200, width 100vw, transform translateX(-100%), transition.

Reference `frontend/styles.css` for sidebar-specific styles.

- [ ] **Step 4: Create Topbar.tsx**

Height: 48px. Contains: hamburger button (mobile only), page title, theme toggle button, user menu (Dropdown).

```tsx
interface TopbarProps {
  title: string;
  onMenuClick: () => void;
}
```

- [ ] **Step 5: Create Topbar.module.css**

Height: var(--topbar-h). Background: var(--paper). Border-bottom: 1px solid var(--line). Flex between. Mobile: show hamburger. Desktop: hide hamburger.

- [ ] **Step 6: Create AppLayout.tsx**

Combines Sidebar + Topbar + main content area via `<Outlet />`.

```tsx
import { useState, useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import styles from './AppLayout.module.css';

const PAGE_TITLES: Record<string, string> = {
  '/': '对话',
  '/sessions': '会话',
  '/settings': '设置',
  '/usage': '用量',
  '/skills': '技能市场',
  '/plugins': '插件构建',
  '/admin': '管理',
  '/observability': '可观测性',
};

export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const handleNavigate = useCallback((page: string) => {
    navigate(page);
    setSidebarOpen(false);
  }, [navigate]);

  const title = PAGE_TITLES[location.pathname] ?? 'Prism';

  return (
    <div className={styles.shell}>
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        currentPage={location.pathname}
        onNavigate={handleNavigate}
      />
      <div className={styles.main}>
        <Topbar title={title} onMenuClick={() => setSidebarOpen(!sidebarOpen)} />
        <div className={styles.content}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create AppLayout.module.css**

Shell: flex, height 100vh. Sidebar: fixed left on desktop, overlay on mobile. Main: flex-1, flex column. Content: flex-1, overflow-y auto.

- [ ] **Step 8: Commit**

```bash
git add frontend-react/src/components/Layout/ frontend-react/src/utils/time.ts
git commit -m "feat(frontend): layout shell — AppLayout, Sidebar, Topbar"
```

---

## Task 12: Router + Placeholder Pages + Final Assembly

**Files:**
- Create: `frontend-react/src/pages/Placeholder.tsx`
- Modify: `frontend-react/src/App.tsx` — full router + context providers

- [ ] **Step 1: Create pages/Placeholder.tsx**

```tsx
interface PlaceholderProps {
  name: string;
}

export function Placeholder({ name }: PlaceholderProps) {
  return (
    <div style={{ padding: 40 }}>
      <h2 style={{ fontFamily: 'var(--serif)', marginBottom: 8 }}>{name}</h2>
      <p style={{ color: 'var(--ink-3)' }}>This page will be built in Phase 3+</p>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx with router + providers**

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ThemeProvider } from '@/context/ThemeContext';
import { SessionProvider } from '@/context/SessionContext';
import { ToastProvider } from '@/components/Toast/ToastContext';
import { AppLayout } from '@/components/Layout/AppLayout';
import { useAuth } from '@/hooks/useAuth';
import { Placeholder } from '@/pages/Placeholder';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ padding: 40 }}>Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Placeholder name="Login" />} />
      <Route path="/register" element={<Placeholder name="Register" />} />
      <Route element={<AuthGuard><AppLayout /></AuthGuard>}>
        <Route index element={<Placeholder name="Chat" />} />
        <Route path="sessions" element={<Placeholder name="Sessions" />} />
        <Route path="settings" element={<Placeholder name="Settings" />} />
        <Route path="usage" element={<Placeholder name="Usage" />} />
        <Route path="skills" element={<Placeholder name="Skills Market" />} />
        <Route path="plugins" element={<Placeholder name="Plugin Builder" />} />
        <Route path="admin/*" element={<Placeholder name="Admin" />} />
        <Route path="observability" element={<Placeholder name="Observability" />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <SessionProvider>
              <AppRoutes />
            </SessionProvider>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
```

- [ ] **Step 3: Verify full app renders**

Run: `cd frontend-react && npx vite`

Verify:
1. Dev server starts at localhost:3000
2. Placeholder pages render for each route
3. Sidebar navigation works (clicking nav items changes pages)
4. Mobile viewport (< 640px): sidebar becomes overlay with hamburger
5. Theme toggle switches light/dark
6. Toast notifications work
7. No TypeScript errors (`npx tsc --noEmit`)
8. No console errors

- [ ] **Step 4: Commit**

```bash
git add frontend-react/src/App.tsx frontend-react/src/pages/
git commit -m "feat(frontend): router, auth guard, placeholder pages — Phase 1+2 complete"
```

---

## Final Verification

- [ ] **Step 1: Full TypeScript check**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: Zero errors

- [ ] **Step 2: Vite build**

Run: `cd frontend-react && npx vite build`
Expected: Build succeeds, outputs to `dist/`

- [ ] **Step 3: Visual inspection**

Open http://localhost:3000 and verify:
- Design language matches existing Prism (serif font, amber accent, warm paper background)
- All 35 icons render correctly
- Button variants display (primary/ghost/danger)
- Modal opens/closes with backdrop
- Toast notifications appear and auto-dismiss
- Sidebar shows nav items with icons
- Mobile responsive (resize to 390px width → sidebar becomes overlay)
- Dark mode toggle works
- No visual regressions vs existing Prism.html design

- [ ] **Step 4: Final commit + summary**

```bash
git add -A frontend-react/
git commit -m "chore(frontend): Phase 1+2 complete — foundation + infrastructure"
```
