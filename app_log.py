"""App-wide status / error log, shown on Settings → 🧾 Log.

One plain-text file per install, `logs/tradelog.log` next to the app, rotated
at 1 MB with three old files kept, so it can never grow without bound. Each
line is

    2026-11-04 12:34:56 | ERROR | IB | Connection failed: ... | <detail>

with newlines in the message/detail escaped, so one event is always one line
and the reader never has to guess where an entry ends. `detail` carries a
traceback or raw broker text that's useful when troubleshooting but too long
for the table.

Pure Python, no Streamlit: ib_client.py logs from here too. Every public
function swallows its own failures, so a full disk or locked file can never
take the app down with it.

Repeated identical events (an IB connection that fails on every rerun while
TWS is closed) are rate-limited per (category, message) so they don't bury
everything else.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "tradelog.log"
_MAX_BYTES = 1_000_000
_BACKUPS = 3
_SEP = " | "
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

_lock = threading.Lock()
_logger: logging.Logger | None = None
_last_seen: dict[tuple, float] = {}
_REPEAT_WINDOW_S = 300


def _esc(v) -> str:
    return str(v or "").replace("\r", "").replace("\\", "\\\\").replace("\n", "\\n").replace(" | ", " ¦ ")


def _unesc(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\\\", "\\")


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    with _lock:
        if _logger is None:
            lg = logging.getLogger("tradelog.app")
            lg.setLevel(logging.DEBUG)
            lg.propagate = False
            if not lg.handlers:
                LOG_DIR.mkdir(exist_ok=True)
                h = RotatingFileHandler(LOG_FILE, maxBytes=_MAX_BYTES,
                                        backupCount=_BACKUPS, encoding="utf-8")
                h.setFormatter(logging.Formatter("%(message)s"))
                lg.addHandler(h)
                _attach_library_loggers(h)
            _logger = lg
    return _logger


class _LibraryHandler(logging.Handler):
    """Forwards third-party warnings (ib_insync's API error codes, e.g. 326
    'client id already in use' or 502 'couldn't connect') into log(), so the
    single file handler above is the only thing that ever opens the file —
    two handlers on one file can't rotate it on Windows."""

    _tradelog = True

    def emit(self, record):
        lvl = record.levelname if record.levelname in LEVELS else "WARNING"
        log(lvl, "IB API", record.getMessage())


def _attach_library_loggers(_main_handler: RotatingFileHandler) -> None:
    for name in ("ib_insync",):
        lg = logging.getLogger(name)
        if not any(getattr(x, "_tradelog", False) for x in lg.handlers):
            h = _LibraryHandler(level=logging.WARNING)
            lg.addHandler(h)
            if lg.level == logging.NOTSET or lg.level > logging.WARNING:
                lg.setLevel(logging.WARNING)


def log(level: str, category: str, message: str, detail: str = "",
        dedupe: bool = True) -> None:
    """Record one event. level: DEBUG/INFO/WARNING/ERROR. category: a short
    area name shown as its own column (IB, Flex, Schwab, Import, Sync...)."""
    try:
        level = level.upper() if level and level.upper() in LEVELS else "INFO"
        if dedupe:
            key = (level, category, message)
            now = time.time()
            with _lock:
                if now - _last_seen.get(key, 0) < _REPEAT_WINDOW_S:
                    return
                _last_seen[key] = now
        line = _SEP.join([time.strftime("%Y-%m-%d %H:%M:%S"), level,
                          _esc(category), _esc(message), _esc(detail)])
        _get_logger().log(getattr(logging, level), line)
    except Exception:
        pass


def info(category: str, message: str, detail: str = "") -> None:
    log("INFO", category, message, detail, dedupe=False)


def warning(category: str, message: str, detail: str = "") -> None:
    log("WARNING", category, message, detail)


def error(category: str, message: str, detail: str = "") -> None:
    log("ERROR", category, message, detail)


def exception(category: str, message: str, exc: BaseException | None = None) -> None:
    """ERROR with the exception text in the message and its traceback as detail."""
    try:
        if exc is not None:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            text = str(exc).strip() or type(exc).__name__
            log("ERROR", category, f"{message}: {text}" if message else text, tb)
        else:
            log("ERROR", category, message, traceback.format_exc())
    except Exception:
        pass


def read_entries(limit: int = 2000) -> list[dict]:
    """Newest first: [{time, level, category, message, detail}], reading the
    current file and its rotated predecessors until `limit` entries."""
    out: list[dict] = []
    files = [LOG_FILE] + [LOG_FILE.with_name(f"{LOG_FILE.name}.{i}") for i in range(1, _BACKUPS + 1)]
    for f in files:
        if len(out) >= limit:
            break
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except (FileNotFoundError, OSError):
            continue
        for ln in reversed(lines):
            parts = ln.split(_SEP, 4)
            if len(parts) < 4:
                continue
            parts += [""] * (5 - len(parts))
            out.append({
                "time": parts[0], "level": parts[1], "category": _unesc(parts[2]),
                "message": _unesc(parts[3]), "detail": _unesc(parts[4]),
            })
            if len(out) >= limit:
                break
    return out


def log_text() -> str:
    """Whole log (oldest first) as one text blob, for the download button."""
    chunks = []
    for i in range(_BACKUPS, 0, -1):
        f = LOG_FILE.with_name(f"{LOG_FILE.name}.{i}")
        try:
            chunks.append(f.read_text(encoding="utf-8", errors="replace"))
        except (FileNotFoundError, OSError):
            pass
    try:
        chunks.append(LOG_FILE.read_text(encoding="utf-8", errors="replace"))
    except (FileNotFoundError, OSError):
        pass
    return "".join(chunks)


def clear() -> None:
    """Empty the log (current and rotated files)."""
    try:
        lg = _get_logger()
        for h in lg.handlers:
            try:
                h.acquire()
                h.stream.seek(0)       # type: ignore[attr-defined]
                h.stream.truncate()    # type: ignore[attr-defined]
            finally:
                h.release()
        for i in range(1, _BACKUPS + 1):
            LOG_FILE.with_name(f"{LOG_FILE.name}.{i}").unlink(missing_ok=True)
        with _lock:
            _last_seen.clear()
    except Exception:
        pass
