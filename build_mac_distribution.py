#!/usr/bin/env python3
"""
Build the Mac distribution for Trade Log.

Produces: dist/Trade Log Mac.tar.gz

Run this from Windows OR Mac — it uses Python's tarfile module to set
Unix execute permissions correctly so the .app bundle works on Mac.

Usage:
    python build_mac_distribution.py
"""

import io
import tarfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DIST_DIR   = SCRIPT_DIR / "dist"
OUTPUT     = DIST_DIR / "Trade Log Mac.tar.gz"
TOP        = "Trade Log Mac"
BUNDLE     = f"{TOP}/Trade Log.app/Contents"

# ── Mac launcher shell script ───────────────────────────────────────────────
# Placed at: Trade Log.app/Contents/MacOS/launcher  (mode 0o755)
# The script:
#   • finds Python 3.10+ on the Mac (system or user-installed)
#   • creates a venv inside the .app bundle on the first run
#   • installs pip dependencies
#   • starts Streamlit on port 8502
#   • opens the default browser
#   • blocks on an osascript dialog until the user clicks Quit
LAUNCHER = r"""#!/bin/bash
# Trade Log — Mac launcher
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$(cd "$MACOS_DIR/../Resources" && pwd)"
VENV_DIR="$RESOURCES_DIR/.venv"
PORT=8502

alert() {
    osascript -e "display alert \"Trade Log\" message \"$*\" as critical \
        buttons {\"OK\"} default button \"OK\"" 2>/dev/null \
        || echo "ERROR: $*" >&2
}

notify() {
    osascript -e "display notification \"$*\" with title \"Trade Log\"" 2>/dev/null
}

# ── First-run setup ─────────────────────────────────────────────────────────
if [ ! -f "$VENV_DIR/bin/python" ]; then

    PYTHON3=""
    for cmd in python3.12 python3.11 python3.10 python3 /usr/bin/python3; do
        if command -v "$cmd" &>/dev/null; then
            VER=$("$cmd" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null)
            if [ "$VER" = "True" ]; then
                PYTHON3="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON3" ]; then
        alert "Python 3.10 or newer is required.\n\nDownload it free from python.org then try again."
        exit 1
    fi

    notify "Setting up Trade Log for the first time — this may take 1–2 minutes..."

    "$PYTHON3" -m venv "$VENV_DIR" || {
        alert "Could not create a Python environment.\n\nMake sure Python 3 is installed from python.org."
        exit 1
    }

    "$VENV_DIR/bin/pip" install --quiet -r "$RESOURCES_DIR/requirements.txt" || {
        alert "Could not install dependencies.\n\nCheck your internet connection and try again."
        rm -rf "$VENV_DIR"
        exit 1
    }

fi

# ── Kill any stale Streamlit on this port ───────────────────────────────────
lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true

# ── Launch Streamlit ────────────────────────────────────────────────────────
"$VENV_DIR/bin/python" -m streamlit run "$RESOURCES_DIR/app.py" \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

# ── Open browser once Streamlit is ready ────────────────────────────────────
sleep 5
open "http://localhost:$PORT"

# ── Block until user clicks Quit ────────────────────────────────────────────
osascript -e 'display dialog "Trade Log is running in your browser.\n\nClick Quit to stop the app." \
    with title "Trade Log" buttons {"Quit"} default button "Quit" with icon note' 2>/dev/null \
    || read -r -p "Press Enter to quit Trade Log..." _

# ── Cleanup ─────────────────────────────────────────────────────────────────
kill "$STREAMLIT_PID" 2>/dev/null
wait "$STREAMLIT_PID" 2>/dev/null
"""

INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.tradelog.app</string>
    <key>CFBundleName</key>
    <string>Trade Log</string>
    <key>CFBundleDisplayName</key>
    <string>Trade Log</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""

SOURCE_FILES = ["app.py", "db.py", "ib_client.py", "updater.py", "requirements.txt", "VERSION"]


def add_str(tar: tarfile.TarFile, arcname: str, content: str, mode: int = 0o644) -> None:
    data = content.encode("utf-8")
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def add_file(tar: tarfile.TarFile, arcname: str, src: Path, mode: int = 0o644) -> None:
    data = src.read_bytes()
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def build() -> None:
    DIST_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("  Trade Log — Mac Distribution Builder")
    print("=" * 60)
    print()

    with tarfile.open(OUTPUT, "w:gz") as tar:
        # Launcher shell script — must be executable
        add_str(tar, f"{BUNDLE}/MacOS/launcher", LAUNCHER, mode=0o755)
        print("  + MacOS/launcher (executable)")

        # Info.plist — tells macOS this is an app bundle
        add_str(tar, f"{BUNDLE}/Info.plist", INFO_PLIST)
        print("  + Info.plist")

        # App source files
        for name in SOURCE_FILES:
            src = SCRIPT_DIR / name
            if src.exists():
                add_file(tar, f"{BUNDLE}/Resources/{name}", src)
                print(f"  + Resources/{name}")
            else:
                print(f"  ! {name} not found — skipping")

        # Streamlit config
        config = SCRIPT_DIR / ".streamlit" / "config.toml"
        if config.exists():
            add_file(tar, f"{BUNDLE}/Resources/.streamlit/config.toml", config)
            print("  + Resources/.streamlit/config.toml")

    size_kb = OUTPUT.stat().st_size // 1024
    print()
    print(f"Done!  {OUTPUT}  ({size_kb:,} KB)")
    print()
    print("-" * 60)
    print("Mac install instructions for end users:")
    print()
    print("  1. Copy 'Trade Log Mac.tar.gz' to the Mac")
    print("  2. Double-click it -- macOS extracts a 'Trade Log Mac' folder")
    print("  3. Open that folder and double-click 'Trade Log.app'")
    print("  4. If macOS shows a security warning:")
    print("       right-click the app -> Open -> Open")
    print("  5. On first launch, dependencies install automatically")
    print("     (requires internet, takes about 1-2 minutes)")
    print("-" * 60)


if __name__ == "__main__":
    build()
