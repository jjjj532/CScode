# CScode GUI Redesign — Pixel-perfect OpenCode Replica

## Overview

Rewrite `src/cscode/web/` from a bare-bones React + inline-style app to a full-featured GUI that pixel-perfectly replicates OpenCode v1.17's desktop web UI. Uses React + TypeScript + Vite + Tailwind CSS, with Zustand for state management.

## Architecture

### Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React 18 | Already in use, largest ecosystem |
| Language | TypeScript 5.5 | Already in use |
| Build | Vite 5 | Already in use |
| CSS | Tailwind CSS 3 | Pixel-level control, utility-first, matches OpenCode approach |
| State | Zustand | Precise re-renders, low boilerplate, replaces bloated Context |
| Markdown | react-markdown + rehype-highlight | Standard rendering pipeline |
| Icons | lucide-react | Same icon set OpenCode uses (or close alternative) |

### Directory Structure

```
src/cscode/web/
├── index.html
├── package.json               # + tailwindcss, postcss, zustand, lucide-react, etc.
├── tailwind.config.ts
├── postcss.config.js
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── App.tsx                 # Root layout container
    ├── index.css               # Tailwind directives + CSS custom properties
    ├── types.ts
    ├── stores/
    │   ├── useSessionStore.ts  # sessions, messages, activeSessionId
    │   ├── useConfigStore.ts   # provider, model, api settings
    │   └── useUIStore.ts       # theme, mode (plan/build), sidebar, panels
    ├── hooks/
    │   ├── useChat.ts          # SSE stream -> message store
    │   └── useTheme.ts         # CSS variable swapping
    ├── lib/
    │   ├── api.ts              # typed fetch wrappers
    │   └── markdown.ts         # remark/rehype plugins config
    ├── components/
    │   ├── layout/
    │   │   ├── Titlebar.tsx
    │   │   ├── Sidebar.tsx
    │   │   └── MainContent.tsx
    │   ├── sidebar/
    │   │   ├── ThreadsHeader.tsx
    │   │   ├── ProjectList.tsx
    │   │   └── ProjectItem.tsx
    │   ├── chat/
    │   │   ├── MessageList.tsx
    │   │   ├── Message.tsx
    │   │   ├── Composer.tsx
    │   │   └── ThinkingIndicator.tsx
    │   ├── markdown/
    │   │   ├── MarkdownRenderer.tsx
    │   │   └── CodeBlock.tsx
    │   └── ui/
    │       ├── ToolCallDisplay.tsx
    │       ├── ModeToggle.tsx
    │       ├── SettingsPanel.tsx
    │       └── ThemeProvider.tsx
    └── themes/
        └── index.ts            # 6 preset themes as CSS variable maps
```

### State Management (Zustand)

Three stores with no overlapping responsibilities:

- **useSessionStore**: `sessions[]`, `messages[]`, `activeSessionId`, `loadSessions()`, `sendMessage()`, `deleteSession()`
- **useConfigStore**: `provider`, `model`, `apiBase`, `apiKey`, `temperature`, `maxTokens`, `systemPrompt`
- **useUIStore**: `theme`, `mode` (plan|build), `sidebarOpen`, `settingsOpen`, `attachedFiles`

### Data Flow

```
User types in Composer → enter
  → sendMessage() in useChat hook
  → POST /api/chat/stream (FormData with text + attachments)
  → SSE stream parsed:
      - "session" → set sessionId
      - "thinking" → show thinking indicator
      - "tool:start" → append ToolCallDisplay
      - "tool:complete" → update tool result
      - "file_created" → fetch download URL
      - "complete" → append final Message
  → MessageList re-renders via Zustand selector
  → MarkdownRenderer renders content
```

## Component Specifications

### 1. Layout Shell

```
┌─────────────────────────────────────────────────┐
│ Titlebar                                         │
│  [🐚 CScode] — [~/project]    [● Plan] [—] [✕] │
├──────────┬──────────────────────────────────────┤
│ Sidebar  │ MainContent                          │
│ (256px)  │ ┌──────────────────────────────────┐ │
│          │ │ MessageList                      │ │
│ Threads  │ │  • User bubble (right, accent)   │ │
│ [🔍↕👁️+] │ │  • Assistant bubble (left)      │ │
│          │ │  • Markdown / code / tool calls  │ │
│ 📁 proj  │ │                                   │ │
│  💬 ses1 │ └──────────────────────────────────┘ │
│  💬 ses2 │ ┌──────────────────────────────────┐ │
│ 📁 proj2 │ │ Composer                         │ │
│          │ │ [📎] Ask something...    [▶]     │ │
│ ⚙️  ❓   │ └──────────────────────────────────┘ │
└──────────┴──────────────────────────────────────┘
```

### 2. Titlebar

- Height: ~40px
- Dark background (`bg-v2-background-bg-deep`)
- Left: App icon/name + project directory path
- Right: Plan/Build mode badge + window controls (minimize/maximize/close)
- Mode badge is clickable — switches between Plan (blue) and Build (green)

### 3. Sidebar (Unified, 256px)

- "THREADS" header with toolbar: Filter (🔍), Sort (↕), View (👁️), Add Project (＋)
- Projects displayed as expandable folder rows
  - Chevron (▶/▼) + folder icon + project name
  - Click chevron to expand/collapse sub-items
- Sessions appear as sub-items under their project (💬 icon)
- Workspaces can nest further under projects
- Active session highlighted with background color
- Bottom: Settings (⚙️) and Help (❓) links
- Smooth collapse/expand animations
- Drag-and-drop reordering (future)

### 4. MainContent

- Rounded corners (`rounded-[10px]`) with elevation shadow
- Outer background (`bg-v2-background-bg-deep`), inner background (`bg-v2-background-bg-base`)
- Contains MessageList (scrollable) + Composer (fixed bottom)

### 5. MessageList & Message

- Messages rendered in reverse-chronological order (newest at bottom, auto-scroll)
- **User messages**: Right-aligned, accent-colored background, "You" label
- **Assistant messages**: Left-aligned, neutral background, "CScode" label with accent color
- **Thinking indicator**: Animated pulse/ellipsis while waiting for response
- Each message content goes through MarkdownRenderer

### 6. MarkdownRenderer & CodeBlock

- Uses `react-markdown` + `rehype-highlight` for code syntax highlighting
- Code blocks: Dark background (`#111`), header shows language + copy button
- Inline code: Subtle background highlight
- Tables, lists, headings, links all properly styled
- Image attachments rendered inline
- Copy-to-clipboard button on code blocks

### 7. Composer

- Text input with placeholder "Ask anything or @mention a file..."
- 📎 Attach file button (triggers Tauri dialog or browser file input)
- Attached files shown as removable tags above input
- @mention autocomplete (fuzzy file search via `/api/files/search`)
- Send button (▶) or Stop button (■) while loading
- Footer bar: Model name + shortcut hints

### 8. ToolCallDisplay

- Appears inline in message flow (not as separate messages)
- Shows: tool icon + tool name + target file/URL
- States: running (spinner), completed (green check), failed (red X)
- Expandable: click to show full tool output

### 9. ModeToggle (Plan/Build)

- Toggle switch (pill/segmented control)
- **Plan mode**: Blue accent, read-only agent, "Read-only · no file changes"
- **Build mode**: Green accent, full-access agent, "Full access · can edit files"
- Keyboard shortcut: Tab (as in OpenCode)
- Visual indicator in Titlebar + StatusBar

### 10. SettingsPanel

- Slide-out panel from right (overlay, ~400px)
- Sections:
  - Provider selection (dropdown)
  - Custom provider name (if "custom" selected)
  - Model selection (dynamic based on provider)
  - API Base URL (text input)
  - API Key (password input)
  - Temperature (slider 0-2)
  - Max Tokens (number input)
  - System Prompt (textarea)
- Save button at bottom
- Close via ✕ button or click outside

### 11. Theme System

- CSS custom properties scoped to `:root` via class on `<html>`
- 7 categories of CSS variables:
  - `--bg-deep`, `--bg-base`, `--bg-surface` — backgrounds
  - `--text-primary`, `--text-secondary`, `--text-muted` — text
  - `--accent-primary`, `--accent-secondary` — accent colors
  - `--border`, `--border-light` — borders
  - `--elevation-raised`, `--elevation-overlay` — shadows
  - `--msg-user-bg`, `--msg-assistant-bg` — message bubbles
  - `--code-bg`, `--code-header` — code blocks
- 6 presets: `opencode-dark`, `opencode-light`, `catppuccin`, `dracula`, `github-dark`, `github-light`
- Theme selector in Settings panel

## Build Integration

### Development
```bash
# Terminal 1: Python backend
cd /Users/mac/AI/CScode && source .venv/bin/activate && python3 -m cscode server --port 8080

# Terminal 2: Vite dev server (proxy /api -> backend)
cd src/cscode/web && npm run dev    # -> http://localhost:5173
```

### Production (Tauri Bundle)
```bash
# 1. Build frontend
cd src/cscode/web && npm run build    # -> dist/
cp -r dist/ ../../desktop/src-tauri/web-dist/

# 2. Build Tauri
cd desktop && npm run build

# Tauri points to Python server at http://127.0.0.1:8080 which serves the SPA
```

### Vite Config
- Dev: proxy `/api` to `http://localhost:8080`
- Build: output to `dist/`, base path `/`

## Implementation Phases

### Phase 1 — Foundation + Shell
- Add Tailwind CSS + PostCSS + Zustand + lucide-react to web/package.json
- Create `index.css` with Tailwind directives + CSS variable theme system
- Create all 3 Zustand stores
- Build Layout shell: Titlebar, Sidebar, MainContent
- Build ModeToggle
- Build ThemeProvider with 6 themes
- **Verify**: App renders with correct layout, theme switching works

### Phase 2 — Session Management
- Build Sidebar sub-components: ThreadsHeader, ProjectList, ProjectItem
- Connect to `/api/sessions` endpoints
- Session CRUD (create, list, switch, delete)
- **Verify**: Can create/switch/delete sessions via Sidebar

### Phase 3 — Chat Experience
- Build MessageList, Message, Composer, ThinkingIndicator
- Build useChat hook (SSE streaming via fetch ReadableStream)
- Build ToolCallDisplay
- **Verify**: Can send messages, see streaming responses, see tool calls

### Phase 4 — Markdown & Code
- Build MarkdownRenderer, CodeBlock
- Syntax highlighting with rehype-highlight
- Copy button, image rendering, table styling
- **Verify**: Code blocks are syntax-highlighted, Markdown renders correctly

### Phase 5 — Settings & Polish
- Build SettingsPanel with all config fields
- Connect to `/api/config` endpoints
- Keyboard shortcuts (@mention, Tab for mode, Cmd+K)
- Composer @mention autocomplete
- **Verify**: Settings save/load, keyboard shortcuts work

## Implementation Approach

**Shell-first, incremental replacement** (Approach 3):
1. Phase 1 builds the new layout shell around the existing `App.tsx` content
2. Each subsequent phase replaces one section of the old code with the new component
3. Old `App.tsx`, `Sidebar.tsx`, `SettingsPanel.tsx` are deleted when their replacements are complete
4. This ensures the app stays functional throughout the rewrite

## Acceptance Criteria

1. Layout pixel-matches OpenCode v1.17 desktop web UI
2. All 6 themes render correctly with no hardcoded colors
3. Chat messages stream via SSE with real-time updates
4. Code blocks syntax-highlighted with copy button
5. Sidebar shows sessions grouped by project
6. Plan/Build mode toggle works (changes agent behavior)
7. Settings panel saves/loads provider configuration
8. File attachments work via Tauri dialog
9. Composer @mention shows file suggestions
10. Tool execution visible inline in message flow
11. Keyboard shortcuts: Tab (mode), @ (mention), Enter (send)
