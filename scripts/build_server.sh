#!/bin/bash
set -e

# Build the Python backend into a standalone executable via PyInstaller.
# Usage: ./scripts/build-server.sh [target-triple]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TARGET_TRIPLE="${1:-}"
if [ -z "$TARGET_TRIPLE" ]; then
    case "$(uname -s)" in
        Darwin)  TARGET_TRIPLE="x86_64-apple-darwin" ;;
        Linux)   TARGET_TRIPLE="x86_64-unknown-linux-gnu" ;;
        MINGW*|MSYS*|CYGWIN*) TARGET_TRIPLE="x86_64-pc-windows-msvc" ;;
        *) echo "Unknown platform"; exit 1 ;;
    esac
fi

echo "Building cscode-server for $TARGET_TRIPLE..."

# Build frontend first
echo "Building frontend..."
cd "$PROJECT_DIR/src/cscode/web"
npm ci 2>/dev/null || true
npx vite build

# Activate venv and build PyInstaller binary
cd "$PROJECT_DIR"
source .venv/bin/activate 2>/dev/null || true
pip install pyinstaller

# Read cscode-server version
VERSION=$(python3 -c "from cscode import __version__; print(__version__)")

# Build
pyinstaller \
    --onefile \
    --name "cscode-server" \
    --hidden-import cscode \
    --hidden-import cscode.core \
    --hidden-import cscode.core.config \
    --hidden-import cscode.core.engine \
    --hidden-import cscode.core.messages \
    --hidden-import cscode.providers \
    --hidden-import cscode.providers.base \
    --hidden-import cscode.providers.openai \
    --hidden-import cscode.providers.anthropic \
    --hidden-import cscode.providers.ollama \
    --hidden-import cscode.tools \
    --hidden-import cscode.tools.base \
    --hidden-import cscode.tools.read \
    --hidden-import cscode.tools.write \
    --hidden-import cscode.tools.edit \
    --hidden-import cscode.tools.bash \
    --hidden-import cscode.tools.grep \
    --hidden-import cscode.tools.glob \
    --hidden-import cscode.tools.ls \
    --hidden-import cscode.storage \
    --hidden-import cscode.storage.db \
    --hidden-import cscode.storage.session \
    --hidden-import cscode.server \
    --add-data "src/cscode/web/dist:web/dist" \
    src/cscode/server/app.py

echo "PyInstaller build complete."

# Copy to Tauri binary directory
# Copy to Tauri binary directory (replaces placeholder)
BINARIES_DIR="$PROJECT_DIR/desktop/src-tauri/binaries"
mkdir -p "$BINARIES_DIR"
cp "dist/cscode-server" "$BINARIES_DIR/cscode-server"
echo "Copied to $BINARIES_DIR/cscode-server"
echo "Server binary built successfully."
