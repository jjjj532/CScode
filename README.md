# CScode — AI Coding Assistant

AI-powered coding assistant with CLI, TUI, web UI, and desktop app. Supports OpenAI, Anthropic, Ollama, Gemini, Azure, and OpenRouter.

## Features

- Multi-provider LLM support (OpenAI, Anthropic, Ollama, Gemini, Azure, OpenRouter)
- Interactive CLI, Terminal UI (Textual), Web UI, and Desktop app (Tauri)
- Tool system: read, write, edit, bash, grep, glob, ls, web fetch/search, git, LSP, browser automation
- Multi-session management with SQLite persistence
- Plugin/SDK system and skill system
- MCP (Model Context Protocol) client and server
- Session sharing and enterprise features (remote config, policies, audit)

## Quick Start

```bash
pip install -e .
cs
```

Set your API key:

```bash
# OpenAI
cs config set --global OPENAI_API_KEY sk-...
# or Anthropic
cs config set --global ANTHROPIC_API_KEY sk-ant-...
```

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 22+
- Rust (for desktop app)
- Playwright browsers (for browser tool)

### Python Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test,dev]"
```

Install Playwright browsers:

```bash
playwright install chromium
```

Run tests:

```bash
pytest
```

### React Web UI

```bash
cd src/cscode/web
npm ci
npm run dev        # dev server at localhost:5173
npm run build      # production build
npm test           # unit tests
npm run test:e2e   # Playwright E2E tests
```

### Tauri Desktop App

```bash
cd desktop
npm ci
npm run tauri dev    # development window
npm run tauri build  # production bundle
```

### Code Quality

```bash
ruff check src/
mypy src/
npx tsc --noEmit -p src/cscode/web
```

### CLI Commands

```bash
cs chat             # Start interactive chat
cs review           # Review git changes
cs tui              # Terminal UI
cs server           # Start web server
cs web              # Open web UI
cs desktop          # Launch desktop app
cs config           # Configuration
cs session          # Session management
```

## Building Installers

### Local macOS Desktop

```bash
bash scripts/build-desktop.sh
# Output: dist/CScode_*.dmg
```

### CLI Binary (PyInstaller)

```bash
bash scripts/build.sh macos    # macOS
bash scripts/build.sh linux    # Linux
bash scripts/build.sh windows  # Windows
```

### CI (GitHub Actions)

Push a `v*` tag to trigger automatic multi-platform builds:

```bash
git tag v0.2.99 && git push origin v0.2.99
```

Builds for macOS (DMG), Linux (DEB), and Windows (NSIS) are published to GitHub Releases.

## Project Structure

```
src/cscode/          # Python package
  cli.py             # CLI entry point
  core/              # Engine, config, sessions, agents
  tools/             # Tool implementations
  server/            # FastAPI web server
  web/               # React frontend (Vite + TS + Tailwind)
  tui/               # Textual terminal UI
  providers/         # LLM providers
  mcp/               # MCP client/server
  plugins/           # Plugin system
  skills/            # Skill system
desktop/             # Tauri v2 desktop app
  src-tauri/         # Rust code + app config
tests/               # Python tests
scripts/             # Build scripts
docs/                # Documentation
openspec/            # Specifications
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure tests pass: `pytest`
5. Run linting: `ruff check src/`
6. Submit a pull request

## Version

Current version: 0.3.3

When bumping version, update all files listed in `AGENTS.md`.
