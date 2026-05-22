import atexit
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

# Override with TRADELOG_DB env var to point at a different database
# (used by launch_demo.bat to run against demo/tradelog_demo.db)
DB_PATH = Path(os.environ.get("TRADELOG_DB", Path(__file__).parent / "tradelog.db"))
BACKUP_DIR = Path(__file__).parent / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
BACKUP_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB


def _do_backup():
    """Copy the DB to backup-YYYY-MM-DD.db if it exists and is under the size limit."""
    if not DB_PATH.exists():
        return
    if DB_PATH.stat().st_size > BACKUP_SIZE_LIMIT:
        return
    dest = BACKUP_DIR / f"backup-{date.today().isoformat()}.db"
    try:
        shutil.copy2(DB_PATH, dest)
    except Exception:
        pass


atexit.register(_do_backup)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date   TEXT,
    ticker       TEXT,
    quantity     REAL,
    entry_price  REAL,
    exit_date    TEXT,
    exit_price   REAL,
    notes        TEXT,
    stop_enabled INTEGER DEFAULT 1,
    opening_stop REAL,
    current_stop REAL
);

CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS trade_tags (
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    tag_id   INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (trade_id, tag_id)
);

CREATE TABLE IF NOT EXISTS trade_attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    filepath    TEXT NOT NULL,
    uploaded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_prices (
    ticker TEXT NOT NULL,
    date   TEXT NOT NULL,
    close  REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS cash_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    type        TEXT NOT NULL,
    amount      REAL NOT NULL,
    description TEXT,
    source      TEXT DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS accounts (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

INSERT OR IGNORE INTO accounts (name) VALUES ('Default');

CREATE TABLE IF NOT EXISTS equity_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT UNIQUE NOT NULL,
    balance       REAL NOT NULL,
    contributions REAL DEFAULT 0,
    withdrawals   REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS trading_plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_at      TEXT DEFAULT (datetime('now')),
    ticker        TEXT,
    sentiment     TEXT,
    rationale     TEXT,
    fundamentals  TEXT,
    technicals    TEXT,
    trade_type    TEXT,
    hold_time     TEXT,
    entry_signal  TEXT,
    confirm1      TEXT,
    confirm2      TEXT,
    entry_price   REAL,
    profit_target REAL,
    stop_loss     REAL,
    rr_ratio      REAL
);

CREATE TABLE IF NOT EXISTS trading_plan_attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER NOT NULL REFERENCES trading_plans(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    filepath    TEXT NOT NULL,
    uploaded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_lots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id  INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    date      TEXT NOT NULL,
    quantity  REAL NOT NULL,
    price     REAL NOT NULL,
    lot_type  TEXT DEFAULT 'buy',
    notes     TEXT
);

CREATE TABLE IF NOT EXISTS trade_dividends (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id         INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    ex_date          TEXT NOT NULL,
    amount_per_share REAL NOT NULL,
    quantity         REAL,
    total_amount     REAL,
    notes            TEXT
);
"""

# Columns added after initial release — safe to run on existing databases
MIGRATIONS = [
    ("trades", "notes",           "TEXT"),
    ("trades", "stop_enabled",    "INTEGER DEFAULT 1"),
    ("trades", "opening_stop",    "REAL"),
    ("trades", "current_stop",    "REAL"),
    # options / futures
    ("trades", "instrument_type", "TEXT DEFAULT 'stock'"),
    ("trades", "expiration",      "TEXT"),
    ("trades", "strike",          "REAL"),
    ("trades", "option_type",     "TEXT"),
    ("trades", "multiplier",      "REAL DEFAULT 1"),
    ("trades", "leg_group",       "TEXT"),
    ("trades", "leg_label",       "TEXT"),
    ("trades", "side",            "TEXT DEFAULT 'long'"),
    # chart & earnings
    ("trades", "chart_notes",     "TEXT"),
    ("trades", "earnings_date",   "TEXT"),
    # options greeks (populated by IB)
    ("trades", "delta",           "REAL"),
    ("trades", "theta",           "REAL"),
    # spread grouping
    ("trades", "spread_type",     "TEXT"),
    # commissions and execution detail
    ("trades", "commission",                "REAL DEFAULT 0"),
    ("trades", "underlying_price_at_entry", "REAL"),
    ("trades", "account_name",             "TEXT DEFAULT 'Default'"),
    # rolling options
    ("trades", "roll_group",               "TEXT"),
    # multi-currency
    ("trades", "native_currency",          "TEXT DEFAULT 'USD'"),
    ("trades", "fx_rate_entry",            "REAL DEFAULT 1.0"),
    ("trades", "fx_rate_exit",             "REAL DEFAULT 1.0"),
    # trailing stop
    ("trades", "trail_type",               "TEXT DEFAULT 'fixed'"),
    ("trades", "trail_amount",             "REAL"),
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_trades_entry_date      ON trades(entry_date)",
    "CREATE INDEX IF NOT EXISTS idx_trades_exit_date       ON trades(exit_date)",
    "CREATE INDEX IF NOT EXISTS idx_trades_instrument_type ON trades(instrument_type)",
    "CREATE INDEX IF NOT EXISTS idx_trade_tags_trade_id    ON trade_tags(trade_id)",
    "CREATE INDEX IF NOT EXISTS idx_trade_lots_trade_id    ON trade_lots(trade_id)",
    "CREATE INDEX IF NOT EXISTS idx_trade_divs_trade_id    ON trade_dividends(trade_id)",
]


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        # Add any columns that don't exist yet (idempotent)
        for table, col, typedef in MIGRATIONS:
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        for idx_sql in INDEXES:
            conn.execute(idx_sql)
    # Startup backup: once per calendar day if DB is under size limit
    today_backup = BACKUP_DIR / f"backup-{date.today().isoformat()}.db"
    if not today_backup.exists():
        _do_backup()


def is_duplicate_trade(
    ticker: str,
    entry_date,
    quantity,
    entry_price,
    instrument_type: str = "stock",
    expiration=None,
    strike=None,
) -> bool:
    """Return True if a trade with the same key fields already exists.

    Numeric columns use small tolerances to absorb float precision drift.
    Expiration and strike are only checked when provided (non-None).
    """
    if not ticker or entry_date is None or quantity is None or entry_price is None:
        return False
    entry_iso = (
        entry_date.isoformat() if hasattr(entry_date, "isoformat") else str(entry_date)[:10]
    )
    qty_f   = float(quantity)
    price_f = float(entry_price)
    with get_connection() as conn:
        if expiration and strike is not None:
            row = conn.execute(
                """SELECT 1 FROM trades
                   WHERE ticker = ?
                     AND entry_date = ?
                     AND ABS(quantity    - ?) < 0.001
                     AND ABS(entry_price - ?) < 0.0001
                     AND LOWER(COALESCE(instrument_type,'stock')) = LOWER(?)
                     AND expiration = ?
                     AND ABS(COALESCE(strike, 0) - ?) < 0.01
                   LIMIT 1""",
                (ticker.upper().strip(), entry_iso, qty_f, price_f,
                 instrument_type or "stock", str(expiration)[:10], float(strike)),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT 1 FROM trades
                   WHERE ticker = ?
                     AND entry_date = ?
                     AND ABS(quantity    - ?) < 0.001
                     AND ABS(entry_price - ?) < 0.0001
                     AND LOWER(COALESCE(instrument_type,'stock')) = LOWER(?)
                   LIMIT 1""",
                (ticker.upper().strip(), entry_iso, qty_f, price_f,
                 instrument_type or "stock"),
            ).fetchone()
    return row is not None


def find_open_trade_id(
    ticker: str,
    entry_date,
    quantity,
    entry_price,
    instrument_type: str = "stock",
    expiration=None,
    strike=None,
) -> int | None:
    """Return the ID of a matching trade that is still open (no exit_date), or None."""
    if not ticker or entry_date is None or quantity is None or entry_price is None:
        return None
    entry_iso = (
        entry_date.isoformat() if hasattr(entry_date, "isoformat") else str(entry_date)[:10]
    )
    qty_f   = float(quantity)
    price_f = float(entry_price)
    with get_connection() as conn:
        if expiration and strike is not None:
            row = conn.execute(
                """SELECT id FROM trades
                   WHERE ticker = ?
                     AND entry_date = ?
                     AND ABS(quantity    - ?) < 0.001
                     AND ABS(entry_price - ?) < 0.0001
                     AND LOWER(COALESCE(instrument_type,'stock')) = LOWER(?)
                     AND expiration = ?
                     AND ABS(COALESCE(strike, 0) - ?) < 0.01
                     AND (exit_date IS NULL OR exit_date = '')
                   LIMIT 1""",
                (ticker.upper().strip(), entry_iso, qty_f, price_f,
                 instrument_type or "stock", str(expiration)[:10], float(strike)),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT id FROM trades
                   WHERE ticker = ?
                     AND entry_date = ?
                     AND ABS(quantity    - ?) < 0.001
                     AND ABS(entry_price - ?) < 0.0001
                     AND LOWER(COALESCE(instrument_type,'stock')) = LOWER(?)
                     AND (exit_date IS NULL OR exit_date = '')
                   LIMIT 1""",
                (ticker.upper().strip(), entry_iso, qty_f, price_f,
                 instrument_type or "stock"),
            ).fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    init_db()
    print(f"Database ready at {DB_PATH}")
