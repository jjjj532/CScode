#!/usr/bin/env bash
# CScode Cross-Platform Build Script
# Usage: ./scripts/build.sh [macos|linux|windows|all]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
BUILD_DIR="$ROOT/build"

PLATFORM="${1:-macos}"

echo "=== CScode Build Script ==="
echo "Platform: $PLATFORM"
echo "Root: $ROOT"

# Activate venv if exists
if [ -f "$ROOT/.venv/bin/activate" ]; then
    source "$ROOT/.venv/bin/activate"
fi

# Ensure PyInstaller is installed
pip install pyinstaller --quiet

# Clean previous builds
rm -rf "$DIST" "$BUILD_DIR"

build_cli() {
    local platform="$1"
    echo ""
    echo "--- Building standalone CLI for $platform ---"

    # PyInstaller build
    pyinstaller \
        --clean \
        --noconfirm \
        --distpath "$DIST/$platform" \
        --workpath "$BUILD_DIR/$platform" \
        "$ROOT/cscode-cli.spec"

    echo "CLI binary: $DIST/$platform/cscode"
}

package_macos() {
    echo ""
    echo "--- Packaging for macOS ---"

    local APP_DIR="$DIST/macos/CScode.app"
    mkdir -p "$APP_DIR/Contents/MacOS"
    mkdir -p "$APP_DIR/Contents/Resources"

    # Copy binary as 'cscode-bin' (not overwriting launcher)
    cp "$DIST/macos/cscode" "$APP_DIR/Contents/MacOS/cscode-bin"

    # Create launcher script that opens Terminal
    cat > "$APP_DIR/Contents/MacOS/cscode" << 'EOF'
#!/bin/bash
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/cscode-bin"
osascript -e 'tell app "Terminal" to do script "'"$SCRIPT_PATH"' tui" &'
sleep 1
EOF
    chmod +x "$APP_DIR/Contents/MacOS/cscode"

    # Create Info.plist
    cat > "$APP_DIR/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>CScode</string>
    <key>CFBundleDisplayName</key>
    <string>CScode</string>
    <key>CFBundleIdentifier</key>
    <string>com.cscode.app</string>
    <key>CFBundleVersion</key>
    <string>0.3.4</string>
    <key>CFBundleShortVersionString</key>
    <string>0.3.4</string>
    <key>CFBundleExecutable</key>
    <string>CScode</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

    # Create DMG
    echo "Creating DMG..."
    hdiutil create -volname "CScode" \
        -srcfolder "$APP_DIR" \
        -ov -format UDZO \
        "$DIST/CScode-0.3.4-macos.dmg" 2>/dev/null || \
        echo "DMG creation skipped (requires macOS)"

    echo "macOS package: $DIST/CScode-0.3.4-macos.dmg"
}

package_linux() {
    echo ""
    echo "--- Packaging for Linux ---"

    local PKG_DIR="$DIST/linux/cscode-0.3.4"
    mkdir -p "$PKG_DIR/usr/local/bin"
    mkdir -p "$PKG_DIR/usr/share/applications"
    mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"

    cp "$DIST/linux/cscode" "$PKG_DIR/usr/local/bin/cscode"

    # Create .desktop file
    cat > "$PKG_DIR/usr/share/applications/cscode.desktop" << 'EOF'
[Desktop Entry]
Name=CScode
Comment=AI-powered coding assistant
Exec=cscode
Terminal=true
Type=Application
Categories=Development;IDE;
EOF

    # Create tar.gz
    cd "$DIST/linux"
    tar -czf "$DIST/CScode-0.3.4-linux-x64.tar.gz" "cscode-0.3.4"
    cd "$ROOT"

    echo "Linux package: $DIST/CScode-0.3.4-linux-x64.tar.gz"
}

package_windows() {
    echo ""
    echo "--- Packaging for Windows ---"

    # Windows: rename to .exe, create zip
    cp "$DIST/windows/cscode" "$DIST/windows/cscode.exe" 2>/dev/null || true

    cd "$DIST/windows"
    zip -r "$DIST/CScode-0.3.4-windows-x64.zip" cscode.exe 2>/dev/null || \
        echo "zip failed (install zip utility")
    cd "$ROOT"

    echo "Windows package: $DIST/CScode-0.3.4-windows-x64.zip"
}

case "$PLATFORM" in
    macos)
        build_cli "macos"
        package_macos
        ;;
    linux)
        build_cli "linux"
        package_linux
        ;;
    windows)
        build_cli "windows"
        package_windows
        ;;
    all)
        build_cli "macos"
        package_macos
        build_cli "linux"
        package_linux
        build_cli "windows"
        package_windows
        ;;
    *)
        echo "Unknown platform: $PLATFORM"
        echo "Usage: $0 [macos|linux|windows|all]"
        exit 1
        ;;
esac

echo ""
echo "=== Build Complete ==="
echo "Output: $DIST/"
ls -la "$DIST"/*.dmg "$DIST"/*.tar.gz "$DIST"/*.zip 2>/dev/null || ls -la "$DIST/"
