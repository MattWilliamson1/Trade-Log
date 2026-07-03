#!/usr/bin/env python3
"""
Build the Mac distribution for Trade Log.

Produces: dist/Trade Log Mac.tar.gz

Bundles a universal uv binary (arm64 + x86_64) so end-users do NOT
need Python pre-installed.  uv downloads Python 3.12 and all
dependencies automatically on first launch.

Run this from Windows OR Mac — Python's tarfile module sets Unix
execute permissions correctly so the .app bundle works on Mac.

The uv binary is downloaded once and cached in dist/_uv_mac/.
Subsequent builds reuse the cache (no re-download needed).

Usage:
    python build_mac_distribution.py
"""

import io
import tarfile
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DIST_DIR   = SCRIPT_DIR / "dist"
OUTPUT     = DIST_DIR / "Trade Log Mac.tar.gz"
TOP        = "Trade Log Mac"
BUNDLE     = f"{TOP}/Trade Log.app/Contents"

# Separate binaries for Apple Silicon (arm64) and Intel (x86_64)
UV_MAC_URLS = {
    "arm64":  "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz",
    "x86_64": "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz",
}
UV_MAC_CACHE = DIST_DIR / "_uv_mac"   # local cache dir (dist/ is gitignored)

# ── Launcher shell script ────────────────────────────────────────────────────
# Placed at: Trade Log.app/Contents/MacOS/launcher  (mode 0o755)
#
# What it does on FIRST launch:
#   1. Uses the bundled uv to install Python 3.12 (no system Python needed)
#   2. Creates a venv inside the .app bundle
#   3. Installs pip dependencies from requirements.txt
#
# On SUBSEQUENT launches:
#   • venv already exists → skips straight to starting Streamlit
#   • Kills any stale Streamlit on port 8502 first (safe to re-launch)
LAUNCHER = r"""#!/bin/bash
# Trade Log — Mac launcher
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$(cd "$MACOS_DIR/../Resources" && pwd)"
VENV_DIR="$RESOURCES_DIR/.venv"
PORT=8502

# When the .app is double-clicked in Finder, macOS launches it with a bare-bones
# environment — a minimal PATH and sometimes no HOME — which is different from a
# normal Terminal session. uv's first-run setup can fail in that environment
# (e.g. "Could not create a Python environment") even though it works fine when
# the launcher is run from Terminal. Restore sane defaults so setup behaves the
# same either way.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
[ -n "$HOME" ] || export HOME="$(/usr/bin/dscl . -read "/Users/$(/usr/bin/id -un)" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"

# Keep uv's Python + cache downloads in one predictable, writable spot (no spaces
# in the path) so they don't depend on whatever the launch environment provides.
export UV_CACHE_DIR="$HOME/.tradelog/uv-cache"
export UV_PYTHON_INSTALL_DIR="$HOME/.tradelog/python"

# Force copy instead of hardlink. If the install path sits under a cloud-synced
# folder (iCloud Drive, OneDrive, Dropbox), hardlinking from the cache can fail;
# copy mode sidesteps it. Matches the Windows installer.
export UV_LINK_MODE=copy

# Pick the right binary for this Mac's CPU
ARCH=$(uname -m)   # arm64 on Apple Silicon, x86_64 on Intel
UV_BIN="$RESOURCES_DIR/_uv/$ARCH/uv"

# Everything during first-run setup is logged here so failures are diagnosable.
LOG_DIR="$HOME/Library/Logs"
LOG="$LOG_DIR/Trade Log Setup.log"
mkdir -p "$LOG_DIR" 2>/dev/null

alert() {
    osascript -e "display alert \"Trade Log\" message \"$*\" as critical \
        buttons {\"OK\"} default button \"OK\"" 2>/dev/null \
        || echo "ERROR: $*" >&2
}

# Surface the real error (tail of the setup log) so the user can report what
# actually went wrong instead of just "please try again".
fail() {
    local detail
    detail="$(tail -n 6 "$LOG" 2>/dev/null)"
    alert "$1\n\nDetails:\n$detail\n\nFull log:\n$LOG"
    exit 1
}

# ── First-run setup ─────────────────────────────────────────────────────────
if [ ! -x "$VENV_DIR/bin/python" ]; then

    if [ ! -f "$UV_BIN" ]; then
        alert "Setup tools are missing.\n\nPlease re-download Trade Log and try again."
        exit 1
    fi

    # Strip the macOS quarantine flag from the bundled tools so Gatekeeper
    # doesn't silently block them when launched from Finder.
    xattr -dr com.apple.quarantine "$RESOURCES_DIR" 2>/dev/null || true
    chmod +x "$UV_BIN" 2>/dev/null || true

    # Clear any half-built venv left behind by a previous failed attempt.
    rm -rf "$VENV_DIR" 2>/dev/null

    osascript -e 'display notification "Setting up Trade Log for the first time — this takes 1–2 minutes..." with title "Trade Log"' 2>/dev/null

    {
        echo "=== Trade Log setup: $(date) ==="
        echo "arch=$ARCH  HOME=$HOME"
        echo "PATH=$PATH"
    } >>"$LOG" 2>&1

    # Install Python 3.12 (downloaded by uv, no system Python needed)
    "$UV_BIN" python install 3.12 >>"$LOG" 2>&1 \
        || fail "Could not install Python.\n\nPlease check your internet connection and try again."

    # Create virtual environment
    "$UV_BIN" venv --python 3.12 "$VENV_DIR" >>"$LOG" 2>&1 \
        || fail "Could not create a Python environment."

    # Install Trade Log dependencies
    "$UV_BIN" pip install -r "$RESOURCES_DIR/requirements.txt" \
        --python "$VENV_DIR/bin/python" >>"$LOG" 2>&1 \
        || { rm -rf "$VENV_DIR"; fail "Could not install dependencies.\n\nPlease check your internet connection and try again."; }

fi

# ── Kill any stale Streamlit on this port ───────────────────────────────────
lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true

# ── Launch Streamlit via the supervisor (background) ─────────────────────────
# launch.py picks a light/dark theme base matching the saved theme and relaunches
# Streamlit when the app requests a restart. On Quit we send it SIGTERM (below)
# and it tears down its Streamlit child.
"$VENV_DIR/bin/python" "$RESOURCES_DIR/launch.py" --port "$PORT" --no-browser &
STREAMLIT_PID=$!

# ── Open browser once Streamlit is ready ─────────────────────────────────────
sleep 5
open "http://localhost:$PORT"

# ── Show Quit dialog (keeps app "running" so user knows how to stop it) ───────
osascript -e 'display dialog "Trade Log is running in your browser.\n\nClick Quit to stop the app." \
    with title "Trade Log" buttons {"Quit"} default button "Quit" with icon note' 2>/dev/null \
    || read -r -p "Press Enter to quit Trade Log..." _

# ── Cleanup ──────────────────────────────────────────────────────────────────
kill "$STREAMLIT_PID" 2>/dev/null
wait "$STREAMLIT_PID" 2>/dev/null
"""

# ── Primary .command launcher ────────────────────────────────────────────────
# Placed next to the .app at the top level of the distribution folder (mode 0o755).
#
# This is the RECOMMENDED way to start Trade Log. A .command is a plain script
# that Finder always runs on double-click — it never depends on macOS recognising
# the .app as a bundle. That matters because a .app built off-Mac and shipped in a
# .tar.gz is often extracted as a plain folder (no "Show Package Contents", won't
# launch); the .command sidesteps that entirely. It also clears the download
# quarantine from the whole folder, so the .app itself becomes launchable after
# one run for users who prefer it.
COMMAND_FALLBACK = r"""#!/bin/bash
# Trade Log — launcher (recommended).
#
# Double-click this to start Trade Log. It runs the app from a Terminal window,
# which works on every Mac — including ones where double-clicking "Trade Log.app"
# only opens a folder or is blocked by macOS security.
#
# First time only: macOS may say it "cannot verify the developer." If so,
# right-click this file -> Open -> Open.
DIR="$(cd "$(dirname "$0")" && pwd)"
# Trust everything we shipped here: clear the download quarantine so neither this
# script, the app bundle, nor the bundled tools get blocked by Gatekeeper.
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null || true
exec "$DIR/Trade Log.app/Contents/MacOS/launcher"
"""

# ── Info.plist — identifies this as a macOS app bundle ──────────────────────
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

SOURCE_FILES = [
    "app.py",
    "db.py",
    "ib_client.py",
    "schwab_client.py",
    "fidelity_client.py",
    "updater.py",
    "launch.py",
    "requirements.txt",
    "VERSION",
]


# ── Tar helpers ──────────────────────────────────────────────────────────────

def add_str(tf: tarfile.TarFile, arcname: str, content: str, mode: int = 0o644) -> None:
    data = content.encode("utf-8")
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = mode
    tf.addfile(info, io.BytesIO(data))


def add_file(tf: tarfile.TarFile, arcname: str, src: Path, mode: int = 0o644) -> None:
    data = src.read_bytes()
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = mode
    tf.addfile(info, io.BytesIO(data))


def add_bytes(tf: tarfile.TarFile, arcname: str, data: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = mode
    tf.addfile(info, io.BytesIO(data))


def add_dir(tf: tarfile.TarFile, arcname: str, mode: int = 0o755) -> None:
    """Write an explicit directory entry. Bundles extract more reliably when the
    .app / Contents / MacOS / Resources dirs are present as real entries rather
    than implied by their files — some unarchivers (and Finder's bundle
    detection) don't treat an implicitly-created .app as a package."""
    info = tarfile.TarInfo(name=arcname.rstrip("/") + "/")
    info.type = tarfile.DIRTYPE
    info.mode = mode
    info.size = 0
    tf.addfile(info)


# ── uv download / cache ──────────────────────────────────────────────────────

def get_uv_binary(arch: str) -> bytes:
    """Return the uv binary for the given arch, downloading and caching if needed."""
    cached = UV_MAC_CACHE / arch / "uv"
    if cached.exists():
        size_kb = cached.stat().st_size // 1024
        print(f"  [cached]   uv/{arch}/uv ({size_kb:,} KB)")
        return cached.read_bytes()

    url = UV_MAC_URLS[arch]
    print(f"  [download] uv for {arch} (one-time, ~15 MB)...")
    with urllib.request.urlopen(url) as resp:
        gz_data = resp.read()

    # Extract the 'uv' binary from the downloaded tar.gz
    import tarfile as _tf
    with _tf.open(fileobj=io.BytesIO(gz_data), mode="r:gz") as inner:
        for member in inner.getmembers():
            if member.name.split("/")[-1] == "uv" and not member.isdir():
                f = inner.extractfile(member)
                if f:
                    data = f.read()
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    cached.write_bytes(data)
                    size_kb = len(data) // 1024
                    print(f"  [cached]   -> dist/_uv_mac/{arch}/uv ({size_kb:,} KB)")
                    return data

    raise RuntimeError(f"Could not find 'uv' binary inside {url}")


# ── Main build ───────────────────────────────────────────────────────────────

def build() -> None:
    DIST_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("  Trade Log — Mac Distribution Builder")
    print("=" * 60)
    print()

    print("Step 1: Fetching uv binaries (cached after first download):")
    uv_binaries = {arch: get_uv_binary(arch) for arch in UV_MAC_URLS}
    print()

    print("Step 2: Building tar.gz:")
    missing = []

    with tarfile.open(OUTPUT, "w:gz") as tf:

        # Explicit directory entries for the bundle tree — added first so the
        # .app is recognised as a package rather than extracted as a plain folder.
        for d in (
            TOP,
            f"{TOP}/Trade Log.app",
            f"{BUNDLE}",
            f"{BUNDLE}/MacOS",
            f"{BUNDLE}/Resources",
            f"{BUNDLE}/Resources/.streamlit",
            f"{BUNDLE}/Resources/_uv",
            *(f"{BUNDLE}/Resources/_uv/{arch}" for arch in UV_MAC_URLS),
        ):
            add_dir(tf, d)
        print("  + (bundle directory entries)")

        # Launcher — executable
        add_str(tf, f"{BUNDLE}/MacOS/launcher", LAUNCHER, mode=0o755)
        print("  + MacOS/launcher")

        # Primary .command launcher next to the .app — the recommended,
        # bundle-recognition-proof way to start the app.
        command_name = f"{TOP}/Start Trade Log.command"
        add_str(tf, command_name, COMMAND_FALLBACK, mode=0o755)
        print(f"  + {command_name}")

        # App metadata
        add_str(tf, f"{BUNDLE}/Info.plist", INFO_PLIST)
        print("  + Info.plist")

        # PkgInfo — legacy bundle type marker; helps LaunchServices classify the
        # .app as an application package (APPL) rather than a folder.
        add_str(tf, f"{BUNDLE}/PkgInfo", "APPL????")
        print("  + PkgInfo")

        # Source files
        for name in SOURCE_FILES:
            src = SCRIPT_DIR / name
            if src.exists():
                add_file(tf, f"{BUNDLE}/Resources/{name}", src)
                print(f"  + Resources/{name}")
            else:
                missing.append(name)
                print(f"  ! {name} — NOT FOUND (skipped)")

        # Streamlit config
        config = SCRIPT_DIR / ".streamlit" / "config.toml"
        if config.exists():
            add_file(tf, f"{BUNDLE}/Resources/.streamlit/config.toml", config)
            print("  + Resources/.streamlit/config.toml")
        else:
            missing.append(".streamlit/config.toml")
            print("  ! .streamlit/config.toml — NOT FOUND (skipped)")

        # uv binaries — one per architecture, both executable
        for arch, data in uv_binaries.items():
            add_bytes(tf, f"{BUNDLE}/Resources/_uv/{arch}/uv", data, mode=0o755)
            print(f"  + Resources/_uv/{arch}/uv ({len(data) // 1024:,} KB)")

    size_kb = OUTPUT.stat().st_size // 1024
    print()
    print(f"Done!  {OUTPUT.name}  ({size_kb:,} KB)")

    if missing:
        print()
        print("  WARNING — these items were missing:")
        for m in missing:
            print(f"    - {m}")

    print()
    print("-" * 60)
    print("End-user install steps (share these with Mac users):")
    print()
    print("  1. Double-click 'Trade Log Mac.tar.gz' to extract")
    print("  2. Open the 'Trade Log Mac' folder")
    print("  3. Double-click 'Start Trade Log.command'  (recommended)")
    print("  4. macOS security prompt:")
    print("       right-click 'Start Trade Log.command' -> Open -> Open")
    print("       (macOS 15 Sequoia: System Settings -> Privacy & Security")
    print("        -> scroll down -> 'Open Anyway')")
    print("  5. First launch only: Trade Log installs itself (~1–2 min)")
    print("     No Python required — everything is included.")
    print("  6. Your browser opens Trade Log automatically.")
    print("  7. Click 'Quit' in the dialog to stop the app.")
    print()
    print("  'Start Trade Log.command' is the reliable path — it works even when")
    print("  macOS shows 'Trade Log.app' as a plain folder. It also clears the")
    print("  download quarantine, so 'Trade Log.app' can be double-clicked")
    print("  directly on later launches if preferred.")
    print("  Setup errors are logged to ~/Library/Logs/Trade Log Setup.log")
    print("-" * 60)
    print()


if __name__ == "__main__":
    build()
