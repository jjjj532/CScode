#!/usr/bin/env bash
# CScode macOS Desktop DMG Build Script
# Builds the Tauri desktop app and packages it as a DMG
# Usage: ./scripts/build-desktop.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== CScode Desktop DMG Build ==="
echo "Root: $ROOT"

# --- Git status check: ensure clean working directory ---
echo ""
echo "=== Git status check ==="
if [ -d "$ROOT/.git" ]; then
    cd "$ROOT"
    # Check for uncommitted changes
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        echo "ERROR: You have uncommitted changes. Commit or stash before building."
        echo ""
        echo "Uncommitted changes:"
        git status --short
        exit 1
    fi
    
    # Check if branch is ahead of remote
    LOCAL_HEAD=$(git rev-parse HEAD)
    if git rev-parse @{u} >/dev/null 2>&1; then
        REMOTE_HEAD=$(git rev-parse @{u})
        if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
            echo "WARNING: Local commits not pushed to remote."
            echo "  Local:  $LOCAL_HEAD"
            echo "  Remote: $REMOTE_HEAD"
            echo "  Commit(s) ahead: $(git rev-list --count @{u}..HEAD)"
            echo ""
            echo "Push before building? (y/n)"
            read -r confirm
            if [ "$confirm" != "y" ]; then
                echo "Aborting build."
                exit 1
            fi
        fi
    fi
    
    echo "Git status OK - working directory is clean"
    echo "Current commit: $(git rev-parse --short HEAD)"
    echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
else
    echo "WARNING: Not a git repository, skipping git check"
fi

# Activate venv if exists
if [ -f "$ROOT/.venv/bin/activate" ]; then
    source "$ROOT/.venv/bin/activate"
fi

# --- Pre-build cleanup (from AGENTS.md) ---
echo ""
echo "=== Pre-build cleanup ==="
diskutil unmount force /Volumes/CScode* 2>/dev/null || true
rm -rf /Applications/CScode.app
rm -rf desktop/src-tauri/target
rm -rf desktop/src-tauri/.dmg-background
rm -rf desktop/dist
rm -rf desktop/src-tauri/web-dist
rm -rf desktop/src-tauri/python
rm -f dist/*.dmg dist/cscode-desktop
echo "Cleanup done"

# --- Build Tauri frontend dist (spinner page) ---
echo ""
echo "=== Create Tauri frontend dist ==="
mkdir -p desktop/dist
cat > desktop/dist/index.html << 'HTML'
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/><title>CScode</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#f5f5f5;display:flex;align-items:center;justify-content:center;height:100vh;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;opacity:1;transition:opacity .2s ease}body.fade-out{opacity:0}.spinner{width:28px;height:28px;border:3px solid #ddd;border-top-color:#646cff;border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}</style></head><body><div class="spinner"></div></body></html>
HTML
echo "Spinner page created"

# --- Build React frontend ---
echo ""
echo "=== Build React frontend ==="
if [ -f "src/cscode/web/package.json" ]; then
    cd src/cscode/web
    npm ci --silent 2>/dev/null || npm ci
    npx vite build
    cd "$ROOT"
    echo "React frontend built"
else
    echo "WARNING: web/package.json not found, skipping React build"
fi

# --- Python backend build (resources) ---
echo ""
echo "=== Build Python backend resources ==="
mkdir -p desktop/src-tauri/resources
rm -rf desktop/src-tauri/resources/*

# Install to temp dir and zip
TMP_PYTHON="$ROOT/build/python-resources"
rm -rf "$TMP_PYTHON"
mkdir -p "$TMP_PYTHON"

pip install --target="$TMP_PYTHON" --quiet "$ROOT" 2>&1 | tail -2

# Clean up cache and compile artifacts
find "$TMP_PYTHON" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$TMP_PYTHON" -name "*.pyc" -delete
rm -rf "$TMP_PYTHON/bin" 2>/dev/null || true

# Copy source code
mkdir -p "$TMP_PYTHON/python/cscode"
cp -r "$ROOT/src/cscode/" "$TMP_PYTHON/python/cscode/"
rm -rf "$TMP_PYTHON/python/cscode/web" 2>/dev/null || true

# Copy web dist into python resources
if [ -d "$ROOT/src/cscode/web/dist" ]; then
    cp -r "$ROOT/src/cscode/web/dist" "$TMP_PYTHON/python/cscode/web/"
fi

# Copy dependencies to python_deps/ directory (not zip — native .so can't load from zip)
mkdir -p "$ROOT/desktop/src-tauri/resources/python_deps"
cp -r "$TMP_PYTHON/"* "$ROOT/desktop/src-tauri/resources/python_deps/"
rm -rf "$ROOT/desktop/src-tauri/resources/python_deps/python" 2>/dev/null || true

# Copy python source separately
mkdir -p "$ROOT/desktop/src-tauri/resources/python"
cp -r "$TMP_PYTHON/python/cscode" "$ROOT/desktop/src-tauri/resources/python/"
rm -rf "$ROOT/desktop/src-tauri/resources/python/cscode/web/dist" 2>/dev/null || true
if [ -d "$ROOT/src/cscode/web/dist" ]; then
    cp -r "$ROOT/src/cscode/web/dist" "$ROOT/desktop/src-tauri/resources/python/cscode/web/"
fi

# Cleanup
rm -rf "$TMP_PYTHON"
cd "$ROOT"

echo "Python resources ready:"
du -sh desktop/src-tauri/resources/python_deps/ desktop/src-tauri/resources/python/

# --- Build Tauri app ---
echo ""
echo "=== Build Tauri app ==="
cd desktop
npm ci --silent 2>/dev/null || npm ci
npx tauri build --verbose --bundles app
cd "$ROOT"

# --- Create DMG ---
echo ""
echo "=== Create DMG ==="
APP_PATH="desktop/src-tauri/target/release/bundle/macos/CScode.app"
DMG_DIR="dist"
mkdir -p "$DMG_DIR"

if [ -d "$APP_PATH" ]; then
    STAGING="/tmp/cscode-dmg-$$"
    mkdir -p "$STAGING"
    cp -rf "$APP_PATH" "$STAGING/"
    ln -s /Applications "$STAGING/Applications"
    
    VERSION=$(grep '"version"' desktop/src-tauri/tauri.conf.json | head -1 | cut -d'"' -f4)
    ARCH=$(uname -m)
    DMG_NAME="CScode_${VERSION}_${ARCH}.dmg"
    
    rm -f "$DMG_DIR/$DMG_NAME"
    hdiutil create -volname "CScode" -srcfolder "$STAGING" -ov -format UDZO -imagekey zlib-level=9 "$DMG_DIR/$DMG_NAME"
    rm -rf "$STAGING"
    
    echo "DMG created: $DMG_DIR/$DMG_NAME ($(du -sh "$DMG_DIR/$DMG_NAME" | cut -f1))"
else
    echo "ERROR: App bundle not found at $APP_PATH"
    echo "Build may have failed"
    exit 1
fi

echo ""
echo "=== Build complete ==="
echo "DMG: $DMG_DIR/$DMG_NAME"
