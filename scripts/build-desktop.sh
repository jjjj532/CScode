#!/bin/bash
set -e

# Full desktop build: frontend → bundle Python → Tauri .app → DMG
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Building cscode desktop app ==="

# Step 1: Build React frontend
echo ""
echo ">>> Step 1: Building React frontend..."
cd "$PROJECT_DIR/src/cscode/web"
npm ci 2>/dev/null || true
npx vite build

# Step 2: Copy frontend to Tauri resource dirs
echo ""
echo ">>> Step 2: Copying frontend to Tauri dirs..."
rm -rf "$PROJECT_DIR/desktop/dist" "$PROJECT_DIR/desktop/src-tauri/web-dist"
mkdir -p "$PROJECT_DIR/desktop/dist" "$PROJECT_DIR/desktop/src-tauri/web-dist"
cp -r "$PROJECT_DIR/src/cscode/web/dist/"* "$PROJECT_DIR/desktop/dist/"
cp -r "$PROJECT_DIR/src/cscode/web/dist/"* "$PROJECT_DIR/desktop/src-tauri/web-dist/"

# Step 3: Bundle Python source into Tauri resources
echo ""
echo ">>> Step 3: Bundling Python source..."
rm -rf "$PROJECT_DIR/desktop/src-tauri/python"
mkdir -p "$PROJECT_DIR/desktop/src-tauri/python"
# Copy only Python files and exclude web frontend source (node_modules is too large)
cd "$PROJECT_DIR/src"
find cscode -path '*/web/dist' -prune -o -path '*/node_modules' -prune -o -type f \( -name '*.py' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' \) -print | cpio -pdm "$PROJECT_DIR/desktop/src-tauri/python/" 2>/dev/null || true
# Copy web/dist separately (needed by the server for file serving)
mkdir -p "$PROJECT_DIR/desktop/src-tauri/python/cscode/web"
cp -r "$PROJECT_DIR/src/cscode/web/dist" "$PROJECT_DIR/desktop/src-tauri/python/cscode/web/"
# Clean up __pycache__
find "$PROJECT_DIR/desktop/src-tauri/python" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
echo "Python source bundled at desktop/src-tauri/python/"
du -sh "$PROJECT_DIR/desktop/src-tauri/python/"

# Step 3b: Install pip dependencies into bundled Python (for Tauri system python3)
echo ""
echo ">>> Step 3b: Installing pip dependencies into bundled Python..."
pip install --target="$PROJECT_DIR/desktop/src-tauri/python" python-multipart 2>&1 | tail -3
echo "python-multipart installed to bundled Python"

# Step 4: Build Tauri .app
echo ""
echo ">>> Step 4: Building Tauri .app..."
cd "$PROJECT_DIR/desktop"
npm ci 2>/dev/null || true
npx tauri build --bundles app

# Step 5: Create DMG from the .app
echo ""
echo ">>> Step 5: Creating DMG..."
APP_PATH="$PROJECT_DIR/desktop/src-tauri/target/release/bundle/macos/CScode.app"
DMG_DIR="$PROJECT_DIR/desktop/src-tauri/target/release/bundle/dmg"
mkdir -p "$DMG_DIR"

# Ensure web-dist is in the .app Resources
if [ ! -d "$APP_PATH/Contents/Resources/web-dist" ]; then
    mkdir -p "$APP_PATH/Contents/Resources/web-dist"
    cp -r "$PROJECT_DIR/src/cscode/web/dist/"* "$APP_PATH/Contents/Resources/web-dist/"
fi

# Ensure python is in the .app Resources
if [ ! -d "$APP_PATH/Contents/Resources/python" ]; then
    mkdir -p "$APP_PATH/Contents/Resources/python"
    cp -r "$PROJECT_DIR/desktop/src-tauri/python/"* "$APP_PATH/Contents/Resources/python/"
fi

# Create DMG staging
STAGING="/tmp/cscode-dmg-$$"
mkdir -p "$STAGING"
cp -rf "$APP_PATH" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

VERSION=$(grep '"version"' "$PROJECT_DIR/desktop/src-tauri/tauri.conf.json" | cut -d'"' -f4)
DMG_FILE="$DMG_DIR/CScode_${VERSION}_x64.dmg"
hdiutil create -volname "CScode" -srcfolder "$STAGING" -ov -format UDZO -imagekey zlib-level=9 "$DMG_FILE"
rm -rf "$STAGING"

echo ""
echo "=== Build complete ==="
echo ".app: $APP_PATH"
echo ".dmg: $DMG_FILE"
