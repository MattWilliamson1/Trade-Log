"""launch.py — Trade Log launcher / supervisor.

Streamlit reads its theme exactly once, at startup, and the data tables
(st.dataframe / st.data_editor) are drawn on a canvas that follows that theme —
they cannot be re-themed with CSS at runtime. So we read the user's saved theme
here and pass a matching light/dark base to Streamlit *before* it starts, which
keeps those tables in step with the chosen theme.

We also supervise the Streamlit process: when the app asks for a restart (the
user switched between a light and a dark theme), it writes a sentinel file and
exits; we relaunch Streamlit so the tables pick up the new base. The browser tab
reloads itself once the new server is up (handled in app.py).

The .bat / .sh launchers just call this script, so all of the above lives in one
place and behaves identically on Windows and macOS.

Usage:
    python launch.py                 # find a free port, open the browser
    python launch.py --port 8502     # use a specific port
    python launch.py --no-browser    # don't open a browser (launcher already did)
"""
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESTART_SENTINEL = HERE / ".restart_requested"

_current_proc = None  # the running Streamlit child, so signal handlers can stop it

# Theme key -> (base, backgroundColor, secondaryBackgroundColor, textColor,
# primaryColor). Mirrors THEMES in app.py. Only the light/dark base is critical
# (it's what keeps the data tables readable); the colors just help them blend in.
# Keep roughly in sync with app.py's THEMES.
_THEME_CONFIG = {
    "ocean_dark": ("dark",  "#131929", "#1a2236", "#c8cfe0", "#4e8ef7"),
    "midnight":   ("dark",  "#0a0a0f", "#16161f", "#d4d4e8", "#9b59b6"),
    "forest":     ("dark",  "#0d1a0f", "#172a1c", "#c0d8c4", "#2ecc71"),
    "light":      ("light", "#f5f7fa", "#e8ecf4", "#1a1f2e", "#2563eb"),
    "warm_sand":  ("light", "#faf7f0", "#f0ebe0", "#3d2c1a", "#c0622a"),
}
_DEFAULT_THEME = "ocean_dark"


def _db_path() -> Path:
    """The database the app will use (honours the TRADELOG_DB override)."""
    return Path(os.environ.get("TRADELOG_DB") or (HERE / "tradelog.db"))


def _saved_theme() -> str:
    """Read app_theme straight from SQLite. Falls back to the default on any error."""
    db = _db_path()
    if not db.exists():
        return _DEFAULT_THEME
    try:
        import sqlite3
        con = sqlite3.connect(str(db))
        try:
            row = con.execute(
                "SELECT value FROM settings WHERE key='app_theme'"
            ).fetchone()
            if row and row[0] in _THEME_CONFIG:
                return row[0]
        finally:
            con.close()
    except Exception:
        pass
    return _DEFAULT_THEME


def _theme_flags() -> list:
    base, bg, bg2, text, primary = _THEME_CONFIG.get(
        _saved_theme(), _THEME_CONFIG[_DEFAULT_THEME]
    )
    return [
        f"--theme.base={base}",
        f"--theme.backgroundColor={bg}",
        f"--theme.secondaryBackgroundColor={bg2}",
        f"--theme.textColor={text}",
        f"--theme.primaryColor={primary}",
    ]


def _port_in_use(port: int) -> bool:
    """True if something is already listening on 127.0.0.1:<port>."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _find_free_port(start: int = 8502, attempts: int = 50) -> int:
    port = start
    for _ in range(attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port  # connect failed -> nothing listening -> free
        port += 1
    return start


def _open_browser_later(url: str, delay: float = 4.0):
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()


def _arg_value(name: str):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _shutdown(signum, frame):
    """Forward an external stop (e.g. the macOS Quit dialog's `kill`) to the
    Streamlit child so it doesn't outlive us and hold the port."""
    if _current_proc is not None and _current_proc.poll() is None:
        try:
            _current_proc.terminate()
        except Exception:
            pass
    os._exit(0)


def main():
    global _current_proc

    port = _arg_value("--port")
    port = int(port) if port else _find_free_port()
    open_browser = "--no-browser" not in sys.argv

    # An explicit --port that is already taken means an older copy of the app is
    # still serving it. Streamlit would fail to bind and sit there doing nothing
    # while the browser keeps talking to that older process — which is how a
    # session ends up pointing at a database that has since been replaced. Hand
    # the user over to the instance that is actually running instead.
    if _port_in_use(port):
        print(f"Trade Log is already running at http://localhost:{port} - "
              f"opening that instance instead of starting a second one.")
        print("Close the running app first if you want a fresh start.")
        if open_browser:
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception:
                pass
        return

    if RESTART_SENTINEL.exists():
        RESTART_SENTINEL.unlink()

    for _sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(_sig, _shutdown)
        except (ValueError, OSError):
            pass  # not in main thread / unsupported platform

    if open_browser:
        _open_browser_later(f"http://localhost:{port}")

    # Let the app know it is supervised (so it can offer an automatic restart)
    # and on which port, so its reload script targets the right server.
    os.environ["TRADELOG_SUPERVISED"] = "1"
    os.environ["TRADELOG_PORT"] = str(port)

    while True:
        cmd = [
            sys.executable, "-m", "streamlit", "run", str(HERE / "app.py"),
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
            *_theme_flags(),
        ]
        _current_proc = subprocess.Popen(cmd)
        _current_proc.wait()

        # Streamlit exited. Relaunch only if the app requested a restart;
        # otherwise the user closed it and we should stop too.
        if RESTART_SENTINEL.exists():
            RESTART_SENTINEL.unlink()
            time.sleep(1.0)  # let the port fully release before rebinding
            continue
        break


if __name__ == "__main__":
    main()
