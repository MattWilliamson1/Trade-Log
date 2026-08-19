"""
seed_demo.py — recreate demo/tradelog_demo.db with ~200 realistic dummy trades.

Run directly:    python seed_demo.py
Run via launcher: launch_demo.bat calls this automatically before starting Streamlit.
"""
import os
import sys
import uuid
import random
import math
import datetime as _dt
from pathlib import Path
from datetime import date, timedelta

DEMO_DB = Path(__file__).parent / "demo" / "tradelog_demo.db"
DEMO_DB.parent.mkdir(exist_ok=True)

os.environ["TRADELOG_DB"] = str(DEMO_DB)

if DEMO_DB.exists():
    DEMO_DB.unlink()

sys.path.insert(0, str(Path(__file__).parent))
from db import init_db, get_connection  # noqa: E402

init_db()

# ── Constants ─────────────────────────────────────────────────────────────────

TODAY = date(2026, 5, 20)
START = date(2025, 5, 20)   # 1 year of history

random.seed(42)

def iso(d: date) -> str:
    return d.isoformat()

def bday(d: date, n: int) -> date:
    """Advance d by n business days (negative = backward)."""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if d.weekday() < 5:
            remaining -= 1
    return d

def rand_bday(start: date, end: date) -> date:
    """Return a random business day between start and end inclusive."""
    days = (end - start).days
    for _ in range(200):
        d = start + timedelta(days=random.randint(0, days))
        if d.weekday() < 5:
            return d
    return start

# ── Account / risk model ───────────────────────────────────────────────────────
# Every trade is sized so its OPEN RISK — (entry − stop) × shares for stocks, or
# the defined max-loss for options — is a consistent fraction of the account. This
# is what makes the demo's numbers hang together: normalized risk in, a believable
# equity curve out.

STARTING_EQUITY = 25_000.0
CONTRIB_AMT     = 500.0          # monthly contribution
RISK_PCT        = 0.005          # 0.5% of account risked per trade

def first_bdays_of_months(start: date, end: date) -> list:
    """First business day of each month strictly after `start`'s month, up to `end`."""
    out = []
    y, m = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    while True:
        d = date(y, m, 1)
        if d > end:
            break
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if start <= d <= end:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out

CONTRIB_DATES = first_bdays_of_months(START, TODAY)

def ref_equity(d: date) -> float:
    """Account value for risk sizing — starting equity plus contributions to date.

    Deliberately excludes trading P&L so position sizing stays independent of the
    (later, trade-derived) equity curve rather than circular with it.
    """
    n = sum(1 for cd in CONTRIB_DATES if cd <= d)
    return STARTING_EQUITY + CONTRIB_AMT * n

def trade_risk_dollars(d: date) -> float:
    """Target open risk for a trade entered on `d`: 0.5% of account, lightly jittered."""
    return ref_equity(d) * RISK_PCT * random.uniform(0.85, 1.15)

# ── Tags ─────────────────────────────────────────────────────────────────────

TAGS = [
    ("Breakout",       "Price breaks above a key resistance level"),
    ("Swing",          "Multi-day swing trade"),
    ("Earnings Play",  "Trade around a scheduled earnings release"),
    ("Options Income", "Sell premium for income (spreads, covered calls)"),
    ("Speculative",    "Higher-risk, smaller position size"),
]

EXTRA_TAGS = [
    ("Mean Reversion", "Fade an extended move back toward the average"),
    ("High Conviction","Thesis with multiple confirming factors"),
    ("Sector Rotation","Capital flowing into an underweighted sector"),
]

with get_connection() as conn:
    for name, desc in TAGS + EXTRA_TAGS:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?,?)", (name, desc))

with get_connection() as conn:
    tag_rows = conn.execute("SELECT id, name FROM tags").fetchall()
tag_id = {row["name"]: row["id"] for row in tag_rows}

# Only the 5 preset tags are randomly applied to trades
PRESET_TAG_NAMES = [t[0] for t in TAGS]

def rand_tags(n_min=1, n_max=2):
    k = random.randint(n_min, min(n_max, len(PRESET_TAG_NAMES)))
    return random.sample(PRESET_TAG_NAMES, k)

# ── Settings ──────────────────────────────────────────────────────────────────

with get_connection() as conn:
    for k, v in {
        "account_balance":      "25000",  # placeholder — recomputed from trades at the end
        "starting_equity":      "25000",
        "starting_date":        iso(START),
        "euro_dates":           "0",
        "app_mode":             "demo",
        "app_theme":            "warm_sand",
        "col_order":            '["Entry Date", "Ticker", "Quantity", "Entry Price", "Live Price", "P&L", "Unrealized P&L %", "Open Risk", "Opening Risk", "% of Account", "Tags"]',
        "native_currency":      "USD",
        "currency_mode":        "0",
        "pct_account_yellow":   "5",
        "pct_account_red":      "10",
        "stop_dist_unit":       "%",
        "stop_dist_yellow":     "5",
        "stop_dist_red":        "2",
        "row_color_enabled":    "1",
        "row_color_style":      "text",
        "color_open_profit":    "#2ecc71",
        "color_open_loss":      "#e74c3c",
        "color_closed_profit":  "#27ae60",
        "color_closed_loss":    "#c0392b",
        "default_commission":   "0",
        "options_commission":   "0.65",
        "futures_commission":   "2.25",
        "broker":               "ib",
        "ib_host":              "127.0.0.1",
        "ib_port":              "7497",
        "ib_client_id":         "1",
        "ib_use_live_prices":   "0",
        "ib_auto_sync_balance": "0",
        "ib_auto_connect":      "0",
    }.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, v))

# ── Helpers ───────────────────────────────────────────────────────────────────

def add_trade(conn, **kw) -> int:
    cols = list(kw.keys())
    vals = list(kw.values())
    placeholders = ",".join("?" * len(cols))
    col_str = ",".join(cols)
    cur = conn.execute(
        f"INSERT INTO trades ({col_str}) VALUES ({placeholders})", vals
    )
    return cur.lastrowid

def tag_trade(conn, trade_id: int, *tag_names):
    for name in tag_names:
        tid = tag_id.get(name)
        if tid:
            conn.execute(
                "INSERT OR IGNORE INTO trade_tags (trade_id, tag_id) VALUES (?,?)",
                (trade_id, tid),
            )

# ── Stock Universe ────────────────────────────────────────────────────────────
# (ticker, base_price, typical_qty)
STOCKS = [
    ("AAPL",  210,  40),  ("MSFT",  420,  20),  ("NVDA",  900,  10),
    ("META",  580,  15),  ("AMZN",  220,  35),  ("TSLA",  320,  25),
    ("GOOG",  195,  30),  ("AMD",   155,  50),  ("INTC",   25, 200),
    ("JPM",   250,  30),  ("BAC",    44, 150),  ("GS",    600,  12),
    ("MS",    110,  60),  ("XOM",   118,  55),  ("CVX",   162,  40),
    ("LLY",   800,   8),  ("JNJ",   157,  40),  ("PFE",    28, 200),
    ("MRNA",   70, 100),  ("COST",  920,   8),  ("WMT",    90,  75),
    ("TGT",   140,  45),  ("HD",    385,  15),  ("LOW",   250,  25),
    ("NFLX",  880,   8),  ("DIS",   100,  65),  ("SPOT",  360,  18),
    ("ROKU",   70, 100),  ("PYPL",   70,  90),  ("V",     300,  20),
    ("MA",    470,  15),  ("UBER",   82,  80),  ("CRM",   320,  20),
    ("NOW",   980,   7),  ("SNOW",  165,  35),  ("PLTR",   90,  80),
    ("DDOG",  125,  50),  ("SHOP",  115,  55),  ("MU",    110,  55),
    ("COIN",  270,  25),  ("RIVN",   14, 350),  ("BYND",    7, 400),
    ("SPY",   580,  15),  ("QQQ",   490,  12),  ("IWM",   210,  30),
    ("GLD",   260,  25),  ("SLV",    30, 150),
]

STOCK_MAP = {t: (p, q) for t, p, q in STOCKS}

def gen_stock_trade(conn, *, open_pos=False):
    ticker, base, base_qty = random.choice(STOCKS)
    side = "long" if random.random() < 0.85 else "short"

    # entry date: distributed across the year; open trades cluster near end
    if open_pos:
        ed = rand_bday(bday(TODAY, -25), bday(TODAY, -2))
    else:
        ed = rand_bday(START, bday(TODAY, -30))

    # price with ±15% noise around base
    ep = round(base * random.uniform(0.85, 1.15), 2)

    # stop: 4–8% below entry for longs, above for shorts; opening stop is never edited
    stop_pct = random.uniform(0.04, 0.08)
    stop = round(ep * (1 - stop_pct) if side == "long" else ep * (1 + stop_pct), 2)

    # quantity is sized FROM the risk, not the other way round: pick shares so that
    # open risk = (entry − stop) × shares ≈ the 0.5%-of-account target. Round to a
    # clean lot without letting the rounding distort the risk much.
    risk_per_share = abs(ep - stop)
    raw_qty = trade_risk_dollars(ed) / risk_per_share if risk_per_share else 0
    if   raw_qty >= 200: qty = max(10, round(raw_qty / 10) * 10)
    elif raw_qty >= 40:  qty = max(5,  round(raw_qty / 5) * 5)
    else:                qty = max(1,  round(raw_qty))

    # current stop only ever trails toward entry (locking in), never loosens away from it
    trail = random.uniform(0.0, 0.6)            # 0 = untouched, 1 = pulled up to entry
    cur_stop = round(stop + (ep - stop) * trail, 2)

    commission = round(qty * 0.005, 2)

    trade_kw = dict(
        entry_date=iso(ed),
        ticker=ticker,
        quantity=qty,
        entry_price=ep,
        instrument_type="stock",
        side=side,
        opening_stop=stop,
        current_stop=cur_stop,
        stop_enabled=1,
        commission=commission,
        notes=f"Demo {'open' if open_pos else 'closed'} — {ticker}",
    )

    if not open_pos:
        hold = random.randint(2, 30)
        xd = bday(ed, hold)
        if xd >= TODAY:
            xd = bday(TODAY, -1)

        # exit price: ~55% win-rate. Both winners and losers are expressed as a
        # multiple of the trade's own risk-per-share, so results scale with the
        # (normalized) risk taken and R-multiples stay in a believable band.
        rps = abs(ep - stop)                    # 1R, per share
        win = random.random() < 0.55
        if win:
            r_mult = random.uniform(0.4, 1.8)   # winners run ~0.4R–1.8R
            xp = ep + rps * r_mult if side == "long" else ep - rps * r_mult
        else:
            # a loss never runs far past the stop — at/near it (a touch of slippage)
            # or a smaller discretionary loss between entry and the stop
            frac = random.uniform(0.4, 1.05)    # 1.0 = right at the opening stop
            xp = ep - rps * frac if side == "long" else ep + rps * frac
        xp = round(max(0.01, xp), 2)
        trade_kw["exit_date"]  = iso(xd)
        trade_kw["exit_price"] = xp

    tid = add_trade(conn, **trade_kw)
    tag_trade(conn, tid, *rand_tags(1, 2))
    return tid

# Generate 130 closed + 20 open stock trades = 150 total
with get_connection() as conn:
    for _ in range(130):
        gen_stock_trade(conn, open_pos=False)
    for _ in range(20):
        gen_stock_trade(conn, open_pos=True)

# ── Option helpers ────────────────────────────────────────────────────────────

def add_option_leg(conn, ticker, ed, xd, side, qty, ep, xp,
                   strike, expiry, opt_type, leg_group, leg_label, mult=100, spread_type=None):
    commission = round(qty * 0.65, 2)
    kw = dict(
        entry_date=iso(ed),
        ticker=ticker,
        quantity=qty,
        entry_price=ep,
        instrument_type="option",
        side=side,
        opening_stop=None,
        current_stop=None,
        stop_enabled=0,
        strike=strike,
        expiration=iso(expiry),
        option_type=opt_type,
        multiplier=mult,
        leg_group=leg_group,
        leg_label=leg_label,
        commission=commission,
        notes="Demo options trade",
    )
    if spread_type:
        kw["spread_type"] = spread_type
    if xd:
        kw["exit_date"]  = iso(xd)
        kw["exit_price"] = xp
    return add_trade(conn, **kw)

def new_grp():
    return str(uuid.uuid4())[:8]

# ── Options: defined-risk, risk-normalized ────────────────────────────────────
# Options don't have a stop, so their "open risk" is the defined max loss of the
# structure (debit paid, or width − credit for verticals). Each position is sized
# so that max loss ≈ the same 0.5%-of-account target as the stock trades — on a
# ~$25k account that floors most structures at 1 contract. Outcomes are expressed
# in R (multiples of that max risk), and the leg premiums are derived from R so the
# recorded P&L always equals R × risk.

OPT_MULT = 100.0

def _opt_qty(per_contract_risk: float, ed: date) -> int:
    """Contracts so that per-contract risk × qty ≈ the account risk target (min 1)."""
    if per_contract_risk <= 0:
        return 1
    return max(1, round(trade_risk_dollars(ed) / per_contract_risk))

def _tail() -> float:
    """A small residual premium for a leg that expires near-worthless."""
    return round(random.uniform(0.02, 0.10), 2)

def _dates(ed_off, hold, *, extra=(6, 12), open_pos=False):
    """Resolve (entry, exit, expiry). For open positions ed_off is measured back
    from TODAY and the trade is left open (no exit) with an expiry still in the future."""
    if open_pos:
        ed  = bday(TODAY, ed_off)
        exp = bday(TODAY, random.randint(16, 28))
    else:
        ed  = bday(START, ed_off)
        exp = bday(ed, (hold if hold is not None else 25) + random.randint(*extra))
    xd = None if hold is None else bday(ed, hold)
    return ed, xd, exp

def emit_vertical(conn, ticker, ed_off, hold, direction, outcome_R, tags, *, kind, open_pos=False):
    """Debit or credit vertical spread, sized to the risk target.

    kind='debit'  : long the near strike, short one width out (bull call / bear put).
    kind='credit' : short the near strike, long one width out (put/call credit).
    direction     : 'call' or 'put' (drives strike placement & labels).
    """
    ed, xd, exp = _dates(ed_off, hold, open_pos=open_pos)
    base = STOCK_MAP[ticker][0]

    if kind == "debit":
        W = 5.0
        long_ep  = round(random.uniform(2.4, 3.4), 2)
        debit    = round(random.uniform(1.4, 2.2), 2)
        short_ep = round(max(0.05, long_ep - debit), 2)
        debit    = round(long_ep - short_ep, 2)
        risk_pc  = debit * OPT_MULT
        long_k   = float(round(base))
        short_k  = long_k + W if direction == "call" else long_k - W
        spread_type = "Bull Call Spread" if direction == "call" else "Bear Put Spread"
        # Spread is worth `debit` at entry; grows toward the width on a win.
        val = min(W, max(0.0, debit * (1 + outcome_R)))
        if open_pos:
            long_x = short_x = None                 # still open — no exit fills
        elif val <= 0.02:
            long_x = short_x = _tail()
        else:
            short_x = _tail()
            long_x  = round(short_x + val, 2)
        legs = [
            ("long",  long_ep,  long_x,  long_k,  f"Long {direction.title()} ${long_k:g}"),
            ("short", short_ep, short_x, short_k, f"Short {direction.title()} ${short_k:g}"),
        ]
    else:  # credit
        W = 2.5
        short_ep = round(random.uniform(1.0, 1.6), 2)
        credit   = round(random.uniform(0.85, 1.15), 2)
        long_ep  = round(max(0.05, short_ep - credit), 2)
        credit   = round(short_ep - long_ep, 2)
        risk_pc  = (W - credit) * OPT_MULT
        short_k  = round(base * (0.96 if direction == "put" else 1.04) * 2) / 2.0
        long_k   = short_k - W if direction == "put" else short_k + W
        spread_type = "Put Credit Spread" if direction == "put" else "Call Credit Spread"
        # Spread is worth `credit` at entry; a win buys it back near zero, a loss
        # toward the full width.
        val = min(W, max(0.0, credit - outcome_R * (W - credit)))
        long_x  = _tail()
        short_x = round(long_x + val, 2)
        legs = [
            ("short", short_ep, short_x, short_k, f"Short {direction.title()} ${short_k:g}"),
            ("long",  long_ep,  long_x,  long_k,  f"Long {direction.title()} ${long_k:g}"),
        ]

    qty = _opt_qty(risk_pc, ed)
    grp = new_grp()
    for lside, lep, lxp, lk, label in legs:
        lid = add_option_leg(conn, ticker, ed, xd, lside, qty, lep, lxp, lk, exp,
                             direction, grp, label, spread_type=spread_type)
        tag_trade(conn, lid, *tags)

def emit_iron_condor(conn, ticker, ed_off, hold, outcome_R, *, open_pos=False):
    """Four-leg iron condor (put spread + call spread), sized to the risk target.

    Max loss = one wing width − total credit collected; only one side can lose.
    """
    ed, xd, exp = _dates(ed_off, hold, extra=(6, 10), open_pos=open_pos)
    base = STOCK_MAP[ticker][0]
    W = 2.5
    put_c  = round(random.uniform(0.45, 0.60), 2)   # credit per side
    call_c = round(random.uniform(0.45, 0.60), 2)
    total_c = round(put_c + call_c, 2)
    risk_pc = (W - total_c) * OPT_MULT

    ph = round(base * 0.96 * 2) / 2.0               # short put strike
    pl = ph - W                                     # long put strike
    cl = round(base * 1.04 * 2) / 2.0               # short call strike
    ch = cl + W                                     # long call strike

    sp_ep = round(random.uniform(0.75, 1.05), 2); lp_ep = round(max(0.05, sp_ep - put_c), 2)
    sc_ep = round(random.uniform(0.75, 1.05), 2); lc_ep = round(max(0.05, sc_ep - call_c), 2)

    if outcome_R >= 0 or open_pos:                  # win / still open → decays toward 0
        sp_xp, lp_xp = _tail(), _tail()
        sc_xp, lc_xp = _tail(), _tail()
    else:                                           # loss on the put side → put spread → width
        lp_xp = _tail()
        sp_xp = round(lp_xp + W, 2)
        sc_xp, lc_xp = _tail(), _tail()

    qty = _opt_qty(risk_pc, ed)
    grp = new_grp()
    legs = [
        ("short", sp_ep, sp_xp, ph, "put",  f"Short Put ${ph:g}"),
        ("long",  lp_ep, lp_xp, pl, "put",  f"Long Put ${pl:g}"),
        ("short", sc_ep, sc_xp, cl, "call", f"Short Call ${cl:g}"),
        ("long",  lc_ep, lc_xp, ch, "call", f"Long Call ${ch:g}"),
    ]
    for lside, lep, lxp, lk, otype, label in legs:
        lid = add_option_leg(conn, ticker, ed, xd, lside, qty, lep, lxp, lk, exp,
                             otype, grp, label, spread_type="Iron Condor")
        tag_trade(conn, lid, "Options Income")

def emit_single(conn, ticker, ed_off, hold, direction, outcome_R, tags, *, open_pos=False):
    """Single long call/put, sized so premium × 100 × qty ≈ the risk target."""
    ed, xd, exp = _dates(ed_off, hold, extra=(6, 10), open_pos=open_pos)
    base = STOCK_MAP[ticker][0]
    ep  = round(random.uniform(1.4, 2.2), 2)        # premium; risk = ep × 100
    xp  = None if open_pos else round(max(0.02, ep * (1 + outcome_R)), 2)
    strike = float(round(base))
    qty = _opt_qty(ep * OPT_MULT, ed)
    lid = add_option_leg(conn, ticker, ed, xd, "long", qty, ep, xp, strike, exp,
                         direction, None, None)
    tag_trade(conn, lid, *tags)

# ── Closed option trades ──────────────────────────────────────────────────────
# (ticker, entry-offset, hold, direction, outcome in R)

BULL_CALLS = [("AAPL", 20, 15, "call", 1.2), ("MSFT", 40, 18, "call", 1.0),
              ("NVDA", 55, 12, "call", -1.0), ("META", 70, 16, "call", -1.0),
              ("AMD", 95, 14, "call", 1.3), ("GOOG", 115, 13, "call", 0.9)]
BEAR_PUTS  = [("SPY", 110, 12, "put", 1.1), ("QQQ", 130, 14, "put", 1.0),
              ("TSLA", 145, 16, "put", -1.0), ("NFLX", 160, 13, "put", 1.3),
              ("IWM", 175, 15, "put", -1.0)]
PUT_CREDITS = [("AAPL", 280, 18, "put", 0.6), ("MSFT", 295, 16, "put", 0.6),
               ("V", 310, 20, "put", 0.6), ("JPM", 325, 18, "put", -1.0)]
IRON_CONDORS = [("SPY", 200, 20, 0.67), ("QQQ", 220, 18, 0.67),
                ("IWM", 240, 22, 0.67), ("SPY", 255, 15, -1.0)]
LONG_CALLS = [("NFLX", 45, 6, "call", 1.3), ("NVDA", 55, 7, "call", 1.5),
              ("TSLA", 70, 5, "call", 1.0), ("AMD", 120, 6, "call", -1.0),
              ("PLTR", 185, 8, "call", -1.0)]
LONG_PUTS  = [("META", 110, 6, "put", -1.0), ("SPY", 155, 7, "put", 1.2),
              ("TSLA", 205, 5, "put", 1.3), ("QQQ", 230, 6, "put", -1.0)]

with get_connection() as conn:
    for tk, off, hold, d, r in BULL_CALLS:
        emit_vertical(conn, tk, off, hold, d, r, rand_tags(1, 2), kind="debit")
    for tk, off, hold, d, r in BEAR_PUTS:
        emit_vertical(conn, tk, off, hold, d, r, rand_tags(1, 2), kind="debit")
    for tk, off, hold, d, r in PUT_CREDITS:
        emit_vertical(conn, tk, off, hold, d, r, ("Options Income",), kind="credit")
    for tk, off, hold, r in IRON_CONDORS:
        emit_iron_condor(conn, tk, off, hold, r)
    for tk, off, hold, d, r in LONG_CALLS:
        emit_single(conn, tk, off, hold, d, r, rand_tags(1, 2))
    for tk, off, hold, d, r in LONG_PUTS:
        emit_single(conn, tk, off, hold, d, r, rand_tags(1, 2))

# ── Open option positions ─────────────────────────────────────────────────────
# entry-offset here is measured back from TODAY (negative), hold=None keeps them open.
with get_connection() as conn:
    emit_vertical(conn, "AAPL", -12, None, "call", 0.0, ("Options Income", "Breakout"), kind="debit", open_pos=True)
    emit_iron_condor(conn, "SPY", -8, None, 0.0, open_pos=True)
    emit_single(conn, "MSFT", -5, None, "call", 0.0, ("Speculative", "Breakout"), open_pos=True)

# ── Equity curve — rebuilt from the trades themselves ─────────────────────────
# The curve is no longer an independent random walk. Each day's balance is the
# starting equity, plus contributions to date, plus the realized (net) P&L of every
# trade closed to date — so the trade log, the equity curve, and the account balance
# all tell the same story. A small mean-reverting wiggle stands in for the daily
# mark-to-market of open positions so the line looks alive rather than a staircase.

from collections import defaultdict  # noqa: E402

def _net_pnl(r) -> float:
    ep, xp, q = r["entry_price"], r["exit_price"], r["quantity"]
    m = r["multiplier"] or 1.0
    gross = (xp - ep) * q * m if (r["side"] or "long") == "long" else (ep - xp) * q * m
    return gross - (r["commission"] or 0.0)

with get_connection() as conn:
    closed = conn.execute(
        "SELECT entry_price, exit_price, quantity, multiplier, side, commission, exit_date "
        "FROM trades WHERE exit_date IS NOT NULL AND exit_price IS NOT NULL"
    ).fetchall()

realized_by_day = defaultdict(float)
for r in closed:
    realized_by_day[r["exit_date"]] += _net_pnl(r)

contrib_by_day = {iso(cd): CONTRIB_AMT for cd in CONTRIB_DATES}

bdays = []
_d = START
while _d <= TODAY:
    if _d.weekday() < 5:
        bdays.append(_d)
    _d += timedelta(days=1)

equity_rows = []
running = STARTING_EQUITY
dev = 0.0
for i, dcur in enumerate(bdays):
    iso_d   = iso(dcur)
    contrib = contrib_by_day.get(iso_d, 0.0)
    running += contrib + realized_by_day.get(iso_d, 0.0)
    dev = 0.85 * dev + random.gauss(0.0, 90.0)      # AR(1) open-position mark-to-market
    if i == len(bdays) - 1:
        dev = 0.0                                    # land the last point on the clean value
    equity_rows.append((iso_d, round(running + dev, 2), contrib, 0.0))

final_balance = round(running, 2)

with get_connection() as conn:
    conn.execute("DELETE FROM equity_entries")
    conn.executemany(
        "INSERT OR REPLACE INTO equity_entries (date, balance, contributions, withdrawals) VALUES (?,?,?,?)",
        equity_rows,
    )
    # Account balance now agrees with the trades + contributions instead of a guess.
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('account_balance', ?)",
                 (str(final_balance),))

# ── Cash transactions ─────────────────────────────────────────────────────────
# Exactly the monthly contributions recorded on the equity curve — nothing that
# isn't reflected there, so deposits never masquerade as trading profit.

cash_txns = [(iso(cd), "deposit", CONTRIB_AMT, "Monthly contribution", "manual")
             for cd in CONTRIB_DATES]

with get_connection() as conn:
    conn.executemany(
        "INSERT INTO cash_transactions (date, type, amount, description, source) VALUES (?,?,?,?,?)",
        cash_txns,
    )

# ── Trading plans ─────────────────────────────────────────────────────────────

PLANS = [
    {
        "ticker": "AAPL", "sentiment": "Bullish",
        "rationale": "Breaking out of a 3-month base on high volume. Services and Vision Pro upgrade cycle.",
        "fundamentals": "P/E 28x, services growing 15% YoY, $100B buyback intact.",
        "technicals": "Weekly close above $210 resistance. RSI 57 — room to run. 50-day MA trending up.",
        "trade_type": "Swing", "hold_time": "2–4 weeks",
        "entry_signal": "Daily close above $212 on volume > 20-day avg",
        "confirm1": "SPY holding above 200-day MA", "confirm2": "No major macro events",
        "entry_price": 212.00, "profit_target": 235.00, "stop_loss": 200.00, "rr_ratio": 1.9,
    },
    {
        "ticker": "NVDA", "sentiment": "Bullish",
        "rationale": "AI infrastructure spending accelerating. Blackwell demand exceeding supply.",
        "fundamentals": "Revenue +78% YoY, data center 80% of revenue. Forward P/E 35x.",
        "technicals": "Tight consolidation at highs. Bollinger Bands squeezing.",
        "trade_type": "Momentum", "hold_time": "3–6 weeks",
        "entry_signal": "Break and hold above $900 on daily close",
        "confirm1": "SOX semiconductor index trending up", "confirm2": "No guidance cut from hyperscalers",
        "entry_price": 900.00, "profit_target": 1020.00, "stop_loss": 855.00, "rr_ratio": 2.7,
    },
    {
        "ticker": "SPY", "sentiment": "Bearish",
        "rationale": "Market extended after 10-week rally. VIX compression + overbought readings.",
        "fundamentals": "S&P 500 forward P/E 22x — above 10-year avg. Earnings growth slowing.",
        "technicals": "RSI 71 on weekly. Volume declining on up days.",
        "trade_type": "Options Play", "hold_time": "2–3 weeks",
        "entry_signal": "Daily close below 20-day MA",
        "confirm1": "Yield curve widening", "confirm2": "Put/call ratio rising",
        "entry_price": 595.00, "profit_target": 570.00, "stop_loss": 605.00, "rr_ratio": 2.5,
    },
    {
        "ticker": "MSFT", "sentiment": "Bullish",
        "rationale": "Azure cloud re-accelerating. Copilot monetization beginning to show.",
        "fundamentals": "Revenue +16% YoY, operating margin 45%.",
        "technicals": "Breakout above $420 on weekly. Prior ATH becomes support.",
        "trade_type": "Swing", "hold_time": "3–5 weeks",
        "entry_signal": "Hold above $422 for 3 days",
        "confirm1": "XLK holding 50-day MA", "confirm2": "No Fed rate shock",
        "entry_price": 422.00, "profit_target": 465.00, "stop_loss": 405.00, "rr_ratio": 2.5,
    },
]

with get_connection() as conn:
    for i, plan in enumerate(PLANS):
        saved = _dt.datetime.combine(bday(START, i * 20), _dt.time(9, 30)).isoformat(sep=" ")
        conn.execute(
            """INSERT INTO trading_plans
               (saved_at, ticker, sentiment, rationale, fundamentals, technicals,
                trade_type, hold_time, entry_signal, confirm1, confirm2,
                entry_price, profit_target, stop_loss, rr_ratio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (saved, plan["ticker"], plan["sentiment"], plan["rationale"],
             plan["fundamentals"], plan["technicals"], plan["trade_type"],
             plan["hold_time"], plan["entry_signal"], plan["confirm1"],
             plan["confirm2"], plan["entry_price"], plan["profit_target"],
             plan["stop_loss"], plan["rr_ratio"]),
        )

# ── Done ──────────────────────────────────────────────────────────────────────

with get_connection() as conn:
    n_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    n_stocks = conn.execute("SELECT COUNT(*) FROM trades WHERE instrument_type='stock'").fetchone()[0]
    n_opts   = conn.execute("SELECT COUNT(*) FROM trades WHERE instrument_type='option'").fetchone()[0]
    n_equity = conn.execute("SELECT COUNT(*) FROM equity_entries").fetchone()[0]
    n_plans  = conn.execute("SELECT COUNT(*) FROM trading_plans").fetchone()[0]
    n_tags   = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

print(f"Demo DB seeded: {n_trades} trades ({n_stocks} stock, {n_opts} option) | "
      f"{n_equity} equity entries | {n_plans} plans | {n_tags} tags")
print(f"  -> {DEMO_DB}")
