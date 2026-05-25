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
        "account_balance":      "28500",
        "starting_equity":      "25000",
        "starting_date":        iso(START),
        "euro_dates":           "0",
        "app_mode":             "demo",
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

    # quantity scaled to rough $5k–$20k position size
    position_size = random.uniform(5000, 20000)
    qty = max(1, round(position_size / ep / 10) * 10)  # round to nearest 10

    # stop: 4–8% below for longs, above for shorts
    stop_pct = random.uniform(0.04, 0.08)
    stop = round(ep * (1 - stop_pct) if side == "long" else ep * (1 + stop_pct), 2)
    cur_stop = round(stop * random.uniform(0.98, 1.02), 2)

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

        # exit price: ~55% win-rate; chg is always a positive magnitude
        win = random.random() < 0.55
        chg = random.uniform(0.01, 0.14) if win else random.uniform(0.005, 0.10)
        if side == "long":
            xp = round(ep * (1 + chg if win else 1 - chg), 2)
        else:  # short: profit when price falls
            xp = round(ep * (1 - chg if win else 1 + chg), 2)
        xp = max(0.01, xp)
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

# ── Closed option trades ──────────────────────────────────────────────────────

# --- Bull call spreads (6) ---
BULL_CALL_PARAMS = [
    ("AAPL",  20, 25, 230, 240, 4.50, 8.20, 1.80, 0.30, 5, "call"),  # win
    ("MSFT",  35, 20, 420, 430, 5.20, 9.10, 2.10, 0.35, 8, "call"),  # win
    ("NVDA",  50, 15, 880, 900, 8.50, 2.10, 3.20, 0.80, 4, "call"),  # loss — stock pulled back
    ("META",  65, 18, 570, 585, 6.30, 1.50, 2.60, 0.55, 6, "call"),  # loss — failed to break out
    ("AMD",   80, 20, 150, 160, 2.80, 5.10, 1.10, 0.20, 10,"call"),  # win
    ("GOOG",  95, 22, 190, 200, 4.10, 7.50, 1.65, 0.25, 7, "call"),  # win
]

with get_connection() as conn:
    for ticker, ed_off, hold, lo, hi, ep_lo, xp_lo, ep_hi, xp_hi, qty, _ in BULL_CALL_PARAMS:
        ed  = bday(START, ed_off)
        xd  = bday(ed, hold)
        exp = bday(ed, hold + 10)
        grp = new_grp()
        i1 = add_option_leg(conn, ticker, ed, xd, "long",  qty, ep_lo, xp_lo, lo, exp, "call", grp, f"Long Call ${lo}", spread_type="Bull Call Spread")
        i2 = add_option_leg(conn, ticker, ed, xd, "short", qty, ep_hi, xp_hi, hi, exp, "call", grp, f"Short Call ${hi}", spread_type="Bull Call Spread")
        tag_trade(conn, i1, *rand_tags(1, 2))
        tag_trade(conn, i2, *rand_tags(1, 2))

# --- Bear put spreads (5) ---
BEAR_PUT_PARAMS = [
    ("SPY",   110, 15, 590, 580, 3.20, 5.80, 1.10, 0.20, 10, "put"),  # win
    ("QQQ",   130, 12, 490, 480, 2.90, 4.70, 1.05, 0.18, 8,  "put"),  # win
    ("TSLA",  145, 18, 320, 305, 5.50, 0.25, 2.30, 0.10, 6,  "put"),  # loss — TSLA rallied
    ("NFLX",  160, 14, 880, 860, 8.10, 13.5, 3.20, 0.55, 3,  "put"),  # win
    ("IWM",   175, 16, 210, 200, 2.40, 0.10, 0.95, 0.05, 12, "put"),  # loss — market rallied
]

with get_connection() as conn:
    for ticker, ed_off, hold, hi, lo, ep_hi, xp_hi, ep_lo, xp_lo, qty, _ in BEAR_PUT_PARAMS:
        ed  = bday(START, ed_off)
        xd  = bday(ed, hold)
        exp = bday(ed, hold + 10)
        grp = new_grp()
        i1 = add_option_leg(conn, ticker, ed, xd, "long",  qty, ep_hi, xp_hi, hi, exp, "put", grp, f"Long Put ${hi}", spread_type="Bear Put Spread")
        i2 = add_option_leg(conn, ticker, ed, xd, "short", qty, ep_lo, xp_lo, lo, exp, "put", grp, f"Short Put ${lo}", spread_type="Bear Put Spread")
        tag_trade(conn, i1, *rand_tags(1, 2))
        tag_trade(conn, i2, *rand_tags(1, 2))

# --- Iron condors (4 × 4 legs = 16 legs) ---
# Columns: ticker, ed_off, hold, put_lo, put_hi, call_lo, call_hi, qty,
#          sp_ep, sp_xp, lp_ep, lp_xp, sc_ep, sc_xp, lc_ep, lc_xp
IRON_CONDOR_PARAMS = [
    ("SPY", 200, 20, 560, 570, 600, 610, 8,  1.50, 0.10, 0.60, 0.02, 1.50, 0.10, 0.60, 0.02),  # win
    ("QQQ", 220, 18, 455, 465, 505, 515, 6,  1.50, 0.10, 0.60, 0.02, 1.50, 0.10, 0.60, 0.02),  # win
    ("IWM", 240, 22, 185, 195, 225, 235, 10, 1.50, 0.10, 0.60, 0.02, 1.50, 0.10, 0.60, 0.02),  # win
    # Market broke through put side — max-loss on put spread, calls expired fine
    ("SPY", 260, 15, 555, 565, 595, 605, 8,  1.50, 8.50, 0.60, 5.20, 1.50, 0.10, 0.60, 0.02),  # loss
]

with get_connection() as conn:
    for ticker, ed_off, hold, pl, ph, cl, ch, qty, sp_ep, sp_xp, lp_ep, lp_xp, sc_ep, sc_xp, lc_ep, lc_xp in IRON_CONDOR_PARAMS:
        ed  = bday(START, ed_off)
        xd  = bday(ed, hold)
        exp = bday(ed, hold + 8)
        grp = new_grp()
        sp  = add_option_leg(conn, ticker, ed, xd, "short", qty, sp_ep, sp_xp, ph, exp, "put",  grp, f"Short Put ${ph}", spread_type="Iron Condor")
        lp  = add_option_leg(conn, ticker, ed, xd, "long",  qty, lp_ep, lp_xp, pl, exp, "put",  grp, f"Long Put ${pl}", spread_type="Iron Condor")
        sc  = add_option_leg(conn, ticker, ed, xd, "short", qty, sc_ep, sc_xp, cl, exp, "call", grp, f"Short Call ${cl}", spread_type="Iron Condor")
        lc  = add_option_leg(conn, ticker, ed, xd, "long",  qty, lc_ep, lc_xp, ch, exp, "call", grp, f"Long Call ${ch}", spread_type="Iron Condor")
        for leg_id in (sp, lp, sc, lc):
            tag_trade(conn, leg_id, "Options Income")

# --- Put credit spreads (4 × 2 legs = 8 legs) ---
PUT_CREDIT_PARAMS = [
    ("AAPL",  280, 20, 200, 190, 2.10, 0.15, 0.85, 0.05, 8),   # win
    ("MSFT",  295, 18, 400, 390, 2.80, 0.20, 1.10, 0.06, 6),   # win
    ("V",     310, 22, 285, 275, 1.90, 0.12, 0.75, 0.04, 10),  # win
    ("JPM",   325, 20, 235, 225, 1.75, 7.20, 0.70, 4.50, 8),   # loss — JPM dropped hard
]

with get_connection() as conn:
    for ticker, ed_off, hold, hi, lo, ep_hi, xp_hi, ep_lo, xp_lo, qty in PUT_CREDIT_PARAMS:
        ed  = bday(START, ed_off)
        xd  = bday(ed, hold)
        exp = bday(ed, hold + 8)
        grp = new_grp()
        sp = add_option_leg(conn, ticker, ed, xd, "short", qty, ep_hi, xp_hi, hi, exp, "put", grp, f"Short Put ${hi}", spread_type="Put Credit Spread")
        lp = add_option_leg(conn, ticker, ed, xd, "long",  qty, ep_lo, xp_lo, lo, exp, "put", grp, f"Long Put ${lo}", spread_type="Put Credit Spread")
        tag_trade(conn, sp, "Options Income")
        tag_trade(conn, lp, "Options Income")

# --- Single-leg long calls (5) ---
LONG_CALL_PARAMS = [
    ("NFLX",  45,  5, 900, 12.50, 28.00, 3),   # win
    ("NVDA",  55,  6, 880, 15.20, 34.50, 2),   # win
    ("TSLA",  70,  4, 330,  8.80, 18.40, 5),   # win
    ("AMD",   120, 5, 155,  3.20,  0.15, 8),   # loss — stock didn't move, theta decay
    ("PLTR",  185, 7, 90,   2.10,  0.05, 10),  # loss — expired worthless
]

with get_connection() as conn:
    for ticker, ed_off, hold, strike, ep, xp, qty in LONG_CALL_PARAMS:
        ed  = bday(START, ed_off)
        xd  = bday(ed, hold)
        exp = bday(ed, hold + 8)
        i = add_option_leg(conn, ticker, ed, xd, "long", qty, ep, xp, strike, exp, "call", None, None)
        tag_trade(conn, i, *rand_tags(1, 2))

# --- Single-leg long puts (4) ---
LONG_PUT_PARAMS = [
    ("META",  110, 5, 620,  8.00,  3.50, 4),   # loss — market didn't drop enough
    ("SPY",   155, 6, 590,  4.50,  9.20, 6),   # win
    ("TSLA",  205, 4, 310,  6.20, 13.80, 3),   # win
    ("QQQ",   230, 5, 480,  3.80,  0.10, 5),   # loss — QQQ rallied, expired worthless
]

with get_connection() as conn:
    for ticker, ed_off, hold, strike, ep, xp, qty in LONG_PUT_PARAMS:
        ed  = bday(START, ed_off)
        xd  = bday(ed, hold)
        exp = bday(ed, hold + 8)
        i = add_option_leg(conn, ticker, ed, xd, "long", qty, ep, xp, strike, exp, "put", None, None)
        tag_trade(conn, i, *rand_tags(1, 2))

# ── Open option positions ─────────────────────────────────────────────────────

# Open bull call spread — AAPL
grp_oc1 = new_grp()
oc1_ed  = bday(TODAY, -12)
oc1_exp = bday(TODAY, 18)
with get_connection() as conn:
    i1 = add_trade(conn, entry_date=iso(oc1_ed), ticker="AAPL", quantity=8, entry_price=4.80,
                   instrument_type="option", side="long", opening_stop=None, current_stop=None,
                   stop_enabled=0, strike=215.0, expiration=iso(oc1_exp), option_type="call",
                   multiplier=100, leg_group=grp_oc1, leg_label="Long Call $215",
                   spread_type="Bull Call Spread", commission=round(8*0.65,2), notes="Demo open option")
    i2 = add_trade(conn, entry_date=iso(oc1_ed), ticker="AAPL", quantity=8, entry_price=2.10,
                   instrument_type="option", side="short", opening_stop=None, current_stop=None,
                   stop_enabled=0, strike=225.0, expiration=iso(oc1_exp), option_type="call",
                   multiplier=100, leg_group=grp_oc1, leg_label="Short Call $225",
                   spread_type="Bull Call Spread", commission=round(8*0.65,2), notes="Demo open option")
    tag_trade(conn, i1, "Options Income", "Breakout")
    tag_trade(conn, i2, "Options Income", "Breakout")

# Open iron condor — SPY
grp_oc2 = new_grp()
oc2_ed  = bday(TODAY, -8)
oc2_exp = bday(TODAY, 22)
with get_connection() as conn:
    for side, strike, opt_type, label, ep in [
        ("short", 555, "put",  "Short Put $555",  1.45),
        ("long",  545, "put",  "Long Put $545",   0.55),
        ("short", 605, "call", "Short Call $605", 1.45),
        ("long",  615, "call", "Long Call $615",  0.55),
    ]:
        li = add_trade(conn, entry_date=iso(oc2_ed), ticker="SPY", quantity=10, entry_price=ep,
                       instrument_type="option", side=side, opening_stop=None, current_stop=None,
                       stop_enabled=0, strike=float(strike), expiration=iso(oc2_exp),
                       option_type=opt_type, multiplier=100, leg_group=grp_oc2, leg_label=label,
                       spread_type="Iron Condor", commission=round(10*0.65,2), notes="Demo open option")
        tag_trade(conn, li, "Options Income")

# Open long call — MSFT
oc3_ed  = bday(TODAY, -5)
oc3_exp = bday(TODAY, 25)
with get_connection() as conn:
    li = add_trade(conn, entry_date=iso(oc3_ed), ticker="MSFT", quantity=5, entry_price=6.20,
                   instrument_type="option", side="long", opening_stop=None, current_stop=None,
                   stop_enabled=0, strike=430.0, expiration=iso(oc3_exp), option_type="call",
                   multiplier=100, leg_group=None, leg_label=None,
                   commission=round(5*0.65,2), notes="Demo open option")
    tag_trade(conn, li, "Speculative", "Breakout")

# ── Equity curve — 1 year starting at $25,000 ────────────────────────────────

def generate_equity_curve(start: date, end: date, start_balance: float):
    rows = []
    balance = start_balance
    d = start
    in_drawdown = False
    drawdown_dur = 0

    while d <= end:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue

        contributions = 500.0 if d.day == 1 else 0.0
        withdrawals   = 0.0

        daily_return = random.gauss(0.0006, 0.013)

        if not in_drawdown and random.random() < 0.035:
            in_drawdown = True
            drawdown_dur = random.randint(5, 18)
        if in_drawdown:
            daily_return -= 0.007
            drawdown_dur -= 1
            if drawdown_dur <= 0:
                in_drawdown = False

        balance = balance * (1 + daily_return) + contributions - withdrawals
        balance = max(balance, start_balance * 0.65)

        rows.append((iso(d), round(balance, 2), contributions, withdrawals))
        d += timedelta(days=1)

    return rows

equity_rows = generate_equity_curve(START, TODAY, 25_000.0)

with get_connection() as conn:
    conn.executemany(
        "INSERT OR REPLACE INTO equity_entries (date, balance, contributions, withdrawals) VALUES (?,?,?,?)",
        equity_rows,
    )

# ── Cash transactions ─────────────────────────────────────────────────────────

cash_txns = []
d = START
while d <= TODAY:
    if d.day == 1 and d.weekday() < 5:
        cash_txns.append((iso(d), "deposit", 500.0, "Monthly contribution", "manual"))
    d += timedelta(days=1)

cash_txns.append((iso(bday(START, 3)),  "deposit", 5000.0, "Initial transfer",   "manual"))
cash_txns.append((iso(bday(START, 60)), "deposit", 2500.0, "Extra contribution", "manual"))

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
