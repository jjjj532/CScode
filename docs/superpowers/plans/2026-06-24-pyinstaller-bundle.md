# PyInstaller Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task.

**Goal:** Bundle Python runtime + all dependencies into a single binary using PyInstaller, making CScode desktop app truly self-contained.

**Architecture:** A new `desktop/backend-server.py` entry point is compiled by PyInstaller → `cscode-backend` binary. Tauri's lib.rs launches this binary directly instead of discovering system Python. web/dist is embedded in the binary via `--add-data`. Playwright Python package + Node driver are bundled; Chromium downloads on first use.

**Tech Stack:** PyInstaller, Tauri (Rust), Python, FastAPI/Uvicorn

---

## File Changes

| File | Action | Purpose |
|------|--------|---------|
| `desktop/backend-server.py` | **Create** | PyInstaller entry point: parse args, start uvicorn |
| `desktop/src-tauri/src/lib.rs` | **Modify** | Launch `cscode-backend` binary instead of `python3 -m cscode server` |
| `desktop/src-tauri/tauri.conf.json` | **Modify** | Resources glob: `resources/cscode-backend*` + `resources/web-dist/**/*` |
| `.github/workflows/build.yml` | **Modify** | Add PyInstaller build step, remove site-packages.zip + python/ steps |
| `scripts/build-desktop.sh` | **Modify** | Add local PyInstaller build step |
| `src/cscode/__init__.py` | **Modify** | Version 0.3.0 |
| `src/cscode/server/app.py` | **Modify** | Version 0.3.0 |
| `src/cscode/mcp/client.py` | **Modify** | Version 0.3.0 |
| `src/cscode/mcp/server.py` | **Modify** | Version 0.3.0 |
| `desktop/src-tauri/Cargo.toml` | **Modify** | Version 0.3.0 |
| `scripts/build.sh` | **Modify** | Version 0.3.0 |

---

### Task 1: Create branch and entry point

- [ ] Create branch `pyinstaller-bundle` from main
- [ ] Create `desktop/backend-server.py`:

```python
"""PyInstaller entry point for CScode backend server.

Compiled by PyInstaller into a standalone binary.
Usage: cscode-backend --port 8080 --host 127.0.0.1
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="CScode Backend Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    # Import triggers all tool registrations via the lifespan
    from cscode.server.app import app
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
```

### Task 2: Test backend-server.py locally

- [ ] Verify it can import and start:
  ```bash
  source .venv/bin/activate
  python3 desktop/backend-server.py --port 19999 --host 127.0.0.1 &
  sleep 3
  curl -s http://127.0.0.1:19999/api/health
  kill %1
  ```
- [ ] Verify health endpoint returns 200

### Task 3: Build PyInstaller binary and test

- [ ] Install PyInstaller: `pip install pyinstaller`
- [ ] Build: `pyinstaller --onefile --name cscode-backend --add-data "src/cscode/web/dist:web/dist" desktop/backend-server.py --clean --noconfirm`
- [ ] Test the binary:
  ```bash
  CSCODE_API_KEY=test dist/cscode-backend --port 19998 --host 127.0.0.1 &
  sleep 5
  curl -s http://127.0.0.1:19998/api/health
  kill %1
  ```
- [ ] Verify health endpoint returns 200

### Task 4: Update lib.rs

- [ ] Modify `desktop/src-tauri/src/lib.rs`:
  - In `start()` method, check for `resources/cscode-backend` (or `cscode-backend.exe` on Windows)
  - Launch directly with `Command::new(binary_path).args(["--port", &port_str, "--host", "127.0.0.1"])`
  - Keep `PATH` env (for Chromium discovery by Playwright)
  - Keep `CSCODE_API_KEY` env var
  - Remove PYTHONPATH setup (not needed with PyInstaller)
  - Remove Python discovery logic
  - Fall back to old behavior (find python3) if binary not found (safe migration)

### Task 5: Update tauri.conf.json

- [ ] Change resources from `"resources/**/*"` to include both the binary and web-dist:
  ```json
  "resources": [
    "resources/cscode-backend*",
    "resources/web-dist/**/*"
  ]
  ```

### Task 6: Update CI build.yml

- [ ] After Python venv + playwright install step, add PyInstaller build:
  ```yaml
  - name: Build PyInstaller binary
    run: |
      pip install pyinstaller
      pyinstaller --onefile --name cscode-backend \
        --add-data "src/cscode/web/dist:web/dist" \
        desktop/backend-server.py --clean --noconfirm
      mkdir -p desktop/src-tauri/resources
      cp dist/cscode-backend* desktop/src-tauri/resources/
  ```
- [ ] Remove old `Bundle Python deps as site-packages.zip` step
- [ ] Remove old `Bundle cscode source + web/dist` step
- [ ] Update resource validation to check for `cscode-backend*`

### Task 7: Update build-desktop.sh

- [ ] Add PyInstaller step before `npx tauri build`:
  ```bash
  pip install pyinstaller
  pyinstaller --onefile --name cscode-backend \
    --add-data "src/cscode/web/dist:web/dist" \
    desktop/backend-server.py --clean --noconfirm
  cp dist/cscode-backend* desktop/src-tauri/resources/
  ```

### Task 8: Update version to 0.3.0

- [ ] All 7 locations: `0.2.99` → `0.3.0`

### Task 9: Push, tag, CI test

- [ ] Commit all changes with message "feat: bundle Python backend via PyInstaller (v0.3.0)"
- [ ] Push branch
- [ ] Create tag v0.3.0-rc1
- [ ] Monitor CI
- [ ] Verify artifacts
- [ ] Report results to user
