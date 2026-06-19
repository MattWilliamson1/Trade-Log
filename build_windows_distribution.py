#!/usr/bin/env python3
"""
Build the Windows distribution zip for Trade Log.

Produces: dist/Trade Log Windows.zip  (stable name so each release replaces the
previous build instead of piling up dated zips on the GitHub release).

The zip contains a single top-level folder "Trade Log" with exactly
these items (nothing else — no .venv, no stale zips, no dev files):

  Trade Log/
    app.py
    db.py
    ib_client.py
    schwab_client.py
    requirements.txt
    launch.bat
    INSTALL - Double-Click This First.bat
    PLEASE_READ_THIS_FIRST.txt
    DIAGNOSE - Run If Trade Log Won't Open.bat
    .streamlit/
      config.toml
    _uv/
      uv.exe
      uvw.exe
      uvx.exe

Usage:
    python build_windows_distribution.py
"""

import zipfile
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
INSTALLER    = SCRIPT_DIR / "installer"        # tracked installer assets
UV_DIR       = SCRIPT_DIR / "dist" / "Trade Log" / "_uv"   # uv binaries (local only)

# Files copied from the project root
ROOT_FILES = [
    "app.py",
    "db.py",
    "ib_client.py",
    "schwab_client.py",
    "updater.py",
    "launch.py",
    "requirements.txt",
    "VERSION",
]

# Flat files from installer/
INSTALLER_FILES = [
    "launch.bat",
    "INSTALL - Double-Click This First.bat",
    "PLEASE_READ_THIS_FIRST.txt",
    "DIAGNOSE - Run If Trade Log Won't Open.bat",
]

# Folders copied recursively from installer/
INSTALLER_FOLDERS = [
    ".streamlit",
]


def build() -> None:
    output = SCRIPT_DIR / "dist" / "Trade Log Windows.zip"
    output.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Trade Log — Windows Distribution Builder")
    print("=" * 60)
    print()

    missing = []

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        # ── Root-level source files ──────────────────────────────────────────
        for name in ROOT_FILES:
            src = SCRIPT_DIR / name
            if src.exists():
                zf.write(src, f"Trade Log/{name}")
                print(f"  + {name}")
            else:
                missing.append(name)
                print(f"  ! {name} — NOT FOUND (skipped)")

        # ── Installer flat files ─────────────────────────────────────────────
        for name in INSTALLER_FILES:
            src = INSTALLER / name
            if src.exists():
                zf.write(src, f"Trade Log/{name}")
                print(f"  + {name}")
            else:
                missing.append(name)
                print(f"  ! {name} — NOT FOUND (skipped)")

        # ── Installer folders (recursive) ────────────────────────────────────
        for folder in INSTALLER_FOLDERS:
            folder_path = INSTALLER / folder
            if not folder_path.exists():
                missing.append(folder)
                print(f"  ! {folder}/ — NOT FOUND (skipped)")
                continue
            for file in sorted(folder_path.rglob("*")):
                if file.is_file():
                    arc = "Trade Log/" + file.relative_to(INSTALLER).as_posix()
                    zf.write(file, arc)
                    print(f"  + {arc}")

        # ── uv binaries ──────────────────────────────────────────────────────
        if UV_DIR.exists():
            for file in sorted(UV_DIR.rglob("*")):
                if file.is_file():
                    arc = "Trade Log/_uv/" + file.name
                    zf.write(file, arc)
                    print(f"  + {arc}")
        else:
            missing.append("_uv/")
            print(f"  ! _uv/ — NOT FOUND (uv.exe will be downloaded at install time)")

    size_kb = output.stat().st_size // 1024
    print()
    print(f"Done!  {output.name}  ({size_kb:,} KB)")

    if missing:
        print()
        print("  WARNING — these items were missing:")
        for m in missing:
            print(f"    - {m}")

    print()


if __name__ == "__main__":
    build()
