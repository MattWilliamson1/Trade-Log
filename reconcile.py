"""Compare the log's open positions with a broker's, broker as source of truth.

Pure functions only — no Streamlit, no DB. app.py loads the log's open trades
and a broker's position list (Schwab API, IB TWS/Gateway, or a positions CSV
exported from any broker), hands both here, and gets back one row per contract
saying whether the two agree and, if not, what change would make the log match.

Every position on either side is reduced to a *contract key* —
(instrument, ticker, expiration, strike, call/put) — and a *signed* quantity:
positive long, negative short, in shares or contracts. Several open log trades
on the same contract (scale-ins logged separately, or the same position split
across imports) sum into one position, because the broker only ever reports
the net.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import math
import re

QTY_TOL = 1e-6


# ── Contract keys ──────────────────────────────────────────────────────────────

def _norm_instrument(v) -> str:
    v = str(v or "stock").strip().lower()
    return v if v in ("option", "future") else "stock"


def _norm_date(v) -> str:
    """ISO YYYY-MM-DD from ISO, YYYYMMDD, or MM/DD/YYYY; '' when absent."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    s = str(v).strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if re.fullmatch(r"\d{6}", s):          # IB futures: YYYYMM
        return f"{s[:4]}-{s[4:]}"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return s[:10]


def _norm_strike(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 4)


def _norm_right(v) -> str:
    v = str(v or "").strip().upper()
    return "call" if v.startswith("C") else "put" if v.startswith("P") else ""


def contract_key(instrument_type, ticker, expiration=None, strike=None,
                 option_type=None) -> tuple:
    inst = _norm_instrument(instrument_type)
    tkr = str(ticker or "").strip().upper()
    if inst == "option":
        return (inst, tkr, _norm_date(expiration), _norm_strike(strike),
                _norm_right(option_type))
    if inst == "future":
        return (inst, tkr, _norm_date(expiration)[:7], None, "")
    return (inst, tkr, "", None, "")


def describe_key(key: tuple) -> str:
    inst, tkr, exp, strike, right = key
    if inst == "option":
        s = f"{strike:g}" if strike is not None else "?"
        return f"{tkr} {exp} {s} {right[:1].upper() or '?'}"
    if inst == "future":
        return f"{tkr} {exp} (future)" if exp else f"{tkr} (future)"
    return tkr


# ── Option symbol parsing ──────────────────────────────────────────────────────

# OCC, with or without the space padding Schwab's API uses: "AAPL  260918C00200000"
_OCC_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,5})\s*(\d{6})([CP])(\d{8})$")
# Fidelity positions export: "-AAPL260918C200" / " -SPY260918P552.5"
_FID_RE = re.compile(r"^-?([A-Z][A-Z0-9.]{0,5})(\d{6})([CP])(\d+(?:\.\d+)?)$")
# Schwab positions export: "AAPL 09/18/2026 200.00 C"
_SCHWAB_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,5})\s+(\d{2}/\d{2}/\d{4})\s+([\d.]+)\s+([CP])$")


def _yymmdd(s: str) -> str:
    return f"20{s[:2]}-{s[2:4]}-{s[4:6]}"


def parse_symbol(sym: str) -> dict:
    """Split a broker symbol into {instrument_type, ticker, expiration, strike,
    option_type}. Anything that isn't a recognised option format is a stock."""
    s = str(sym or "").strip().upper()
    m = _OCC_RE.match(s)
    if m:
        return {"instrument_type": "option", "ticker": m.group(1),
                "expiration": _yymmdd(m.group(2)), "strike": int(m.group(4)) / 1000.0,
                "option_type": "call" if m.group(3) == "C" else "put"}
    m = _FID_RE.match(s)
    if m:
        return {"instrument_type": "option", "ticker": m.group(1),
                "expiration": _yymmdd(m.group(2)), "strike": float(m.group(4)),
                "option_type": "call" if m.group(3) == "C" else "put"}
    m = _SCHWAB_RE.match(s)
    if m:
        return {"instrument_type": "option", "ticker": m.group(1),
                "expiration": _norm_date(m.group(2)), "strike": float(m.group(3)),
                "option_type": "call" if m.group(4) == "C" else "put"}
    return {"instrument_type": "stock", "ticker": s.lstrip("-").strip(),
            "expiration": None, "strike": None, "option_type": None}


# ── Positions CSV (any broker) ─────────────────────────────────────────────────

def _num(v) -> float | None:
    s = str(v if v is not None else "").strip()
    if not s or s in ("--", "-", "N/A", "n/a"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[,$£€\s()+]", "", s)
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def _find_col(header: list[str], *tests) -> int | None:
    low = [h.strip().lower() for h in header]
    for test in tests:
        for i, h in enumerate(low):
            if test(h):
                return i
    return None


_SKIP_SYMBOL = re.compile(r"(^|\b)(cash|total|pending|account)\b|\*\*$", re.I)


def parse_positions_csv(raw: bytes) -> tuple[list[dict], str]:
    """Read a positions export (Fidelity, Schwab, or a hand-made
    Symbol/Quantity/Average Price sheet). Returns (positions, error).

    The header row is found by content, not position, so title lines above it
    (Schwab) and disclaimer lines below the data (Fidelity) are skipped.
    """
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    hdr_idx = sym_c = qty_c = None
    for i, r in enumerate(rows[:40]):
        s = _find_col(r, lambda h: h == "symbol", lambda h: h.startswith("symbol"),
                      lambda h: h in ("ticker", "financial instrument", "instrument"))
        q = _find_col(r, lambda h: h == "quantity", lambda h: h.startswith("qty"),
                      lambda h: "quantity" in h, lambda h: h == "position")
        if s is not None and q is not None:
            hdr_idx, sym_c, qty_c = i, s, q
            break
    if hdr_idx is None:
        return [], ("Couldn't find a header row with a Symbol and a Quantity column. "
                    "The file needs at least those two.")
    header = rows[hdr_idx]
    avg_c = _find_col(header,
                      lambda h: "average cost" in h and "total" not in h,
                      lambda h: h in ("avg cost", "avg price", "average price", "cost/share",
                                      "cost per share", "price paid"),
                      lambda h: "avg" in h and ("cost" in h or "price" in h))
    acct_c = _find_col(header, lambda h: h == "account name", lambda h: h == "account number",
                       lambda h: h == "account")

    out: list[dict] = []
    for r in rows[hdr_idx + 1:]:
        if len(r) <= max(sym_c, qty_c):
            continue
        sym = r[sym_c].strip()
        qty = _num(r[qty_c])
        if not sym or qty is None or qty == 0 or _SKIP_SYMBOL.search(sym):
            continue
        p = parse_symbol(sym)
        if not p["ticker"]:
            continue
        # Fidelity writes a short option as "-AAPL…" with a negative quantity;
        # a leading dash alone never flips the sign.
        p.update({
            "quantity":    qty,
            "avg_price":   _num(r[avg_c]) if avg_c is not None and len(r) > avg_c else None,
            "multiplier":  100.0 if p["instrument_type"] == "option" else 1.0,
            "account":     r[acct_c].strip() if acct_c is not None and len(r) > acct_c else "",
            "description": sym,
        })
        out.append(p)
    if not out:
        return [], "Found the header row but no position rows under it."
    return out, ""


# ── Aggregation ────────────────────────────────────────────────────────────────

def log_positions(open_trades: list[dict]) -> dict[tuple, dict]:
    """Net the log's open trades per contract.

    Returns {key: {qty (signed), avg_price, multiplier, trades}}; ``trades`` is
    the contributing rows oldest first, which is the order a reduction closes
    them in (FIFO, like the brokers).
    """
    out: dict[tuple, dict] = {}
    for t in sorted(open_trades, key=lambda t: (str(t.get("entry_date") or ""), t.get("id") or 0)):
        qty = float(t.get("quantity") or 0)
        if abs(qty) < QTY_TOL:
            continue
        key = contract_key(t.get("instrument_type"), t.get("ticker"), t.get("expiration"),
                           t.get("strike"), t.get("option_type"))
        sign = -1.0 if str(t.get("side") or "long").lower() == "short" else 1.0
        p = out.setdefault(key, {"qty": 0.0, "cost": 0.0, "abs": 0.0,
                                 "multiplier": float(t.get("multiplier") or 1.0), "trades": []})
        p["qty"] += sign * qty
        p["cost"] += qty * float(t.get("entry_price") or 0)
        p["abs"] += qty
        p["trades"].append(t)
    for p in out.values():
        p["avg_price"] = p.pop("cost") / p["abs"] if p["abs"] else None
        p.pop("abs")
    return out


def broker_positions(positions: list[dict]) -> dict[tuple, dict]:
    """Net a broker position list per contract (a broker can list the same
    contract once per sub-account or tax lot)."""
    out: dict[tuple, dict] = {}
    for b in positions:
        qty = float(b.get("quantity") or 0)
        if abs(qty) < QTY_TOL:
            continue
        key = contract_key(b.get("instrument_type"), b.get("ticker"), b.get("expiration"),
                           b.get("strike"), b.get("option_type"))
        p = out.setdefault(key, {"qty": 0.0, "cost": 0.0, "priced": 0.0,
                                 "multiplier": float(b.get("multiplier") or 1.0)})
        p["qty"] += qty
        if b.get("avg_price") is not None:
            p["cost"] += abs(qty) * float(b["avg_price"])
            p["priced"] += abs(qty)
    for p in out.values():
        p["avg_price"] = p.pop("cost") / p["priced"] if p["priced"] else None
        p.pop("priced")
    return out


# ── Reconciliation ─────────────────────────────────────────────────────────────

MATCH, QTY, MISSING, EXTRA, FLIPPED, OFFSET = (
    "match", "qty_mismatch", "missing_in_log", "not_at_broker", "side_mismatch",
    "offsetting")

STATUS_LABEL = {
    MATCH:   "✅ Matches",
    QTY:     "⚠️ Quantity differs",
    MISSING: "➕ Missing from log",
    EXTRA:   "➖ Not held at broker",
    FLIPPED: "🔁 Long/short differs",
    OFFSET:  "🔀 Buy and sell both open",
}


def _is_short(t: dict) -> bool:
    return str(t.get("side") or "long").lower() == "short"


def plan_offsets(trades: list[dict]) -> list[dict]:
    """Pair open long trades against open short trades on the same contract.

    A broker never holds a long and a short on one contract at once, so when
    the log does, the later trade is the fill that closed the earlier one,
    imported as a new position instead of as its exit (IB's "today's trades"
    import does this for a same-day close). Walks the trades oldest first,
    FIFO: each later opposite trade closes the oldest still-open trade(s) at
    its own price and date. Returns [{open_id, close_id, qty, price, date}].
    """
    queue: list[list] = []          # [trade, qty left], all one side
    pairs: list[dict] = []
    for t in trades:
        left = float(t.get("quantity") or 0)
        while left > QTY_TOL and queue and _is_short(queue[0][0]) != _is_short(t):
            q = min(left, queue[0][1])
            pairs.append({"open_id": int(queue[0][0]["id"]), "close_id": int(t["id"]),
                          "qty": q, "price": float(t.get("entry_price") or 0),
                          "date": str(t.get("entry_date") or "")[:10]})
            queue[0][1] -= q
            left -= q
            if queue[0][1] <= QTY_TOL:
                queue.pop(0)
        if left > QTY_TOL:
            queue.append([t, left])
    return pairs


def implied_add_price(log_qty: float, log_avg, broker_qty: float, broker_avg):
    """Price for the extra shares that leaves the log's average cost equal to
    the broker's. Falls back to the broker's average when that would be
    non-positive (the broker's basis includes adjustments the log can't see)."""
    if broker_avg is None:
        return None
    diff = abs(broker_qty) - abs(log_qty)
    if diff <= QTY_TOL or log_avg is None:
        return broker_avg
    p = (abs(broker_qty) * broker_avg - abs(log_qty) * log_avg) / diff
    return round(p, 4) if p > 0 else broker_avg


def reconcile(log: dict[tuple, dict], broker: dict[tuple, dict]) -> list[dict]:
    """One row per contract on either side.

    Each row: key, contract, status, log_qty, broker_qty, log_avg, broker_avg,
    trades (log rows, oldest first), close_qty (to take off the log, >= 0) and
    add_qty (to put on, signed), multiplier.
    """
    rows = []
    for key in sorted(set(log) | set(broker), key=lambda k: (k[1], k[0], k[2], k[3] or 0, k[4])):
        lp, bp = log.get(key), broker.get(key)
        lq = lp["qty"] if lp else 0.0
        bq = bp["qty"] if bp else 0.0
        row = {
            "key": key, "contract": describe_key(key),
            "log_qty": lq, "broker_qty": bq,
            "log_avg": lp["avg_price"] if lp else None,
            "broker_avg": bp["avg_price"] if bp else None,
            "multiplier": (bp or lp)["multiplier"],
            "trades": lp["trades"] if lp else [],
            "close_qty": 0.0, "add_qty": 0.0,
        }
        if lp and len({_is_short(t) for t in lp["trades"]}) > 1:
            # Tidy the log's own contradiction first; any difference from the
            # broker that's left shows up on the next pass.
            row["status"], row["offsets"] = OFFSET, plan_offsets(lp["trades"])
        elif abs(lq - bq) < QTY_TOL:
            row["status"] = MATCH
        elif not lp:
            row["status"], row["add_qty"] = MISSING, bq
        elif abs(bq) < QTY_TOL:
            row["status"], row["close_qty"] = EXTRA, abs(lq)
        elif (lq > 0) != (bq > 0):
            row["status"], row["close_qty"], row["add_qty"] = FLIPPED, abs(lq), bq
        else:
            row["status"] = QTY
            if abs(bq) < abs(lq):
                row["close_qty"] = abs(lq) - abs(bq)
            else:
                row["add_qty"] = bq - lq
        rows.append(row)
    return rows


def plan_closes(trades: list[dict], close_qty: float) -> list[tuple[int, float, float]]:
    """FIFO split of a reduction across open trades: [(trade_id, qty, qty_held)]."""
    out, left = [], close_qty
    for t in trades:
        if left <= QTY_TOL:
            break
        held = float(t.get("quantity") or 0)
        take = min(held, left)
        out.append((int(t["id"]), take, held))
        left -= take
    return out


def option_expired(key: tuple, today: _dt.date | None = None) -> bool:
    if key[0] != "option" or not key[2]:
        return False
    try:
        return _dt.date.fromisoformat(key[2]) < (today or _dt.date.today())
    except ValueError:
        return False
