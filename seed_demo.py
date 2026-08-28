"""
seed_demo.py — recreate demo/tradelog_demo.db with ~200 realistic dummy trades.

Prices are real. One year of daily OHLC for the demo universe is pulled from
Yahoo (cached in demo/price_history.json) and every fill is placed inside the
actual high–low range of the day it is dated: entries fill somewhere in the
entry day's range, winners exit at a target the stock genuinely traded through,
losers exit at the stop on the day the stock actually broke it. Option premiums
are Black-Scholes marks off the same real underlying path. If the download
fails and there is no cache, a synthetic random walk stands in so seeding never
hard-fails.

Run directly:    python seed_demo.py
Run via launcher: launch_demo.bat calls this automatically before starting Streamlit.
"""
import os
import bisect
import json
import socket
import statistics
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

# Re-seeding deletes the demo database outright. If a copy of the app is still
# serving the demo port, doing that pulls the file out from under a live browser
# session: everything entered since that session started is gone, and its cached
# tag / plan ids now point at rows that no longer exist (saving a trade with one
# of those tags fails with "FOREIGN KEY constraint failed"). Refuse instead.
def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


DEMO_PORT = int(os.environ.get("TRADELOG_PORT") or 8502)
if _port_in_use(DEMO_PORT):
    print(f"Trade Log is already running at http://localhost:{DEMO_PORT}.")
    print("Close it before re-seeding - otherwise the demo database it is using")
    print("would be deleted out from under that session.")
    sys.exit(2)

if DEMO_DB.exists():
    DEMO_DB.unlink()

sys.path.insert(0, str(Path(__file__).parent))
from db import init_db, get_connection  # noqa: E402

init_db()

random.seed(42)

def iso(d: date) -> str:
    return d.isoformat()

# ── Stock universe ────────────────────────────────────────────────────────────
# (ticker, fallback_price) — the fallback price only anchors the synthetic path
# used when no real history can be loaded for that symbol.
STOCKS = [
    ("AAPL",  210), ("MSFT",  420), ("NVDA",  180), ("META",  600),
    ("AMZN",  220), ("TSLA",  320), ("GOOG",  195), ("AMD",   155),
    ("INTC",   25), ("JPM",   250), ("BAC",    44), ("GS",    600),
    ("MS",    110), ("XOM",   118), ("CVX",   162), ("LLY",   800),
    ("JNJ",   157), ("PFE",    28), ("MRNA",   70), ("COST",  920),
    ("WMT",    90), ("TGT",   140), ("HD",    385), ("LOW",   250),
    ("NFLX",  880), ("DIS",   100), ("SPOT",  360), ("ROKU",   70),
    ("PYPL",   70), ("V",     300), ("MA",    470), ("UBER",   82),
    ("CRM",   320), ("NOW",   980), ("SNOW",  165), ("PLTR",   90),
    ("DDOG",  125), ("SHOP",  115), ("MU",    110), ("COIN",  270),
    ("RIVN",   14), ("BYND",    7), ("SPY",   580), ("QQQ",   490),
    ("IWM",   210), ("GLD",   260), ("SLV",    30),
]

TICKERS = [t for t, _ in STOCKS]
FALLBACK_PRICE = dict(STOCKS)

# Annualised vol, used only by the synthetic fallback path.
FALLBACK_VOL = {
    "SPY": 0.15, "QQQ": 0.19, "IWM": 0.21, "GLD": 0.13, "SLV": 0.26,
    "JNJ": 0.16, "WMT": 0.19, "COST": 0.19, "V": 0.19, "MA": 0.20,
    "XOM": 0.23, "CVX": 0.22, "JPM": 0.23, "BAC": 0.26, "MS": 0.26,
    "AAPL": 0.26, "MSFT": 0.25, "GOOG": 0.28, "AMZN": 0.30, "META": 0.35,
    "NVDA": 0.48, "AMD": 0.50, "TSLA": 0.58, "COIN": 0.70, "PLTR": 0.62,
    "MRNA": 0.62, "ROKU": 0.60, "RIVN": 0.70, "BYND": 0.75, "SNOW": 0.48,
    "DDOG": 0.42, "SHOP": 0.48, "MU": 0.45, "NFLX": 0.34, "SPOT": 0.38,
}
DEFAULT_VOL = 0.34

# ── Price history ─────────────────────────────────────────────────────────────

PRICE_CACHE = Path(__file__).parent / "demo" / "price_history.json"
CACHE_MAX_AGE_DAYS = 5          # re-fetch once the cache falls this far behind


def _weekday_calendar(start: date, end: date) -> list:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _fetch_history(tickers, start: date, end: date) -> dict:
    """{ticker: {iso_date: [o, h, l, c]}} of real split/dividend-adjusted bars."""
    import pandas as pd
    import yfinance as yf

    df = yf.download(tickers, start=iso(start), end=iso(end + timedelta(days=1)),
                     auto_adjust=True, progress=False, group_by="ticker", threads=True)
    if df is None or df.empty:
        return {}
    out = {}
    for t in tickers:
        try:
            sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
        except KeyError:
            continue
        sub = sub.dropna(subset=["Close"])
        if len(sub) < 200:                      # too sparse to place trades in
            continue
        out[t] = {
            ts.date().isoformat(): [round(float(r["Open"]), 4), round(float(r["High"]), 4),
                                    round(float(r["Low"]), 4), round(float(r["Close"]), 4)]
            for ts, r in sub.iterrows()
        }
    return out


def _load_cache() -> dict:
    if not PRICE_CACHE.exists():
        return {}
    try:
        blob = json.loads(PRICE_CACHE.read_text())
        data = blob.get("data")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _cache_is_fresh(data: dict, tickers) -> bool:
    if not data or any(t not in data for t in tickers):
        return False
    newest = max((max(v) for v in data.values() if v), default="")
    return newest >= iso(date.today() - timedelta(days=CACHE_MAX_AGE_DAYS))


def _synth_history(ticker: str, cal: list) -> dict:
    """Geometric random walk anchored so the last close is the fallback price."""
    base = FALLBACK_PRICE[ticker]
    sig = FALLBACK_VOL.get(ticker, DEFAULT_VOL) / math.sqrt(252)
    mu = random.uniform(-0.10, 0.30) / 252
    closes = [1.0]
    for _ in range(len(cal) - 1):
        closes.append(closes[-1] * math.exp(mu - 0.5 * sig * sig + sig * random.gauss(0, 1)))
    scale = base / closes[-1]
    closes = [c * scale for c in closes]
    bars = {}
    for i, d in enumerate(cal):
        c = closes[i]
        o = closes[i - 1] * math.exp(0.35 * sig * random.gauss(0, 1)) if i else c
        hi = max(o, c) * (1 + abs(random.gauss(0, 1)) * 0.45 * sig)
        lo = min(o, c) * (1 - abs(random.gauss(0, 1)) * 0.45 * sig)
        bars[iso(d)] = [round(o, 4), round(hi, 4), round(lo, 4), round(c, 4)]
    return bars


_today = date.today()
_hist_start = _today - timedelta(days=430)
_cached = _load_cache()

if _cache_is_fresh(_cached, TICKERS):
    PRICE, PRICE_SOURCE = _cached, "cache"
else:
    try:
        fetched = _fetch_history(TICKERS, _hist_start, _today)
    except Exception as exc:                     # offline, rate-limited, API change…
        print(f"  price download failed ({exc.__class__.__name__}) - falling back")
        fetched = {}
    PRICE = dict(_cached)
    PRICE.update(fetched)
    PRICE_SOURCE = "yahoo" if fetched else ("cache" if _cached else "synthetic")
    if fetched:
        real = {t: v for t, v in PRICE.items() if t in TICKERS}
        try:
            PRICE_CACHE.write_text(json.dumps({"fetched": iso(_today), "data": real}))
        except Exception:
            pass

# Market calendar: real trading days (holidays already absent) taken from the
# broadest series we have, so no demo trade is dated on a day the market was shut.
if PRICE:
    _ref = PRICE.get("SPY") or max(PRICE.values(), key=len)
    CAL = sorted(_dt.date.fromisoformat(k) for k in _ref)
else:
    CAL = _weekday_calendar(_hist_start, _today)

CAL = CAL[-253:]                                 # roughly one year of sessions
START, TODAY = CAL[0], CAL[-1]

for _t in TICKERS:                               # fill in any symbol we could not load
    if _t not in PRICE or len(PRICE[_t]) < 200:
        PRICE[_t] = _synth_history(_t, CAL)


def cal_i(d: date) -> int:
    """Index of the session on or before d."""
    return max(0, min(bisect.bisect_right(CAL, d) - 1, len(CAL) - 1))


def cal_shift(d: date, n: int) -> date:
    return CAL[max(0, min(cal_i(d) + n, len(CAL) - 1))]


def rand_cal_day(start: date, end: date) -> date:
    lo, hi = cal_i(start), cal_i(end)
    if hi < lo:
        lo, hi = hi, lo
    return CAL[random.randint(lo, hi)]


def bar(ticker: str, d: date):
    """(open, high, low, close) for `ticker` on `d`, or the most recent prior bar."""
    rows = PRICE.get(ticker)
    if not rows:
        return None
    for back in range(0, 8):
        hit = rows.get(iso(d - timedelta(days=back)))
        if hit:
            return hit
    return None


def close_on(ticker: str, d: date):
    b = bar(ticker, d)
    return b[3] if b else None

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
    ("Felix",      "Setup called out in Felix's room / alert list"),
    ("Breakout",   "Price breaks above a key resistance level on expanding volume"),
    ("MOMO",       "Momentum continuation — relative-strength leader already in motion"),
    ("Meme Stock", "Retail- and social-media-driven name; size down, hard stop"),
    ("W-Pattern",  "Double-bottom reversal — entry on the break of the middle peak"),
    ("BullFlag",   "Tight consolidation after an impulse leg, entered on the flag break"),
]

with get_connection() as conn:
    for name, desc in TAGS:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?,?)", (name, desc))

with get_connection() as conn:
    tag_rows = conn.execute("SELECT id, name FROM tags").fetchall()
tag_id = {row["name"]: row["id"] for row in tag_rows}

# Setups are applied where they make sense rather than uniformly at random: the
# long-side chart patterns only go on long trades, and "Meme Stock" only lands on
# names that actually trade like one.
LONG_SETUPS  = ["Breakout", "BullFlag", "W-Pattern", "MOMO"]
SHORT_SETUPS = ["MOMO", "Felix"]
MEME_TICKERS = {"PLTR", "RIVN", "BYND", "COIN", "MRNA", "ROKU", "TSLA"}


def rand_tags(ticker: str = "", side: str = "long"):
    pool = LONG_SETUPS if side == "long" else SHORT_SETUPS
    picked = [random.choice(pool)]
    if ticker in MEME_TICKERS and random.random() < 0.6:
        picked.append("Meme Stock")
    if "Felix" not in picked and random.random() < 0.3:
        picked.append("Felix")
    return picked

# ── Settings ──────────────────────────────────────────────────────────────────

with get_connection() as conn:
    for k, v in {
        "account_balance":      "25000",  # placeholder — recomputed from trades at the end
        "starting_equity":      "25000",
        "starting_date":        iso(START),
        "euro_dates":           "0",
        "date_format":          "us",
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

# ── Stock trades — walked forward over the real price path ────────────────────
# A trade is simulated bar by bar against the ticker's actual OHLC history:
#   entry  — a fill somewhere inside the entry day's high–low range
#   stop   — the first session whose range trades through the stop; a gap fills
#            at that day's open rather than at the stop price
#   target — the first session whose range trades through the profit target
#   timed  — otherwise a discretionary exit inside the final day's range
# Nothing is ever priced outside a range the stock actually printed.

NOTE_BY_SETUP = {
    "Breakout":   "Broke {lvl} on above-average volume; stop under the base.",
    "BullFlag":   "Flag break after the impulse leg; entry {lvl}, stop below the flag low.",
    "W-Pattern":  "Double bottom confirmed through the middle peak at {lvl}.",
    "MOMO":       "Relative-strength leader — joined the move at {lvl}.",
    "Meme Stock": "Social flow driving it. Half size, hard stop, no averaging down.",
    "Felix":      "Felix flagged it at {lvl} — took the standard risk unit.",
}


# Outcome buckets, in multiples of the trade's own risk (R). A log with an edge is
# not just "more winners than losers" — the winners are bigger, and a slice of the
# book is scratched out around break-even. Trades are re-drawn until the real price
# path delivers the bucket that was asked for.
SCRATCH_BAND = 0.5          # |R| below this is a scratch, not a win or a loss
OUTCOME_MIX  = (("win", 0.55), ("loss", 0.35), ("scratch", 0.10))


def _draw_outcome():
    x = random.random()
    cum = 0.0
    for name, wt in OUTCOME_MIX:
        cum += wt
        if x < cum:
            return name
    return "loss"


def _simulate_stock(ticker, side, ed, hold, want):
    """Walk the real path forward from `ed`. Returns fills, or None if the path did
    not produce the requested outcome bucket."""
    b0 = bar(ticker, ed)
    if not b0:
        return None
    o, h, l, c = b0
    if l <= 0:
        return None

    ep = round(random.uniform(l, h), 2)
    stop_pct = random.uniform(0.04, 0.08)
    stop = round(ep * (1 - stop_pct), 2) if side == "long" else round(ep * (1 + stop_pct), 2)
    rps = abs(ep - stop)
    if rps <= 0:
        return None

    r_target = random.uniform(0.6, 2.2)          # a target hit always clears a scratch
    target = ep + rps * r_target if side == "long" else ep - rps * r_target

    i0 = cal_i(ed)
    lowest, highest = l, h
    out = dict(entry_price=ep, opening_stop=stop, exit_date=None, exit_price=None)

    for k in range(1, hold + 1):
        j = i0 + k
        if j >= len(CAL):
            return None                                  # not enough history left
        d = CAL[j]
        bb = bar(ticker, d)
        if not bb:
            continue
        o2, h2, l2, c2 = bb
        lowest, highest = min(lowest, l2), max(highest, h2)
        if side == "long":
            if l2 <= stop:                               # stop trades through
                fill = stop if o2 > stop else o2         # a gap down fills at the open
                out.update(exit_date=d, exit_price=round(max(0.01, fill), 2))
                break
            if h2 >= target:                             # target trades through
                fill = target if o2 < target else o2     # a gap up fills at the open
                out.update(exit_date=d, exit_price=round(fill, 2))
                break
        else:
            if h2 >= stop:
                fill = stop if o2 < stop else o2         # a gap up fills at the open
                out.update(exit_date=d, exit_price=round(fill, 2))
                break
            if l2 <= target:
                fill = target if o2 > target else o2     # a gap down fills at the open
                out.update(exit_date=d, exit_price=round(max(0.01, fill), 2))
                break
    else:
        d = CAL[min(i0 + hold, len(CAL) - 1)]            # timed / discretionary exit
        bb = bar(ticker, d)
        if not bb:
            return None
        out.update(exit_date=d, exit_price=round(random.uniform(bb[2], bb[1]), 2))

    out["low"], out["high"] = lowest, highest
    pnl = (out["exit_price"] - ep) if side == "long" else (ep - out["exit_price"])
    r = pnl / rps
    out["r"] = r
    if want == "win" and r < SCRATCH_BAND:
        return None
    if want == "loss" and r > -SCRATCH_BAND:
        return None
    if want == "scratch" and abs(r) >= SCRATCH_BAND:
        return None
    return out


def _simulate_open_stock(ticker, side, ed):
    """An open position: the stop must not have been hit between entry and today."""
    b0 = bar(ticker, ed)
    if not b0:
        return None
    o, h, l, c = b0
    if l <= 0:
        return None
    ep = round(random.uniform(l, h), 2)
    stop_pct = random.uniform(0.04, 0.08)
    stop = round(ep * (1 - stop_pct), 2) if side == "long" else round(ep * (1 + stop_pct), 2)

    lowest, highest = l, h
    for j in range(cal_i(ed) + 1, len(CAL)):
        bb = bar(ticker, CAL[j])
        if not bb:
            continue
        lowest, highest = min(lowest, bb[2]), max(highest, bb[1])
        if (side == "long" and bb[2] <= stop) or (side == "short" and bb[1] >= stop):
            return None                                   # would already be closed
    return dict(entry_price=ep, opening_stop=stop, low=lowest, high=highest,
                exit_date=None, exit_price=None, win=None)


def gen_stock_trade(conn, *, open_pos=False):
    """One stock trade. Closed trades are re-drawn until the real path delivers the
    intended outcome bucket, so the demo keeps its expectancy without any price ever
    being invented."""
    want = None if open_pos else _draw_outcome()

    sim = ticker = side = ed = None
    for _ in range(60):
        ticker, _fb = random.choice(STOCKS)
        side = "long" if random.random() < 0.85 else "short"
        if open_pos:
            ed = rand_cal_day(cal_shift(TODAY, -25), cal_shift(TODAY, -2))
            sim = _simulate_open_stock(ticker, side, ed)
        else:
            ed = rand_cal_day(START, cal_shift(TODAY, -32))
            sim = _simulate_stock(ticker, side, ed, random.randint(2, 30), want)
        if sim:
            break
    if not sim:
        return None

    ep, stop = sim["entry_price"], sim["opening_stop"]
    rps = abs(ep - stop)

    # quantity is sized FROM the risk, not the other way round: pick shares so that
    # open risk = (entry − stop) × shares ≈ the 0.5%-of-account target. Round to a
    # clean lot without letting the rounding distort the risk much.
    raw_qty = trade_risk_dollars(ed) / rps if rps else 0
    if   raw_qty >= 200: qty = max(10, round(raw_qty / 10) * 10)
    elif raw_qty >= 40:  qty = max(5,  round(raw_qty / 5) * 5)
    else:                qty = max(1,  round(raw_qty))

    # The current stop only ever trails toward entry, and never past a level the
    # stock already traded through — otherwise it would have been hit before the
    # exit that is actually recorded.
    trail = random.uniform(0.0, 0.6)             # 0 = untouched, 1 = pulled up to entry
    cur_stop = stop + (ep - stop) * trail
    if side == "long":
        cur_stop = max(stop, min(cur_stop, sim["low"] * 0.999))
    else:
        cur_stop = min(stop, max(cur_stop, sim["high"] * 1.001))
    cur_stop = round(cur_stop, 2)

    setups = rand_tags(ticker, side)
    note = NOTE_BY_SETUP.get(setups[0], "Entry at {lvl}.").format(lvl=f"{ep:.2f}")

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
        commission=round(qty * 0.005, 2),
        notes=note,
    )
    if not open_pos:
        trade_kw["exit_date"]  = iso(sim["exit_date"])
        trade_kw["exit_price"] = sim["exit_price"]

    tid = add_trade(conn, **trade_kw)
    tag_trade(conn, tid, *setups)
    return tid


# Generate 130 closed + 20 open stock trades = 150 total
with get_connection() as conn:
    for _ in range(130):
        gen_stock_trade(conn, open_pos=False)
    for _ in range(20):
        gen_stock_trade(conn, open_pos=True)

# ── Option pricing ────────────────────────────────────────────────────────────
# Premiums are Black-Scholes marks on the same real underlying path, using each
# ticker's own trailing realised volatility plus a small IV premium. Every leg is
# filled through the spread (buy the ask, sell the bid), so the recorded P&L is
# what the position would actually have returned over those dates.

OPT_MULT = 100.0
RISK_FREE = 0.04
ETF_UNDERLYINGS = {"SPY", "QQQ", "IWM", "GLD", "SLV"}


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S, K, T, sigma, kind) -> float:
    """Black-Scholes value of a European call/put."""
    if not S or S <= 0 or K <= 0:
        return 0.0
    if T <= 1e-6 or sigma <= 1e-6:
        return max(0.0, S - K) if kind == "call" else max(0.0, K - S)
    d1 = (math.log(S / K) + (RISK_FREE + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    disc = math.exp(-RISK_FREE * T)
    if kind == "call":
        return S * _ncdf(d1) - K * disc * _ncdf(d2)
    return K * disc * _ncdf(-d2) - S * _ncdf(-d1)


def implied_vol(ticker: str, d: date, lookback: int = 60) -> float:
    """Trailing realised vol of the real path, marked up to a plausible IV."""
    i = cal_i(d)
    closes = [c for c in (close_on(ticker, x) for x in CAL[max(0, i - lookback):i + 1]) if c]
    rets = [math.log(closes[k] / closes[k - 1]) for k in range(1, len(closes)) if closes[k - 1] > 0]
    if len(rets) < 10:
        return FALLBACK_VOL.get(ticker, DEFAULT_VOL)
    rv = statistics.pstdev(rets) * math.sqrt(252)
    return min(1.5, max(0.12, rv * 1.15))


def strike_step(ticker: str, S: float) -> float:
    """Strike increment actually listed for a name at that price."""
    if ticker in ETF_UNDERLYINGS:
        return 1.0
    if S < 25:
        return 1.0
    if S < 100:
        return 2.5
    if S < 250:
        return 5.0
    return 10.0


def snap_strike(x: float, step: float) -> float:
    return round(round(x / step) * step, 2)


def _fill(theo: float, action: str) -> float:
    """Cross the spread: pay up to buy, give up edge to sell."""
    edge = max(0.02, theo * 0.02)
    px = theo + edge if action == "buy" else theo - edge
    return round(max(0.01, px), 2)


def yrs(a: date, b: date) -> float:
    return max(0.0, (b - a).days / 365.0)


def friday_after(d: date, days_out: int) -> date:
    """Real options expire on Fridays — snap forward to the next one."""
    t = d + timedelta(days=days_out)
    return t + timedelta(days=(4 - t.weekday()) % 7)


def _opt_qty(per_contract_risk: float, ed: date) -> int:
    """Contracts so that per-contract risk × qty ≈ the account risk target (min 1)."""
    if per_contract_risk <= 0:
        return 1
    return max(1, round(trade_risk_dollars(ed) / per_contract_risk))


def add_option_leg(conn, ticker, ed, xd, side, qty, ep, xp,
                   strike, expiry, opt_type, leg_group, leg_label, mult=100,
                   spread_type=None, notes="Demo options trade"):
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
        notes=notes,
    )
    if spread_type:
        kw["spread_type"] = spread_type
    if xd:
        kw["exit_date"]  = iso(xd)
        kw["exit_price"] = xp
    return add_trade(conn, **kw)


def new_grp():
    return str(uuid.uuid4())[:8]


def _opt_dates(hold, *, open_pos=False):
    """(entry, exit, expiry). Closed trades get a random entry with room for the
    hold; open ones are entered in the last few weeks with expiry still ahead."""
    if open_pos:
        ed = rand_cal_day(cal_shift(TODAY, -14), cal_shift(TODAY, -3))
        return ed, None, friday_after(ed, random.randint(21, 40))
    ed = rand_cal_day(START, cal_shift(TODAY, -(hold + 2)))
    xd = cal_shift(ed, hold)
    return ed, xd, friday_after(xd, random.randint(4, 12))


def _leg_prices(ticker, ed, xd, expiry, strikes, kinds, actions):
    """Entry/exit fills per leg, marked off the real underlying on both dates."""
    S0, iv0, T0 = close_on(ticker, ed), implied_vol(ticker, ed), yrs(ed, expiry)
    entries = [_fill(bs_price(S0, K, T0, iv0, kind), act)
               for K, kind, act in zip(strikes, kinds, actions)]
    if xd is None:
        return entries, None
    S1, iv1, T1 = close_on(ticker, xd), implied_vol(ticker, xd), yrs(xd, expiry)
    exits = [_fill(bs_price(S1, K, T1, iv1, kind), "sell" if act == "buy" else "buy")
             for K, kind, act in zip(strikes, kinds, actions)]
    return entries, exits


def _structure_pnl(entries, exits, sides, qty):
    if exits is None:
        return 0.0
    total = 0.0
    for ep, xp, s in zip(entries, exits, sides):
        total += (xp - ep) * qty * OPT_MULT if s == "long" else (ep - xp) * qty * OPT_MULT
    return total

# ── Option structures ─────────────────────────────────────────────────────────
# Each structure is built at real strikes around where the stock actually traded
# on its entry date, and the entry date is re-drawn until the underlying's real
# move over the holding period produced the intended win or loss.

def _build_vertical(ticker, hold, direction, kind, open_pos):
    ed, xd, expiry = _opt_dates(hold, open_pos=open_pos)
    S = close_on(ticker, ed)
    if not S:
        return None
    step = strike_step(ticker, S)
    if kind == "debit":
        W = 5.0 if ticker in ETF_UNDERLYINGS else (step if step >= 5 else 2 * step)
        near = snap_strike(S, step)
        far = near + W if direction == "call" else near - W
        strikes, kinds, sides = [near, far], [direction, direction], ["long", "short"]
        actions = ["buy", "sell"]
        labels = [f"Long {direction.title()} {near:g}", f"Short {direction.title()} {far:g}"]
        spread_type = "Bull Call Spread" if direction == "call" else "Bear Put Spread"
    else:
        W = 2.0 if ticker in ETF_UNDERLYINGS else (step if step >= 5 else 2 * step)
        short_k = snap_strike(S * (0.96 if direction == "put" else 1.04), step)
        long_k = short_k - W if direction == "put" else short_k + W
        strikes, kinds, sides = [short_k, long_k], [direction, direction], ["short", "long"]
        actions = ["sell", "buy"]
        labels = [f"Short {direction.title()} {short_k:g}", f"Long {direction.title()} {long_k:g}"]
        spread_type = "Put Credit Spread" if direction == "put" else "Call Credit Spread"

    if min(strikes) <= 0:
        return None
    entries, exits = _leg_prices(ticker, ed, xd, expiry, strikes, kinds, actions)
    if kind == "debit":
        risk_pc = max(0.05, entries[0] - entries[1]) * OPT_MULT
    else:
        risk_pc = max(0.05, W - (entries[0] - entries[1])) * OPT_MULT
    qty = _opt_qty(risk_pc, ed)
    return dict(ed=ed, xd=xd, expiry=expiry, strikes=strikes, kinds=kinds, sides=sides,
                entries=entries, exits=exits, labels=labels, spread_type=spread_type,
                qty=qty, pnl=_structure_pnl(entries, exits, sides, qty))


def emit_vertical(conn, ticker, hold, direction, want_win, tags, *, kind, open_pos=False):
    built = None
    for _ in range(40):
        cand = _build_vertical(ticker, hold, direction, kind, open_pos)
        if not cand:
            continue
        built = cand
        if open_pos or (cand["pnl"] > 0) == want_win:
            break
    if not built:
        return
    grp = new_grp()
    for i, (K, otype, side, label) in enumerate(
            zip(built["strikes"], built["kinds"], built["sides"], built["labels"])):
        lid = add_option_leg(
            conn, ticker, built["ed"], built["xd"], side, built["qty"],
            built["entries"][i], None if built["exits"] is None else built["exits"][i],
            K, built["expiry"], otype, grp, label, spread_type=built["spread_type"],
            notes=f"{built['spread_type']} on {ticker}",
        )
        tag_trade(conn, lid, *tags)


def _build_condor(ticker, hold, open_pos):
    ed, xd, expiry = _opt_dates(hold, open_pos=open_pos)
    S = close_on(ticker, ed)
    if not S:
        return None
    step = strike_step(ticker, S)
    W = 2.0 if ticker in ETF_UNDERLYINGS else (step if step >= 5 else 2 * step)
    sp = snap_strike(S * 0.96, step)
    lp = sp - W
    sc = snap_strike(S * 1.04, step)
    lc = sc + W
    if lp <= 0:
        return None
    strikes = [sp, lp, sc, lc]
    kinds   = ["put", "put", "call", "call"]
    sides   = ["short", "long", "short", "long"]
    actions = ["sell", "buy", "sell", "buy"]
    labels  = [f"Short Put {sp:g}", f"Long Put {lp:g}",
               f"Short Call {sc:g}", f"Long Call {lc:g}"]
    entries, exits = _leg_prices(ticker, ed, xd, expiry, strikes, kinds, actions)
    credit = (entries[0] - entries[1]) + (entries[2] - entries[3])
    qty = _opt_qty(max(0.05, W - credit) * OPT_MULT, ed)
    return dict(ed=ed, xd=xd, expiry=expiry, strikes=strikes, kinds=kinds, sides=sides,
                entries=entries, exits=exits, labels=labels, qty=qty,
                pnl=_structure_pnl(entries, exits, sides, qty))


def emit_iron_condor(conn, ticker, hold, want_win, *, open_pos=False):
    built = None
    for _ in range(40):
        cand = _build_condor(ticker, hold, open_pos)
        if not cand:
            continue
        built = cand
        if open_pos or (cand["pnl"] > 0) == want_win:
            break
    if not built:
        return
    grp = new_grp()
    for i, (K, otype, side, label) in enumerate(
            zip(built["strikes"], built["kinds"], built["sides"], built["labels"])):
        lid = add_option_leg(
            conn, ticker, built["ed"], built["xd"], side, built["qty"],
            built["entries"][i], None if built["exits"] is None else built["exits"][i],
            K, built["expiry"], otype, grp, label, spread_type="Iron Condor",
            notes=f"Iron condor around {ticker} — range-bound thesis",
        )
        tag_trade(conn, lid, "Felix")


def _pick_single_strike(ticker, S, T, iv, kind, budget):
    """First strike, walking out of the money in 1% steps, whose premium fits the
    risk budget. Stepping by moneyness rather than by strike increment keeps the
    search honest on expensive names, where ten strikes is barely out of the money.
    Returns None when even a 25%-OTM contract costs far more than the budget — the
    caller then re-draws a different entry date rather than booking a position that
    would blow through the account's risk unit."""
    step = strike_step(ticker, S)
    best = None
    for pct in range(0, 26):
        m = (1 + pct / 100) if kind == "call" else (1 - pct / 100)
        K = snap_strike(S * m, step)
        if K <= 0:
            continue
        theo = bs_price(S, K, T, iv, kind)
        if theo < 0.15:                      # any further out is a lottery ticket
            break
        cost = theo * OPT_MULT
        if best is None or abs(cost - budget) < abs(best[1] - budget):
            best = (K, cost)
        if cost <= budget:
            break
    if not best or best[1] > 2.5 * budget:
        return None
    return best


def _build_single(ticker, hold, direction, open_pos):
    ed, xd, expiry = _opt_dates(hold, open_pos=open_pos)
    S = close_on(ticker, ed)
    if not S:
        return None
    iv, T = implied_vol(ticker, ed), yrs(ed, expiry)
    pick = _pick_single_strike(ticker, S, T, iv, direction, trade_risk_dollars(ed))
    if not pick:
        return None
    K = pick[0]
    entries, exits = _leg_prices(ticker, ed, xd, expiry, [K], [direction], ["buy"])
    qty = _opt_qty(entries[0] * OPT_MULT, ed)
    return dict(ed=ed, xd=xd, expiry=expiry, K=K, entry=entries[0],
                exit=None if exits is None else exits[0], qty=qty,
                pnl=_structure_pnl(entries, exits, ["long"], qty))


def emit_single(conn, ticker, hold, direction, want_win, tags, *, open_pos=False):
    built = None
    for _ in range(40):
        cand = _build_single(ticker, hold, direction, open_pos)
        if not cand:
            continue
        built = cand
        if open_pos or (cand["pnl"] > 0) == want_win:
            break
    if not built:
        return
    lid = add_option_leg(
        conn, ticker, built["ed"], built["xd"], "long", built["qty"],
        built["entry"], built["exit"], built["K"], built["expiry"], direction, None, None,
        notes=f"Long {direction} on {ticker} — directional, defined risk",
    )
    tag_trade(conn, lid, *tags)

# ── Closed option trades ──────────────────────────────────────────────────────
# (ticker, holding days, direction, intended outcome)

BULL_CALLS = [("AAPL", 15, "call", True),  ("MSFT", 18, "call", True),
              ("NVDA", 12, "call", False), ("META", 16, "call", False),
              ("AMD",  14, "call", True),  ("GOOG", 13, "call", True)]
BEAR_PUTS  = [("SPY",  12, "put", True),   ("QQQ",  14, "put", True),
              ("TSLA", 16, "put", False),  ("NFLX", 13, "put", True),
              ("IWM",  15, "put", False)]
PUT_CREDITS = [("AAPL", 18, "put", True),  ("MSFT", 16, "put", True),
               ("V",    20, "put", True),  ("JPM",  18, "put", False)]
IRON_CONDORS = [("SPY", 20, True), ("QQQ", 18, True), ("IWM", 22, True), ("SPY", 15, False)]
LONG_CALLS = [("AMD",  6, "call", True),  ("PLTR", 7, "call", True),
              ("UBER", 5, "call", True),  ("SHOP", 6, "call", False),
              ("PLTR", 8, "call", False)]
LONG_PUTS  = [("DIS",  6, "put", False),  ("MU",   7, "put", True),
              ("COIN", 5, "put", True),   ("QQQ",  6, "put", False)]

with get_connection() as conn:
    for tk, hold, d, w in BULL_CALLS:
        emit_vertical(conn, tk, hold, d, w, rand_tags(tk, "long"), kind="debit")
    for tk, hold, d, w in BEAR_PUTS:
        emit_vertical(conn, tk, hold, d, w, rand_tags(tk, "short"), kind="debit")
    for tk, hold, d, w in PUT_CREDITS:
        emit_vertical(conn, tk, hold, d, w, rand_tags(tk, "long"), kind="credit")
    for tk, hold, w in IRON_CONDORS:
        emit_iron_condor(conn, tk, hold, w)
    for tk, hold, d, w in LONG_CALLS:
        emit_single(conn, tk, hold, d, w, rand_tags(tk, "long"))
    for tk, hold, d, w in LONG_PUTS:
        emit_single(conn, tk, hold, d, w, rand_tags(tk, "short"))

# ── Open option positions ─────────────────────────────────────────────────────
with get_connection() as conn:
    emit_vertical(conn, "AAPL", None, "call", None, ("Breakout", "Felix"),
                  kind="debit", open_pos=True)
    emit_iron_condor(conn, "SPY", None, None, open_pos=True)
    emit_single(conn, "MSFT", None, "call", None, ("BullFlag",), open_pos=True)

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

equity_rows = []
running = STARTING_EQUITY
dev = 0.0
for i, dcur in enumerate(CAL):
    iso_d   = iso(dcur)
    contrib = contrib_by_day.get(iso_d, 0.0)
    running += contrib + realized_by_day.get(iso_d, 0.0)
    dev = 0.85 * dev + random.gauss(0.0, 90.0)      # AR(1) open-position mark-to-market
    if i == len(CAL) - 1:
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
# Levels come from where each name is actually trading now rather than from
# prices baked in when the script was written.

def _plan_levels(ticker, bullish=True):
    S = close_on(ticker, TODAY) or FALLBACK_PRICE[ticker]
    entry = round(S * (1.005 if bullish else 0.995), 2)
    if bullish:
        target = round(entry * random.uniform(1.09, 1.14), 2)
        stop   = round(entry * random.uniform(0.955, 0.97), 2)
        rr     = round((target - entry) / max(0.01, entry - stop), 1)
    else:
        target = round(entry * random.uniform(0.88, 0.93), 2)
        stop   = round(entry * random.uniform(1.025, 1.04), 2)
        rr     = round((entry - target) / max(0.01, stop - entry), 1)
    return entry, target, stop, rr

_aapl = _plan_levels("AAPL", True)
_nvda = _plan_levels("NVDA", True)
_spy  = _plan_levels("SPY", False)
_msft = _plan_levels("MSFT", True)

PLANS = [
    {
        "ticker": "AAPL", "sentiment": "Bullish",
        "rationale": "Breaking out of a 3-month base on high volume. Services and Vision Pro upgrade cycle.",
        "fundamentals": "P/E 28x, services growing 15% YoY, $100B buyback intact.",
        "technicals": f"Weekly close above {_aapl[0]:.2f} resistance. RSI 57 — room to run. 50-day MA trending up.",
        "trade_type": "Swing", "hold_time": "2–4 weeks",
        "entry_signal": f"Daily close above {_aapl[0]:.2f} on volume > 20-day avg",
        "confirm1": "SPY holding above 200-day MA", "confirm2": "No major macro events",
        "entry_price": _aapl[0], "profit_target": _aapl[1], "stop_loss": _aapl[2], "rr_ratio": _aapl[3],
    },
    {
        "ticker": "NVDA", "sentiment": "Bullish",
        "rationale": "AI infrastructure spending accelerating. Blackwell demand exceeding supply.",
        "fundamentals": "Revenue +78% YoY, data center 80% of revenue. Forward P/E 35x.",
        "technicals": "Tight consolidation at highs. Bollinger Bands squeezing.",
        "trade_type": "Momentum", "hold_time": "3–6 weeks",
        "entry_signal": f"Break and hold above {_nvda[0]:.2f} on daily close",
        "confirm1": "SOX semiconductor index trending up", "confirm2": "No guidance cut from hyperscalers",
        "entry_price": _nvda[0], "profit_target": _nvda[1], "stop_loss": _nvda[2], "rr_ratio": _nvda[3],
    },
    {
        "ticker": "SPY", "sentiment": "Bearish",
        "rationale": "Market extended after 10-week rally. VIX compression + overbought readings.",
        "fundamentals": "S&P 500 forward P/E 22x — above 10-year avg. Earnings growth slowing.",
        "technicals": "RSI 71 on weekly. Volume declining on up days.",
        "trade_type": "Options Play", "hold_time": "2–3 weeks",
        "entry_signal": "Daily close below 20-day MA",
        "confirm1": "Yield curve widening", "confirm2": "Put/call ratio rising",
        "entry_price": _spy[0], "profit_target": _spy[1], "stop_loss": _spy[2], "rr_ratio": _spy[3],
    },
    {
        "ticker": "MSFT", "sentiment": "Bullish",
        "rationale": "Azure cloud re-accelerating. Copilot monetization beginning to show.",
        "fundamentals": "Revenue +16% YoY, operating margin 45%.",
        "technicals": f"Breakout above {_msft[0]:.2f} on weekly. Prior ATH becomes support.",
        "trade_type": "Swing", "hold_time": "3–5 weeks",
        "entry_signal": f"Hold above {_msft[0]:.2f} for 3 days",
        "confirm1": "XLK holding 50-day MA", "confirm2": "No Fed rate shock",
        "entry_price": _msft[0], "profit_target": _msft[1], "stop_loss": _msft[2], "rr_ratio": _msft[3],
    },
]

with get_connection() as conn:
    for i, plan in enumerate(PLANS):
        saved = _dt.datetime.combine(cal_shift(START, i * 20), _dt.time(9, 30)).isoformat(sep=" ")
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
print(f"  prices: {PRICE_SOURCE} | {iso(START)} -> {iso(TODAY)} ({len(CAL)} sessions)")
print(f"  -> {DEMO_DB}")
