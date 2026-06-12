from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "desktop"
TAURI_BIN = DESKTOP_DIR / "src-tauri" / "target" / "debug" / "cscode-desktop"


def launch_desktop(dev: bool = False) -> None:
    """Launch the CScode desktop application."""
    if not DESKTOP_DIR.exists():
        sys.exit(f"Error: desktop directory not found at {DESKTOP_DIR}")

    if dev:
        npm_cmd = ["npm", "run", "tauri", "dev"]
        print(f"Starting Tauri dev server in {DESKTOP_DIR}...")
        subprocess.run(npm_cmd, cwd=str(DESKTOP_DIR))
    else:
        tauri_bin = TAURI_BIN
        if not tauri_bin.exists():
            print(f"Tauri binary not found at {tauri_bin}, building first...")
            subprocess.run(
                ["npm", "run", "tauri", "build"],
                cwd=str(DESKTOP_DIR),
            )
            sys.exit("Built Tauri app. Run `cs desktop` again to launch.")
        print("Launching CScode desktop application...")
        subprocess.run([str(tauri_bin)])
