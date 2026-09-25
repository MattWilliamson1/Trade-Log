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
    "reconcile.py",
    "launch.py",
    "requirements.txt",
    "updater.py",
    "VERSION",
    "CHANGELOG.md",
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


# ── Changelog ─────────────────────────────────────────────────────────────────
# CHANGELOG.md holds one "## <version>" section per release, newest first, each
# a bullet list of what changed. CI refuses a push whose VERSION has no section
# (`python updater.py check-changelog`), so the list can't fall behind, and
# the update prompt shows the sections between the installed and new versions.

def version_key(v: str) -> tuple:
    """Sort key for "YYYY-MM-DD" / "YYYY-MM-DD.N" versions (no suffix = .0)."""
    import re
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})(?:\.(\d+))?", v or "")
    return (m.group(1), int(m.group(2) or 0)) if m else ("", 0)


def parse_changelog(text: str) -> list:
    """[(version, [bullet, ...])] in file order (newest first)."""
    import re
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^##\s+v?(\S+)", line)
        if m:
            out.append((m.group(1), []))
        elif out and re.match(r"^\s*[-*]\s+", line):
            out[-1][1].append(re.sub(r"^\s*[-*]\s+", "", line).rstrip())
    return out


def get_local_changelog() -> str:
    p = APP_DIR / "CHANGELOG.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def get_remote_changelog() -> "str | None":
    try:
        with urllib.request.urlopen(f"{RAW_BASE}/CHANGELOG.md", timeout=8) as r:
            return r.read().decode("utf-8")
    except Exception:
        return None


def changelog_entry(version: str, text: "str | None" = None) -> list:
    """Bullets for one version ([] when it has no section)."""
    text = get_local_changelog() if text is None else text
    for v, items in parse_changelog(text):
        if v == version:
            return items
    return []


def changes_since(text: str, installed: str) -> list:
    """Sections newer than the installed version, newest first."""
    floor = version_key(installed)
    return [(v, items) for v, items in parse_changelog(text) if version_key(v) > floor]


def release_notes() -> str:
    """Body for the GitHub release page: this version's changes + install steps."""
    v = get_local_version()
    lines = [f"## Latest build — v{v}", "", "### What's new"]
    lines += [f"- {i}" for i in changelog_entry(v)] or ["- (no notes)"]
    lines += [
        "",
        "### Windows",
        "**Download the zip below**, extract it, and double-click",
        "`INSTALL - Double-Click This First.bat`.",
        "",
        "### Mac",
        "**Download the `.tar.gz` below**, double-click it to extract,",
        "open the `Trade Log Mac` folder, and double-click `Trade Log.app`.",
        "If macOS shows a security warning, right-click the app → Open → Open.",
        "",
        "Every earlier version's changes are in CHANGELOG.md in the repository.",
        "",
        "> This release is updated automatically every time an update is pushed.",
    ]
    return "\n".join(lines) + "\n"


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


if __name__ == "__main__":
    # Release tooling, run from CI:
    #   python updater.py check-changelog   fail unless VERSION has a CHANGELOG entry
    #   python updater.py release-notes     print the GitHub release body
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check-changelog":
        v = get_local_version()
        if not changelog_entry(v):
            sys.exit(f"CHANGELOG.md has no '## {v}' section with at least one bullet. "
                     "Add one before pushing a version bump.")
        print(f"CHANGELOG.md covers {v}.")
    elif cmd == "release-notes":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(release_notes())
    else:
        sys.exit("usage: python updater.py check-changelog | release-notes")
