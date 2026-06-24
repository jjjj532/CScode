#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_PATH="$PROJECT_DIR/desktop/src-tauri/target/release/bundle/macos/CScode.app"
DMG_DIR="$PROJECT_DIR/desktop/src-tauri/target/release/bundle/dmg"

create_dmg() {
  echo ""
  echo ">>> Step 5: Creating DMG..."
  if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: .app not found at $APP_PATH"
    exit 1
  fi
  mkdir -p "$DMG_DIR"

  rm -rf "$APP_PATH/Contents/Resources/web-dist"
  mkdir -p "$APP_PATH/Contents/Resources/web-dist"
  cp -r "$PROJECT_DIR/src/cscode/web/dist/"* "$APP_PATH/Contents/Resources/web-dist/"

  rm -rf "$APP_PATH/Contents/Resources/cscode-backend"
  mkdir -p "$APP_PATH/Contents/Resources/cscode-backend"
  cp -r "$PROJECT_DIR/desktop/src-tauri/resources/cscode-backend/"* "$APP_PATH/Contents/Resources/cscode-backend/"

  STAGING="/tmp/cscode-dmg-$$"
  mkdir -p "$STAGING"
  cp -rf "$APP_PATH" "$STAGING/"
  ln -s /Applications "$STAGING/Applications"

  VERSION=$(grep '"version"' "$PROJECT_DIR/desktop/src-tauri/tauri.conf.json" | cut -d'"' -f4)
  DMG_FILE="$DMG_DIR/CScode_${VERSION}_x64.dmg"
  rm -f "$DMG_FILE"
  hdiutil create -volname "CScode" -srcfolder "$STAGING" -ov -format UDZO -imagekey zlib-level=9 -fs HFS+ "$DMG_FILE"
  rm -rf "$STAGING"

  echo ""
  echo ">>> Step 6: Copying artifacts to dist/..."
  mkdir -p "$PROJECT_DIR/dist"
  cp "$DMG_FILE" "$PROJECT_DIR/dist/"
  echo "DMG copied to $PROJECT_DIR/dist/$(basename "$DMG_FILE")"
  BINARY="$PROJECT_DIR/desktop/src-tauri/target/release/cscode-desktop"
  if [ -f "$BINARY" ]; then
    cp "$BINARY" "$PROJECT_DIR/dist/cscode-desktop"
    echo "Binary copied to $PROJECT_DIR/dist/cscode-desktop"
  fi

  echo ""
  echo "=== Build complete ==="
  echo ".app: $APP_PATH"
  echo ".dmg: $DMG_FILE"
  echo "dist: $PROJECT_DIR/dist/$(basename "$DMG_FILE")"
}

# ==== Entry ====

echo "=== Building cscode desktop app ==="

# Step 0: Clean stale DMG mounts
echo ""
echo ">>> Step 0: Cleaning up stale DMG images..."
for img in $(hdiutil info 2>/dev/null | grep -E "^/dev/disk" | awk '{print $1}' | sort -u); do
  hdiutil detach -force "$img" 2>/dev/null || true
done
rm -rf /tmp/cscode-dmg-* /tmp/dmgcheck 2>/dev/null || true

# --only-dmg: skip frontend + Rust, just repack .app → DMG
if [ "${1:-}" = "--only-dmg" ]; then
  echo "  --only-dmg mode: skipping frontend + Rust build"
  create_dmg
  exit 0
fi

# Step 1: Build React frontend
echo ""
echo ">>> Step 1: Building React frontend..."
cd "$PROJECT_DIR/src/cscode/web"
npm install 2>&1 | tail -3
npx vite build

# Step 2: Copy frontend to Tauri resource dirs
echo ""
echo ">>> Step 2: Copying frontend to Tauri dirs..."
rm -rf "$PROJECT_DIR/desktop/dist" "$PROJECT_DIR/desktop/src-tauri/web-dist"
mkdir -p "$PROJECT_DIR/desktop/dist" "$PROJECT_DIR/desktop/src-tauri/web-dist"
cp -r "$PROJECT_DIR/src/cscode/web/dist/"* "$PROJECT_DIR/desktop/src-tauri/web-dist/"
cat > "$PROJECT_DIR/desktop/dist/index.html" << 'SPINNER'
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/><title>CScode</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#f5f5f5;display:flex;align-items:center;justify-content:center;height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;opacity:1;transition:opacity .2s ease}body.fade-out{opacity:0}.spinner{width:28px;height:28px;border:3px solid #ddd;border-top-color:#646cff;border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}</style></head><body><div class="spinner"></div></body></html>
SPINNER

# Step 3: Build PyInstaller backend
echo ""
echo ">>> Step 3: Building PyInstaller backend..."
pip3 install pyinstaller 2>&1 | tail -3
pip3 install . 2>&1 | tail -3
rm -rf "$PROJECT_DIR/dist/cscode-backend" "$PROJECT_DIR/cscode-backend.spec"
pyinstaller --onedir --name cscode-backend \
  --add-data "src/cscode/web/dist:web/dist" \
  desktop/backend-server.py --clean --noconfirm 2>&1 | tail -3
mkdir -p "$PROJECT_DIR/desktop/src-tauri/resources"
rm -rf "$PROJECT_DIR/desktop/src-tauri/resources/cscode-backend"
cp -r "$PROJECT_DIR/dist/cscode-backend" "$PROJECT_DIR/desktop/src-tauri/resources/"
echo "PyInstaller backend built:"
du -sh "$PROJECT_DIR/desktop/src-tauri/resources/cscode-backend/"

# Step 4: Build Tauri .app
echo ""
echo ">>> Step 4: Building Tauri .app..."
cd "$PROJECT_DIR/desktop"
npm install 2>&1 | tail -3
npx tauri build --bundles app

# Step 5-6: Create DMG + copy artifacts
create_dmg
