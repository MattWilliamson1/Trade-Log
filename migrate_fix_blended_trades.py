"""
migrate_fix_blended_trades.py
------------------------------
Removes 16 blended trade records created before the cycle-splitting fix and
replaces them with the correct individual trades parsed from the most recent
Flex XML.  Any tags attached to a blended record are re-applied to ALL of its
replacement trades so nothing is lost.

Run from the project root:
    python migrate_fix_blended_trades.py

A backup is written to backups/pre_migration_fix_blended.db before any changes.
"""

import os, shutil, sqlite3, sys, xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT    = Path(__file__).parent
DB_PATH = Path(os.environ.get("TRADELOG_DB", ROOT / "tradelog.db"))
XML     = ROOT / "imports" / "flex_20260524_124501.xml"

BAD_IDS = [1746, 1747, 1770, 1777, 1784, 1785, 1807, 1954,
           2042, 2043, 2055, 2056, 2057, 2058, 2061, 2073]

# ── helpers ────────────────────────────────────────────────────────────────────

def _p(v):
    return f"${float(v):.4f}" if v is not None else "—"

def _record_key(r):
    """Canonical key that matches blended DB records to XML trade groups."""
    return (
        str(r.get("ticker", "") or ""),
        str(r.get("instrument_type") or "stock"),
        str(r.get("expiration") or ""),
        str(round(float(r.get("strike") or 0), 2)),
        str(r.get("option_type") or ""),
    )

def _to_iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    s = str(v)
    return s[:10] if s else None

# ── backup ─────────────────────────────────────────────────────────────────────

def backup():
    dest = ROOT / "backups" / "pre_migration_fix_blended.db"
    dest.parent.mkdir(exist_ok=True)
    shutil.copy2(DB_PATH, dest)
    print(f"Backup written -> {dest}")

# ── read existing state ────────────────────────────────────────────────────────

def load_bad_records(conn):
    rows = conn.execute(f"""
        SELECT id, ticker, entry_date, quantity, entry_price,
               exit_date, exit_price, instrument_type,
               expiration, strike, option_type, multiplier, side, notes
        FROM trades WHERE id IN ({','.join(map(str, BAD_IDS))})
    """).fetchall()
    return {r["id"]: dict(r) for r in rows}

def load_tags_for_bad(conn):
    """Return {trade_id: [tag_id, ...]} for the bad records."""
    rows = conn.execute(f"""
        SELECT trade_id, tag_id FROM trade_tags
        WHERE trade_id IN ({','.join(map(str, BAD_IDS))})
    """).fetchall()
    out = defaultdict(list)
    for r in rows:
        out[r["trade_id"]].append(r["tag_id"])
    return dict(out)

def load_tag_names(conn):
    rows = conn.execute("SELECT id, name FROM tags").fetchall()
    return {r["id"]: r["name"] for r in rows}

# ── XML parsing ────────────────────────────────────────────────────────────────

def get_xml_replacements():
    sys.path.insert(0, str(ROOT))
    import ib_client
    tree = ET.parse(XML)
    trades = ib_client.parse_flex_trades(tree.getroot())
    by_key = defaultdict(list)
    for t in trades:
        by_key[_record_key(t)].append(t)
    return by_key

# ── insert one trade, return new ID ───────────────────────────────────────────

def insert_trade(conn, t, tag_ids):
    cur = conn.execute("""
        INSERT INTO trades (
            entry_date, ticker, quantity, entry_price,
            exit_date, exit_price, notes,
            stop_enabled, opening_stop, current_stop,
            instrument_type, expiration, strike, option_type,
            multiplier, side, leg_group, leg_label, spread_type,
            commission, account_name
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        _to_iso(t.get("entry_date")),
        str(t["ticker"]).upper().strip(),
        float(t["quantity"]) if t.get("quantity") else None,
        float(t["entry_price"]) if t.get("entry_price") is not None else None,
        _to_iso(t.get("exit_date")),
        float(t["exit_price"]) if t.get("exit_price") is not None else None,
        t.get("notes") or "Imported via Flex Query",
        0,    # stop_enabled
        None, # opening_stop
        None, # current_stop
        t.get("instrument_type") or "stock",
        _to_iso(t.get("expiration")),
        float(t["strike"]) if t.get("strike") else None,
        t.get("option_type") or None,
        float(t.get("multiplier") or 1.0),
        t.get("side") or "long",
        t.get("leg_group") or None,
        t.get("leg_label") or None,
        t.get("spread_type") or None,
        float(t.get("commission") or 0.0),
        "Default",
    ))
    new_id = cur.lastrowid

    # Re-apply tags
    for tid in tag_ids:
        conn.execute(
            "INSERT OR IGNORE INTO trade_tags (trade_id, tag_id) VALUES (?,?)",
            (new_id, tid),
        )

    # Seed opening trade lot (mirrors add_trade behaviour)
    ep = t.get("entry_price")
    qty = t.get("quantity")
    ed  = t.get("entry_date")
    if ed and ep and qty:
        conn.execute(
            "INSERT INTO trade_lots (trade_id, date, quantity, price, lot_type) VALUES (?,?,?,?,?)",
            (new_id, _to_iso(ed), float(qty), float(ep), "open"),
        )

    return new_id

# ── main ───────────────────────────────────────────────────────────────────────

def run():
    if not DB_PATH.exists():
        sys.exit(f"Database not found: {DB_PATH}")
    if not XML.exists():
        sys.exit(f"XML file not found: {XML}")

    backup()

    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    bad_records  = load_bad_records(conn)
    tags_by_trade = load_tags_for_bad(conn)
    tag_names    = load_tag_names(conn)
    xml_by_key   = get_xml_replacements()

    if len(bad_records) != len(BAD_IDS):
        found = set(bad_records.keys())
        missing = [i for i in BAD_IDS if i not in found]
        print(f"WARNING: {len(missing)} expected record(s) not found in DB "
              f"(already deleted?): {missing}")

    print(f"\nProcessing {len(bad_records)} blended record(s)...\n")

    total_deleted  = 0
    total_inserted = 0
    total_tags     = 0

    try:
        conn.execute("BEGIN")

        for bad_id, rec in sorted(bad_records.items(),
                                  key=lambda x: (x[1]["ticker"], str(x[1]["entry_date"]))):
            key          = _record_key(rec)
            replacements = xml_by_key.get(key, [])
            saved_tags   = tags_by_trade.get(bad_id, [])
            tag_label    = (", ".join(tag_names.get(t, str(t)) for t in saved_tags)
                            if saved_tags else "none")

            print(f"  DELETE  ID={bad_id}  {rec['ticker']}  [{rec['instrument_type']}]"
                  f"  entry={rec['entry_date']}  qty={rec['quantity']}"
                  f"  @ {_p(rec['entry_price'])}  tags=[{tag_label}]")

            if not replacements:
                print(f"    WARNING: no XML replacements found — skipping delete to be safe.")
                continue

            # Delete (cascade removes trade_tags and trade_lots)
            conn.execute("DELETE FROM trades WHERE id=?", (bad_id,))
            total_deleted += 1

            # Insert replacements
            for t in replacements:
                new_id = insert_trade(conn, t, saved_tags)
                total_inserted += 1
                total_tags     += len(saved_tags)
                ep  = _p(t.get("entry_price"))
                xp  = _p(t.get("exit_price"))
                print(f"    + inserted ID={new_id}  entry={t.get('entry_date')}"
                      f"  qty={t['quantity']}  @ {ep}  exit={t.get('exit_date')} @ {xp}"
                      + (f"  tags=[{tag_label}]" if saved_tags else ""))

        conn.execute("COMMIT")
        print(f"\nDone — deleted {total_deleted}, inserted {total_inserted},"
              f" re-applied {total_tags} tag assignment(s).")

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\nERROR — rolled back: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
