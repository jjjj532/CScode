# CScode GUI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `src/cscode/web/` as a pixel-perfect replica of OpenCode v1.17 desktop web UI

**Architecture:** React 18 + TypeScript + Vite + Tailwind CSS. Zustand for state (3 stores: session, config, UI). Shell-first approach — new layout wraps around as old code is incrementally replaced.

**Tech Stack:** Vite 5, React 18, Tailwind CSS 3, Zustand, lucide-react, react-markdown + rehype-highlight

---

## File Structure

### Files to Create
| File | Responsibility |
|------|---------------|
| `src/cscode/web/tailwind.config.ts` | Tailwind config with CSS variable theme |
| `src/cscode/web/postcss.config.js` | PostCSS with Tailwind + autoprefixer |
| `src/cscode/web/src/index.css` | Tailwind directives + CSS custom property themes |
| `src/cscode/web/src/stores/useSessionStore.ts` | Sessions + messages state |
| `src/cscode/web/src/stores/useConfigStore.ts` | Provider/model config state |
| `src/cscode/web/src/stores/useUIStore.ts` | Theme, mode, sidebar, panel state |
| `src/cscode/web/src/hooks/useChat.ts` | SSE stream → message store |
| `src/cscode/web/src/hooks/useTheme.ts` | CSS variable swapping |
| `src/cscode/web/src/lib/api.ts` | Typed fetch wrappers for all endpoints |
| `src/cscode/web/src/lib/markdown.ts` | remark/rehype plugin config |
| `src/cscode/web/src/components/layout/Titlebar.tsx` | Top bar with project path + mode badge |
| `src/cscode/web/src/components/layout/Sidebar.tsx` | Left panel: ThreadsHeader + ProjectList + settings |
| `src/cscode/web/src/components/layout/MainContent.tsx` | Center: MessageList + Composer |
| `src/cscode/web/src/components/sidebar/ThreadsHeader.tsx` | THREADS label + toolbar buttons |
| `src/cscode/web/src/components/sidebar/ProjectList.tsx` | Scrollable project list |
| `src/cscode/web/src/components/sidebar/ProjectItem.tsx` | Expandable project/session row |
| `src/cscode/web/src/components/chat/MessageList.tsx` | Scrollable message list |
| `src/cscode/web/src/components/chat/Message.tsx` | Single message bubble |
| `src/cscode/web/src/components/chat/Composer.tsx` | Input area + attachments |
| `src/cscode/web/src/components/chat/ThinkingIndicator.tsx` | Waiting animation |
| `src/cscode/web/src/components/markdown/MarkdownRenderer.tsx` | Markdown → HTML pipeline |
| `src/cscode/web/src/components/markdown/CodeBlock.tsx` | Syntax-highlighted code |
| `src/cscode/web/src/components/ui/ToolCallDisplay.tsx` | Inline tool execution display |
| `src/cscode/web/src/components/ui/ModeToggle.tsx` | Plan/Build pill toggle |
| `src/cscode/web/src/components/ui/SettingsPanel.tsx` | Config slide-out panel |
| `src/cscode/web/src/components/ui/ThemeProvider.tsx` | Theme context provider |
| `src/cscode/web/src/themes/index.ts` | 6 preset themes as CSS variable maps |

### Files to Modify
| File | Change |
|------|--------|
| `src/cscode/web/package.json` | Add tailwindcss, postcss, zustand, lucide-react, react-markdown, rehype-highlight |
| `src/cscode/web/vite.config.ts` | No changes needed (already proxies /api to :8080) |
| `src/cscode/web/src/main.tsx` | Replace ConfigProvider with ThemeProvider |
| `src/cscode/web/src/App.tsx` | Complete rewrite — new layout shell |
| `src/cscode/web/src/types.ts` | Session, Message, Config → match API + add Project, Thread |

### Files to Delete (after replacement)
| File | When |
|------|------|
| `src/cscode/web/src/context/ConfigContext.tsx` | Phase 1 (replaced by Zustand stores) |
| `src/cscode/web/src/components/Sidebar.tsx` | Phase 2 (replaced by layout/Sidebar) |
| `src/cscode/web/src/components/SettingsPanel.tsx` | Phase 5 (replaced by ui/SettingsPanel) |

---

## Phase 1: Foundation + Layout Shell

### Task 1: Add Tailwind CSS + dependencies

**Files:**
- Modify: `src/cscode/web/package.json`
- Create: `src/cscode/web/tailwind.config.ts`
- Create: `src/cscode/web/postcss.config.js`

- [ ] **Step 1: Update package.json**

```json
{
  "name": "cscode-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tauri-apps/api": "^2.11.0",
    "@tauri-apps/plugin-dialog": "^2.7.1",
    "@tauri-apps/plugin-fs": "^2.5.1",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^5.0.0",
    "lucide-react": "^0.460.0",
    "react-markdown": "^9.0.0",
    "rehype-highlight": "^7.0.0",
    "remark-gfm": "^4.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

- [ ] **Step 2: Create tailwind.config.ts**

```ts
import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'v2-bg-deep': 'var(--bg-deep)',
        'v2-bg-base': 'var(--bg-base)',
        'v2-bg-surface': 'var(--bg-surface)',
        'v2-text-primary': 'var(--text-primary)',
        'v2-text-secondary': 'var(--text-secondary)',
        'v2-text-muted': 'var(--text-muted)',
        'v2-accent': 'var(--accent-primary)',
        'v2-accent-secondary': 'var(--accent-secondary)',
        'v2-border': 'var(--border)',
        'v2-border-light': 'var(--border-light)',
        'v2-msg-user': 'var(--msg-user-bg)',
        'v2-msg-assistant': 'var(--msg-assistant-bg)',
        'v2-code-bg': 'var(--code-bg)',
        'v2-code-header': 'var(--code-header)',
      },
      boxShadow: {
        'v2-raised': 'var(--elevation-raised)',
        'v2-overlay': 'var(--elevation-overlay)',
      },
      borderRadius: {
        'v2': '10px',
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 3: Create postcss.config.js**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 4: Install dependencies**

Run: `cd src/cscode/web && npm install`
Expected: All packages installed without errors

- [ ] **Step 5: Commit**

```bash
git add src/cscode/web/package.json src/cscode/web/package-lock.json src/cscode/web/tailwind.config.ts src/cscode/web/postcss.config.js
git commit -m "feat(gui): add Tailwind CSS + Zustand + lucide-react deps"
```

---

### Task 2: Create theme system + index.css

**Files:**
- Create: `src/cscode/web/src/index.css`
- Create: `src/cscode/web/src/themes/index.ts`

- [ ] **Step 1: Create index.css with Tailwind directives + CSS variables**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

*,
*::before,
*::after {
  box-sizing: border-box;
}

html, body, #root {
  height: 100%;
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
}

/* OpenCode Dark (default) */
:root,
:root[data-theme="opencode-dark"] {
  --bg-deep: #1a1a2e;
  --bg-base: #0f3460;
  --bg-surface: #16213e;
  --text-primary: #e0e0e0;
  --text-secondary: #aaa;
  --text-muted: #666;
  --accent-primary: #4fc3f7;
  --accent-secondary: #4caf50;
  --border: #2a2a4e;
  --border-light: #333;
  --elevation-raised: 0 4px 12px rgba(0, 0, 0, 0.3);
  --elevation-overlay: 0 8px 24px rgba(0, 0, 0, 0.4);
  --msg-user-bg: #1a1a4e;
  --msg-assistant-bg: #1a1a2e;
  --code-bg: #111;
  --code-header: #1a1a1a;
}

:root[data-theme="catppuccin"] {
  --bg-deep: #1e1e2e;
  --bg-base: #181825;
  --bg-surface: #313244;
  --text-primary: #cdd6f4;
  --text-secondary: #a6adc8;
  --text-muted: #6c7086;
  --accent-primary: #89b4fa;
  --accent-secondary: #a6e3a1;
  --border: #313244;
  --border-light: #45475a;
  --elevation-raised: 0 4px 12px rgba(0, 0, 0, 0.3);
  --elevation-overlay: 0 8px 24px rgba(0, 0, 0, 0.4);
  --msg-user-bg: #313244;
  --msg-assistant-bg: #1e1e2e;
  --code-bg: #11111b;
  --code-header: #181825;
}

:root[data-theme="dracula"] {
  --bg-deep: #282a36;
  --bg-base: #21222c;
  --bg-surface: #44475a;
  --text-primary: #f8f8f2;
  --text-secondary: #bd93f9;
  --text-muted: #6272a4;
  --accent-primary: #ff79c6;
  --accent-secondary: #50fa7b;
  --border: #44475a;
  --border-light: #555;
  --elevation-raised: 0 4px 12px rgba(0, 0, 0, 0.3);
  --elevation-overlay: 0 8px 24px rgba(0, 0, 0, 0.4);
  --msg-user-bg: #44475a;
  --msg-assistant-bg: #282a36;
  --code-bg: #1e1f29;
  --code-header: #21222c;
}

:root[data-theme="github-dark"] {
  --bg-deep: #0d1117;
  --bg-base: #161b22;
  --bg-surface: #21262d;
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #484f58;
  --accent-primary: #58a6ff;
  --accent-secondary: #3fb950;
  --border: #30363d;
  --border-light: #21262d;
  --elevation-raised: 0 4px 12px rgba(0, 0, 0, 0.4);
  --elevation-overlay: 0 8px 24px rgba(0, 0, 0, 0.5);
  --msg-user-bg: #1c2128;
  --msg-assistant-bg: #0d1117;
  --code-bg: #0d1117;
  --code-header: #161b22;
}

:root[data-theme="opencode-light"] {
  --bg-deep: #f5f5f5;
  --bg-base: #fff;
  --bg-surface: #e8e8e8;
  --text-primary: #1a1a1a;
  --text-secondary: #666;
  --text-muted: #999;
  --accent-primary: #646cff;
  --accent-secondary: #4caf50;
  --border: #e0e0e0;
  --border-light: #eee;
  --elevation-raised: 0 2px 8px rgba(0, 0, 0, 0.1);
  --elevation-overlay: 0 4px 16px rgba(0, 0, 0, 0.15);
  --msg-user-bg: #e8e8ff;
  --msg-assistant-bg: #fff;
  --code-bg: #f6f8fa;
  --code-header: #e8e8e8;
}

:root[data-theme="github-light"] {
  --bg-deep: #f6f8fa;
  --bg-base: #fff;
  --bg-surface: #e8ecf0;
  --text-primary: #1f2328;
  --text-secondary: #656d76;
  --text-muted: #8b949e;
  --accent-primary: #0969da;
  --accent-secondary: #1a7f37;
  --border: #d0d7de;
  --border-light: #e8ecf0;
  --elevation-raised: 0 2px 8px rgba(0, 0, 0, 0.08);
  --elevation-overlay: 0 4px 16px rgba(0, 0, 0, 0.12);
  --msg-user-bg: #ddf4ff;
  --msg-assistant-bg: #fff;
  --code-bg: #f6f8fa;
  --code-header: #e8ecf0;
}
```

- [ ] **Step 2: Create themes/index.ts**

```ts
export type ThemeId = 'opencode-dark' | 'opencode-light' | 'catppuccin' | 'dracula' | 'github-dark' | 'github-light';

export interface Theme {
  id: ThemeId;
  name: string;
  type: 'dark' | 'light';
}

export const themes: Theme[] = [
  { id: 'opencode-dark', name: 'OpenCode Dark', type: 'dark' },
  { id: 'opencode-light', name: 'OpenCode Light', type: 'light' },
  { id: 'catppuccin', name: 'Catppuccin', type: 'dark' },
  { id: 'dracula', name: 'Dracula', type: 'dark' },
  { id: 'github-dark', name: 'GitHub Dark', type: 'dark' },
  { id: 'github-light', name: 'GitHub Light', type: 'light' },
];

export function applyTheme(themeId: ThemeId): void {
  document.documentElement.setAttribute('data-theme', themeId);
}
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/index.css src/cscode/web/src/themes/index.ts
git commit -m "feat(gui): add Tailwind CSS variables theme system with 6 presets"
```

---

### Task 3: Create Zustand stores

**Files:**
- Create: `src/cscode/web/src/stores/useSessionStore.ts`
- Create: `src/cscode/web/src/stores/useConfigStore.ts`
- Create: `src/cscode/web/src/stores/useUIStore.ts`

- [ ] **Step 1: Create useSessionStore.ts**

```ts
import { create } from 'zustand';

export interface Session {
  id: string;
  title: string;
  provider?: string;
  model?: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface SessionState {
  sessions: Session[];
  messages: Message[];
  activeSessionId: string | null;
  loading: boolean;
  setSessions: (sessions: Session[]) => void;
  setMessages: (messages: Message[]) => void;
  appendMessage: (message: Message) => void;
  setActiveSession: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  addSession: (session: Session) => void;
  removeSession: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  messages: [],
  activeSessionId: null,
  loading: false,
  setSessions: (sessions) => set({ sessions }),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  setActiveSession: (id) => set({ activeSessionId: id }),
  setLoading: (loading) => set({ loading }),
  addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
  removeSession: (id) => set((s) => ({ sessions: s.sessions.filter((x) => x.id !== id) })),
}));
```

- [ ] **Step 2: Create useConfigStore.ts**

```ts
import { create } from 'zustand';

export interface Config {
  provider: string;
  model: string;
  api_base: string | null;
  api_key?: string;
  max_tokens: number;
  temperature: number;
  top_p: number;
  system_prompt: string | null;
}

interface ConfigState {
  config: Config | null;
  loading: boolean;
  setConfig: (config: Config) => void;
  updateConfig: (partial: Partial<Config>) => void;
  setLoading: (loading: boolean) => void;
}

export const useConfigStore = create<ConfigState>((set) => ({
  config: null,
  loading: false,
  setConfig: (config) => set({ config }),
  updateConfig: (partial) => set((s) => ({ config: s.config ? { ...s.config, ...partial } : null })),
  setLoading: (loading) => set({ loading }),
}));
```

- [ ] **Step 3: Create useUIStore.ts**

```ts
import { create } from 'zustand';
import type { ThemeId } from '../themes';

export type Mode = 'plan' | 'build';

interface UIState {
  theme: ThemeId;
  mode: Mode;
  sidebarOpen: boolean;
  settingsOpen: boolean;
  attachedFiles: File[];
  setTheme: (theme: ThemeId) => void;
  setMode: (mode: Mode) => void;
  toggleMode: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSettingsOpen: (open: boolean) => void;
  setAttachedFiles: (files: File[]) => void;
  addAttachedFile: (file: File) => void;
  removeAttachedFile: (index: number) => void;
}

export const useUIStore = create<UIState>((set) => ({
  theme: 'opencode-dark',
  mode: 'build',
  sidebarOpen: true,
  settingsOpen: false,
  attachedFiles: [],
  setTheme: (theme) => set({ theme }),
  setMode: (mode) => set({ mode }),
  toggleMode: () => set((s) => ({ mode: s.mode === 'plan' ? 'build' : 'plan' })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  setAttachedFiles: (files) => set({ attachedFiles: files }),
  addAttachedFile: (file) => set((s) => ({ attachedFiles: [...s.attachedFiles, file] })),
  removeAttachedFile: (index) => set((s) => ({ attachedFiles: s.attachedFiles.filter((_, i) => i !== index) })),
}));
```

- [ ] **Step 4: Commit**

```bash
git add src/cscode/web/src/stores/
git commit -m "feat(gui): add Zustand stores for session, config, UI state"
```

---

### Task 4: Build ThemeProvider + update main.tsx

**Files:**
- Create: `src/cscode/web/src/components/ui/ThemeProvider.tsx`
- Modify: `src/cscode/web/src/main.tsx`

- [ ] **Step 1: Create ThemeProvider.tsx**

```tsx
import { useEffect, type ReactNode } from 'react';
import { useUIStore } from '../../stores/useUIStore';
import { applyTheme } from '../../themes';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useUIStore((s) => s.theme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  return <>{children}</>;
}
```

- [ ] **Step 2: Update main.tsx**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ThemeProvider } from './components/ui/ThemeProvider';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/components/ui/ThemeProvider.tsx src/cscode/web/src/main.tsx
git commit -m "feat(gui): add ThemeProvider, wire up main.tsx"
```

---

### Task 5: Build Titlebar component

**Files:**
- Create: `src/cscode/web/src/components/layout/Titlebar.tsx`

- [ ] **Step 1: Create Titlebar.tsx**

```tsx
import { ModeToggle } from '../ui/ModeToggle';

export function Titlebar() {
  return (
    <div className="flex items-center justify-between h-10 px-4 bg-v2-bg-deep border-b border-v2-border select-none draggable">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-semibold text-v2-text-primary">CScode</span>
        <span className="text-v2-text-muted">—</span>
        <span className="text-v2-text-secondary">~/AI/CScode</span>
      </div>
      <div className="flex items-center gap-3">
        <ModeToggle />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd src/cscode/web && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/components/layout/Titlebar.tsx
git commit -m "feat(gui): add Titlebar component with ModeToggle"
```

---

### Task 6: Build ModeToggle component

**Files:**
- Create: `src/cscode/web/src/components/ui/ModeToggle.tsx`

- [ ] **Step 1: Create ModeToggle.tsx**

```tsx
import { useUIStore, type Mode } from '../../stores/useUIStore';

const modes: { id: Mode; label: string }[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'build', label: 'Build' },
];

export function ModeToggle() {
  const mode = useUIStore((s) => s.mode);
  const setMode = useUIStore((s) => s.setMode);

  return (
    <div className="flex bg-v2-bg-surface rounded-md overflow-hidden text-xs">
      {modes.map((m) => (
        <button
          key={m.id}
          onClick={() => setMode(m.id)}
          className={`px-3 py-1 font-medium transition-colors ${
            mode === m.id
              ? m.id === 'plan'
                ? 'bg-v2-accent text-white'
                : 'bg-v2-accent-secondary text-white'
              : 'text-v2-text-muted hover:text-v2-text-secondary'
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/cscode/web/src/components/ui/ModeToggle.tsx
git commit -m "feat(gui): add Plan/Build mode toggle"
```

---

### Task 7: Build Sidebar + ThreadsHeader

**Files:**
- Create: `src/cscode/web/src/components/layout/Sidebar.tsx`
- Create: `src/cscode/web/src/components/sidebar/ThreadsHeader.tsx`

- [ ] **Step 1: Create ThreadsHeader.tsx**

```tsx
import { Filter, ArrowUpDown, Eye, Plus } from 'lucide-react';

export function ThreadsHeader() {
  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-v2-border">
      <span className="text-xs font-medium text-v2-text-muted tracking-wider">THREADS</span>
      <div className="flex items-center gap-1">
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="Filter">
          <Filter size={14} />
        </button>
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="Sort">
          <ArrowUpDown size={14} />
        </button>
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="View">
          <Eye size={14} />
        </button>
        <button className="p-1 rounded hover:bg-v2-bg-base text-v2-text-muted hover:text-v2-text-secondary transition-colors" title="Add Project">
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create Sidebar.tsx**

```tsx
import { Settings, HelpCircle } from 'lucide-react';
import { ThreadsHeader } from '../sidebar/ThreadsHeader';
import { ProjectList } from '../sidebar/ProjectList';
import { useUIStore } from '../../stores/useUIStore';

export function Sidebar() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);

  return (
    <div className="w-64 bg-v2-bg-surface border-r border-v2-border flex flex-col h-full">
      <ThreadsHeader />
      <ProjectList />
      <div className="mt-auto border-t border-v2-border p-3 flex gap-4">
        <button
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
        >
          <Settings size={14} />
          Settings
        </button>
        <button className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors">
          <HelpCircle size={14} />
          Help
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/components/layout/Sidebar.tsx src/cscode/web/src/components/sidebar/ThreadsHeader.tsx
git commit -m "feat(gui): add Sidebar layout shell + ThreadsHeader"
```

---

### Task 8: Build ProjectList + ProjectItem

**Files:**
- Create: `src/cscode/web/src/components/sidebar/ProjectList.tsx`
- Create: `src/cscode/web/src/components/sidebar/ProjectItem.tsx`

- [ ] **Step 1: Create ProjectItem.tsx**

```tsx
import { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, MessageSquare } from 'lucide-react';
import type { Session } from '../../stores/useSessionStore';

interface ProjectGroup {
  name: string;
  sessions: Session[];
}

interface ProjectItemProps {
  project: ProjectGroup;
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
}

export function ProjectItem({ project, activeSessionId, onSelectSession }: ProjectItemProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-sm text-v2-text-secondary hover:text-v2-text-primary transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Folder size={14} className="text-v2-text-muted" />
        <span>{project.name}</span>
      </button>
      {expanded && (
        <div className="ml-4">
          {project.sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => onSelectSession(session.id)}
              className={`flex items-center gap-1.5 w-full px-3 py-1.5 text-sm rounded-md transition-colors ${
                activeSessionId === session.id
                  ? 'bg-v2-bg-base text-v2-text-primary'
                  : 'text-v2-text-muted hover:text-v2-text-secondary hover:bg-v2-bg-base/50'
              }`}
            >
              <MessageSquare size={14} />
              <span className="truncate">{session.title}</span>
            </button>
          ))}
          {project.sessions.length === 0 && (
            <div className="px-3 py-1 text-xs text-v2-text-muted italic">No sessions</div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create ProjectList.tsx**

```tsx
import { useSessionStore } from '../../stores/useSessionStore';
import { ProjectItem } from './ProjectItem';

export function ProjectList() {
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);

  const projects = [
    {
      name: 'AI-CScode',
      sessions: sessions,
    },
  ];

  return (
    <div className="flex-1 overflow-y-auto py-1">
      {projects.map((project) => (
        <ProjectItem
          key={project.name}
          project={project}
          activeSessionId={activeSessionId}
          onSelectSession={setActiveSession}
        />
      ))}
      {sessions.length === 0 && (
        <div className="px-6 py-8 text-center text-sm text-v2-text-muted">
          No sessions yet. Start a new chat.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/components/sidebar/
git commit -m "feat(gui): add ProjectList and ProjectItem with expand/collapse"
```

---

### Task 9: Build MainContent shell

**Files:**
- Create: `src/cscode/web/src/components/layout/MainContent.tsx`

- [ ] **Step 1: Create MainContent.tsx**

```tsx
import { MessageList } from '../chat/MessageList';
import { Composer } from '../chat/Composer';

export function MainContent() {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-v2-bg-base m-2 mr-2 mb-2 rounded-v2 shadow-v2-raised overflow-hidden">
      <MessageList />
      <Composer />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/cscode/web/src/components/layout/MainContent.tsx
git commit -m "feat(gui): add MainContent layout shell"
```

---

### Task 10: Wire up App.tsx with new layout

**Files:**
- Modify: `src/cscode/web/src/App.tsx` (full rewrite)
- Delete (later cleanup): `src/cscode/web/src/context/ConfigContext.tsx`

- [ ] **Step 1: Rewrite App.tsx**

```tsx
import { useEffect } from 'react';
import { Titlebar } from './components/layout/Titlebar';
import { Sidebar } from './components/layout/Sidebar';
import { MainContent } from './components/layout/MainContent';
import { SettingsPanel } from './components/ui/SettingsPanel';
import { useUIStore } from './stores/useUIStore';
import { useConfigStore } from './stores/useConfigStore';
import { useSessionStore } from './stores/useSessionStore';

function App() {
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const setConfig = useConfigStore((s) => s.setConfig);
  const setSessions = useSessionStore((s) => s.setSessions);

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((data) => {
        if (data && data.provider) setConfig(data);
      })
      .catch(() => {});
  }, [setConfig]);

  useEffect(() => {
    fetch('/api/sessions')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setSessions(data);
      })
      .catch(() => {});
  }, [setSessions]);

  return (
    <div className="h-full flex flex-col bg-v2-bg-deep text-v2-text-primary">
      <Titlebar />
      <div className="flex-1 flex min-h-0">
        <Sidebar />
        <MainContent />
      </div>
      {settingsOpen && <SettingsPanel />}
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Delete old ConfigContext.tsx**

```bash
rm src/cscode/web/src/context/ConfigContext.tsx
```

- [ ] **Step 3: Verify app compiles and runs**

Run: `cd src/cscode/web && npx tsc --noEmit`
Expected: No errors

Then run dev server: `cd src/cscode/web && npm run dev`
Expected: Vite starts on port 5173, page renders layout shell

- [ ] **Step 4: Commit**

```bash
git add src/cscode/web/src/App.tsx
git rm src/cscode/web/src/context/ConfigContext.tsx
git commit -m "feat(gui): wire up new layout shell in App.tsx, remove old ConfigContext"
```

---

## Phase 2: Session Management in Sidebar

### Task 11: Create API client lib

**Files:**
- Create: `src/cscode/web/src/lib/api.ts`

- [ ] **Step 1: Create api.ts**

```ts
import type { Config } from '../stores/useConfigStore';
import type { Session, Message } from '../stores/useSessionStore';

const BASE = '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  config: {
    get: () => request<Config>('/api/config'),
    save: (config: Config) => request<Config>('/api/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  },

  sessions: {
    list: () => request<Session[]>('/api/sessions'),
    create: () => request<Session>('/api/sessions', { method: 'POST' }),
    delete: (id: string) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
    messages: (id: string) => request<Message[]>(`/api/sessions/${id}/messages`),
  },

  chat: {
    send: (message: string, sessionId?: string, files?: string[]) => {
      const body: Record<string, unknown> = { message };
      if (sessionId) body.session_id = sessionId;
      if (files?.length) body.files = files;
      return fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    },
    stream: (message: string, sessionId?: string) => {
      const params = new URLSearchParams({ message });
      if (sessionId) params.set('session_id', sessionId);
      return fetch(`/api/chat/stream?${params}`, { method: 'POST' });
    },
  },

  health: {
    check: () => request<{ status: string }>('/api/health'),
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add src/cscode/web/src/lib/api.ts
git commit -m "feat(gui): add typed API client lib"
```

---

### Task 12: Connect Sidebar to session API

**Files:**
- Modify: `src/cscode/web/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Add session CRUD to Sidebar**

Replace the Sidebar file to include session loading + creation:

```tsx
import { useEffect, useCallback } from 'react';
import { Settings, HelpCircle, Plus } from 'lucide-react';
import { ThreadsHeader } from '../sidebar/ThreadsHeader';
import { ProjectList } from '../sidebar/ProjectList';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUIStore } from '../../stores/useUIStore';
import { api } from '../../lib/api';

export function Sidebar() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const setSessions = useSessionStore((s) => s.setSessions);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setMessages = useSessionStore((s) => s.setMessages);
  const addSession = useSessionStore((s) => s.addSession);
  const removeSession = useSessionStore((s) => s.removeSession);

  useEffect(() => {
    api.sessions.list().then(setSessions).catch(() => {});
  }, [setSessions]);

  const handleSelectSession = useCallback(async (id: string) => {
    setActiveSession(id);
    try {
      const msgs = await api.sessions.messages(id);
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  }, [setActiveSession, setMessages]);

  const handleNewSession = useCallback(async () => {
    try {
      const session = await api.sessions.create();
      addSession(session);
      setActiveSession(session.id);
      setMessages([]);
    } catch (e) {
      console.error('Failed to create session', e);
    }
  }, [addSession, setActiveSession, setMessages]);

  const handleDeleteSession = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this session?')) return;
    try {
      await api.sessions.delete(id);
      removeSession(id);
      if (activeSessionId === id) {
        setActiveSession(null);
        setMessages([]);
      }
    } catch (e) {
      console.error('Failed to delete session', e);
    }
  }, [activeSessionId, removeSession, setActiveSession, setMessages]);

  return (
    <div className="w-64 bg-v2-bg-surface border-r border-v2-border flex flex-col h-full">
      <ThreadsHeader />
      <ProjectList
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />
      <div className="mt-auto border-t border-v2-border p-3 flex gap-4">
        <button
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
        >
          <Settings size={14} />
          Settings
        </button>
        <button className="flex items-center gap-1.5 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors">
          <HelpCircle size={14} />
          Help
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update ProjectList to accept props from Sidebar**

Replace ProjectList.tsx:

```tsx
import { ProjectItem } from './ProjectItem';
import type { Session } from '../../stores/useSessionStore';

interface ProjectListProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
}

export function ProjectList({ sessions, activeSessionId, onSelectSession, onDeleteSession }: ProjectListProps) {
  const projects = [
    { name: 'AI-CScode', sessions },
  ];

  return (
    <div className="flex-1 overflow-y-auto py-1">
      {projects.map((project) => (
        <ProjectItem
          key={project.name}
          project={project}
          activeSessionId={activeSessionId}
          onSelectSession={onSelectSession}
          onDeleteSession={onDeleteSession}
        />
      ))}
      {sessions.length === 0 && (
        <div className="px-6 py-8 text-center text-sm text-v2-text-muted">
          No sessions yet. Start a new chat.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update ProjectItem to accept delete + add X button**

Replace ProjectItem.tsx:

```tsx
import { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, MessageSquare, X } from 'lucide-react';
import type { Session } from '../../stores/useSessionStore';

interface ProjectGroup {
  name: string;
  sessions: Session[];
}

interface ProjectItemProps {
  project: ProjectGroup;
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string, e: React.MouseEvent) => void;
}

export function ProjectItem({ project, activeSessionId, onSelectSession, onDeleteSession }: ProjectItemProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-sm text-v2-text-secondary hover:text-v2-text-primary transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Folder size={14} className="text-v2-text-muted" />
        <span>{project.name}</span>
      </button>
      {expanded && (
        <div className="ml-4">
          {project.sessions.map((session) => (
            <div
              key={session.id}
              className={`group flex items-center rounded-md transition-colors ${
                activeSessionId === session.id
                  ? 'bg-v2-bg-base'
                  : 'hover:bg-v2-bg-base/50'
              }`}
            >
              <button
                onClick={() => onSelectSession(session.id)}
                className="flex items-center gap-1.5 flex-1 px-3 py-1.5 text-sm text-v2-text-muted hover:text-v2-text-secondary truncate"
              >
                <MessageSquare size={14} />
                <span className="truncate">{session.title}</span>
              </button>
              <button
                onClick={(e) => onDeleteSession(session.id, e)}
                className="p-1 mr-1 rounded opacity-0 group-hover:opacity-100 hover:bg-v2-bg-deep text-v2-text-muted hover:text-red-400 transition-all"
              >
                <X size={12} />
              </button>
            </div>
          ))}
          {project.sessions.length === 0 && (
            <div className="px-3 py-1 text-xs text-v2-text-muted italic">No sessions</div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add src/cscode/web/src/components/layout/Sidebar.tsx src/cscode/web/src/components/sidebar/
git commit -m "feat(gui): connect Sidebar to session API with CRUD"
```

---

## Phase 3: Chat Experience

### Task 13: Build useChat hook (SSE streaming)

**Files:**
- Create: `src/cscode/web/src/hooks/useChat.ts`

- [ ] **Step 1: Create useChat.ts**

```ts
import { useRef, useCallback } from 'react';
import { useSessionStore } from '../stores/useSessionStore';

interface StreamEvent {
  type: string;
  session_id?: string;
  content?: string;
  name?: string;
  round?: number;
  max?: number;
  error?: string;
  stepLog?: string[];
}

type EventHandler = (event: StreamEvent) => void;

export function useChat() {
  const abortRef = useRef<AbortController | null>(null);
  const appendMessage = useSessionStore((s) => s.appendMessage);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const setLoading = useSessionStore((s) => s.setLoading);

  const sendMessage = useCallback(async (
    message: string,
    sessionId?: string,
    onThinking?: () => void,
    onToolStart?: (name: string, round: number, max: number) => void,
    onToolComplete?: (name: string, success: boolean) => void,
    onFileCreated?: (url: string) => void,
  ): Promise<string | undefined> => {
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);

    try {
      if (onThinking) onThinking();

      const params = new URLSearchParams({ message });
      if (sessionId) params.set('session_id', sessionId);

      const response = await fetch(`/api/chat/stream?${params}`, {
        method: 'POST',
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let currentSessionId = sessionId;
      let assistantContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          try {
            const event: StreamEvent = JSON.parse(trimmed.slice(6));

            switch (event.type) {
              case 'session':
                if (event.session_id) {
                  currentSessionId = event.session_id;
                  setActiveSession(event.session_id);
                }
                break;
              case 'thinking':
                if (onThinking) onThinking();
                break;
              case 'tool:start':
                if (onToolStart) onToolStart(event.name || '', event.round || 0, event.max || 0);
                break;
              case 'tool:complete':
                if (onToolComplete) onToolComplete(event.name || '', true);
                break;
              case 'file_created':
                if (onFileCreated) onFileCreated(event.content || '');
                break;
              case 'complete':
                if (event.content) {
                  assistantContent = event.content;
                  appendMessage({ role: 'assistant', content: event.content });
                }
                break;
              case 'error':
                console.error('Stream error:', event.error);
                break;
            }
          } catch {
            // skip malformed JSON lines
          }
        }
      }

      return currentSessionId;
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        return sessionId;
      }
      throw err;
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }, [appendMessage, setActiveSession, setLoading]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, [setLoading]);

  return { sendMessage, stop };
}
```

- [ ] **Step 2: Commit**

```bash
git add src/cscode/web/src/hooks/useChat.ts
git commit -m "feat(gui): add useChat hook with SSE streaming"
```

---

### Task 14: Build MessageList + Message components

**Files:**
- Create: `src/cscode/web/src/components/chat/MessageList.tsx`
- Create: `src/cscode/web/src/components/chat/Message.tsx`

- [ ] **Step 1: Create Message.tsx**

```tsx
import { User, Sparkles } from 'lucide-react';
import { MarkdownRenderer } from '../markdown/MarkdownRenderer';
import type { Message as MessageType } from '../../stores/useSessionStore';

interface MessageProps {
  message: MessageType;
}

export function Message({ message }: MessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center">
          <Sparkles size={16} className="text-v2-accent" />
        </div>
      )}
      <div
        className={`max-w-[75%] rounded-v2 px-4 py-2.5 ${
          isUser
            ? 'bg-v2-msg-user border border-v2-border text-v2-text-primary'
            : 'bg-v2-msg-assistant border border-v2-border-light text-v2-text-primary'
        }`}
      >
        <div className={`text-xs font-medium mb-1 ${isUser ? 'text-v2-text-secondary' : 'text-v2-accent'}`}>
          {isUser ? 'You' : 'CScode'}
        </div>
        {isUser ? (
          <div className="text-sm whitespace-pre-wrap break-words leading-relaxed">{message.content}</div>
        ) : (
          <MarkdownRenderer content={message.content} />
        )}
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center">
          <User size={16} className="text-v2-accent" />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create MessageList.tsx**

```tsx
import { useEffect, useRef } from 'react';
import { Message } from './Message';
import { ThinkingIndicator } from './ThinkingIndicator';
import { useSessionStore } from '../../stores/useSessionStore';

export function MessageList() {
  const messages = useSessionStore((s) => s.messages);
  const loading = useSessionStore((s) => s.loading);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-4">🐚</div>
          <h2 className="text-xl font-semibold text-v2-text-primary mb-2">CScode</h2>
          <p className="text-sm text-v2-text-muted max-w-md">
            AI-powered coding assistant. Ask questions, write code, explore your codebase.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {messages.map((msg, i) => (
        <Message key={i} message={msg} />
      ))}
      {loading && <ThinkingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 3: Create ThinkingIndicator.tsx**

```tsx
import { Sparkles } from 'lucide-react';

export function ThinkingIndicator() {
  return (
    <div className="flex gap-3 justify-start">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-accent/20 flex items-center justify-center">
        <Sparkles size={16} className="text-v2-accent" />
      </div>
      <div className="bg-v2-msg-assistant border border-v2-border-light rounded-v2 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <span className="w-2 h-2 bg-v2-accent rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-2 h-2 bg-v2-accent rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-2 h-2 bg-v2-accent rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="text-xs text-v2-text-muted">Thinking...</span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript**

Run: `cd src/cscode/web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add src/cscode/web/src/components/chat/MessageList.tsx src/cscode/web/src/components/chat/Message.tsx src/cscode/web/src/components/chat/ThinkingIndicator.tsx
git commit -m "feat(gui): add MessageList, Message, ThinkingIndicator components"
```

---

### Task 15: Build Composer component

**Files:**
- Create: `src/cscode/web/src/components/chat/Composer.tsx`

- [ ] **Step 1: Create Composer.tsx**

```tsx
import { useState, useRef, useCallback } from 'react';
import { Paperclip, Send, Square, X } from 'lucide-react';
import { useChat } from '../../hooks/useChat';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore } from '../../stores/useConfigStore';

export function Composer() {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, stop } = useChat();
  const loading = useSessionStore((s) => s.loading);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const appendMessage = useSessionStore((s) => s.appendMessage);
  const setActiveSession = useSessionStore((s) => s.setActiveSession);
  const attachedFiles = useUIStore((s) => s.attachedFiles);
  const removeAttachedFile = useUIStore((s) => s.removeAttachedFile);
  const config = useConfigStore((s) => s.config);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    appendMessage({ role: 'user', content: text });

    try {
      const newSessionId = await sendMessage(text, activeSessionId || undefined);
      if (!activeSessionId && newSessionId) {
        setActiveSession(newSessionId);
      }
    } catch (err) {
      console.error('Chat error:', err);
      appendMessage({
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Request failed'}`,
      });
    }
  }, [input, loading, activeSessionId, appendMessage, sendMessage, setActiveSession]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAttachFile = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ multiple: true, title: 'Select files' });
      if (!selected) return;
      for (const path of Array.isArray(selected) ? selected : [selected]) {
        const file = new File([path], typeof path === 'string' ? path.split('/').pop() || path : 'file', { type: 'application/octet-stream' });
        useUIStore.getState().addAttachedFile(file);
      }
    } catch {
      // Browser fallback
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.multiple = true;
      fileInput.onchange = () => {
        if (fileInput.files) {
          Array.from(fileInput.files).forEach((f) => useUIStore.getState().addAttachedFile(f));
        }
      };
      fileInput.click();
    }
  };

  return (
    <div className="border-t border-v2-border bg-v2-bg-base p-3">
      {attachedFiles.length > 0 && (
        <div className="flex gap-2 mb-2 flex-wrap">
          {attachedFiles.map((file, i) => (
            <span
              key={i}
              className="flex items-center gap-1 bg-v2-bg-surface text-xs text-v2-text-secondary px-2 py-1 rounded-md"
            >
              <Paperclip size={12} />
              {file.name}
              <button onClick={() => removeAttachedFile(i)} className="text-v2-text-muted hover:text-red-400">
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 bg-v2-bg-deep border border-v2-border rounded-v2 px-3 py-2">
        <button onClick={handleAttachFile} className="text-v2-text-muted hover:text-v2-text-secondary transition-colors p-1">
          <Paperclip size={18} />
        </button>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything or @mention a file..."
          className="flex-1 bg-transparent text-sm text-v2-text-primary placeholder-v2-text-muted outline-none resize-none py-1 max-h-32"
          rows={1}
        />
        {loading ? (
          <button onClick={stop} className="bg-red-500 text-white p-2 rounded-lg hover:bg-red-600 transition-colors">
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="bg-v2-accent text-white p-2 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={16} />
          </button>
        )}
      </div>
      <div className="flex justify-between mt-1.5 px-1">
        <span className="text-[10px] text-v2-text-muted">
          Model: {config?.model || 'gpt-4o'} ({config?.provider || 'openai'})
        </span>
        <span className="text-[10px] text-v2-text-muted">
          @mention files · Tab to switch mode
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/cscode/web/src/components/chat/Composer.tsx
git commit -m "feat(gui): add Composer with file attachments and send/stop"
```

---

### Task 16: Build ToolCallDisplay

**Files:**
- Create: `src/cscode/web/src/components/ui/ToolCallDisplay.tsx`
- Modify: `src/cscode/web/src/components/chat/MessageList.tsx` (integrate tool calls)

- [ ] **Step 1: Create ToolCallDisplay.tsx**

```tsx
import { useState } from 'react';
import { Loader2, CheckCircle2, XCircle, ChevronDown, ChevronRight, Terminal } from 'lucide-react';

interface ToolCallDisplayProps {
  name: string;
  round: number;
  max: number;
  success?: boolean;
  error?: string;
  output?: string;
}

export function ToolCallDisplay({ name, round, max, success, error, output }: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="flex gap-3 justify-start">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-v2-bg-surface flex items-center justify-center">
        <Terminal size={16} className="text-v2-text-muted" />
      </div>
      <div className="bg-v2-msg-assistant border border-v2-border-light rounded-v2 min-w-[200px]">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 px-3 py-2 w-full text-left hover:bg-v2-bg-deep/50 transition-colors rounded-v2"
        >
          {success === undefined ? (
            <Loader2 size={14} className="text-v2-accent animate-spin" />
          ) : success ? (
            <CheckCircle2 size={14} className="text-v2-accent-secondary" />
          ) : (
            <XCircle size={14} className="text-red-400" />
          )}
          <span className="text-xs text-v2-text-secondary font-medium">{name}</span>
          <span className="text-[10px] text-v2-text-muted ml-auto">
            {round}/{max}
          </span>
          {output && (expanded ? <ChevronDown size={14} className="text-v2-text-muted" /> : <ChevronRight size={14} className="text-v2-text-muted" />)}
        </button>
        {expanded && output && (
          <pre className="px-3 pb-2 text-xs text-v2-text-secondary overflow-x-auto max-h-40">{output}</pre>
        )}
        {error && (
          <pre className="px-3 pb-2 text-xs text-red-400 overflow-x-auto">{error}</pre>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update MessageList.tsx to track tool calls**

Replace MessageList.tsx to accept tool call state:

```tsx
import { useEffect, useRef, useState } from 'react';
import { Message } from './Message';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ToolCallDisplay } from '../ui/ToolCallDisplay';
import { useSessionStore } from '../../stores/useSessionStore';

interface ToolCallState {
  name: string;
  round: number;
  max: number;
  success?: boolean;
  error?: string;
  output?: string;
}

export function MessageList() {
  const messages = useSessionStore((s) => s.messages);
  const loading = useSessionStore((s) => s.loading);
  const endRef = useRef<HTMLDivElement>(null);
  const [toolCalls, setToolCalls] = useState<ToolCallState[]>([]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading, toolCalls]);

  useEffect(() => {
    if (!loading) setToolCalls([]);
  }, [loading]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-4">🐚</div>
          <h2 className="text-xl font-semibold text-v2-text-primary mb-2">CScode</h2>
          <p className="text-sm text-v2-text-muted max-w-md">
            AI-powered coding assistant. Ask questions, write code, explore your codebase.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      {messages.map((msg, i) => (
        <Message key={i} message={msg} />
      ))}
      {toolCalls.map((tc, i) => (
        <ToolCallDisplay key={i} {...tc} />
      ))}
      {loading && toolCalls.length === 0 && <ThinkingIndicator />}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/components/ui/ToolCallDisplay.tsx src/cscode/web/src/components/chat/MessageList.tsx
git commit -m "feat(gui): add ToolCallDisplay and integrate with MessageList"
```

---

## Phase 4: Markdown & Code Highlighting

### Task 17: Build MarkdownRenderer

**Files:**
- Create: `src/cscode/web/src/lib/markdown.ts`
- Create: `src/cscode/web/src/components/markdown/MarkdownRenderer.tsx`

- [ ] **Step 1: Create markdown.ts**

```ts
import type { Components } from 'react-markdown';
import { CodeBlock } from '../components/markdown/CodeBlock';

export const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '');
    const code = String(children).replace(/\n$/, '');
    if (match) {
      return <CodeBlock language={match[1]} code={code} />;
    }
    return (
      <code className="bg-v2-code-bg text-v2-accent px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
        {children}
      </code>
    );
  },
  pre({ children }) {
    return <>{children}</>;
  },
  a({ href, children }) {
    return (
      <a href={href} className="text-v2-accent underline hover:opacity-80" target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  ul({ children }) {
    return <ul className="list-disc pl-5 my-1 space-y-0.5">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="list-decimal pl-5 my-1 space-y-0.5">{children}</ol>;
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-2">
        <table className="border-collapse border border-v2-border text-sm">{children}</table>
      </div>
    );
  },
  th({ children }) {
    return <th className="border border-v2-border bg-v2-bg-surface px-3 py-1.5 text-left font-medium">{children}</th>;
  },
  td({ children }) {
    return <td className="border border-v2-border px-3 py-1.5">{children}</td>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-4 border-v2-accent pl-4 my-2 text-v2-text-secondary italic">
        {children}
      </blockquote>
    );
  },
  h1({ children }) {
    return <h1 className="text-lg font-bold my-3 text-v2-text-primary">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-base font-bold my-2 text-v2-text-primary">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-sm font-bold my-2 text-v2-text-primary">{children}</h3>;
  },
  p({ children }) {
    return <p className="my-1 leading-relaxed">{children}</p>;
  },
  hr() {
    return <hr className="my-3 border-v2-border" />;
  },
};
```

- [ ] **Step 2: Create MarkdownRenderer.tsx**

```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../lib/markdown';

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="text-sm leading-relaxed [&_p]:my-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/lib/markdown.ts src/cscode/web/src/components/markdown/MarkdownRenderer.tsx
git commit -m "feat(gui): add MarkdownRenderer with GFM support"
```

---

### Task 18: Build CodeBlock with syntax highlighting

**Files:**
- Create: `src/cscode/web/src/components/markdown/CodeBlock.tsx`

- [ ] **Step 1: Create CodeBlock.tsx**

```tsx
import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  language: string;
  code: string;
}

export function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-v2-border-light">
      <div className="flex items-center justify-between bg-v2-code-header px-4 py-1.5 border-b border-v2-border-light">
        <span className="text-xs text-v2-text-muted font-mono">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-v2-text-muted hover:text-v2-text-secondary transition-colors"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="bg-v2-code-bg p-4 overflow-x-auto">
        <code className="text-sm font-mono leading-relaxed text-v2-text-primary">{code}</code>
      </pre>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/cscode/web/src/components/markdown/CodeBlock.tsx
git commit -m "feat(gui): add CodeBlock with copy button"
```

---

## Phase 5: Settings & Polish

### Task 19: Build SettingsPanel

**Files:**
- Create: `src/cscode/web/src/components/ui/SettingsPanel.tsx`
- Delete (later): `src/cscode/web/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Create SettingsPanel.tsx**

```tsx
import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore, type Config } from '../../stores/useConfigStore';
import { themes } from '../../themes';

const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'custom', label: 'Custom' },
];

const MODELS: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'o1-mini', 'o3-mini'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3.5-sonnet', 'claude-3-opus'],
  gemini: ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-pro'],
  ollama: ['llama3', 'mistral', 'codellama', 'qwen2.5-coder', 'deepseek-coder'],
};

export function SettingsPanel() {
  const setSettingsOpen = useUIStore((s) => s.setSettingsOpen);
  const theme = useUIStore((s) => s.theme);
  const setTheme = useUIStore((s) => s.setTheme);

  const config = useConfigStore((s) => s.config);
  const setConfig = useConfigStore((s) => s.setConfig);

  const [form, setForm] = useState<Config>({
    provider: 'openai',
    model: 'gpt-4o',
    api_base: null,
    api_key: '',
    max_tokens: 4096,
    temperature: 0.3,
    top_p: 1,
    system_prompt: null,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (config) setForm(config);
  }, [config]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setConfig(form);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch (e) {
      console.error('Failed to save config', e);
    } finally {
      setSaving(false);
    }
  };

  const models = MODELS[form.provider as keyof typeof MODELS] || MODELS.openai;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={() => setSettingsOpen(false)} />
      <div className="relative w-96 bg-v2-bg-base border-l border-v2-border h-full overflow-y-auto shadow-v2-overlay">
        <div className="flex items-center justify-between p-4 border-b border-v2-border">
          <h2 className="text-sm font-semibold text-v2-text-primary">Settings</h2>
          <button onClick={() => setSettingsOpen(false)} className="text-v2-text-muted hover:text-v2-text-primary transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Provider */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Provider</label>
            <select
              value={form.provider}
              onChange={(e) => setForm({ ...form, provider: e.target.value, model: '' })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {form.provider === 'custom' && (
            <div>
              <label className="block text-xs font-medium text-v2-text-secondary mb-1">Custom Provider Name</label>
              <input
                type="text"
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
                className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
              />
            </div>
          )}

          {/* Model */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Model</label>
            <select
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            >
              {form.provider === 'custom' ? (
                <option value={form.model}>{form.model || 'Enter model name'}</option>
              ) : (
                models.map((m) => <option key={m} value={m}>{m}</option>)
              )}
            </select>
          </div>

          {/* API Base URL */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">API Base URL</label>
            <input
              type="text"
              value={form.api_base || ''}
              onChange={(e) => setForm({ ...form, api_base: e.target.value || null })}
              placeholder="https://api.openai.com"
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary placeholder-v2-text-muted"
            />
          </div>

          {/* API Key */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">API Key</label>
            <input
              type="password"
              value={form.api_key || ''}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            />
          </div>

          {/* Temperature */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">
              Temperature ({form.temperature})
            </label>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={form.temperature}
              onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) })}
              className="w-full accent-v2-accent"
            />
          </div>

          {/* Max Tokens */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Max Tokens</label>
            <input
              type="number"
              value={form.max_tokens}
              onChange={(e) => setForm({ ...form, max_tokens: parseInt(e.target.value) || 4096 })}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            />
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">System Prompt</label>
            <textarea
              value={form.system_prompt || ''}
              onChange={(e) => setForm({ ...form, system_prompt: e.target.value || null })}
              rows={4}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary resize-none"
            />
          </div>

          {/* Theme */}
          <div>
            <label className="block text-xs font-medium text-v2-text-secondary mb-1">Theme</label>
            <select
              value={theme}
              onChange={(e) => setTheme(e.target.value as typeof theme)}
              className="w-full bg-v2-bg-deep border border-v2-border rounded-md px-3 py-1.5 text-sm text-v2-text-primary"
            >
              {themes.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full bg-v2-accent text-white py-2 rounded-md text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Delete old SettingsPanel**

```bash
rm src/cscode/web/src/components/SettingsPanel.tsx
```

- [ ] **Step 3: Commit**

```bash
git add src/cscode/web/src/components/ui/SettingsPanel.tsx
git rm src/cscode/web/src/components/SettingsPanel.tsx
git commit -m "feat(gui): add SettingsPanel with config form and theme selector"
```

---

### Task 20: Delete old Sidebar component

**Files:**
- Delete: `src/cscode/web/src/components/Sidebar.tsx`

- [ ] **Step 1: Delete old file**

```bash
rm src/cscode/web/src/components/Sidebar.tsx
```

- [ ] **Step 2: Verify app compiles**

Run: `cd src/cscode/web && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore(gui): remove old Sidebar component"
```

---

### Task 21: Add Tailwind animation config for ThinkingIndicator

**Files:**
- Modify: `src/cscode/web/tailwind.config.ts`

- [ ] **Step 1: Add keyframes for bounce animation**

```bash
# Create a tailwind.config.ts (or modify existing)
# No changes needed if Tailwind's default animate-bounce is used
```

The `animate-bounce` class is built into Tailwind CSS by default. No configuration needed.

- [ ] **Step 2: Verify dev server works**

Run:
```bash
cd src/cscode/web && npm run dev
```

Open `http://localhost:5173` in browser. Verify:
- Layout shell renders (Titlebar, Sidebar, Main Content)
- Theme is applied (dark background)
- Sidebar shows THREADS header with toolbar buttons
- Main content shows welcome message
- ModeToggle shows Plan/Build buttons

Expected: All components render with correct styling

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore(gui): verify layout renders correctly"
```

---

## Self-Review Checklist

1. **Spec coverage:** Every section in the design spec maps to at least one task:
   - Layout shell → Tasks 5-10
   - Theme system → Tasks 2, 4
   - Sidebar session management → Tasks 7, 8, 12
   - Chat experience → Tasks 13-16
   - Markdown & code → Tasks 17, 18
   - Settings panel → Task 19

2. **Placeholder check:** No TBD, TODO, or vague steps. Every step has exact code or command.

3. **Type consistency:** All component props, store fields, and API types use consistent naming:
   - Store: `useSessionStore`, `useConfigStore`, `useUIStore`
   - Types: `Session`, `Message`, `Config`, `Mode`, `ThemeId`
   - API: `api.sessions.list()`, `api.config.get()`, etc.

4. **Scope check:** Focused on GUI redesign only. No backend changes required.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-06-16-cscode-gui-redesign.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
