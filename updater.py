import os
import sys
import subprocess
import urllib.request
from pathlib import Path

REPO     = "MattWilliamson1/Trade-Log"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
APP_DIR  = Path(__file__).parent

SOURCE_FILES = [
    "app.py",
    "db.py",
    "ib_client.py",
    "schwab_client.py",
    "fidelity_client.py",
    "csv_smart.py",
    "launch.py",
    "requirements.txt",
    "updater.py",
    "VERSION",
]

# The Windows launcher ships from installer/launch.bat as the app's launch.bat.
# Refreshing it in place lets existing installs pick up launcher changes (e.g.
# the theme-aware supervisor) without needing a brand-new install.
_WIN_LAUNCHER_SRC = "installer/launch.bat"
_WIN_LAUNCHER_DST = "launch.bat"


_topped_up = False


def fetch_missing_source_files() -> list:
    """Download any module in SOURCE_FILES that is absent on disk; return the names.

    An install brought up to date by an *older* updater has only the files that
    copy knew to fetch, so a module added to the list since is missing until
    the next version bump. app.py calls this at startup, before its optional
    imports, so the gap closes on first run rather than next release. Modules
    only, and never an overwrite: a file that exists is left alone whatever it
    holds. Runs once per process; the cost when nothing is missing is a stat
    per name.
    """
    global _topped_up
    if _topped_up:
        return []
    _topped_up = True
    fetched = []
    for name in SOURCE_FILES:
        if not name.endswith(".py") or (APP_DIR / name).exists():
            continue
        try:
            with urllib.request.urlopen(f"{RAW_BASE}/{name}", timeout=15) as r:
                data = r.read()
            (APP_DIR / name).write_bytes(data)
            fetched.append(name)
        except Exception:
            continue
    return fetched


def get_local_version() -> str:
    v = APP_DIR / "VERSION"
    return v.read_text().strip() if v.exists() else "unknown"


def get_remote_version() -> "str | None":
    try:
        with urllib.request.urlopen(f"{RAW_BASE}/VERSION", timeout=8) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def _source_files_in(updater_src: bytes) -> list:
    """SOURCE_FILES as declared in another copy of this file, read without
    importing it — a regex over the literal, so nothing untrusted executes."""
    import re
    text = updater_src.decode("utf-8", errors="replace")
    m = re.search(r"SOURCE_FILES\s*=\s*\[(.*?)\]", text, re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def download_updates() -> "tuple[bool, str | None]":
    """Download all source files from GitHub main. Returns (success, error_message).

    Downloads everything into memory before writing anything to disk so a
    network failure mid-way leaves no partial state.
    """
    old_reqs = (APP_DIR / "requirements.txt").read_bytes() \
        if (APP_DIR / "requirements.txt").exists() else b""

    downloaded: dict = {}
    try:
        for name in SOURCE_FILES:
            with urllib.request.urlopen(f"{RAW_BASE}/{name}", timeout=30) as r:
                downloaded[name] = r.read()
        # The list driving that loop is the *installed* updater's. A module
        # added to SOURCE_FILES upstream would otherwise arrive one update late:
        # skipped this round because this copy never heard of it, and fetched
        # only after the next version bump. Read the fresh list and top up.
        for name in _source_files_in(downloaded.get("updater.py", b"")):
            if name not in downloaded:
                with urllib.request.urlopen(f"{RAW_BASE}/{name}", timeout=30) as r:
                    downloaded[name] = r.read()
    except Exception as e:
        return False, str(e)

    # Best-effort: refresh the Windows launcher so the supervisor stays current.
    # A failure here must not fail the update — the core files already downloaded.
    launcher_data = None
    if os.name == "nt":
        try:
            with urllib.request.urlopen(
                f"{RAW_BASE}/{_WIN_LAUNCHER_SRC}", timeout=30
            ) as r:
                launcher_data = r.read()
        except Exception:
            launcher_data = None

    for name, data in downloaded.items():
        (APP_DIR / name).write_bytes(data)

    if launcher_data is not None:
        try:
            (APP_DIR / _WIN_LAUNCHER_DST).write_bytes(launcher_data)
        except Exception:
            pass

    # Re-run pip only if requirements.txt changed
    new_reqs = downloaded.get("requirements.txt", b"")
    if new_reqs and new_reqs != old_reqs:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r",
             str(APP_DIR / "requirements.txt")],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return False, f"Files updated but pip install failed:\n{result.stderr}"

    return True, None
