import re
import math
import time as _time_global
import uuid
import smtplib
import concurrent.futures
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from pathlib import Path
from db import init_db, get_connection, is_duplicate_trade, find_open_trade_id, find_open_trade_by_ticker_qty
import ib_client as _ib_mod
import updater as _upd

ATTACHMENTS_DIR = Path(__file__).parent / "attachments"
ATTACHMENTS_DIR.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "account_balance":      "0",
    "starting_equity":      "100000",
    "starting_date":        "",
    "pct_account_yellow":   "5",
    "pct_account_red":      "10",
    "stop_dist_unit":       "%",
    "stop_dist_yellow":     "5",
    "stop_dist_red":        "2",
    "euro_dates":           "0",
    "smtp_host":            "",
    "smtp_port":            "587",
    "smtp_user":            "",
    "smtp_pass":            "",
    "smtp_to":              "",
    "email_threshold_days": "5",
    "email_last_sent":      "",
    # App mode
    "app_mode":             "demo",  # "demo" | "live"
    # Commission defaults
    "default_commission":   "0",     # flat commission per trade (stocks)
    "options_commission":   "0.65",  # per contract
    "futures_commission":   "2.25",  # per contract
    # Currency
    "native_currency":      "USD",   # USD | AUD | CAD | EUR
    "currency_mode":        "0",     # 0 = USD only, 1 = show native currency
    # Row color coding
    "row_color_enabled":    "0",
    "row_color_style":      "text",   # "text" | "row"
    "color_open_profit":    "#2ecc71",
    "color_open_loss":      "#e74c3c",
    "color_closed_profit":  "#27ae60",
    "color_closed_loss":    "#c0392b",
    # Broker selection
    "broker":               "ib",   # "ib" | "schwab" | "fidelity"
    # Interactive Brokers
    "ib_host":              "127.0.0.1",
    "ib_port":              "7497",
    "ib_client_id":         "1",
    "ib_use_live_prices":   "0",
    "ib_auto_sync_balance": "0",
    "ib_auto_connect":      "0",
    # Theme
    "app_theme":            "ocean_dark",
    # Onboarding / guided setup tour ("1" once completed or skipped)
    "onboarding_done":      "0",
}

# ── App themes ────────────────────────────────────────────────────────────────
THEMES: dict[str, dict] = {
    "ocean_dark": {
        "label":          "🌊  Ocean Dark",
        "bg_main":        "#131929",
        "bg_sidebar":     "#1a2236",
        "bg_card":        "#1e2a40",
        "bg_input":       "#131929",
        "bg_select":      "#252a36",
        "bg_expander":    "#1a2236",
        "bg_menu":        "#1e222d",
        "bg_form":        "#1a2236",
        "border":         "#252f45",
        "border_input":   "#2e3a50",
        "accent":         "#4e8ef7",
        "text_primary":   "#c8cfe0",
        "text_secondary": "#8fa4c8",
        "text_dim":       "#7a90b0",
        "text_heading":   "#c8cfe0",
        "text_metric":    "#e0e8f5",
        "hr":             "#252f45",
        "tag_bg":         "#363c48",
        "nav_hover_bg":   "#1f2d46",
        "nav_hover_text": "#c8cfe0",
        "nav_active_bg":  "#1e3566",
        "nav_active_text":"#ffffff",
        "option_hover":   "#30363f",
        "chart_bg":       "#1e2535",
        "chart_grid":     "#2e3a50",
        "chart_font":     "#c8cfe0",
        "chart_legend":   "#252d3f",
        "chart_legend_font": "#c8cfe0",
    },
    "midnight": {
        "label":          "🌑  Midnight",
        "bg_main":        "#0a0a0f",
        "bg_sidebar":     "#111118",
        "bg_card":        "#16161f",
        "bg_input":       "#0a0a0f",
        "bg_select":      "#1c1c27",
        "bg_expander":    "#111118",
        "bg_menu":        "#16161f",
        "bg_form":        "#111118",
        "border":         "#2a2a3d",
        "border_input":   "#2a2a3d",
        "accent":         "#9b59b6",
        "text_primary":   "#d4d4e8",
        "text_secondary": "#8888aa",
        "text_dim":       "#666688",
        "text_heading":   "#d4d4e8",
        "text_metric":    "#e8e8f5",
        "hr":             "#2a2a3d",
        "tag_bg":         "#2a2a3d",
        "nav_hover_bg":   "#1e1e2e",
        "nav_hover_text": "#d4d4e8",
        "nav_active_bg":  "#2d1b69",
        "nav_active_text":"#bb86fc",
        "option_hover":   "#252535",
        "chart_bg":       "#0f0f18",
        "chart_grid":     "#2a2a3d",
        "chart_font":     "#d4d4e8",
        "chart_legend":   "#16161f",
        "chart_legend_font": "#d4d4e8",
    },
    "forest": {
        "label":          "🌲  Forest",
        "bg_main":        "#0d1a0f",
        "bg_sidebar":     "#122016",
        "bg_card":        "#172a1c",
        "bg_input":       "#0d1a0f",
        "bg_select":      "#1c2d20",
        "bg_expander":    "#122016",
        "bg_menu":        "#172a1c",
        "bg_form":        "#122016",
        "border":         "#1e3d25",
        "border_input":   "#2a4d32",
        "accent":         "#2ecc71",
        "text_primary":   "#c0d8c4",
        "text_secondary": "#7aa880",
        "text_dim":       "#5a8860",
        "text_heading":   "#c0d8c4",
        "text_metric":    "#d8f0dc",
        "hr":             "#1e3d25",
        "tag_bg":         "#1e3d25",
        "nav_hover_bg":   "#1a3020",
        "nav_hover_text": "#c0d8c4",
        "nav_active_bg":  "#0d3318",
        "nav_active_text":"#2ecc71",
        "option_hover":   "#1c321e",
        "chart_bg":       "#0f1f12",
        "chart_grid":     "#1e3d25",
        "chart_font":     "#c0d8c4",
        "chart_legend":   "#172a1c",
        "chart_legend_font": "#c0d8c4",
    },
    "light": {
        "label":          "☀️  Light",
        "bg_main":        "#f5f7fa",
        "bg_sidebar":     "#e8ecf4",
        "bg_card":        "#ffffff",
        "bg_input":       "#ffffff",
        "bg_select":      "#ffffff",
        "bg_expander":    "#ffffff",
        "bg_menu":        "#ffffff",
        "bg_form":        "#ffffff",
        "border":         "#d0d8e8",
        "border_input":   "#c0ccd8",
        "accent":         "#2563eb",
        "text_primary":   "#1a1f2e",
        "text_secondary": "#4a5568",
        "text_dim":       "#6b7280",
        "text_heading":   "#1a1f2e",
        "text_metric":    "#1a1f2e",
        "hr":             "#d0d8e8",
        "tag_bg":         "#e2e8f0",
        "nav_hover_bg":   "#dde5f0",
        "nav_hover_text": "#1a1f2e",
        "nav_active_bg":  "#dbeafe",
        "nav_active_text":"#1e40af",
        "option_hover":   "#f0f4ff",
        "chart_bg":       "#ffffff",
        "chart_grid":     "#e2e8f0",
        "chart_font":     "#1a1f2e",
        "chart_legend":   "#f8fafc",
        "chart_legend_font": "#1a1f2e",
    },
    "warm_sand": {
        "label":          "🏖️  Warm Sand",
        "bg_main":        "#faf7f0",
        "bg_sidebar":     "#f0ebe0",
        "bg_card":        "#fffdf7",
        "bg_input":       "#fffdf7",
        "bg_select":      "#fffdf7",
        "bg_expander":    "#fdf9f2",
        "bg_menu":        "#fffdf7",
        "bg_form":        "#fdf9f2",
        "border":         "#ddd0bc",
        "border_input":   "#c8b89a",
        "accent":         "#c0622a",
        "text_primary":   "#3d2c1a",
        "text_secondary": "#6b5040",
        "text_dim":       "#8a7060",
        "text_heading":   "#3d2c1a",
        "text_metric":    "#2a1c0a",
        "hr":             "#ddd0bc",
        "tag_bg":         "#ede0cc",
        "nav_hover_bg":   "#e8dcc8",
        "nav_hover_text": "#3d2c1a",
        "nav_active_bg":  "#fde8cc",
        "nav_active_text":"#c0622a",
        "option_hover":   "#f5ede0",
        "chart_bg":       "#fdf9f2",
        "chart_grid":     "#e8dcc8",
        "chart_font":     "#3d2c1a",
        "chart_legend":   "#f5efe0",
        "chart_legend_font": "#3d2c1a",
    },
}

DEFAULT_COLS = [
    "Trade ID", "Status", "Instrument", "Entry Date", "Ticker", "Quantity",
    "Spread Type", "Entry Price", "Exit Date", "Exit Price", "Live Price", "P&L",
]
ALL_COLS = [
    "Trade ID", "Status", "Instrument", "Entry Date", "Ticker", "Quantity",
    "Entry Price", "Exit Date", "Exit Price", "Live Price", "P&L",
    "Position Value", "Tags", "Stop Loss", "Notes", "Earnings",
    "Opening Stop", "Current Stop",
    "Days in Trade", "Ann. P&L",
    "Entry Value", "Current Value", "% of Account",
    "Realized P&L $", "Realized P&L %", "Unrealized P&L %", "Unrealized Ann. Return %", "Acct P&L %",
    "Day's Change", "Day Change %", "Day P&L", "Day P&L %",
    "Locked-in Profit", "Open Risk", "Opening Risk",
    "Stop Dist $", "Stop Dist %", "Stop Dist ATR",
    "Sector", "Industry", "Beta", "Correlation",
    # Options / Futures
    "Contract", "Leg", "Expiration", "Strike", "Option Type", "Multiplier", "Spread Group", "Spread Type",
    # Options Greeks (IB)
    "Underlying", "Delta", "Theta",
    # Multi-currency
    "P&L (Native)", "Entry (Native)", "Exit (Native)", "FX Rate Entry",
    # Trade costs
    "Commission",
    # Annualized return
    "Ann. Return %",
]

PRESET_STOCK = [
    "Trade ID", "Status", "Instrument", "Entry Date", "Ticker", "Quantity",
    "Entry Price", "Exit Date", "Exit Price", "Live Price", "P&L",
    "Current Stop", "Open Risk", "% of Account",
]
PRESET_OPTIONS = [
    "Trade ID", "Status", "Instrument", "Underlying", "Expiration", "Strike",
    "Quantity", "Entry Price", "Live Price", "P&L", "% of Account", "Delta", "Theta",
]

SECTOR_ETF_MAP = {
    "Technology":             "XLK",
    "Healthcare":             "XLV",
    "Health Care":            "XLV",
    "Financials":             "XLF",
    "Financial Services":     "XLF",
    "Consumer Cyclical":      "XLY",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Industrials":            "XLI",
    "Consumer Defensive":     "XLP",
    "Consumer Staples":       "XLP",
    "Energy":                 "XLE",
    "Utilities":              "XLU",
    "Basic Materials":        "XLB",
    "Materials":              "XLB",
    "Real Estate":            "XLRE",
}


# ── Format helpers ─────────────────────────────────────────────────────────────

def fmt_date(date_str, euro: bool = False) -> str:
    if date_str is None or pd.isna(date_str):
        return "—"
    d = pd.to_datetime(date_str)
    return d.strftime("%d/%m/%Y") if euro else d.strftime("%m/%d/%Y")


def fmt_price(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"${v:,.2f}"


def fmt_pnl(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    return f"${val:,.2f}" if val >= 0 else f"-${abs(val):,.2f}"


def fmt_qty(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{int(v):,}"


def fmt_pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:.2f}%"


def fmt_signed_pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"+{v:.2f}%" if v >= 0 else f"-{abs(v):.2f}%"


def fmt_num(v, decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:,.{decimals}f}"


# ── Instrument helpers ─────────────────────────────────────────────────────────

# IB exchange code → Yahoo Finance ticker suffix for non-US markets.
# US exchanges (NYSE, NASDAQ, ARCA, SMART, etc.) are omitted — no suffix needed.
_IB_EXCHANGE_TO_YF: dict[str, str] = {
    "IBIS":     ".DE",   # Xetra (Germany)
    "IBIS2":    ".DE",
    "FWB":      ".DE",   # Frankfurt
    "LSE":      ".L",    # London Stock Exchange
    "LSEETF":   ".L",
    "AEB":      ".AS",   # Euronext Amsterdam
    "SBF":      ".PA",   # Euronext Paris
    "BVME":     ".MI",   # Borsa Italiana
    "ENEXT.BE": ".BR",   # Euronext Brussels
    "VSE":      ".VI",   # Vienna
    "VIRTX":    ".SW",   # SIX Swiss Exchange
    "TSEJ":     ".T",    # Tokyo Stock Exchange
    "HKEX":     ".HK",   # Hong Kong
    "SEHK":     ".HK",
    "ASX":      ".AX",   # Australian Securities Exchange
    "TSX":      ".TO",   # Toronto Stock Exchange
    "VENTURE":  ".V",    # TSX Venture
    "SGX":      ".SI",   # Singapore
    "KSE":      ".KS",   # Korea
}

# Dropdown options for the manual Add Trade form: (IB code, user-facing label).
# Sorted alphabetically by country. The empty-string entry represents US/default (no suffix).
_EXCHANGE_OPTIONS: list[tuple[str, str]] = [
    ("",          "— US / Default"),
    ("ASX",       "ASX - Australia"),
    ("VSE",       "VSE - Austria"),
    ("ENEXT.BE",  "ENEXT.BE - Belgium"),
    ("TSX",       "TSX - Canada"),
    ("VENTURE",   "VENTURE - Canada (TSX Venture)"),
    ("SBF",       "SBF - France"),
    ("IBIS",      "IBIS - Germany (Xetra)"),
    ("FWB",       "FWB - Germany (Frankfurt)"),
    ("HKEX",      "HKEX - Hong Kong"),
    ("BVME",      "BVME - Italy"),
    ("TSEJ",      "TSEJ - Japan"),
    ("AEB",       "AEB - Netherlands"),
    ("SGX",       "SGX - Singapore"),
    ("KSE",       "KSE - South Korea"),
    ("VIRTX",     "VIRTX - Switzerland"),
    ("LSE",       "LSE - United Kingdom"),
]
_EXCHANGE_LABEL: dict[str, str] = {code: label for code, label in _EXCHANGE_OPTIONS}


def _yf_symbol(ticker: str, exchange: str = "") -> str:
    """Return the Yahoo Finance symbol for a ticker, appending the exchange suffix if needed."""
    suffix = _IB_EXCHANGE_TO_YF.get((exchange or "").upper().strip(), "")
    if suffix and not ticker.upper().endswith(suffix.upper()):
        return f"{ticker}{suffix}"
    return ticker


def build_option_symbol(ticker: str, expiration, strike: float, opt_type: str) -> str:
    """OCC-format symbol: AAPL261231C00242500  (strike × 1000, zero-padded to 8 digits)."""
    exp       = pd.to_datetime(expiration)
    type_char = "C" if str(opt_type).upper().startswith("C") else "P"
    return f"{ticker.upper()}{exp.strftime('%y%m%d')}{type_char}{int(round(float(strike) * 1000)):08d}"


def _get_live_ticker(row) -> str:
    """Symbol used for live-price lookup (OCC symbol for options, yfinance-suffixed for non-US stocks)."""
    if str(row.get("instrument_type") or "stock").lower() == "option":
        exp    = row.get("expiration")
        strike = row.get("strike")
        if exp and strike and not pd.isna(strike):
            return build_option_symbol(
                row["ticker"], exp, float(strike), row.get("option_type") or "C"
            )
    return _yf_symbol(row["ticker"], row.get("exchange") or "")


def _contract_sym(row) -> str:
    if str(row.get("instrument_type") or "stock").lower() == "option":
        exp    = row.get("expiration")
        strike = row.get("strike")
        if exp and strike and not pd.isna(strike):
            return build_option_symbol(
                row["ticker"], exp, float(strike), row.get("option_type") or "C"
            )
    return "—"


# ── Cached fetchers ────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _yf_get_live_data(symbols: tuple) -> dict:
    """Batch-fetch live prices from Yahoo Finance in a single download call."""
    if not symbols:
        return {}
    result: dict = {}
    try:
        raw = yf.download(
            list(symbols), period="2d", auto_adjust=True,
            progress=False, threads=True, group_by="ticker",
        )
        if raw.empty:
            raise ValueError("empty")
        if isinstance(raw.columns, pd.MultiIndex):
            # Multiple tickers → MultiIndex columns. With group_by="ticker" the
            # levels are (ticker, field) so the close is raw[sym]["Close"]; other
            # layouts use (field, ticker) → raw["Close"][sym]. Detect which level
            # holds the tickers instead of assuming (the wrong assumption made
            # every lookup KeyError, so all live prices came back empty).
            _lvl0 = set(raw.columns.get_level_values(0))
            _ticker_first = any(s in _lvl0 for s in symbols)
            for sym in symbols:
                try:
                    _col   = raw[sym]["Close"] if _ticker_first else raw["Close"][sym]
                    closes = _col.dropna()
                    if len(closes) >= 1:
                        price      = float(closes.iloc[-1])
                        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else price
                        result[sym] = {"price": price, "prev_close": prev_close}
                    else:
                        result[sym] = {"price": None, "prev_close": None}
                except Exception:
                    result[sym] = {"price": None, "prev_close": None}
        else:
            # Single ticker → flat columns
            sym    = symbols[0]
            closes = raw["Close"].dropna()
            if len(closes) >= 1:
                price      = float(closes.iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else price
                result[sym] = {"price": price, "prev_close": prev_close}
            else:
                result[sym] = {"price": None, "prev_close": None}
    except Exception:
        # Per-ticker fallback
        for t in symbols:
            try:
                fi = yf.Ticker(t).fast_info
                result[t] = {"price": fi.last_price, "prev_close": fi.previous_close}
            except Exception:
                result[t] = {"price": None, "prev_close": None}
    return result


_OCC_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")


def _is_occ_symbol(s: str) -> bool:
    return bool(_OCC_RE.match(s))


def option_legs_max_risk(legs: list) -> "float | None":
    """Maximum loss (positive dollars) of an option position at expiration.

    `legs` is a list of dicts: {type:'call'/'put', strike, side:'long'/'short',
    qty (contracts, positive), mult (shares/contract), entry_price (premium/share)}.

    Computes the worst-case P&L by evaluating the piecewise-linear expiration payoff
    at S=0 and at every strike (the only breakpoints), net of the entry debit/credit.
    Returns the loss as a positive number, 0.0 if no loss is possible, or None if the
    risk is unbounded (a net-short call position whose payoff → −∞ as the underlying
    rises).
    """
    norm = []
    for lg in legs:
        try:
            k  = float(lg["strike"])
            q  = float(lg["qty"]) * float(lg.get("mult") or 1.0)
            ep = float(lg["entry_price"])
        except (TypeError, ValueError, KeyError):
            return None
        s    = -1.0 if str(lg.get("side", "long")).lower() == "short" else 1.0
        is_c = str(lg.get("type", "")).lower().startswith("c")
        norm.append((s, is_c, k, q, ep))

    if not norm:
        return None

    # Net cash paid at entry (positive = debit paid, negative = credit received)
    cost = sum(s * ep * q for (s, is_c, k, q, ep) in norm)

    # Slope of total payoff as S → ∞ (only calls contribute). Net short → unbounded.
    slope_inf = sum(s * q for (s, is_c, k, q, ep) in norm if is_c)
    if slope_inf < -1e-9:
        return None

    def payoff(S: float) -> float:
        tot = 0.0
        for (s, is_c, k, q, ep) in norm:
            intr = max(S - k, 0.0) if is_c else max(k - S, 0.0)
            tot += s * intr * q
        return tot

    strikes  = sorted({k for (_, _, k, _, _) in norm})
    min_pnl  = min(payoff(S) - cost for S in ([0.0] + strikes))
    return max(0.0, -min_pnl)


def _detect_spread_type(legs) -> str:
    """Infer spread type from leg structure.

    Normalises by collapsing duplicate (side, strike, type, expiration) combos
    first, so a vertical filled in two pieces is still detected as a Vertical.
    """
    if len(legs) < 2:
        return "Single"

    norm_cols = [c for c in ("side", "strike", "option_type", "expiration")
                 if c in legs.columns]
    if norm_cols:
        norm = legs[norm_cols].dropna(subset=norm_cols).drop_duplicates()
    else:
        norm = legs

    n_exps    = norm["expiration"].nunique()  if "expiration"   in norm.columns else 0
    n_strikes = norm["strike"].nunique()      if "strike"       in norm.columns else 0
    n_types   = norm["option_type"].nunique() if "option_type"  in norm.columns else 0

    # ── Multi-expiry ──────────────────────────────────────────────────
    if n_exps > 1:
        # Same strike, different expirations → Calendar
        # Different strikes, different expirations → Diagonal
        return "Calendar" if n_strikes <= 1 else "Diagonal"

    # ── Single expiry — classify by unique strikes and option types ───
    if n_types <= 1:
        # Single option type (all calls or all puts)
        if n_strikes == 2:
            return "Vertical"       # bull/bear spread
        if n_strikes == 3:
            return "Butterfly"      # classic 1-2-1
        if n_strikes == 4:
            return "Condor"         # 1-1-1-1 same type
    else:
        # Mixed calls and puts
        if n_strikes == 1:
            return "Straddle"       # same strike, call + put
        if n_strikes == 2:
            return "Strangle"       # diff strikes, call + put
        if n_strikes == 3:
            return "Iron Fly"       # put spread + call spread, shared middle
        if n_strikes == 4:
            return "Iron Condor"    # put spread + call spread, 4 strikes

    return "Multi-Leg"


def spread_unit_count(quantities) -> "float | None":
    """Number of spread *units* from a list of per-leg quantities.

    A balanced spread (all legs the same quantity) returns that quantity — e.g.
    5 long calls + 5 short calls = 5 spreads. A ratio spread returns the GCD of
    the integer leg quantities (a 1×2 ratio → 1 unit). Returns None when it
    can't be determined (no quantities, or unequal fractional quantities).
    """
    qtys = [abs(float(q)) for q in quantities if q is not None and float(q) != 0]
    if not qtys:
        return None
    if all(abs(q - round(q)) < 1e-9 for q in qtys):
        ints = [int(round(q)) for q in qtys]
        g = ints[0]
        for x in ints[1:]:
            g = math.gcd(g, x)
        return float(g) if g > 0 else None
    if max(qtys) - min(qtys) < 1e-9:
        return qtys[0]
    return None


def row_is_option(row) -> bool:
    return str(row.get("instrument_type") or "stock").lower() == "option"


# ── Black-Scholes greeks (local fallback when IB model greeks aren't available) ──

_SQRT2       = math.sqrt(2.0)
_INV_SQRT2PI = 1.0 / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _norm_pdf(x: float) -> float:
    return _INV_SQRT2PI * math.exp(-0.5 * x * x)


def _bs_price(S: float, K: float, T: float, r: float, sigma: float, is_call: bool) -> float:
    if sigma <= 0 or T <= 0:
        return max(S - K, 0.0) if is_call else max(K - S, 0.0)
    sq = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sq
    d2 = d1 - sq
    if is_call:
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_greeks(S, K, T, r, sigma, is_call):
    """Return (delta_per_share, theta_per_share_per_day) for a European option, or None."""
    try:
        S, K, T, r, sigma = float(S), float(K), float(T), float(r), float(sigma)
    except (TypeError, ValueError):
        return None
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    sqrtT = math.sqrt(T)
    sq    = sigma * sqrtT
    d1    = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sq
    d2    = d1 - sq
    if is_call:
        delta = _norm_cdf(d1)
        theta = (-(S * _norm_pdf(d1) * sigma) / (2 * sqrtT)
                 - r * K * math.exp(-r * T) * _norm_cdf(d2))
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (-(S * _norm_pdf(d1) * sigma) / (2 * sqrtT)
                 + r * K * math.exp(-r * T) * _norm_cdf(-d2))
    return delta, theta / 365.0


def bs_implied_vol(price, S, K, T, r, is_call):
    """Invert Black-Scholes for implied volatility via bisection. None if not solvable."""
    try:
        price, S, K, T, r = float(price), float(S), float(K), float(T), float(r)
    except (TypeError, ValueError):
        return None
    if price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    intrinsic = max(S - K, 0.0) if is_call else max(K - S, 0.0)
    if price < intrinsic - 1e-6:
        return None  # below intrinsic — bad/stale quote
    lo, hi = 1e-4, 5.0
    if price <= _bs_price(S, K, T, r, lo, is_call):
        return lo
    if price >= _bs_price(S, K, T, r, hi, is_call):
        return hi
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _bs_price(S, K, T, r, mid, is_call) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _yf_close_frame(symbols: tuple, period: str):
    """Download `period` of closes and return a {sym: pandas Series of closes}.
    Handles yfinance's multi-ticker (field, ticker) MultiIndex and the single-ticker
    flat-column layouts uniformly."""
    out: dict = {}
    if not symbols:
        return out
    try:
        raw = yf.download(list(symbols), period=period, auto_adjust=True,
                          progress=False, threads=True)
        if raw.empty:
            return out
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]  # default layout → top level is the field
            for sym in symbols:
                try:
                    s = close[sym].dropna()
                    if len(s):
                        out[sym] = s
                except Exception:
                    pass
        else:
            s = raw["Close"].dropna()
            if len(s):
                out[symbols[0]] = s
    except Exception:
        pass
    return out


@st.cache_data(ttl=120)
def get_underlying_spots(symbols: tuple) -> dict:
    """Latest close per symbol from Yahoo. {sym: price}. Correct multi-ticker parsing."""
    return {sym: float(s.iloc[-1]) for sym, s in _yf_close_frame(symbols, "2d").items()}


@st.cache_data(ttl=3600)
def get_historical_vol(symbols: tuple) -> dict:
    """Annualised historical volatility (decimal) per symbol from ~3 months of closes.
    Used as the volatility input for local greeks when an option market price isn't
    available to imply vol from. Cached hourly."""
    out: dict = {}
    for sym, closes in _yf_close_frame(symbols, "3mo").items():
        try:
            rets = np.log(closes / closes.shift(1)).dropna()
            if len(rets) >= 10:
                out[sym] = float(rets.std() * np.sqrt(252))
        except Exception:
            pass
    return out


def compute_position_greeks(open_trades, live_data) -> dict:
    """Signed POSITION greeks per open option trade, keyed by trade id.

    Returns {trade_id: {"delta": share-equiv position delta, "theta": $/day}}.
    Short legs are negative; greeks scale by sign × qty × multiplier so spread
    groups aggregate by simple summation.

    Greeks are computed locally with Black-Scholes — crucially using each option's
    *real market price* (already fetched into `live_data`) to imply volatility, so
    the delta tracks the broker's model delta closely. Implied vol falls back to the
    underlying's historical vol, then 0.30. Underlying spot prices come from Yahoo
    (no extra IB round-trips, so this never blocks on per-contract market-data snapshots).

    Intended to be called once per price refresh and cached — not on every rerun.
    """
    out: dict = {}
    if open_trades is None or open_trades.empty:
        return out
    opt = open_trades[open_trades.apply(row_is_option, axis=1)]
    if opt.empty:
        return out

    r_rate = fetch_risk_free_rate()

    # Underlying spot prices + historical-vol fallback (Yahoo only — fast, cached).
    _under_syms = tuple(sorted({
        _yf_symbol(r["ticker"], r.get("exchange") or "") for _, r in opt.iterrows()
    }))
    spot_data = get_underlying_spots(_under_syms) if _under_syms else {}
    hv_map    = get_historical_vol(_under_syms) if _under_syms else {}

    for _, r in opt.iterrows():
        try:
            tid = int(r["id"]) if pd.notna(r.get("id")) else None
            if tid is None:
                continue
            sign = -1.0 if str(r.get("side", "long")).lower() == "short" else 1.0
            qty  = float(r["quantity"])
            mult = float(r.get("multiplier") or 1.0)

            under_sym = _yf_symbol(r["ticker"], r.get("exchange") or "")
            S   = spot_data.get(under_sym)
            K   = float(r["strike"]) if pd.notna(r.get("strike")) else None
            exp = pd.to_datetime(r.get("expiration"), errors="coerce")
            if not (S and K and pd.notna(exp)):
                continue
            T = max((exp - today_ts).days, 0) / 365.0
            if T <= 0:
                continue

            is_call = str(r.get("option_type", "")).lower().startswith("c")
            _occ    = build_option_symbol(r["ticker"], exp, K, r.get("option_type") or "C")
            _opt_px = (live_data.get(_occ) or {}).get("price")
            sigma   = bs_implied_vol(_opt_px, S, K, T, r_rate, is_call) if _opt_px else None
            if not sigma:
                sigma = hv_map.get(under_sym) or 0.30

            g = bs_greeks(S, K, T, r_rate, sigma, is_call)
            if g:
                dps, tps = g
                out[tid] = {
                    "delta": sign * qty * mult * float(dps),
                    "theta": sign * qty * mult * float(tps),
                }
        except Exception:
            pass

    return out


def get_live_data(symbols: tuple) -> dict:
    """Live price fetcher: tries IB first (if configured), falls back to Yahoo Finance.

    IB connections are throttled via session_state: at most one socket open per 60s
    per unique symbol set, so rapid Streamlit reruns skip the IB round-trip entirely.
    OCC option symbols (e.g. SPY260619C00605000) are stripped before the Yahoo fallback
    because Yahoo Finance cannot price them.
    """
    if not symbols:
        return {}
    ib_cfg = st.session_state.get("_ib_cfg")
    if ib_cfg and ib_cfg.get("use_live") and _ib_mod.is_available():
        import time as _time
        _ck  = f"_ib_live_{symbols}"
        _hit = st.session_state.get(_ck)
        if _hit and (_time.time() - _hit["ts"]) < 60:
            return _hit["data"]
        try:
            with _ib_mod.IBClient(ib_cfg["host"], ib_cfg["port"], ib_cfg["cid"]) as ib:
                ib_result = ib.get_live_prices(list(symbols))
            if ib_result:
                # Fall back to Yahoo for symbols IB didn't return OR returned None price for
                missing_yf = tuple(
                    s for s in symbols
                    if (s not in ib_result or ib_result[s].get("price") is None)
                    and not _is_occ_symbol(s)
                )
                if missing_yf:
                    ib_result.update(_yf_get_live_data(missing_yf))
                st.session_state[_ck] = {"ts": _time.time(), "data": ib_result}
                return ib_result
        except Exception:
            pass
    # Yahoo Finance path: strip OCC option symbols it cannot price
    yf_symbols = tuple(s for s in symbols if not _is_occ_symbol(s))
    return _yf_get_live_data(yf_symbols)


_FX_PAIRS = {
    "AUD": "AUDUSD=X",
    "CAD": "CADUSD=X",
    "EUR": "EURUSD=X",
    "USD": None,
}

@st.cache_data(ttl=3600)
def get_fx_rate(native_currency: str) -> float:
    """Return the USD per 1 unit of native_currency (e.g. EUR→USD rate).
    Returns 1.0 for USD or on error."""
    if native_currency == "USD":
        return 1.0
    pair = _FX_PAIRS.get(native_currency.upper())
    if not pair:
        return 1.0
    try:
        fi = yf.Ticker(pair).fast_info
        return float(fi.last_price or 1.0)
    except Exception:
        return 1.0


@st.cache_data(ttl=86400)
def get_fx_rate_at_date(native_currency: str, date_str: str) -> float:
    """Historical FX rate on a specific date. Returns 1.0 for USD or on error."""
    if native_currency == "USD":
        return 1.0
    pair = _FX_PAIRS.get(native_currency.upper())
    if not pair:
        return 1.0
    try:
        dt  = pd.Timestamp(date_str)
        raw = yf.download(pair,
                          start=(dt - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
                          end=(dt + pd.Timedelta(days=2)).strftime("%Y-%m-%d"),
                          auto_adjust=True, progress=False)
        if raw.empty:
            return 1.0
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        closes = raw["Close"].dropna()
        closes.index = pd.to_datetime(closes.index).normalize()
        on_date = closes[closes.index <= dt.normalize()]
        return float(on_date.iloc[-1]) if not on_date.empty else 1.0
    except Exception:
        return 1.0


@st.cache_data(ttl=86400)
def get_underlying_price_at_date(ticker: str, date_str: str) -> float | None:
    """Return the closing price of `ticker` on `date_str` (YYYY-MM-DD).
    Falls back to the nearest available close if the exact date has no data (weekend/holiday)."""
    try:
        dt   = pd.Timestamp(date_str)
        # fetch a small window around the target date
        raw  = yf.download(
            ticker,
            start=(dt - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
            end=(dt + pd.Timedelta(days=2)).strftime("%Y-%m-%d"),
            auto_adjust=True, progress=False,
        )
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        closes = raw["Close"].dropna()
        if closes.empty:
            return None
        # exact date or closest before
        closes.index = pd.to_datetime(closes.index).normalize()
        on_date = closes[closes.index <= dt.normalize()]
        return float(on_date.iloc[-1]) if not on_date.empty else float(closes.iloc[0])
    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_highest_high_since(ticker: str, entry_date: str) -> float | None:
    """Return the highest intraday High for ticker from entry_date through today."""
    try:
        today = pd.Timestamp.today().strftime("%Y-%m-%d")
        raw   = yf.download(ticker, start=entry_date, end=today,
                             auto_adjust=True, progress=False)
        if raw.empty:
            return None
        highs = raw["High"]
        if isinstance(highs, pd.DataFrame):
            highs = highs.iloc[:, 0]
        return float(highs.max())
    except Exception:
        return None


@st.cache_data(ttl=30)
def _get_single_live_price(ticker: str, exchange: str = "") -> float | None:
    """Fast single-ticker price lookup for trade-entry forms (30-second cache)."""
    try:
        p = yf.Ticker(_yf_symbol(ticker, exchange)).fast_info.last_price
        return float(p) if p else None
    except Exception:
        return None


@st.cache_data(ttl=3600)
def validate_ticker(ticker: str, exchange: str = "") -> bool:
    try:
        return yf.Ticker(_yf_symbol(ticker, exchange)).fast_info.last_price is not None
    except Exception:
        return False


@st.cache_data(ttl=3600)
def get_ticker_info(ticker: str, exchange: str = "") -> dict | None:
    try:
        info = yf.Ticker(_yf_symbol(ticker, exchange)).info
        name = info.get("longName") or info.get("shortName")
        exch = info.get("fullExchangeName") or info.get("exchange")
        return {"name": name, "exchange": exch} if name else None
    except Exception:
        return None


@st.cache_data(ttl=86400)
def get_ticker_sector(ticker: str, exchange: str = "") -> str | None:
    try:
        return yf.Ticker(_yf_symbol(ticker, exchange)).info.get("sector")
    except Exception:
        return None


@st.cache_data(ttl=86400)
def get_ticker_metadata(tickers: tuple) -> dict:
    if not tickers:
        return {}
    result = {t: {"sector": None, "industry": None, "beta": None,
                  "atr14": None, "correlation_spy": None} for t in tickers}
    all_dl = list(set(list(tickers) + ([] if "SPY" in tickers else ["SPY"])))
    try:
        raw = yf.download(all_dl, period="1y", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            close_df = raw["Close"]
            high_df  = raw["High"]
            low_df   = raw["Low"]
        else:
            t0 = all_dl[0]
            close_df = raw[["Close"]].rename(columns={"Close": t0})
            high_df  = raw[["High"]].rename(columns={"High": t0})
            low_df   = raw[["Low"]].rename(columns={"Low": t0})
        returns_df = close_df.pct_change().dropna()
        for t in tickers:
            if t not in close_df.columns:
                continue
            try:
                h  = high_df[t].dropna()
                lo = low_df[t].dropna()
                c  = close_df[t].dropna()
                pc = c.shift(1)
                tr = pd.concat([(h - lo).abs(), (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
                atr_s = tr.rolling(14).mean().dropna()
                if not atr_s.empty:
                    result[t]["atr14"] = float(atr_s.iloc[-1])
            except Exception:
                pass
            try:
                if "SPY" in returns_df.columns and t in returns_df.columns:
                    result[t]["correlation_spy"] = float(returns_df[t].corr(returns_df["SPY"]))
            except Exception:
                pass
    except Exception:
        pass
    def _fetch_info(t):
        try:
            info = yf.Ticker(t).info
            return t, {
                "sector":   info.get("sector"),
                "industry": info.get("industry"),
                "beta":     info.get("beta"),
            }
        except Exception:
            return t, {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for t, info_data in pool.map(_fetch_info, tickers):
            result[t].update(info_data)
    return result


@st.cache_data(ttl=3600)
def load_chart_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return raw
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def fetch_next_earnings(ticker: str) -> str | None:
    """Return next earnings date (ISO string) for ticker, or None."""
    try:
        info = yf.Ticker(ticker).info
        ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if ts:
            dt = pd.Timestamp(ts, unit="s").date()
            if dt >= pd.Timestamp.today().date():
                return str(dt)
        cal = yf.Ticker(ticker).calendar
        if cal is not None:
            today_d = pd.Timestamp.today().date()
            if isinstance(cal, dict):
                for v in cal.get("Earnings Date", []):
                    try:
                        d = pd.to_datetime(v).date()
                        if d >= today_d:
                            return str(d)
                    except Exception:
                        pass
            elif hasattr(cal, "to_dict"):
                for col in cal.columns:
                    for v in cal[col]:
                        try:
                            d = pd.to_datetime(v).date()
                            if d >= today_d:
                                return str(d)
                        except Exception:
                            pass
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600)
def fetch_risk_free_rate() -> float:
    """Return the current annualised risk-free rate (decimal) from yfinance ^IRX (3-month T-bill).
    Falls back to 4.50% if the feed is unavailable."""
    try:
        raw = yf.download("^IRX", period="5d", auto_adjust=True, progress=False)
        if not raw.empty:
            close = raw["Close"].dropna()
            if not close.empty:
                return round(float(close.iloc[-1]) / 100, 4)
    except Exception:
        pass
    return 0.045  # 4.50% default


@st.cache_data(ttl=3600)
def compute_benchmark_stats(ticker: str, start_date: str, end_date: str) -> dict:
    """Annualised Sharpe, Sortino, Calmar for a benchmark over a date range."""
    try:
        raw = yf.download(ticker, start=start_date, end=end_date,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return {}
        prices = raw["Close"]
        if isinstance(prices, pd.DataFrame):
            prices = prices.iloc[:, 0]
        prices = prices.dropna()
        if len(prices) < 5:
            return {}
        daily = prices.pct_change().dropna()
        mean_r = float(daily.mean())
        std_r  = float(daily.std())
        neg    = daily[daily < 0]
        std_d  = float(neg.std()) if len(neg) > 1 else float("nan")
        sharpe  = mean_r / std_r * (252 ** 0.5) if std_r > 0 else float("nan")
        sortino = mean_r / std_d * (252 ** 0.5) if std_d > 0 else float("nan")
        cum        = (1 + daily).cumprod()
        roll_max   = cum.cummax()
        dd         = (roll_max - cum) / roll_max
        max_dd_pct = float(dd.max())
        ann_ret    = (cum.iloc[-1] - 1) * (252 / max(len(daily), 1))
        calmar     = ann_ret / max_dd_pct if max_dd_pct > 0 else float("nan")
        return {"sharpe": sharpe, "sortino": sortino, "calmar": calmar,
                "max_dd_pct": max_dd_pct * 100}
    except Exception:
        return {}


# ── Settings helpers ───────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_all_settings() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def seed_default_settings():
    with get_connection() as conn:
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))


# ── Cached DB wrappers (session-state version counter busts the @cache) ────────

@st.cache_data(show_spinner=False)
def _cached_load_trades(_v: int) -> pd.DataFrame:
    return load_trades()

@st.cache_data(show_spinner=False)
def _cached_get_settings(_v: int) -> dict:
    return get_all_settings()

@st.cache_data(show_spinner=False)
def _cached_load_tags(_v: int) -> list:
    return load_tags()

@st.cache_data(show_spinner=False)
def _cached_load_accounts(_v: int) -> list:
    return load_accounts()

@st.cache_data(show_spinner=False)
def _cached_load_equity_entries(_v: int) -> list:
    return load_equity_entries()

@st.cache_data(show_spinner=False)
def _cached_load_trading_plans(_v: int) -> list:
    return load_trading_plans()

def _bust(*keys: str):
    """Increment one or more version counters so the next render re-queries."""
    for k in keys:
        st.session_state[k] = st.session_state.get(k, 0) + 1


# ── Benchmark helpers ──────────────────────────────────────────────────────────

def fetch_benchmark_data(tickers: list, start_date: str):
    if not tickers:
        return
    latest_dates = {}
    with get_connection() as conn:
        for ticker in tickers:
            row = conn.execute(
                "SELECT MAX(date) FROM benchmark_prices WHERE ticker=?", (ticker,)
            ).fetchone()
            latest_dates[ticker] = row[0] if row and row[0] else None

    min_cached = None
    for ticker in tickers:
        ld = latest_dates.get(ticker)
        if ld is None:
            min_cached = None
            break
        if min_cached is None or ld < min_cached:
            min_cached = ld

    fetch_from = min_cached if min_cached else (start_date or "2015-01-01")
    try:
        raw = yf.download(tickers, start=fetch_from, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            close_df = raw["Close"]
        elif len(tickers) == 1:
            close_df = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            close_df = raw[["Close"]]

        rows_to_insert = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            for date_idx, price in close_df[ticker].dropna().items():
                date_str = date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, "strftime") else str(date_idx)[:10]
                rows_to_insert.append((ticker, date_str, float(price)))

        if rows_to_insert:
            with get_connection() as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO benchmark_prices (ticker, date, close) VALUES (?, ?, ?)",
                    rows_to_insert,
                )
    except Exception:
        pass


def load_benchmark_series(ticker: str, start_date: str, start_equity: float,
                          normalize: bool = True) -> pd.Series:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT date, close FROM benchmark_prices WHERE ticker=? AND date >= ? ORDER BY date",
            (ticker, start_date or "1900-01-01"),
        ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([r["close"] for r in rows], index=pd.to_datetime([r["date"] for r in rows]), name=ticker)
    # normalize=False returns the raw closes — used for VIX, which is an index
    # level (≈10–80), not a price to rebase onto the portfolio's equity.
    if normalize and len(s) > 0 and s.iloc[0] != 0:
        s = s / s.iloc[0] * start_equity
    return s


def smooth_line_xy(x_num, y, strength: float, subdivisions: int = 18):
    """Visually smooth a line WITHOUT averaging the data.

    Returns a denser (x, y) curve that still passes through every original point
    but curves smoothly between them, using a centripetal-style Catmull-Rom spline
    on the y-values. `strength` (0..1) blends from the straight polyline (0) to the
    full smooth curve (1); x stays linear within each segment so dates remain
    strictly increasing. Because the curve always hits the original points, this is
    pure line smoothing — not a moving average.
    """
    x_num = np.asarray(x_num, dtype=float)
    y     = np.asarray(y, dtype=float)
    n = len(x_num)
    if n < 3 or strength <= 0:
        return x_num, y
    xs = np.concatenate(([x_num[0]], x_num, [x_num[-1]]))
    ys = np.concatenate(([y[0]],     y,     [y[-1]]))
    t  = np.linspace(0.0, 1.0, subdivisions, endpoint=False)
    t2, t3 = t * t, t * t * t
    out_x, out_y = [], []
    for i in range(1, n):
        p0y, p1y, p2y, p3y = ys[i - 1], ys[i], ys[i + 1], ys[i + 2]
        cy = 0.5 * ((2 * p1y)
                    + (-p0y + p2y) * t
                    + (2 * p0y - 5 * p1y + 4 * p2y - p3y) * t2
                    + (-p0y + 3 * p1y - 3 * p2y + p3y) * t3)
        lx = xs[i] + (xs[i + 1] - xs[i]) * t        # linear x within the segment
        ly = p1y + (p2y - p1y) * t                  # straight-line y reference
        out_x.extend(lx.tolist())
        out_y.extend((ly + (cy - ly) * strength).tolist())
    out_x.append(x_num[-1])
    out_y.append(y[-1])
    return np.asarray(out_x), np.asarray(out_y)


# ── Logic helpers ──────────────────────────────────────────────────────────────

def _is_open(row) -> bool:
    return pd.isna(row["exit_date"])


def _pnl_numeric(row, live_data: dict):
    qty        = row["quantity"]
    ep         = row["entry_price"]
    multiplier = float(row.get("multiplier") or 1.0)
    side       = str(row.get("side") or "long").lower()
    if not qty or not ep:
        return None
    live_key = _get_live_ticker(row)
    if _is_open(row):
        lp = live_data.get(live_key, {}).get("price")
        if lp is None:
            return None
        raw = (lp - ep) * qty * multiplier
        return -raw if side == "short" else raw
    xp = row["exit_price"]
    if xp is None or (isinstance(xp, float) and pd.isna(xp)):
        return None
    raw = (float(xp) - ep) * qty * multiplier
    return -raw if side == "short" else raw


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _style_table(df: pd.DataFrame, settings: dict, group_keys: "pd.Series | None" = None):
    pct_acct_yellow = float(settings.get("pct_account_yellow", 5))
    pct_acct_red    = float(settings.get("pct_account_red",    10))
    stop_unit       = settings.get("stop_dist_unit", "%")
    stop_yellow     = float(settings.get("stop_dist_yellow", 5))
    stop_red        = float(settings.get("stop_dist_red",    2))
    stop_col        = {"%" : "Stop Dist %", "$": "Stop Dist $", "ATR": "Stop Dist ATR"}.get(stop_unit, "Stop Dist %")

    # Row color-coding settings
    rc_enabled = settings.get("row_color_enabled", "0") == "1"
    rc_style   = settings.get("row_color_style",   "text")   # "text" | "row"
    rc_op      = settings.get("color_open_profit",   "#2ecc71")
    rc_ol      = settings.get("color_open_loss",     "#e74c3c")
    rc_cp      = settings.get("color_closed_profit", "#27ae60")
    rc_cl      = settings.get("color_closed_loss",   "#c0392b")

    sign_cols = {"P&L", "Realized P&L $", "Acct P&L %", "Ann. P&L",
                 "Day P&L", "Day P&L %", "Locked-in Profit", "Open Risk",
                 "Day's Change", "Day Change %", "Realized P&L %", "Ann. Return %",
                 "Unrealized P&L %", "Unrealized Ann. Return %"}

    today_date = pd.Timestamp.today().date()
    cols       = df.columns.tolist()
    n_rows     = len(df)

    # Build style array as a 2-D list (rows × cols) using vectorised ops per column.
    # This avoids a Python-level loop over every cell and is 5-10× faster than
    # df.style.apply(row_fn, axis=1) for large DataFrames.
    styles = [[""] * len(cols) for _ in range(n_rows)]

    # Closed-row dim — precompute as a boolean mask
    is_closed_mask = (df["Status"] == "Closed").to_numpy() if "Status" in df.columns else np.zeros(n_rows, dtype=bool)

    # Row color-coding pre-pass: determine per-row base style
    row_base = [""] * n_rows  # stores the base style per row for sign_col merging
    if rc_enabled and "P&L" in df.columns:
        pnl_col_vals = df["P&L"].astype(str)
        for i in range(n_rows):
            v = pnl_col_vals.iloc[i]
            try:
                num = float(v.replace("$", "").replace(",", "").replace("+", "").strip())
                is_profit = num > 0
                is_loss   = num < 0
            except (ValueError, AttributeError):
                continue
            if not is_profit and not is_loss:
                continue
            closed = bool(is_closed_mask[i])
            if closed:
                color = rc_cp if is_profit else rc_cl
            else:
                color = rc_op if is_profit else rc_ol
            if rc_style == "row":
                base = f"background-color:{_hex_to_rgba(color, 0.25)}"
            else:
                base = f"color:{color}"
            row_base[i] = base
            for j in range(len(cols)):
                styles[i][j] = base

    for j, col in enumerate(cols):
        col_vals = df[col].astype(str)

        if col in sign_cols:
            for i, v in enumerate(col_vals):
                if v.startswith("+"):
                    sign_style = "color:#2ecc71;font-weight:bold"
                elif v.startswith("-"):
                    sign_style = "color:#e74c3c;font-weight:bold"
                else:
                    continue
                base = row_base[i]
                if rc_enabled and base:
                    if rc_style == "row":
                        # Keep background tint, add sign color as text
                        styles[i][j] = f"{base};{sign_style}"
                    else:
                        # Text mode: custom color already set; just add bold
                        styles[i][j] = f"{base};font-weight:bold"
                else:
                    styles[i][j] = sign_style

        elif col == "Earnings":
            for i, v in enumerate(col_vals):
                if is_closed_mask[i] or not v or v in ("—", ""):
                    continue
                try:
                    d  = pd.to_datetime(v).date()
                    bd = int(np.busday_count(today_date, d))
                    if bd >= 0:
                        if bd < 5:
                            styles[i][j] = "background-color:#FF0000;color:#FFFFFF;font-weight:bold"
                        elif bd < 10:
                            styles[i][j] = "background-color:#FFD700;color:#000000;font-weight:bold"
                except Exception:
                    pass

        elif col == "% of Account":
            for i, v in enumerate(col_vals):
                try:
                    num = float(v.replace("%", "").replace("$", "").replace(",", "").strip())
                    if num > pct_acct_red:
                        styles[i][j] = "color:#e74c3c;font-weight:bold"
                    elif num > pct_acct_yellow:
                        styles[i][j] = "color:#f39c12"
                except Exception:
                    pass

        elif col == stop_col:
            for i, v in enumerate(col_vals):
                if v == "—":
                    continue
                try:
                    num = float(v.replace("%", "").replace("$", "").replace(",", "").strip())
                    if num < stop_red:
                        styles[i][j] = "color:#e74c3c;font-weight:bold;text-decoration:underline"
                    elif num < stop_yellow:
                        styles[i][j] = "color:#f39c12"
                except Exception:
                    pass

        elif not rc_enabled:
            # Only dim closed rows when color coding is off (color coding provides the distinction)
            for i in range(n_rows):
                if is_closed_mask[i]:
                    styles[i][j] = "color:#888888"

    _pos_map = {label: i for i, label in enumerate(df.index)}
    def _apply_row(row):
        return pd.Series(styles[_pos_map[row.name]], index=row.index)

    styled = df.style.apply(_apply_row, axis=1)

    if group_keys is not None and len(group_keys):
        _palette   = ["rgba(100,149,237,0.13)", "rgba(144,238,144,0.10)"]
        _group_idx: dict = {}
        for grp in group_keys:
            g = str(grp) if grp and not pd.isna(grp) else ""
            if g and g not in _group_idx:
                _group_idx[g] = len(_group_idx) % len(_palette)

        # Align group_keys by position to the display DataFrame's index labels
        _label_to_grp = dict(zip(df.index, group_keys))

        def _band_row(row):
            g = str(_label_to_grp.get(row.name, ""))
            if g and g not in ("nan", "None") and g in _group_idx:
                c = _palette[_group_idx[g]]
                return [f"background-color:{c}" for _ in row]
            return ["" for _ in row]

        styled = styled.apply(_band_row, axis=1)

    return styled


@st.cache_data(show_spinner=False)
def compute_stats(pnl_tuple: tuple, dates_tuple: tuple, account_balance: float) -> dict:
    pnl_series   = pd.Series(pnl_tuple, dtype=float)
    dates_series = pd.Series(dates_tuple)
    if len(pnl_series) == 0:
        return {}
    winners = pnl_series[pnl_series > 0]
    losers  = pnl_series[pnl_series < 0]
    n       = len(pnl_series)
    stats   = {
        "total":         n,
        "win_rate":      len(winners) / n * 100 if n else 0,
        "avg_winner":    float(winners.mean()) if len(winners) > 0 else None,
        "std_winner":    float(winners.std())  if len(winners) > 1 else None,
        "avg_loser":     float(losers.mean())  if len(losers)  > 0 else None,
        "std_loser":     float(losers.std())   if len(losers)  > 1 else None,
        "sharpe":  None, "sortino": None, "max_dd": None, "recovery_days": None,
        "calmar":  None, "var_95":  None,
    }
    # Historical VaR 95 %: worst 5th-percentile single-trade outcome
    if len(pnl_series) >= 5:
        stats["var_95"] = float(np.percentile(pnl_series, 5))
    # Daily-annualised Sharpe & Sortino (same basis as benchmark calculations)
    if account_balance and account_balance > 0 and len(dates_series) > 1:
        try:
            _dates_dt  = pd.to_datetime(dates_series).dt.normalize()
            _daily_pnl = pd.Series(pnl_series.values, index=_dates_dt).groupby(level=0).sum()
            # Fill every calendar day in range with 0 so std reflects idle periods
            _full_idx  = pd.date_range(_daily_pnl.index.min(), _daily_pnl.index.max(), freq="D")
            _daily_pnl = _daily_pnl.reindex(_full_idx, fill_value=0.0)
            _daily_r   = _daily_pnl / account_balance
            _mean_r    = float(_daily_r.mean())
            _std_r     = float(_daily_r.std(ddof=1)) if len(_daily_r) > 1 else None
            _neg_r     = _daily_r[_daily_r < 0]
            _std_down  = float(_neg_r.std(ddof=1)) if len(_neg_r) > 1 else None
            _ann       = 252 ** 0.5
            stats["sharpe"]  = _mean_r / _std_r   * _ann if _std_r  and _std_r  > 0 else None
            stats["sortino"] = _mean_r / _std_down * _ann if _std_down and _std_down > 0 else None
        except Exception:
            pass
    if len(dates_series) > 0:
        order        = pd.to_datetime(dates_series).argsort()
        sorted_pnl   = pnl_series.iloc[order].reset_index(drop=True)
        sorted_dates = pd.to_datetime(dates_series).iloc[order].reset_index(drop=True)
        cum          = sorted_pnl.cumsum()
        running_max  = cum.cummax()
        drawdown     = running_max - cum
        max_dd       = float(drawdown.max())
        stats["max_dd"] = max_dd
        if account_balance and account_balance > 0:
            stats["max_dd_pct"] = max_dd / account_balance * 100
        if max_dd > 0:
            trough_i    = int(drawdown.idxmax())
            trough_date = sorted_dates.iloc[trough_i]
            peak_val    = float(running_max.iloc[trough_i])
            post_cum    = cum.iloc[trough_i + 1:]
            post_dates  = sorted_dates.iloc[trough_i + 1:]
            if not post_cum[post_cum >= peak_val].empty:
                rec_date = post_dates.iloc[int((post_cum >= peak_val).values.argmax())]
                stats["recovery_days"] = (rec_date - trough_date).days
        else:
            stats["recovery_days"] = 0
        # Calmar: annualised return / max drawdown (both as fraction of account)
        if account_balance and account_balance > 0 and max_dd > 0:
            date_span_days = max(1, (sorted_dates.iloc[-1] - sorted_dates.iloc[0]).days)
            ann_ret = (pnl_series.sum() / account_balance) * (365 / date_span_days)
            stats["calmar"] = ann_ret / (max_dd / account_balance)
    return stats


# ── DB functions ───────────────────────────────────────────────────────────────

def load_trades() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql("""
            SELECT
                t.id, t.entry_date, t.ticker, t.quantity, t.entry_price,
                t.exit_date, t.exit_price,
                t.notes, t.stop_enabled, t.opening_stop, t.current_stop,
                t.trail_type, t.trail_amount,
                t.instrument_type, t.expiration, t.strike, t.option_type,
                t.multiplier, t.leg_group, t.leg_label, t.side,
                t.chart_notes, t.earnings_date,
                t.commission, t.underlying_price_at_entry,
                t.account_name, t.roll_group,
                GROUP_CONCAT(tg.name, ', ') AS tags
            FROM trades t
            LEFT JOIN trade_tags tt ON tt.trade_id = t.id
            LEFT JOIN tags tg       ON tg.id = tt.tag_id
            GROUP BY t.id
            ORDER BY t.entry_date DESC
        """, conn)


def load_accounts() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name").fetchall()
        names = [r[0] for r in rows]
    return names if names else ["Default"]


def add_account(name: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts (name) VALUES (?)", (name.strip(),))


def delete_account(name: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM accounts WHERE name=? AND name != 'Default'", (name,))


def load_tags() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, description FROM tags ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def load_equity_entries() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, date, balance, contributions, withdrawals FROM equity_entries ORDER BY date"
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_equity_entry(date: str, balance: float, contributions: float = 0.0, withdrawals: float = 0.0):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO equity_entries (date, balance, contributions, withdrawals)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   balance=excluded.balance,
                   contributions=excluded.contributions,
                   withdrawals=excluded.withdrawals""",
            (date, balance, contributions, withdrawals),
        )


def delete_equity_entry(entry_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM equity_entries WHERE id = ?", (entry_id,))


def clear_equity_entries():
    with get_connection() as conn:
        conn.execute("DELETE FROM equity_entries")


PLAN_ATTACHMENTS_DIR = Path(__file__).parent / "plan_attachments"
PLAN_ATTACHMENTS_DIR.mkdir(exist_ok=True)


def save_trading_plan(plan: dict) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO trading_plans
               (ticker, sentiment, rationale, fundamentals, technicals,
                trade_type, hold_time, entry_signal, confirm1, confirm2,
                entry_price, profit_target, stop_loss, rr_ratio)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                plan.get("ticker"), plan.get("sentiment"), plan.get("rationale"),
                plan.get("fundamentals"), plan.get("technicals"),
                plan.get("trade_type"), plan.get("hold_time"),
                plan.get("entry_signal"), plan.get("confirm1"), plan.get("confirm2"),
                plan.get("entry_price"), plan.get("profit_target"),
                plan.get("stop_loss"), plan.get("rr_ratio"),
            ),
        )
        return cur.lastrowid


def load_trading_plans() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trading_plans ORDER BY saved_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_trading_plan(plan_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT filepath FROM trading_plan_attachments WHERE plan_id=?", (plan_id,)
        ).fetchall()
        for r in rows:
            try:
                Path(r["filepath"]).unlink(missing_ok=True)
            except Exception:
                pass
        conn.execute("DELETE FROM trading_plans WHERE id=?", (plan_id,))


def save_plan_attachment(plan_id: int, filename: str, data: bytes):
    safe_name = f"{plan_id}_{filename}"
    filepath  = PLAN_ATTACHMENTS_DIR / safe_name
    filepath.write_bytes(data)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO trading_plan_attachments (plan_id, filename, filepath) VALUES (?,?,?)",
            (plan_id, filename, str(filepath)),
        )


def load_plan_attachments(plan_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, filename, filepath FROM trading_plan_attachments WHERE plan_id=? ORDER BY uploaded_at",
            (plan_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_plan_attachment(attachment_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT filepath FROM trading_plan_attachments WHERE id=?", (attachment_id,)
        ).fetchone()
        if row:
            try:
                Path(row["filepath"]).unlink(missing_ok=True)
            except Exception:
                pass
        conn.execute("DELETE FROM trading_plan_attachments WHERE id=?", (attachment_id,))


def get_trade_tag_ids(trade_id: int) -> list[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT tag_id FROM trade_tags WHERE trade_id = ?", (trade_id,)).fetchall()
        return [r[0] for r in rows]


def load_attachments(trade_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, filename, filepath FROM trade_attachments WHERE trade_id = ? ORDER BY uploaded_at",
            (trade_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_trade(entry_date, ticker, quantity, entry_price, exit_date, exit_price,
              notes, stop_enabled, opening_stop, tag_ids, current_stop=None,
              instrument_type="stock", expiration=None, strike=None, option_type=None,
              multiplier=1.0, leg_group=None, leg_label=None, side="long",
              spread_type=None, commission=0.0, underlying_price_at_entry=None,
              account_name="Default", roll_group=None,
              native_currency="USD", fx_rate_entry=1.0, fx_rate_exit=1.0,
              trail_type="fixed", trail_amount=None, exchange="") -> int:
    with get_connection() as conn:
        cs = current_stop if current_stop is not None else (opening_stop if stop_enabled else None)
        cur = conn.execute("""
            INSERT INTO trades (entry_date, ticker, quantity, entry_price,
                                exit_date, exit_price, notes,
                                stop_enabled, opening_stop, current_stop,
                                instrument_type, expiration, strike, option_type,
                                multiplier, leg_group, leg_label, side, spread_type,
                                commission, underlying_price_at_entry, account_name, roll_group,
                                native_currency, fx_rate_entry, fx_rate_exit,
                                trail_type, trail_amount, exchange)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_date.isoformat() if entry_date else None,
            ticker.upper().strip(),
            quantity or None,
            entry_price or None,
            exit_date.isoformat() if exit_date else None,
            float(exit_price) if exit_price is not None else None,
            notes or None,
            1 if stop_enabled else 0,
            opening_stop if stop_enabled else None,
            cs,
            instrument_type or "stock",
            expiration.isoformat() if hasattr(expiration, "isoformat") else expiration,
            strike or None,
            option_type or None,
            float(multiplier) if multiplier else 1.0,
            leg_group or None,
            leg_label or None,
            side or "long",
            spread_type or None,
            float(commission) if commission else 0.0,
            underlying_price_at_entry or None,
            account_name or "Default",
            roll_group or None,
            native_currency or "USD",
            float(fx_rate_entry) if fx_rate_entry else 1.0,
            float(fx_rate_exit)  if fx_rate_exit  else 1.0,
            trail_type or "fixed",
            float(trail_amount) if trail_amount else None,
            exchange or "",
        ))
        trade_id = cur.lastrowid
        for tid in tag_ids:
            conn.execute("INSERT OR IGNORE INTO trade_tags (trade_id, tag_id) VALUES (?, ?)", (trade_id, tid))
        # Record the opening lot so tax-lot view starts populated
        if entry_date and entry_price and quantity:
            _lot_date = entry_date.isoformat() if hasattr(entry_date, "isoformat") else str(entry_date)
            conn.execute(
                "INSERT INTO trade_lots (trade_id, date, quantity, price, lot_type) VALUES (?,?,?,?,?)",
                (trade_id, _lot_date, float(quantity), float(entry_price), "open"),
            )
        return trade_id


def update_trade(trade_id, exit_date, exit_price, notes, current_stop, stop_enabled, tag_ids,
                 entry_date=None, ticker=None, quantity=None, entry_price=None,
                 opening_stop=None, instrument_type=None, expiration=None,
                 strike=None, option_type=None, multiplier=None, side=None,
                 commission=None, account_name=None,
                 trail_type=None, trail_amount=None):
    with get_connection() as conn:
        # Build the update dynamically — only overwrite fields that were passed
        sets = [
            "exit_date=?", "exit_price=?", "notes=?", "current_stop=?", "stop_enabled=?"
        ]
        vals = [
            exit_date.isoformat() if exit_date else None,
            float(exit_price) if exit_price is not None else None,
            notes or None,
            current_stop if stop_enabled else None,
            1 if stop_enabled else 0,
        ]
        if entry_date is not None:
            sets.append("entry_date=?")
            vals.append(entry_date.isoformat() if hasattr(entry_date, "isoformat") else entry_date)
        if ticker is not None:
            sets.append("ticker=?")
            vals.append(ticker.upper().strip())
        if quantity is not None:
            sets.append("quantity=?")
            vals.append(float(quantity))
        if entry_price is not None:
            sets.append("entry_price=?")
            vals.append(float(entry_price))
        if opening_stop is not None:
            sets.append("opening_stop=?")
            vals.append(float(opening_stop))
        if instrument_type is not None:
            sets.append("instrument_type=?")
            vals.append(instrument_type)
        if expiration is not None:
            sets.append("expiration=?")
            vals.append(expiration.isoformat() if hasattr(expiration, "isoformat") else expiration)
        if strike is not None:
            sets.append("strike=?")
            vals.append(float(strike))
        if option_type is not None:
            sets.append("option_type=?")
            vals.append(option_type)
        if multiplier is not None:
            sets.append("multiplier=?")
            vals.append(float(multiplier))
        if side is not None:
            sets.append("side=?")
            vals.append(side)
        if commission is not None:
            sets.append("commission=?")
            vals.append(float(commission))
        if account_name is not None:
            sets.append("account_name=?")
            vals.append(account_name)
        if trail_type is not None:
            sets.append("trail_type=?")
            vals.append(trail_type)
        if trail_amount is not None:
            sets.append("trail_amount=?")
            vals.append(float(trail_amount))
        vals.append(trade_id)
        conn.execute(f"UPDATE trades SET {', '.join(sets)} WHERE id=?", vals)
        conn.execute("DELETE FROM trade_tags WHERE trade_id=?", (trade_id,))
        for tid in tag_ids:
            conn.execute("INSERT OR IGNORE INTO trade_tags (trade_id, tag_id) VALUES (?, ?)", (trade_id, tid))


def update_spread_group(trade_ids: list, leg_group: str | None, spread_type: str | None):
    with get_connection() as conn:
        for tid in trade_ids:
            conn.execute(
                "UPDATE trades SET leg_group=?, spread_type=? WHERE id=?",
                (leg_group or None, spread_type or None, tid),
            )


def update_chart_notes(trade_id: int, notes: str):
    with get_connection() as conn:
        conn.execute("UPDATE trades SET chart_notes=? WHERE id=?", (notes or None, trade_id))


def update_earnings_override(trade_id: int, date_str: str):
    with get_connection() as conn:
        conn.execute("UPDATE trades SET earnings_date=? WHERE id=?", (date_str or None, trade_id))


def send_earnings_email(alerts: list[dict], settings: dict) -> str:
    """Send earnings alert email. Returns '' on success or error message."""
    host    = settings.get("smtp_host", "")
    port    = int(settings.get("smtp_port", 587) or 587)
    user    = settings.get("smtp_user", "")
    pwd     = settings.get("smtp_pass", "")
    to_addr = settings.get("smtp_to", "")
    if not all([host, user, pwd, to_addr]):
        return "SMTP not fully configured."
    rows = "".join(
        f"<tr><td>{a['ticker']}</td><td>{a['earnings_date']}</td><td>{a['bdays']} trading days</td></tr>"
        for a in alerts
    )
    body = f"""<html><body>
<h2>Upcoming Earnings Alert</h2>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Ticker</th><th>Earnings Date</th><th>Days Away</th></tr>
{rows}
</table>
<p>Generated by Trade Log</p>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Earnings Alert — {len(alerts)} position(s)"
    msg["From"]    = user
    msg["To"]      = to_addr
    msg.attach(MIMEText(body, "html"))
    try:
        with smtplib.SMTP(host, port, timeout=10) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(user, pwd)
            srv.sendmail(user, to_addr, msg.as_string())
        return ""
    except Exception as exc:
        return str(exc)


def add_trade_lot(trade_id: int, date: str, quantity: float, price: float,
                  lot_type: str = "add", notes: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO trade_lots (trade_id, date, quantity, price, lot_type, notes) VALUES (?,?,?,?,?,?)",
            (trade_id, date, quantity, price, lot_type, notes or ""),
        )
        return cur.lastrowid


def load_trade_lots(trade_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, date, quantity, price, lot_type, notes FROM trade_lots WHERE trade_id=? ORDER BY date, id",
            (trade_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def load_lots_for_trades(trade_ids: list) -> dict[int, list[dict]]:
    """Return {trade_id: [lot, ...]} for a list of trade IDs in one query."""
    if not trade_ids:
        return {}
    placeholders = ",".join("?" for _ in trade_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, trade_id, date, quantity, price, lot_type, notes "
            f"FROM trade_lots WHERE trade_id IN ({placeholders}) ORDER BY date, id",
            trade_ids,
        ).fetchall()
    result: dict[int, list] = {tid: [] for tid in trade_ids}
    for r in rows:
        result[r["trade_id"]].append(dict(r))
    return result


def load_dividends_for_trades(trade_ids: list) -> dict[int, list[dict]]:
    """Return {trade_id: [div, ...]} for a list of trade IDs in one query."""
    if not trade_ids:
        return {}
    placeholders = ",".join("?" for _ in trade_ids)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, trade_id, ex_date, amount_per_share, quantity, total_amount, notes "
            f"FROM trade_dividends WHERE trade_id IN ({placeholders}) ORDER BY ex_date, id",
            trade_ids,
        ).fetchall()
    result: dict[int, list] = {tid: [] for tid in trade_ids}
    for r in rows:
        result[r["trade_id"]].append(dict(r))
    return result


def delete_trade_lot(lot_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM trade_lots WHERE id=?", (lot_id,))


# ── Dividend helpers ───────────────────────────────────────────────────────────

def add_trade_dividend(trade_id: int, ex_date: str, amount_per_share: float,
                       quantity: float | None = None, notes: str = "") -> int:
    total = (amount_per_share * quantity) if quantity else None
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO trade_dividends
               (trade_id, ex_date, amount_per_share, quantity, total_amount, notes)
               VALUES (?,?,?,?,?,?)""",
            (trade_id, ex_date, amount_per_share, quantity, total, notes or ""),
        )
        return cur.lastrowid


def load_trade_dividends(trade_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, ex_date, amount_per_share, quantity, total_amount, notes
               FROM trade_dividends WHERE trade_id=? ORDER BY ex_date, id""",
            (trade_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_trade_dividend(div_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM trade_dividends WHERE id=?", (div_id,))


def update_position(trade_id: int, add_qty: float, add_price: float, add_date: str | None = None):
    import datetime as _dt
    with get_connection() as conn:
        row = conn.execute("SELECT quantity, entry_price FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            raise ValueError(f"Trade {trade_id} not found")
        old_qty   = float(row["quantity"] or 0)
        old_price = float(row["entry_price"] or 0)
        new_qty   = old_qty + add_qty
        new_avg   = (old_qty * old_price + add_qty * add_price) / new_qty if new_qty else 0
        conn.execute("UPDATE trades SET quantity=?, entry_price=? WHERE id=?",
                     (new_qty, new_avg, trade_id))
    # Record lot outside the main connection (lots table is a separate write)
    lot_date = add_date or _dt.date.today().isoformat()
    add_trade_lot(trade_id, lot_date, add_qty, add_price, lot_type="add")
    return new_qty, new_avg


def partial_exit_trade(trade_id: int, exit_qty: float, exit_price: float, exit_date):
    with get_connection() as conn:
        conn.execute(
            "UPDATE trades SET exit_date=?, exit_price=?, quantity=? WHERE id=?",
            (exit_date.isoformat() if exit_date else None, float(exit_price) if exit_price is not None else None, exit_qty, trade_id),
        )


def delete_trade(trade_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))


def bulk_delete_trades(trade_ids: list):
    if not trade_ids:
        return
    placeholders = ",".join("?" for _ in trade_ids)
    with get_connection() as conn:
        conn.execute(f"DELETE FROM trades WHERE id IN ({placeholders})", trade_ids)


def find_duplicate_trade_groups() -> list:
    """Find groups of trades that look like the same fill imported more than once.

    Two trades are flagged as duplicates only when ALL of these match: ticker,
    instrument identity (type / expiration / strike / option type), side, entry
    date, quantity, and entry price. Entry date is the finest execution-time
    granularity stored, so it stands in for "same time". Returns a list of
    groups (each a dict with the shared match key and its member trade rows),
    limited to keys that have 2 or more trades. Read-only — never deletes.
    """
    from collections import defaultdict
    groups: dict = defaultdict(list)
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, entry_date, ticker, quantity, entry_price, exit_date,
                      exit_price, side, instrument_type, expiration, strike,
                      option_type, notes
                 FROM trades ORDER BY id"""
        ).fetchall()
    for r in rows:
        key = (
            (r["ticker"] or "").upper().strip(),
            (r["instrument_type"] or "stock").lower(),
            str(r["expiration"] or ""),
            round(float(r["strike"]), 4) if r["strike"] is not None else None,
            (r["option_type"] or "").lower(),
            (r["side"] or "long").lower(),
            str(r["entry_date"] or "")[:10],
            round(float(r["quantity"]), 6) if r["quantity"] is not None else None,
            round(float(r["entry_price"]), 6) if r["entry_price"] is not None else None,
        )
        groups[key].append(dict(r))
    return [{"key": k, "trades": v} for k, v in groups.items() if len(v) >= 2]


def add_tag(name: str, description: str):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO tags (name, description) VALUES (?, ?)",
                     (name.strip(), description.strip()))


def update_tag(tag_id: int, name: str, description: str):
    with get_connection() as conn:
        conn.execute("UPDATE tags SET name=?, description=? WHERE id=?",
                     (name.strip(), description.strip(), tag_id))


def delete_tag(tag_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))


def clear_all_tags():
    with get_connection() as conn:
        conn.execute("DELETE FROM tags")


# ── Cache-busting wrappers ──────────────────────────────────────────────────
# Re-shadow each mutating function so callers never need explicit cache calls.
# Use .clear() on the decorated function directly — this is guaranteed to
# invalidate regardless of how Streamlit hashes the cache key internally.
# _bust() still increments the version counter so the *same* cached value is
# never returned for two different logical DB states within one session.
_raw_add_trade = add_trade
def add_trade(*args, **kwargs):
    r = _raw_add_trade(*args, **kwargs)
    _cached_load_trades.clear()
    _bust("_v_trades")
    return r

_raw_update_trade = update_trade
def update_trade(*a, **kw):
    _raw_update_trade(*a, **kw)
    _cached_load_trades.clear()
    _bust("_v_trades")

_raw_delete_trade = delete_trade
def delete_trade(trade_id):
    _raw_delete_trade(trade_id)
    _cached_load_trades.clear()
    _bust("_v_trades")

_raw_bulk_delete_trades = bulk_delete_trades
def bulk_delete_trades(trade_ids: list):
    _raw_bulk_delete_trades(trade_ids)
    _cached_load_trades.clear()
    _bust("_v_trades")

_raw_add_tag = add_tag
def add_tag(*args, **kwargs):
    r = _raw_add_tag(*args, **kwargs)
    _cached_load_tags.clear()
    _bust("_v_tags")
    return r

_raw_delete_tag = delete_tag
def delete_tag(tag_id):
    _raw_delete_tag(tag_id)
    _cached_load_tags.clear()
    _bust("_v_tags")

_raw_update_tag = update_tag
def update_tag(tag_id, name, description):
    _raw_update_tag(tag_id, name, description)
    _cached_load_tags.clear()
    _bust("_v_tags")

_raw_clear_all_tags = clear_all_tags
def clear_all_tags():
    _raw_clear_all_tags()
    _cached_load_tags.clear()
    _bust("_v_tags")

_raw_set_setting = set_setting
def set_setting(key, value):
    _raw_set_setting(key, value)
    _cached_get_settings.clear()
    _bust("_v_settings")

_raw_add_account = add_account
def add_account(name: str):
    _raw_add_account(name)
    _cached_load_accounts.clear()
    _bust("_v_accounts")

_raw_delete_account = delete_account
def delete_account(name: str):
    _raw_delete_account(name)
    _cached_load_accounts.clear()
    _bust("_v_accounts")
# ───────────────────────────────────────────────────────────────────────────


def add_tag_to_trade(trade_id: int, tag_id: int):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO trade_tags (trade_id, tag_id) VALUES (?, ?)", (trade_id, tag_id))


def remove_tag_from_trade(trade_id: int, tag_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM trade_tags WHERE trade_id=? AND tag_id=?", (trade_id, tag_id))


def save_attachment(trade_id: int, uploaded_file):
    safe_name = f"{trade_id}_{uploaded_file.name}"
    filepath  = ATTACHMENTS_DIR / safe_name
    filepath.write_bytes(uploaded_file.getbuffer())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO trade_attachments (trade_id, filename, filepath) VALUES (?, ?, ?)",
            (trade_id, uploaded_file.name, str(filepath)),
        )


def delete_attachment(attachment_id: int, filepath: str):
    try:
        Path(filepath).unlink(missing_ok=True)
    except Exception:
        pass
    with get_connection() as conn:
        conn.execute("DELETE FROM trade_attachments WHERE id=?", (attachment_id,))


def import_trades_from_csv(df: pd.DataFrame) -> tuple[int, list[str]]:
    df.columns = [str(c).strip() for c in df.columns]
    col_map = {
        "entry date":        "entry_date",
        "ticker":            "ticker",
        "q":                 "quantity",
        "entry price":       "entry_price",
        "tags":              "tags_raw",
        "initial stop loss": "opening_stop",
        "current stop":      "current_stop",
        "exit date":         "exit_date",
        "exit price":        "exit_price",
        # broker / options columns
        "instrument type":   "instrument_type",
        "type":              "instrument_type",
        "asset":             "instrument_type",
        "sectype":           "instrument_type",
        "expiration":        "expiration",
        "expiry":            "expiration",
        "exp date":          "expiration",
        "strike":            "strike",
        "strike price":      "strike",
        "option type":       "option_type",
        "put/call":          "option_type",
        "p/c":               "option_type",
        "multiplier":        "multiplier",
        "timestamp":         "timestamp",
        "date/time":         "timestamp",
        "datetime":          "timestamp",
        "time":              "timestamp",
        "side":              "side",
        "buy/sell":          "side",
        "action":            "side",
        "underlying":        "underlying_ticker",
        "underlying ticker": "underlying_ticker",
        "symbol":            "ticker",
    }
    col_lookup = {}
    for df_col in df.columns:
        key = col_map.get(df_col.lower())
        if key:
            col_lookup[key] = df_col

    def _val(row, key):
        col = col_lookup.get(key)
        if col is None:
            return None
        v = row.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
            return None
        return v

    def _float(row, key):
        v = _val(row, key)
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").replace("$", ""))
        except ValueError:
            return None

    def _date(row, key):
        v = _val(row, key)
        if v is None:
            return None
        try:
            dt = pd.to_datetime(v).date()
            # IB exports 0 for absent dates, which pandas parses as 1970-01-01
            if dt.year < 1990:
                return None
            return dt
        except Exception:
            return None

    tag_cache = {t["name"].lower(): t["id"] for t in load_tags()}
    success, skipped_dupes, errors = 0, 0, []
    for i, row in df.iterrows():
        try:
            ticker = _val(row, "ticker")
            if not ticker:
                errors.append(f"Row {i+2}: Ticker missing — skipped")
                continue
            ticker = str(ticker).upper().strip()

            tags_raw = _val(row, "tags_raw")
            tag_ids  = []
            if tags_raw:
                for tname in str(tags_raw).split(","):
                    tname = tname.strip()
                    if not tname:
                        continue
                    if tname.lower() not in tag_cache:
                        add_tag(tname, "")
                        tag_cache = {t["name"].lower(): t["id"] for t in load_tags()}
                    tid = tag_cache.get(tname.lower())
                    if tid:
                        tag_ids.append(tid)

            opening_stop = _float(row, "opening_stop")
            current_stop = _float(row, "current_stop")
            stop_enabled = opening_stop is not None or current_stop is not None

            # ── Read option fields first so they can inform type detection ─────
            expiration  = _val(row, "expiration")
            if expiration:
                try:
                    expiration = pd.to_datetime(expiration).strftime("%Y-%m-%d")
                except Exception:
                    expiration = None
            strike      = _float(row, "strike")

            # ── Options / futures detection ────────────────────────────────
            raw_itype  = _val(row, "instrument_type")
            itype_str  = str(raw_itype).lower() if raw_itype else ""
            if expiration or strike is not None:
                # Presence of option-specific fields overrides the type label
                instrument_type = "option"
            elif any(k in itype_str for k in ("opt", "call", "put", "bag", "combo", "option")):
                instrument_type = "option"
            elif any(k in itype_str for k in ("fut", "future")):
                instrument_type = "future"
            else:
                instrument_type = "stock"
            raw_pc      = _val(row, "option_type")
            option_type = None
            if raw_pc:
                option_type = "call" if str(raw_pc).lower().startswith("c") else "put"
            mult_v      = _float(row, "multiplier") or 1.0
            raw_side    = _val(row, "side")
            side        = "short" if raw_side and str(raw_side).lower() in ("short", "s", "sell", "b/s-sell") else "long"

            # ── Underlying price at timestamp ──────────────────────────────
            underlying_px = None
            if instrument_type == "option":
                raw_ts     = _val(row, "timestamp")
                entry_dt   = _date(row, "entry_date")
                undl_ticker = _val(row, "underlying_ticker") or ticker
                # For options, ticker might be an OCC symbol — derive underlying
                if len(undl_ticker) > 6:
                    # OCC-format symbol: first 1-6 alpha chars are the underlying
                    import re as _re
                    _m = _re.match(r"^([A-Z]{1,6})", undl_ticker.upper())
                    undl_ticker = _m.group(1) if _m else undl_ticker[:5]
                date_for_fetch = None
                if raw_ts:
                    try:
                        date_for_fetch = pd.to_datetime(raw_ts).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                if not date_for_fetch and entry_dt:
                    date_for_fetch = str(entry_dt)
                if date_for_fetch:
                    underlying_px = get_underlying_price_at_date(undl_ticker, date_for_fetch)

            _entry_date  = _date(row, "entry_date")
            _quantity    = _float(row, "quantity")
            _entry_price = _float(row, "entry_price")

            if is_duplicate_trade(
                ticker, _entry_date, _quantity, _entry_price,
                instrument_type, expiration, strike,
            ):
                skipped_dupes += 1
                continue

            add_trade(
                entry_date               = _entry_date,
                ticker                   = ticker,
                quantity                 = _quantity,
                entry_price              = _entry_price,
                exit_date                = _date(row, "exit_date"),
                exit_price               = _float(row, "exit_price"),
                notes                    = None,
                stop_enabled             = stop_enabled,
                opening_stop             = opening_stop,
                tag_ids                  = tag_ids,
                current_stop             = current_stop,
                instrument_type          = instrument_type,
                expiration               = expiration,
                strike                   = strike,
                option_type              = option_type,
                multiplier               = mult_v,
                side                     = side,
                underlying_price_at_entry= underlying_px,
            )
            success += 1
        except Exception as e:
            errors.append(f"Row {i+2}: {e}")

    if skipped_dupes:
        errors.insert(0, f"ℹ️  {skipped_dupes} row(s) skipped — already exist in the log")
    return success, errors


# ── Export for Review (PDF report) ────────────────────────────────────────────

def _exp_to_float(v):
    f = pd.to_numeric(v, errors="coerce")
    return float(f) if pd.notna(f) else None


def _exp_effective_stop(row):
    """Active stop level — current_stop for fixed stops, the trailing level otherwise.
    Mirrors the Trading Log table's effective-stop logic; falls back to current_stop
    for cases needing extra market data (ATR trails, short-side trails)."""
    tt = str(row.get("trail_type") or "fixed")
    ta = row.get("trail_amount")
    cs = _exp_to_float(row.get("current_stop"))
    if tt == "fixed" or ta is None or (isinstance(ta, float) and pd.isna(ta)):
        return cs
    side = str(row.get("side") or "long").lower()
    try:
        ta = float(ta)
        if side == "long":
            hh = get_highest_high_since(row.get("ticker") or "", row.get("entry_date") or "")
            if hh is None:
                return cs
            if tt == "$":
                return hh - ta
            if tt == "%":
                return hh * (1 - ta / 100)
        # ATR trails and short-side trails need extra data — use current_stop.
    except Exception:
        return cs
    return cs


def _exp_days_held(entry_date, exit_date):
    try:
        start = pd.to_datetime(entry_date, errors="coerce")
        end   = pd.to_datetime(exit_date, errors="coerce") if exit_date else pd.Timestamp.today()
        if pd.isna(start) or pd.isna(end):
            return None
        return max(0, int((end.normalize() - start.normalize()).days))
    except Exception:
        return None


def _compute_review_rows(df: "pd.DataFrame", live_data: dict, acct_bal: float) -> list:
    """Per-trade numeric metrics for the review report (mirrors the trade-table math)."""
    if df.empty:
        return []
    div_map = load_dividends_for_trades(df["id"].tolist())
    out = []
    for _, r in df.iterrows():
        qty  = _exp_to_float(r.get("quantity"))
        ep   = _exp_to_float(r.get("entry_price"))
        xp   = _exp_to_float(r.get("exit_price"))
        mult = _exp_to_float(r.get("multiplier")) or 1.0
        sign = -1.0 if str(r.get("side") or "long").lower() == "short" else 1.0
        is_open = _is_open(r)
        live_sym = _get_live_ticker(r)
        live_px  = _exp_to_float(live_data.get(live_sym, {}).get("price")) if live_sym else None
        price = live_px if is_open else xp
        div_dollars = float(sum((d.get("total_amount") or 0) for d in div_map.get(r.get("id"), [])))

        if qty is not None and ep is not None and price is not None:
            pnl = (price - ep) * qty * mult * sign + div_dollars
        elif div_dollars:
            pnl = div_dollars
        else:
            pnl = None

        commission = _exp_to_float(r.get("commission")) or 0.0
        pnl_net = (pnl - commission) if pnl is not None else None

        eff_stop     = _exp_to_float(_exp_effective_stop(r))
        opening_stop = _exp_to_float(r.get("opening_stop"))

        opening_risk = (abs(ep - opening_stop) * qty * mult
                        if (ep is not None and opening_stop is not None and qty is not None) else None)
        cur_val  = (qty * price * mult) if (qty is not None and price is not None) else None
        pct_acct = (cur_val / acct_bal * 100) if (cur_val is not None and acct_bal and acct_bal > 0) else None
        open_risk = ((price - eff_stop) * qty * mult
                     if (is_open and price is not None and eff_stop is not None and qty is not None) else None)

        out.append({
            "id": r.get("id"),
            "ticker": str(r.get("ticker") or ""),
            "entry_date": r.get("entry_date") or "",
            "is_open": is_open,
            "qty": qty,
            "entry_price": ep,
            "stop": eff_stop if eff_stop is not None else opening_stop,
            "opening_risk": opening_risk,
            "pct_acct": pct_acct,
            "pnl": pnl,
            "pnl_net": pnl_net,
            "open_risk": open_risk,
            "commission": commission,
            "days_held": _exp_days_held(r.get("entry_date"), r.get("exit_date")),
            "tags": str(r.get("tags") or ""),
            "notes": str(r.get("notes") or ""),
        })
    return out


def _review_stat_lines(rows: list, acct_bal: float, net: bool) -> list:
    """[(label, value), ...] — the full numeric stat set for a group of trades."""
    pnl_key = "pnl_net" if net else "pnl"
    have = [t for t in rows if t.get(pnl_key) is not None]
    if not have:
        return [("Trades", "0")]
    pnls  = [t[pnl_key] for t in have]
    dates = [t["entry_date"] for t in have]
    s = compute_stats(tuple(pnls), tuple(dates), acct_bal)
    pnl_ser = pd.Series(pnls, dtype=float)
    winners = pnl_ser[pnl_ser > 0]
    losers  = pnl_ser[pnl_ser < 0]
    gross_win  = float(winners.sum())
    gross_loss = float(-losers.sum())
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win == 0 else float("inf"))
    total_comm = float(sum(t.get("commission") or 0 for t in rows))
    days = [t["days_held"] for t in have if t.get("days_held") is not None]
    avg_days = (sum(days) / len(days)) if days else None

    def money(v): return fmt_pnl(v) if v is not None else "—"
    def price(v): return fmt_price(v) if v is not None else "—"
    def pct(v):   return fmt_pct(v)  if v is not None else "—"
    def num(v, d=2): return fmt_num(v, d) if v is not None else "—"
    pf_str = ("∞" if profit_factor == float("inf") else num(profit_factor)) if profit_factor is not None else "—"

    return [
        ("Trades",               str(len(have))),
        ("Win rate",             pct(s.get("win_rate"))),
        ("Total P&L",            money(float(pnl_ser.sum()))),
        ("Average P&L / trade",  money(float(pnl_ser.mean()))),
        ("Profit factor",        pf_str),
        ("Average winner",       money(s.get("avg_winner"))),
        ("Average loser",        money(s.get("avg_loser"))),
        ("Largest winner",       money(float(winners.max())) if len(winners) else "—"),
        ("Largest loser",        money(float(losers.min()))  if len(losers)  else "—"),
        ("Std dev (winners)",    money(s.get("std_winner"))),
        ("Std dev (losers)",     money(s.get("std_loser"))),
        ("Avg days in trade",    num(avg_days, 1) if avg_days is not None else "—"),
        ("Total commission",     price(total_comm)),
        ("Sharpe (annualised)",  num(s.get("sharpe"))  if s.get("sharpe")  is not None else "—"),
        ("Sortino (annualised)", num(s.get("sortino")) if s.get("sortino") is not None else "—"),
        ("Calmar",               num(s.get("calmar"))  if s.get("calmar")  is not None else "—"),
        ("VaR 95% (per trade)",  money(s.get("var_95"))),
        ("Max drawdown",         money(s.get("max_dd"))),
        ("Max drawdown %",       pct(s.get("max_dd_pct")) if s.get("max_dd_pct") is not None else "—"),
        ("Recovery (days)",      str(s.get("recovery_days")) if s.get("recovery_days") is not None else "—"),
    ]


def _account_summary_lines(all_rows: list, open_rows: list, closed_rows: list,
                           acct_bal: float, net: bool) -> list:
    pnl_key = "pnl_net" if net else "pnl"
    def _sum(rows, key): return float(sum((t.get(key) or 0) for t in rows))
    realized   = _sum(closed_rows, pnl_key)
    unrealized = _sum(open_rows,   pnl_key)
    return [
        ("Account balance",          fmt_price(acct_bal) if acct_bal else "— (set in Settings)"),
        ("Trades in range",          str(len(all_rows))),
        ("  · Closed",               str(len(closed_rows))),
        ("  · Still open",           str(len(open_rows))),
        ("Realized P&L (closed)",    fmt_pnl(realized)),
        ("Unrealized P&L (open)",    fmt_pnl(unrealized)),
        ("Combined P&L",             fmt_pnl(realized + unrealized)),
        ("Total commission",         fmt_price(_sum(all_rows, "commission"))),
        ("Open risk (to stops)",     fmt_pnl(_sum(open_rows, "open_risk"))),
        ("Opening risk (at entry)",  fmt_price(_sum(open_rows, "opening_risk"))),
        ("Open exposure (% of acct)", fmt_pct(_sum(open_rows, "pct_acct")) if acct_bal else "—"),
    ]


def build_review_pdf(start_date, end_date, net_commission: bool, acct_bal: float) -> bytes:
    """Build the 'Export for Review' PDF (trade log + full stats) and return its bytes."""
    from io import BytesIO
    from xml.sax.saxutils import escape as _xesc
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    # ── Gather + filter (entry date within range) ────────────────────────────
    df = load_trades()
    if not df.empty:
        _ed  = pd.to_datetime(df["entry_date"], errors="coerce").dt.date
        df = df[(_ed >= start_date) & (_ed <= end_date)].copy()
        df = df.sort_values("entry_date").reset_index(drop=True)

    live_data = {}
    if not df.empty:
        open_syms = sorted({_get_live_ticker(r) for _, r in df.iterrows()
                            if _is_open(r) and _get_live_ticker(r)})
        if open_syms:
            try:
                live_data = get_live_data(tuple(open_syms))
            except Exception:
                live_data = {}

    rows        = _compute_review_rows(df, live_data, acct_bal)
    open_rows   = [t for t in rows if t["is_open"]]
    closed_rows = [t for t in rows if not t["is_open"]]
    pnl_key     = "pnl_net" if net_commission else "pnl"

    # ── Styles ───────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    h1    = ParagraphStyle("rv_h1", parent=styles["Heading1"], fontSize=16, spaceAfter=2)
    h2    = ParagraphStyle("rv_h2", parent=styles["Heading2"], fontSize=12, spaceBefore=12, spaceAfter=4)
    h3    = ParagraphStyle("rv_h3", parent=styles["Heading3"], fontSize=10, spaceAfter=3)
    sub   = ParagraphStyle("rv_sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#444444"))
    small = ParagraphStyle("rv_sm", parent=styles["Normal"], fontSize=7, leading=8.5)

    def _para(text, style=small):
        return Paragraph(_xesc(str(text or "")).replace("\n", "<br/>"), style)

    story = []
    story.append(Paragraph("Trade Log — Export for Review", h1))
    _range = f"{fmt_date(str(start_date), euro_dates)}  →  {fmt_date(str(end_date), euro_dates)}"
    story.append(Paragraph(
        f"Trades by entry date: <b>{_range}</b> &nbsp;·&nbsp; "
        f"Account balance: <b>{fmt_price(acct_bal) if acct_bal else '—'}</b> &nbsp;·&nbsp; "
        f"P&amp;L basis: <b>{'Net of commission' if net_commission else 'Gross'}</b>", sub))
    story.append(Spacer(1, 8))

    # ── Trade log table ──────────────────────────────────────────────────────
    story.append(Paragraph(f"Trade Log — {len(rows)} trade(s) "
                           f"({len(open_rows)} open, {len(closed_rows)} closed)", h2))
    if rows:
        header = ["Ticker", "Entry Date", "Qty", "Entry", "Stop", "Opening Risk",
                  "% Acct", "P&L", "Open Risk", "Tags", "Notes"]
        data = [header]
        for t in rows:
            data.append([
                _para(t["ticker"]),
                fmt_date(str(t["entry_date"]), euro_dates),
                fmt_qty(t["qty"]) if t["qty"] is not None else "—",
                fmt_price(t["entry_price"]) if t["entry_price"] is not None else "—",
                fmt_price(t["stop"]) if t["stop"] is not None else "—",
                fmt_price(t["opening_risk"]) if t["opening_risk"] is not None else "—",
                fmt_pct(t["pct_acct"]) if t["pct_acct"] is not None else "—",
                fmt_pnl(t[pnl_key]) if t[pnl_key] is not None else "—",
                fmt_pnl(t["open_risk"]) if t["open_risk"] is not None else "—",
                _para(t["tags"]),
                _para(t["notes"]),
            ])
        col_w = [0.7, 0.85, 0.5, 0.72, 0.72, 0.9, 0.55, 0.9, 0.9, 1.25, 1.55]
        tbl = Table(data, colWidths=[w * inch for w in col_w], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2236")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("ALIGN",      (2, 1), (8, -1), "RIGHT"),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5fa")]),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 3),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No trades have an entry date in this range.", sub))

    # ── Statistics (closed / open / account, side by side) ───────────────────
    story.append(Paragraph("Statistics", h2))

    def _stat_table(lines):
        t = Table([[lbl, val] for lbl, val in lines], colWidths=[1.95 * inch, 1.25 * inch])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN",    (1, 0), (1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e6ee")),
            ("TOPPADDING",    (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ]))
        return t

    cell_closed = [Paragraph("Closed trades", h3), _stat_table(_review_stat_lines(closed_rows, acct_bal, net_commission))]
    cell_open   = [Paragraph("Open trades", h3),   _stat_table(_review_stat_lines(open_rows, acct_bal, net_commission))]
    cell_acct   = [Paragraph("Account summary", h3), _stat_table(_account_summary_lines(rows, open_rows, closed_rows, acct_bal, net_commission))]
    stats_layout = Table([[cell_closed, cell_open, cell_acct]],
                         colWidths=[3.3 * inch, 3.3 * inch, 3.3 * inch])
    stats_layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(stats_layout)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter),
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            title="Trade Log — Export for Review")
    doc.build(story)
    return buf.getvalue()


@st.dialog("✅  Trade Added")
def _trade_added_dialog(summary: dict):
    st.markdown(f"**{summary.get('title', 'Trade added to your log.')}**")
    for _ln in summary.get("lines", []):
        st.markdown(_ln)
    if st.button("OK", type="primary", width="stretch", key="_trade_added_ok"):
        st.rerun()


@st.dialog("📄  Export for Review")
def _export_dialog(acct_bal: float):
    st.markdown(
        "Generate a PDF you can save or print — your **trade log** plus the **full "
        "statistics** (open and closed, with account-level totals) for a date range."
    )
    _today = pd.Timestamp.today().date()
    st.session_state.setdefault("_exp_from", (pd.Timestamp.today() - pd.Timedelta(days=90)).date())
    st.session_state.setdefault("_exp_to", _today)
    c1, c2 = st.columns(2)
    start = c1.date_input("From", key="_exp_from")
    end   = c2.date_input("To",   key="_exp_to")
    net   = st.checkbox("Show P&L net of commission", value=True, key="_exp_net")

    if start > end:
        st.error("The ‘From’ date must be on or before the ‘To’ date.")
        return

    if st.button("📄  Build PDF report", type="primary", width="stretch", key="_exp_build"):
        with st.spinner("Building report (fetching live prices for open trades)…"):
            try:
                st.session_state["_exp_pdf"] = build_review_pdf(start, end, net, acct_bal)
                st.session_state["_exp_pdf_name"] = f"trade-review_{start}_{end}.pdf"
            except ImportError:
                st.session_state.pop("_exp_pdf", None)
                st.error("The PDF engine (reportlab) isn't installed yet. Update the app, "
                         "or run `pip install reportlab`, then try again.")
            except Exception as _e:
                st.session_state.pop("_exp_pdf", None)
                st.error(f"Could not build the report: {_e}")

    if st.session_state.get("_exp_pdf"):
        st.success("Report ready.")
        st.download_button("⬇  Download PDF", data=st.session_state["_exp_pdf"],
                           file_name=st.session_state.get("_exp_pdf_name", "trade-review.pdf"),
                           mime="application/pdf", width="stretch", key="_exp_dl")

    if st.button("Close", width="stretch", key="_exp_close"):
        st.session_state["_show_export"] = False
        st.session_state.pop("_exp_pdf", None)
        st.session_state.pop("_exp_pdf_name", None)
        st.rerun()


# ── App startup ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trade Log", layout="wide")

# Run schema init + migrations only once per browser session (not on every rerun)
if not st.session_state.get("_db_ready"):
    init_db()
    seed_default_settings()
    # Don't show the setup tour to users who already have trades (existing installs)
    if get_setting("onboarding_done", "0") != "1":
        with get_connection() as _c0:
            _existing_trades = _c0.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
        if _existing_trades > 0:
            set_setting("onboarding_done", "1")
    st.session_state["_db_ready"] = True

# Initialise version counters used to bust @st.cache_data caches on mutations
for _ck in ("_v_trades", "_v_settings", "_v_tags", "_v_accounts", "_v_equity", "_v_plans"):
    st.session_state.setdefault(_ck, 0)

# Live prices are fetched only on explicit button click — no auto-load

settings   = _cached_get_settings(st.session_state["_v_settings"])
today_ts   = pd.Timestamp.today().normalize()
euro_dates = settings.get("euro_dates", "0") == "1"

# ── Active theme + chart color shorthands ─────────────────────────────────────
_theme_key    = settings.get("app_theme", "ocean_dark")
_TH           = THEMES.get(_theme_key, THEMES["ocean_dark"])
_CHT_BG       = _TH["chart_bg"]
_CHT_GRID     = _TH["chart_grid"]
_CHT_FONT     = _TH["chart_font"]
_CHT_LEG      = _TH["chart_legend"]
_CHT_LEG_FONT = _TH["chart_legend_font"]
app_mode   = settings.get("app_mode", "demo")   # "demo" | "live"
is_demo    = app_mode != "live"
# Demo: use saved setting (default 0). Live: 0 until a broker pull is done this session.
if is_demo:
    acct_bal = float(settings.get("account_balance", 0))
else:
    acct_bal = (float(settings.get("account_balance", 0))
                if st.session_state.get("_live_balance_set") else 0.0)

# Push IB config to session_state so get_live_data() can read it without DB calls
if "_ib_cfg" not in st.session_state:
    st.session_state["_ib_cfg"] = {
        "host":     settings.get("ib_host",            "127.0.0.1"),
        "port":     int(settings.get("ib_port",         "7497") or 7497),
        "cid":      int(settings.get("ib_client_id",    "1")    or 1),
        "use_live": settings.get("ib_use_live_prices",  "0") == "1",
    }

# Auto-connect to IB once per browser session if enabled (skipped in demo mode)
if (not is_demo
        and settings.get("broker", "ib") == "ib"
        and settings.get("ib_auto_connect", "0") == "1"
        and _ib_mod.is_available()
        and not st.session_state.get("_ib_auto_connect_done")):
    _ib_cfg_ac = st.session_state["_ib_cfg"]
    try:
        _ac_ok, _ac_msg = _ib_mod.test_connection(
            _ib_cfg_ac["host"], _ib_cfg_ac["port"], _ib_cfg_ac["cid"]
        )
        st.session_state["_ib_connected"]    = _ac_ok
        st.session_state["_ib_connect_msg"]  = _ac_msg
    except Exception as _e:
        st.session_state["_ib_connected"]   = False
        st.session_state["_ib_connect_msg"] = str(_e)
    st.session_state["_ib_auto_connect_done"] = True

# Auto-sync account balance from IB once per browser session (skipped in demo mode)
if (not is_demo
        and settings.get("ib_auto_sync_balance") == "1"
        and _ib_mod.is_available()
        and not st.session_state.get("_ib_auto_synced")):
    try:
        _ib_cfg_ss = st.session_state["_ib_cfg"]
        with _ib_mod.IBClient(_ib_cfg_ss["host"], _ib_cfg_ss["port"], _ib_cfg_ss["cid"]) as _ib_auto:
            _auto_acct = _ib_auto.get_account_summary()
        if _auto_acct.get("net_liquidation"):
            acct_bal = _auto_acct["net_liquidation"]
            st.session_state["_live_balance_set"] = True
        st.session_state["_ib_auto_synced"] = True
    except Exception:
        st.session_state["_ib_auto_synced"] = True  # don't retry on error


# ── Global CSS / JS ────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Hide Streamlit noise ───────────────────────────── */
[data-testid="InputInstructions"] { display: none !important; }

/* ── Base surfaces ──────────────────────────────────── */
[data-testid="stAppViewContainer"]  { background: #131929; }
[data-testid="stSidebar"]           { background: #1a2236 !important; border-right: 1px solid #252f45; }
[data-testid="stSidebarContent"]    { padding-top: 1rem; }
section[data-testid="stMain"]       { background: #131929; }

/* ── Sidebar title ──────────────────────────────────── */
[data-testid="stSidebar"] h1 {
    color: #4e8ef7;
    font-size: 1.4rem;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #2e3a50;
    padding-bottom: 0.5rem;
    margin-bottom: 0.75rem;
}

/* ── Sidebar nav buttons ────────────────────────────── */
[data-testid="stSidebar"] .stButton button {
    background: transparent;
    border: none;
    color: #8fa4c8;
    text-align: left;
    font-size: 0.9rem;
    padding: 0.4rem 0.75rem;
    border-radius: 6px;
    transition: background 0.15s, color 0.15s;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #1f2d46;
    color: #c8cfe0;
}
[data-testid="stSidebar"] .stButton button[kind="primary"] {
    background: #1e3566;
    color: #ffffff;
    font-weight: 600;
}

/* ── Expanders ──────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #1a2236;
    border: 1px solid #252f45;
    border-radius: 8px;
    margin-bottom: 0.75rem;
}
[data-testid="stExpander"] summary {
    color: #a8b9d8;
    font-weight: 600;
}

/* ── Metric cards ───────────────────────────────────── */
[data-testid="stMetric"] {
    background: #1e2a40;
    border: 1px solid #263045;
    border-radius: 8px;
    padding: 0.65rem 0.9rem;
}
[data-testid="stMetric"] label  { color: #7a90b0 !important; font-size: 0.78rem; }
[data-testid="stMetricValue"]   { color: #e0e8f5 !important; }

/* ── Section heading accents ────────────────────────── */
h4, h5 { color: #c8cfe0; }

/* ── Dividers ───────────────────────────────────────── */
hr { border-color: #252f45 !important; }

/* ── Forms / inputs ─────────────────────────────────── */
[data-testid="stForm"] {
    background: #1a2236;
    border: 1px solid #252f45;
    border-radius: 8px;
    padding: 1rem;
}
input, textarea, select,
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div {
    background: #131929 !important;
    border-color: #2e3a50 !important;
    color: #c8cfe0 !important;
}

/* ── Dataframe ──────────────────────────────────────── */
[data-testid="stDataFrame"] { border: 1px solid #252f45; border-radius: 6px; }

/* ── Popover ────────────────────────────────────────── */
[data-testid="stPopover"] > div {
    background: #1a2236;
    border: 1px solid #252f45;
}

/* ── Tabs (if any) ──────────────────────────────────── */
[data-testid="stTabs"] button {
    color: #8fa4c8;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #4e8ef7;
    border-bottom-color: #4e8ef7;
}

/* ── Alerts / banners ───────────────────────────────── */
[data-testid="stAlert"] { border-radius: 6px; }

/* ── Mode badge ─────────────────────────────────────── */
.mode-badge-live {
    display: inline-block;
    background: #1e6f3a;
    color: #7fffb0;
    font-weight: 800;
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    padding: 0.3rem 0.9rem;
    border-radius: 20px;
    margin: 0.4rem 0 0.6rem 0;
    width: 100%;
    text-align: center;
    border: 2px solid #27ae60;
}
.mode-badge-demo {
    display: inline-block;
    background: #1e6f3a;
    color: #7fffb0;
    font-weight: 800;
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    padding: 0.3rem 0.9rem;
    border-radius: 20px;
    margin: 0.4rem 0 0.6rem 0;
    width: 100%;
    text-align: center;
    border: 2px solid #27ae60;
}

/* ── Primary action buttons ─────────────────────────── */
button[kind="primary"] {
    color: #0a2558 !important;
    font-weight: 700 !important;
}

/* ── Fetch live button ───────────────────────────────── */
.stButton.fetch-live > button {
    background: #2c3e6a !important;
    border: 1px solid #3a5a9a !important;
    font-weight: 700 !important;
}

/* ── Dropdowns / Selectboxes — neutral gray ─────────── */
[data-baseweb="select"] > div:first-child {
    background-color: #252a36 !important;
    border-color: #424857 !important;
    border-radius: 6px !important;
}
/* Flatten all inner containers to match the outer background */
[data-baseweb="select"] > div:first-child > div,
[data-baseweb="select"] > div:first-child > div > div,
[data-baseweb="select"] > div:first-child > div > div > div,
[data-baseweb="select"] input,
[data-baseweb="input"],
[data-baseweb="base-input"] {
    background-color: #252a36 !important;
    background: #252a36 !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] [class*="singleValue"],
[data-baseweb="select"] [class*="placeholder"] {
    color: #c8cfe0 !important;
}
[data-baseweb="select"] svg { fill: #7a8598 !important; }
[data-baseweb="menu"] {
    background-color: #1e222d !important;
    border: 1px solid #424857 !important;
    border-radius: 6px !important;
}
[data-baseweb="option"] {
    background-color: transparent !important;
    color: #c8cfe0 !important;
}
[data-baseweb="option"]:hover,
[data-baseweb="option"][aria-selected="true"] {
    background-color: #30363f !important;
    color: #ffffff !important;
}
[data-baseweb="tag"] {
    background-color: #363c48 !important;
    color: #c8cfe0 !important;
}
[data-baseweb="tag"] svg { fill: #7a8598 !important; }

/* ── Remove status/separator lines inside dropdowns ─── */
/* Hides the thin divider bar between the value area and the chevron arrow */
[data-baseweb="select"] > div:first-child > div:last-child {
    border-left: none !important;
}
/* Hide any hr or empty span used as a visual separator.
   The :empty guard is essential — without it this rule also matched the
   multiselect chip's delete (×) wrapper (an aria-hidden span that *contains*
   an svg), hiding it and making individual tags impossible to remove. The
   real separator is an empty span, so :empty hides it while sparing the × . */
[data-baseweb="select"] hr,
[data-baseweb="select"] > div span[aria-hidden="true"]:not([class*="icon"]):empty {
    display: none !important;
}
/* Remove the bottom status/focus bar that appears on some Streamlit builds */
[data-baseweb="form-control"] > div:last-child:not([class]):empty,
[data-testid="stSelectbox"] > div > div:last-child > div:empty {
    display: none !important;
}
/* Suppress any block-level status indicator inside selectbox wrappers */
[data-testid="stSelectbox"] [data-baseweb="select"] ~ *:empty,
[data-testid="stMultiSelect"] [data-baseweb="select"] ~ *:empty {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# ── Theme override CSS (applied on top of the base dark styles above) ──────────
def _build_theme_css(t: dict) -> str:
    return f"""
<style>
[data-testid="stAppViewContainer"]  {{ background: {t['bg_main']} !important; }}
section[data-testid="stMain"]       {{ background: {t['bg_main']} !important; }}
[data-testid="stSidebar"]           {{ background: {t['bg_sidebar']} !important; border-right-color: {t['border']} !important; }}

[data-testid="stSidebar"] h1 {{ color: {t['accent']} !important; border-bottom-color: {t['border']} !important; }}
[data-testid="stSidebar"] .stButton button {{ color: {t['text_secondary']} !important; background: transparent !important; }}
[data-testid="stSidebar"] .stButton button:hover {{ background: {t['nav_hover_bg']} !important; color: {t['nav_hover_text']} !important; }}
[data-testid="stSidebar"] .stButton button[kind="primary"] {{ background: {t['nav_active_bg']} !important; color: {t['nav_active_text']} !important; }}

[data-testid="stExpander"] {{ background: {t['bg_expander']} !important; border-color: {t['border']} !important; }}
[data-testid="stExpander"] summary {{ color: {t['text_secondary']} !important; }}
[data-testid="stExpander"] summary svg {{ fill: {t['text_secondary']} !important; }}

[data-testid="stMetric"] {{ background: {t['bg_card']} !important; border-color: {t['border']} !important; }}
[data-testid="stMetric"] label {{ color: {t['text_dim']} !important; }}
[data-testid="stMetricValue"] {{ color: {t['text_metric']} !important; }}

h4, h5 {{ color: {t['text_heading']} !important; }}
hr {{ border-color: {t['hr']} !important; }}
.stMarkdown p, p {{ color: {t['text_primary']}; }}
[data-testid="stCaptionContainer"] p {{ color: {t['text_dim']} !important; }}
[data-testid="stWidgetLabel"] p {{ color: {t['text_secondary']} !important; }}
[data-testid="stRadio"] label p,
[data-testid="stCheckbox"] label p {{ color: {t['text_primary']} !important; }}

[data-testid="stForm"] {{ background: {t['bg_form']} !important; border-color: {t['border']} !important; }}
input, textarea, select,
[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div {{
    background: {t['bg_input']} !important;
    border-color: {t['border_input']} !important;
    color: {t['text_primary']} !important;
}}

[data-baseweb="select"] > div:first-child {{
    background-color: {t['bg_select']} !important;
    border-color: {t['border_input']} !important;
}}
[data-baseweb="select"] > div:first-child > div,
[data-baseweb="select"] > div:first-child > div > div,
[data-baseweb="select"] > div:first-child > div > div > div,
[data-baseweb="select"] input,
[data-baseweb="input"],
[data-baseweb="base-input"] {{
    background-color: {t['bg_select']} !important;
    background: {t['bg_select']} !important;
}}
[data-baseweb="select"] span,
[data-baseweb="select"] [class*="singleValue"],
[data-baseweb="select"] [class*="placeholder"] {{ color: {t['text_primary']} !important; }}
[data-baseweb="menu"] {{
    background-color: {t['bg_menu']} !important;
    border-color: {t['border_input']} !important;
}}
[data-baseweb="option"] {{ color: {t['text_primary']} !important; background: transparent !important; }}
[data-baseweb="option"]:hover,
[data-baseweb="option"][aria-selected="true"] {{
    background-color: {t['option_hover']} !important;
    color: {t['text_primary']} !important;
}}
[data-baseweb="tag"] {{ background-color: {t['tag_bg']} !important; color: {t['text_primary']} !important; }}

[data-testid="stDataFrame"] {{ border-color: {t['border']} !important; }}
[data-testid="stTabs"] button {{ color: {t['text_secondary']} !important; }}
[data-testid="stTabs"] button[aria-selected="true"] {{ color: {t['accent']} !important; border-bottom-color: {t['accent']} !important; }}

[data-testid="stPopover"] > div {{ background: {t['bg_expander']} !important; border-color: {t['border']} !important; }}
</style>
"""

if _theme_key != "ocean_dark":
    st.markdown(_build_theme_css(_TH), unsafe_allow_html=True)

st.iframe("""
<script>
(function() {
    var doc = window.parent.document;

    // Ctrl+Enter form submission
    doc.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.ctrlKey) {
            var active = doc.activeElement;
            if (active && active.tagName !== 'TEXTAREA') {
                var btn = doc.querySelector(
                    'button[kind="primaryFormSubmit"], button[kind="secondaryFormSubmit"]'
                );
                if (btn) e.preventDefault();
            }
        }
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            var btns = doc.querySelectorAll(
                'button[kind="primaryFormSubmit"], button[kind="secondaryFormSubmit"]'
            );
            for (var i = 0; i < btns.length; i++) {
                var r = btns[i].getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { btns[i].click(); break; }
            }
        }
    }, true);

    // Green labels for required fields (labels whose text ends with " *")
    function applyRequiredLabelStyle() {
        doc.querySelectorAll('label, [data-testid="stWidgetLabel"] p').forEach(function(el) {
            if (el.dataset && el.dataset.reqStyled) return;
            var txt = el.textContent || '';
            if (txt.indexOf('*') !== -1) {
                el.style.color = '#7fffb0';
                el.style.fontWeight = '600';
                if (el.dataset) el.dataset.reqStyled = '1';
            }
        });
    }
    applyRequiredLabelStyle();
    new MutationObserver(applyRequiredLabelStyle).observe(doc.body, { childList: true, subtree: true });
})();
</script>
""", height=1)  # st.iframe (was components.html, deprecated); min height 1, JS-only injector


# ── Sidebar navigation ────────────────────────────────────────────────────────

_MAIN_PAGES  = ["📋  Trading Log", "📝  Trading Plan", "📊  Statistics", "📈  Equity Curve", "🛠️  Trading Tools"]
_ADMIN_PAGES = ["🏷️  Tags", "🔗  Broker Sync", "⚙️  Settings", "📖  Glossary"]

# ── Glossary content (edit freely — plain markdown) ─────────────────────────────
GLOSSARY_MD = """
**Charting and Analysis Platforms**
- **Thinkorswim** — Charles Schwab's advanced desktop charting and trading platform.
- **TradingView** — Web-based charting platform with social features and scripting (Pine Script).
- **TradeVision** — Charting and analysis platform.
- **StockCharts** — Web-based charting and technical analysis service.

**Screening Platforms**
- **Finviz** — Stock screener and market visualization (heatmaps, news, screens).
- **TradingView** — Built-in screener for stocks, forex, and crypto.
- **Thinkorswim** — Scan/screening tools built into the platform.
- **TradeVision** — Screening platform.
- **StockCharts** — Screening via scans and predefined filters.
- **Chartmill** — Technical and fundamental stock screener.

**Execution Platforms**
- **TradingView** — Order entry and execution through connected brokers.

**Brokers**
- **IBKR** — Interactive Brokers; low-cost global broker with deep API access.
- **Schwab (TOS)** — Charles Schwab, parent of the Thinkorswim platform.
- **Fidelity** — Full-service US broker.
- **Robinhood** — Commission-free mobile-first broker.
- **ETrade** — US online broker (owned by Morgan Stanley).
- **WeBull** — Commission-free broker with active-trader tools.
- **212** — Trading 212; UK/EU commission-free broker.

**Indicator List**
- **RSI** — Relative Strength Index; momentum oscillator measuring speed/magnitude of price moves (0–100).
- **MACD** — Moving Average Convergence Divergence; trend/momentum indicator from two EMAs.
- **Stochastic** — Momentum oscillator comparing close to a range over a period.
- **Moving Averages** — Smoothed average price over a window.
    - **SMA** — Simple Moving Average; equal weighting of all periods.
    - **EMA** — Exponential Moving Average; more weight to recent prices.
- **MRSI** — Modified/Mean RSI variant.
- **Bollinger Bands** — Volatility bands set a number of standard deviations around a moving average.
- **ATR** — Average True Range; measure of volatility.

**Terms**

*Orders*
- **Market** — Buy/sell immediately at the best available price.
- **Limit** — Execute only at a specified price or better.
- **Stop (Market)** — Becomes a market order once the stop price is hit.
- **Stop (Limit)** — Becomes a limit order once the stop price is hit.
- **Stop Buy orders** — Stop order to enter long above the current price.
- **Trailing Stop** — Stop that follows price by a set distance/percentage.
- **OCO** — One-Cancels-Other; filling one order cancels the other.
- **OTOCO** — One-Triggers-OCO; an entry order that triggers a bracket (OCO) of exits.
- **OTO** — One-Triggers-Other; filling the first order activates the next.
- **1st Triggers OCO** — First order, once filled, activates an OCO pair.
- **Multiple OCOs** — Several linked OCO groups managed together.
- **MOC order** — Market-On-Close; executes at the closing price.
- **LOC order** — Limit-On-Close; executes at the close only if the limit is met.
- **AON order** — All-Or-None; fill the entire quantity or none.
- **FOK order** — Fill-Or-Kill; fill immediately and completely or cancel.
- **Conditional code for entries** — Rule/condition-based logic that triggers entries.

*Miscellaneous Jargon*
- _(add terms here)_

**Metrics**
- **Sharpe** — Risk-adjusted return using total volatility (std. deviation).
- **Sortino** — Risk-adjusted return penalizing only downside volatility.
- **R Value** — Profit/loss expressed in multiples of initial risk (1R = risk per trade).
- **Calmar** — Return divided by maximum drawdown.
- **Drawdown** — Peak-to-trough decline in equity.
- **EV/Expectancy** — Average expected profit/loss per trade.

**Risk Management**
- **Risk based position sizing** — Size positions from the dollar risk per trade (entry to stop).
- **Allocation based position sizing** — Size positions as a fixed percentage of account capital.
"""

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "📋  Trading Log"

with st.sidebar:
    st.title("Trade Log")

    # ── Mode badge ─────────────────────────────────────────────────────────
    if is_demo:
        st.markdown('<div class="mode-badge-demo">📴  Offline</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="mode-badge-live">🟢  Connected to Broker</div>', unsafe_allow_html=True)

    for _p in _MAIN_PAGES:
        _active = st.session_state["nav_page"] == _p
        if st.button(_p, width='stretch', key=f"nav_{_p}",
                     type="primary" if _active else "secondary"):
            st.session_state["nav_page"] = _p
            st.rerun()
    st.markdown("---")
    for _p in _ADMIN_PAGES:
        _active = st.session_state["nav_page"] == _p
        if st.button(_p, width='stretch', key=f"nav_{_p}",
                     type="primary" if _active else "secondary"):
            st.session_state["nav_page"] = _p
            st.rerun()

    # ── Export for Review (big, prominent) ──────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "<style>"
        "div[data-testid='stSidebar'] .st-key-sb_export_review button {"
        "  background: linear-gradient(135deg,#3b1d6e,#6d28d9,#8b5cf6) !important;"
        "  color:#fff !important; font-size:1.35rem !important; font-weight:900 !important;"
        "  border:none !important; border-radius:12px !important; padding:1.0rem 0 !important;"
        "  letter-spacing:0.05em !important;"
        "  box-shadow:0 4px 18px rgba(139,92,246,0.5),0 2px 6px #0008 !important;"
        "  text-shadow:0 1px 4px #0005 !important; transition:transform .1s, box-shadow .1s !important;"
        "}"
        "div[data-testid='stSidebar'] .st-key-sb_export_review button:hover {"
        "  transform:scale(1.03) !important;"
        "  box-shadow:0 6px 24px rgba(139,92,246,0.65),0 3px 8px #000a !important;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )
    if st.button("📄  EXPORT FOR REVIEW", width='stretch', key="sb_export_review",
                 help="Create a PDF review report (trade log + full stats) for a date range"):
        st.session_state["_show_export"] = True
        st.rerun()

    # ── App updates ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(f"v{_upd.get_local_version()}")
    if st.button("Check for updates", width="stretch", key="sb_check_updates"):
        with st.spinner("Checking…"):
            _remote_ver = _upd.get_remote_version()
        if _remote_ver is None:
            st.session_state["_upd_status"] = "error"
            st.session_state.pop("_upd_remote_ver", None)
        elif _remote_ver == _upd.get_local_version():
            st.session_state["_upd_status"] = "current"
            st.session_state.pop("_upd_remote_ver", None)
        else:
            st.session_state["_upd_status"] = "available"
            st.session_state["_upd_remote_ver"] = _remote_ver

    _upd_status = st.session_state.get("_upd_status")
    if _upd_status == "error":
        st.error("Could not reach GitHub.")
    elif _upd_status == "current":
        st.success("You're up to date.")
    elif _upd_status == "available":
        st.info(f"Update available → {st.session_state.get('_upd_remote_ver', '')}")
        if st.button("⬇  Install update", width="stretch", key="sb_do_update", type="primary"):
            with st.spinner("Downloading and installing…"):
                _ok, _err = _upd.download_updates()
            if _ok:
                st.session_state.pop("_upd_status", None)
                st.session_state.pop("_upd_remote_ver", None)
                st.rerun()
            else:
                st.error(f"Update failed: {_err}")

    # ── Live data fetch (sidebar, always docked) ───────────────────────────
    st.markdown("---")
    st.markdown(
        "<style>"
        "#sb_fetch_live_container { margin: 0.5rem 0 0.25rem 0; }"
        "div[data-testid='stSidebar'] div[data-testid='stButton']:last-of-type button {"
        "  background: linear-gradient(135deg,#0d4a28,#1a8a40,#22c55e) !important;"
        "  color: #fff !important; font-size: 1.45rem !important;"
        "  font-weight: 900 !important; border: none !important;"
        "  border-radius: 12px !important; padding: 1.1rem 0 !important;"
        "  letter-spacing: 0.06em !important;"
        "  box-shadow: 0 4px 18px rgba(34,197,94,0.5), 0 2px 6px #0008 !important;"
        "  text-shadow: 0 1px 4px #0005 !important;"
        "  transition: transform 0.1s, box-shadow 0.1s !important;"
        "}"
        "div[data-testid='stSidebar'] div[data-testid='stButton']:last-of-type button:hover {"
        "  transform: scale(1.03) !important;"
        "  box-shadow: 0 6px 24px rgba(34,197,94,0.65), 0 3px 8px #000a !important;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )
    if st.button("⚡  REFRESH LIVE PRICES", width='stretch', key="sb_fetch_live",
                 help="Clear the price cache and re-fetch all live quotes now"):
        _yf_get_live_data.clear()
        for _k in [k for k in st.session_state if k.startswith("_ib_live_")]:
            del st.session_state[_k]
        st.session_state.pop("_live_data_cache", None)
        st.session_state["_live_prices_loaded"] = True
        st.rerun()
    st.markdown(
        "<div style='text-align:center;font-size:0.75rem;color:#888;margin-top:-6px'>"
        "Prices do not auto-load — click above to fetch."
        "</div>",
        unsafe_allow_html=True,
    )

page = st.session_state["nav_page"]


# ── Guided setup tour ─────────────────────────────────────────────────────────
# A first-run walkthrough: a welcome modal, then highlighted "coach" cards pinned
# above the real widgets on each page. Driven by st.session_state["_tour_step"].

TOUR_STEPS = [
    {
        "section": "broker",
        "page": "🔗  Broker Sync",
        "title": "Connect to Interactive Brokers (optional)",
        "body": (
            "If you use **Interactive Brokers**, you can connect Trade Log to TWS or "
            "IB Gateway for live prices and automatic balance sync.\n\n"
            "Expand **“🛟 How to connect — step by step”** below for plain-English "
            "instructions. Set the **Host / Port / Client ID**, then click "
            "**🔌 Test Connection**.\n\n"
            "Don't use IBKR, or want to set this up later? Just hit **Skip this section** — "
            "everything works fine entering trades manually."
        ),
    },
    {
        "section": "settings",
        "page": "⚙️  Settings",
        "title": "Set your account balance",
        "body": (
            "Open the **Account & Equity** section below and enter your current account "
            "value, then **Save**.\n\n"
            "This drives position sizing and the **% of Account** risk figures in your "
            "trade table."
        ),
    },
    {
        "section": "settings",
        "page": "⚙️  Settings",
        "title": "Choose your date format",
        "body": (
            "In the **Display** section, flip **Euro dates** on if you prefer "
            "**DD/MM/YYYY** instead of **MM/DD/YYYY**. This changes how every date is "
            "shown across the app."
        ),
    },
    {
        "section": "settings",
        "page": "⚙️  Settings",
        "title": "Set your default commissions",
        "body": (
            "In **Commission Defaults**, enter your broker's typical fees for stocks "
            "(flat per trade), options (per contract), and futures (per contract).\n\n"
            "These pre-fill whenever you log a trade, so your P&L can be shown **net of "
            "fees** automatically."
        ),
    },
    {
        "section": "settings",
        "page": "⚙️  Settings",
        "title": "Add any extra currencies",
        "body": (
            "Trading in a non-USD account? Open **Multi-Currency**, switch it on, and "
            "pick your **native currency** (AUD, CAD, EUR).\n\n"
            "Trade Log will then show P&L converted to your currency alongside the USD "
            "figures. USD-only? Skip ahead."
        ),
    },
    {
        "section": "tags",
        "page": "🏷️  Tags",
        "title": "Create your first tag",
        "body": (
            "**Tags** let you slice and filter your trades later — by strategy, setup, "
            "watchlist, conviction, anything you like.\n\n"
            "Type a name in **Add New Tag** below (try something like *Breakout* or "
            "*Swing*) and click **Add**. Go ahead and create one now — then hit "
            "**Next →**."
        ),
    },
    {
        "section": "equity",
        "page": "📈  Equity Curve",
        "title": "Track your equity over time",
        "body": (
            "Click the **✏️ Manual Entry** tab above. Enter a **date** and your "
            "**end-of-day balance** (plus any deposits or withdrawals that day) and "
            "**Save**.\n\n"
            "Add an entry regularly — or bulk-import from a CSV or Interactive Brokers — "
            "and Trade Log plots your equity curve and time-weighted return."
        ),
    },
    {
        "section": "log",
        "page": "📋  Trading Log",
        "title": "Log your first trade",
        "body": (
            "This is home base. Click **➕ Add Trade** below to open the form.\n\n"
            "Required fields are marked with a green **\\***: **Ticker**, **Quantity**, "
            "and **Entry Price** (plus the **Entry Date**). Everything else — exit "
            "price/date, stop loss, tags, notes — is optional and can be filled in "
            "later.\n\n"
            "Press **Ctrl+Enter** or click **Add Trade** to save. That's it — you're "
            "set up!"
        ),
    },
]


def _start_tour():
    st.session_state["_tour_active"] = True
    st.session_state["_tour_step"] = 0
    st.session_state["nav_page"] = TOUR_STEPS[0]["page"]
    st.rerun()


def _end_tour():
    st.session_state["_tour_active"] = False
    st.session_state.pop("_tour_step", None)
    set_setting("onboarding_done", "1")
    _bust("_v_settings")
    st.rerun()


def _tour_goto(idx: int):
    """Advance/rewind the tour to a step index; ends the tour past the last step."""
    if idx < 0:
        idx = 0
    if idx >= len(TOUR_STEPS):
        _end_tour()
        return
    st.session_state["_tour_step"] = idx
    st.session_state["nav_page"] = TOUR_STEPS[idx]["page"]
    st.rerun()


def _tour_skip_section(idx: int):
    """Jump to the first step of the next section (or end the tour)."""
    section = TOUR_STEPS[idx]["section"]
    j = idx + 1
    while j < len(TOUR_STEPS) and TOUR_STEPS[j]["section"] == section:
        j += 1
    _tour_goto(j)


def render_tour_panel(page_key: str):
    """Render the guided-tour coach card at the top of a page, if it's the active step."""
    if not st.session_state.get("_tour_active"):
        return
    idx = st.session_state.get("_tour_step", 0)
    if idx >= len(TOUR_STEPS):
        return
    step = TOUR_STEPS[idx]
    if step["page"] != page_key:
        return

    with st.container(border=True):
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#1a8a40,#22c55e);"
            f"color:#fff;font-weight:800;padding:0.35rem 0.7rem;border-radius:8px;"
            f"display:inline-block;margin-bottom:0.4rem'>"
            f"🧭 Setup Tour · Step {idx + 1} of {len(TOUR_STEPS)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {step['title']}")
        st.markdown(step["body"])
        is_last = idx == len(TOUR_STEPS) - 1
        b1, b2, b3, b4 = st.columns([1, 1, 1.3, 1.3])
        if b1.button("✕ End tour", key=f"_tour_end_{idx}", width="stretch"):
            _end_tour()
        if b2.button("← Back", key=f"_tour_back_{idx}", width="stretch", disabled=idx == 0):
            _tour_goto(idx - 1)
        if not is_last:
            if b3.button("Skip this section ⏭", key=f"_tour_skipsec_{idx}", width="stretch"):
                _tour_skip_section(idx)
        if b4.button("Finish ✓" if is_last else "Next →", key=f"_tour_next_{idx}",
                     type="primary", width="stretch"):
            _tour_goto(idx + 1)


def _welcome_body():
    st.markdown(
        "Trade Log is your personal trading journal — it runs entirely on **your "
        "own computer** and your data never leaves your machine.\n\n"
        "This quick **setup tour** walks you through getting ready:\n\n"
        "- 🔗 Connecting **Interactive Brokers** (optional)\n"
        "- ⚙️ Setting your **account balance, date format, commissions & currency**\n"
        "- 🏷️ Creating your first **tag**\n"
        "- 📈 Logging your **equity**\n"
        "- 📋 Logging your first **trade**\n\n"
        "It takes about a minute, and you can **skip any part** at any time."
    )
    wc1, wc2 = st.columns(2)
    if wc1.button("🧭  Start setup tour", type="primary", width="stretch", key="_welcome_start"):
        _start_tour()
    if wc2.button("Skip for now", width="stretch", key="_welcome_skip"):
        _end_tour()
    st.caption("You can replay this tour anytime from ⚙️ Settings.")


if hasattr(st, "dialog"):
    @st.dialog("👋  Welcome to Trade Log")
    def _welcome_dialog():
        _welcome_body()
else:
    def _welcome_dialog():
        with st.container(border=True):
            st.markdown("### 👋  Welcome to Trade Log")
            _welcome_body()


# Show the welcome splash on first run. We call it on EVERY run (until the user
# starts or skips) so the dialog's buttons are re-instantiated on the rerun that
# processes a click — otherwise the click would be lost and nothing would happen.
if (settings.get("onboarding_done", "0") != "1"
        and not st.session_state.get("_tour_active")):
    _welcome_dialog()

# Export-for-Review dialog — opened from the sidebar; re-rendered every run while
# open so its buttons (Build / Download / Close) are processed correctly.
if st.session_state.get("_show_export"):
    _export_dialog(acct_bal)

# Sidebar reminder + escape hatch while a tour is running
if st.session_state.get("_tour_active"):
    with st.sidebar:
        st.markdown("---")
        st.info("🧭 Setup tour in progress")
        if st.button("End tutorial", width="stretch", key="sb_end_tour"):
            _end_tour()


# ── Shared data ────────────────────────────────────────────────────────────────

all_tags       = _cached_load_tags(st.session_state["_v_tags"])
tag_name_to_id = {t["name"]: t["id"] for t in all_tags}
tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
all_accounts   = _cached_load_accounts(st.session_state["_v_accounts"])
_default_commission      = float(settings.get("default_commission",  "0")    or 0)
_options_commission      = float(settings.get("options_commission",  "0.65") or 0.65)
_futures_commission      = float(settings.get("futures_commission",  "2.25") or 2.25)


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — TRADING LOG
# ════════════════════════════════════════════════════════════════════════════════

if page == "📋  Trading Log":

    render_tour_panel("📋  Trading Log")

    # Initialise filter defaults once per session (explicit keys prevent rerun-resets)
    _FILTER_DEFAULTS: dict = {
        "filter_status":     "Open",
        "filter_ticker":     [],
        "filter_tags":       [],
        "filter_pnl":        "All",
        "filter_date_col":   "Entry Date",
        "filter_date_range": [],
    }
    for _fk, _fv in _FILTER_DEFAULTS.items():
        if _fk not in st.session_state:
            st.session_state[_fk] = _fv

    # ── Ticker Lookup ─────────────────────────────────────────────────────────

    tl_col, _ = st.columns([1, 3])
    lookup_val = tl_col.text_input(
        "🔍 Ticker Lookup",
        placeholder="Type a ticker to see company info…",
        key="ticker_lookup",
    )
    if lookup_val.strip():
        info = get_ticker_info(lookup_val.strip().upper())
        if info and info.get("name"):
            tl_col.caption(f"✅ **{info['name']}** · {info.get('exchange', '—')}")
        else:
            tl_col.caption("⚠️ Not found on Yahoo Finance")

    # ── Add Trade ─────────────────────────────────────────────────────────────

    # On the rerun after a successful add, surface the confirmation dialog. Popping
    # the flag before opening it makes the dialog one-shot: OK (or dismiss) reruns
    # with no flag → it closes.
    _just_added = st.session_state.pop("_trade_added", None)
    if _just_added:
        # Reset the ticker field by bumping its key seed: the ticker lives outside
        # the form (so clear_on_submit can't reach it) and deleting its key doesn't
        # reliably reset a text_input. A fresh key = a brand-new, empty widget.
        st.session_state["_add_tk_seed"] = st.session_state.get("_add_tk_seed", 0) + 1
        _trade_added_dialog(_just_added)

    with st.expander("➕  Add Trade", expanded=False):

        # Green highlight + bordered box around the fields needed to log a trade
        st.markdown(
            "<style>"
            ".st-key-add_need_ticker, .st-key-add_need_fields {"
            "  border:1px solid rgba(46,204,113,0.55) !important;"
            "  border-radius:10px !important; background:rgba(46,204,113,0.06) !important;"
            "}"
            ".st-key-add_need_ticker label, .st-key-add_need_fields label,"
            ".st-key-add_need_fields .stMarkdown p,"
            ".st-key-add_need_fields [data-testid='stCaptionContainer'],"
            ".st-key-add_opt_tags label, .st-key-add_fut_tags label {"
            "  color:#27ae60 !important; font-weight:700 !important;"
            "}"
            "</style>",
            unsafe_allow_html=True,
        )

        # Instrument type selector — outside form so it drives field layout
        ih1, ih2 = st.columns([3, 1])
        add_inst = ih1.selectbox(
            "Instrument type",
            ["Stock", "Option", "Future"],
            key="add_inst_type",
            label_visibility="collapsed",
        )
        add_num_legs = 1
        if add_inst in ("Option", "Future"):
            add_num_legs = int(ih2.number_input(
                "Legs", min_value=1, max_value=4, value=1, step=1, format="%d",
                key="add_num_legs",
            ))

        # Same-expiration shortcut for option multi-leg entry
        if add_inst == "Option" and add_num_legs > 1:
            _osk1, _osk2 = st.columns(2)
            _osk1.checkbox("Same expiration for all legs", key="opt_same_exp", value=True)
            _osk2.checkbox("Same underlying for all legs", key="opt_same_under", value=True,
                           help="All legs share the underlying ticker entered above")

        # Ticker + trailing stop — outside form so both react on each keystroke / click
        _at_inst = st.session_state.get("add_inst_type", "Stock")
        _at_lk_label = "Symbol" if _at_inst == "Future" else "Underlying Ticker" if _at_inst == "Option" else "Ticker"
        with st.container(border=True, key="add_need_ticker"):
            if _at_inst == "Stock":
                _tlk1, _tlk2, _tlk3 = st.columns([2, 3, 1])
                _tlk3.checkbox("Trailing Stop", key="add_trailing_en", value=False)
            else:
                _tlk1, _tlk2 = st.columns([2, 3])
            _at_tk_key = f"add_ticker_lookup_{st.session_state.get('_add_tk_seed', 0)}"
            _at_ticker_raw = _tlk1.text_input(
                _at_lk_label,
                key=_at_tk_key,
                placeholder="e.g. AAPL",
                label_visibility="visible",
            )
            _at_ticker = _at_ticker_raw.strip().upper()
            _at_exchange = st.session_state.get("add_stock_exchange", "") or ""
            if _at_ticker:
                _at_price = _get_single_live_price(_at_ticker, _at_exchange)
                _at_yf_sym = _yf_symbol(_at_ticker, _at_exchange)
                if _at_price is not None:
                    _sym_label = f" · via {_at_yf_sym}" if _at_yf_sym != _at_ticker else ""
                    _tlk2.markdown(
                        f"<div style='padding-top:28px;font-size:1rem'>"
                        f"<b>{_at_ticker}</b>{_sym_label} &nbsp; <span style='color:#2ecc71;font-size:1.2rem;font-weight:700'>"
                        f"${_at_price:,.2f}</span></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    _sym_hint = f" ({_at_yf_sym})" if _at_yf_sym != _at_ticker else ""
                    _tlk2.caption(f"No price found{_sym_hint} — check the ticker or exchange code.")

        with st.form("add_trade", clear_on_submit=True):
            inst   = st.session_state.get("add_inst_type", "Stock")
            n_legs = max(1, int(st.session_state.get("add_num_legs", 1))) if inst != "Stock" else 1

            # ── STOCK ───────────────────────────────────────────────────────
            if inst == "Stock":
                s_ticker = _at_ticker
                with st.container(border=True, key="add_need_fields"):
                    st.caption("● Required to log a trade")
                    c1, c2, c3 = st.columns(3)
                    entry_date  = c1.date_input("Entry Date *")
                    quantity    = c2.number_input("Quantity *", min_value=0.0, step=1.0, format="%.0f", value=None)
                    entry_price = c3.number_input("Entry Price *", min_value=0.0, step=0.01, format="%.2f", value=None)
                    st.markdown("**Stop Loss**")
                    _trailing_en = st.session_state.get("add_trailing_en", False)
                    sc1, sc2 = st.columns([1, 2])
                    stop_enabled = sc1.checkbox("Enabled", value=True)
                    opening_stop = sc2.number_input("Opening Stop", min_value=0.0, step=0.01, format="%.2f", value=None)
                    if _trailing_en:
                        _tr1, _tr2 = st.columns(2)
                        _add_trail_type   = _tr1.selectbox("Trail Unit", ["$", "%", "ATR"], key="add_trail_type")
                        _add_trail_amount = _tr2.number_input("Trail Amount", min_value=0.0, step=0.01,
                                                              format="%.2f", value=None, key="add_trail_amount")
                    else:
                        _add_trail_type, _add_trail_amount = "fixed", None
                    sel_tag_names = st.multiselect("Tags", options=list(tag_name_to_id.keys()))
                c5, c6 = st.columns(2)
                exit_date  = c5.date_input("Exit Date", value=None)
                exit_price = c6.number_input("Exit Price", min_value=0.0, step=0.01, format="%.2f", value=None)
                notes = st.text_area("Notes", height=68,
                                     placeholder="Trade thesis, setup, how it played out…")
                with st.expander("Advanced", expanded=False):
                    ca1, ca2 = st.columns(2)
                    stock_account    = ca1.selectbox("Account", options=all_accounts, key="add_stock_acct")
                    stock_commission = ca2.number_input("Commission ($)", min_value=0.0, step=0.01,
                                                        format="%.2f", value=_default_commission, key="add_stock_comm")
                    stock_exchange = st.selectbox(
                        "Exchange",
                        options=[code for code, _ in _EXCHANGE_OPTIONS],
                        format_func=lambda c: _EXCHANGE_LABEL.get(c, c),
                        key="add_stock_exchange",
                        help="Leave as US / Default for NYSE, NASDAQ, and other US exchanges.",
                    )
                    uploaded_files = st.file_uploader(
                        "Attachments", accept_multiple_files=True,
                        type=["png", "jpg", "jpeg", "gif", "pdf", "webp"],
                    )

            # ── OPTION ──────────────────────────────────────────────────────
            elif inst == "Option":
                s_ticker = _at_ticker
                oc1, oc2 = st.columns(2)
                opt_entry_dt  = oc1.date_input("Entry Date *")
                opt_mult      = oc2.number_input("Multiplier", value=100.0, step=1.0, format="%.0f",
                                                 help="Shares per contract (typically 100)")

                _SPREAD_TYPES = ["Vertical", "Straddle", "Strangle", "Iron Condor", "Butterfly", "Calendar", "Custom"]
                opt_spread_type = st.selectbox("Spread Type", ["—"] + _SPREAD_TYPES, key="opt_spread_type") if n_legs > 1 else None

                # Per-leg fields
                leg_sides, leg_qtys, leg_strikes = [], [], []
                leg_exps, leg_types, leg_prices  = [], [], []

                _same_exp = st.session_state.get("opt_same_exp", True) if n_legs > 1 else False
                if _same_exp and n_legs > 1:
                    st.markdown("**Legs**")
                    st.caption("Side · Qty · Strike · C/P · Premium  (shared expiration below)")
                    _global_exp = st.date_input("Expiration (all legs) *", key="opt_global_exp")
                elif n_legs > 1:
                    st.markdown("**Legs**")
                    st.caption("Side · Qty · Strike · Expiration · C/P · Premium")

                for i in range(n_legs):
                    if n_legs > 1:
                        st.markdown(f"*Leg {i+1}*")
                    if _same_exp and n_legs > 1:
                        lc = st.columns([1, 1, 1, 1, 1])
                        leg_sides.append(lc[0].selectbox("Side",     ["Long", "Short"], key=f"leg_{i}_side"))
                        leg_qtys.append( lc[1].number_input("Qty *", min_value=0.0, step=1.0, format="%.0f", value=None, key=f"leg_{i}_qty"))
                        leg_strikes.append(lc[2].number_input("Strike *", min_value=0.0, step=0.5, format="%.2f", value=None, key=f"leg_{i}_strike"))
                        leg_exps.append(_global_exp)
                        leg_types.append( lc[3].selectbox("C/P",     ["Call", "Put"], key=f"leg_{i}_type"))
                        leg_prices.append(lc[4].number_input("Premium *", min_value=0.0, step=0.01, format="%.2f", value=None, key=f"leg_{i}_price"))
                    else:
                        lc = st.columns([1, 1, 1, 2, 1, 1])
                        leg_sides.append(lc[0].selectbox("Side",       ["Long", "Short"], key=f"leg_{i}_side"))
                        leg_qtys.append( lc[1].number_input("Qty *",   min_value=0.0, step=1.0, format="%.0f", value=None, key=f"leg_{i}_qty"))
                        leg_strikes.append(lc[2].number_input("Strike *", min_value=0.0, step=0.5, format="%.2f", value=None, key=f"leg_{i}_strike"))
                        leg_exps.append(  lc[3].date_input("Expiration *", key=f"leg_{i}_exp"))
                        leg_types.append( lc[4].selectbox("C/P",       ["Call", "Put"],   key=f"leg_{i}_type"))
                        leg_prices.append(lc[5].number_input("Premium *", min_value=0.0, step=0.01, format="%.2f", value=None, key=f"leg_{i}_price"))

                oe1, oe2 = st.columns(2)
                opt_exit_dt    = oe1.date_input("Exit Date (all legs)", value=None)
                opt_exit_price = oe2.number_input("Exit Price", min_value=0.0, step=0.01, format="%.2f", value=None)
                sel_tag_names  = st.multiselect("Tags", options=list(tag_name_to_id.keys()), key="add_opt_tags")
                notes = st.text_area("Notes", height=68,
                                     placeholder="Trade thesis, setup, how it played out…")
                with st.expander("Advanced", expanded=False):
                    oa1, oa2, oa3 = st.columns(3)
                    opt_account      = oa1.selectbox("Account", options=all_accounts, key="add_opt_acct")
                    opt_commission   = oa2.number_input("Commission ($)", min_value=0.0, step=0.01,
                                                        format="%.2f", value=_options_commission, key="add_opt_comm",
                                                        help="Per-contract rate from Settings. Override as needed.")
                    opt_underlying_px = oa3.number_input("Underlying Price at Entry",
                                                         min_value=0.0, step=0.01, format="%.2f", value=None,
                                                         help="Price of the underlying stock/ETF at the time of entry.")
                uploaded_files = []

            # ── FUTURE ──────────────────────────────────────────────────────
            else:
                s_ticker = _at_ticker
                fc1, fc2, fc3 = st.columns(3)
                fut_mult     = fc1.number_input("Multiplier *", value=50.0, step=1.0, format="%.0f",
                                               help="Contract multiplier (ES=50, NQ=20, CL=1000…)")
                quantity     = fc2.number_input("Contracts *", min_value=0.0, step=1.0, format="%.0f", value=None)
                entry_price  = fc3.number_input("Entry Price *", min_value=0.0, step=0.01, format="%.2f", value=None)
                fe1, fe2     = st.columns(2)
                entry_date   = fe1.date_input("Entry Date *")
                exit_date    = fe2.date_input("Exit Date", value=None)
                exit_price   = st.number_input("Exit Price", min_value=0.0, step=0.01, format="%.2f", value=None)
                sel_tag_names = st.multiselect("Tags", options=list(tag_name_to_id.keys()), key="add_fut_tags")
                notes = st.text_area("Notes", height=68,
                                     placeholder="Trade thesis, setup, how it played out…")
                with st.expander("Advanced", expanded=False):
                    fa1, fa2 = st.columns(2)
                    fut_account    = fa1.selectbox("Account", options=all_accounts, key="add_fut_acct")
                    fut_commission = fa2.number_input("Commission ($)", min_value=0.0, step=0.01,
                                                      format="%.2f", value=_futures_commission, key="add_fut_comm",
                                                      help="Per-contract rate from Settings. Override as needed.")
                uploaded_files = []

            st.caption("\\* Required  ·  Ctrl+Enter to submit")
            if st.form_submit_button("Add Trade", width='stretch', type="primary"):

                if inst == "Stock":
                    missing = []
                    if not s_ticker.strip():  missing.append("Ticker")
                    if not quantity:          missing.append("Quantity")
                    if not entry_price:       missing.append("Entry Price")
                    if missing:
                        st.error(f"Please fill in: {', '.join(missing)}")
                    else:
                        try:
                            t       = s_ticker.upper().strip()
                            sel_ids = [tag_name_to_id[n] for n in sel_tag_names]
                            _cur_nat    = settings.get("native_currency", "USD")
                            _cur_mode   = settings.get("currency_mode", "0") == "1"
                            _fx_entry   = get_fx_rate_at_date(_cur_nat, str(entry_date)) if _cur_mode and _cur_nat != "USD" else 1.0
                            _fx_exit    = get_fx_rate_at_date(_cur_nat, str(exit_date))  if _cur_mode and _cur_nat != "USD" and exit_date else 1.0
                            new_id  = add_trade(
                                entry_date, t,
                                float(quantity), float(entry_price),
                                exit_date,
                                float(exit_price) if exit_price else None,
                                notes or None,
                                stop_enabled,
                                float(opening_stop) if opening_stop else None,
                                sel_ids,
                                instrument_type="stock",
                                commission=float(stock_commission) if stock_commission else 0.0,
                                account_name=stock_account,
                                native_currency=_cur_nat,
                                fx_rate_entry=_fx_entry,
                                fx_rate_exit=_fx_exit,
                                trail_type=_add_trail_type,
                                trail_amount=float(_add_trail_amount) if _add_trail_amount else None,
                                exchange=stock_exchange or "",
                            )
                            for f in (uploaded_files or []):
                                save_attachment(new_id, f)
                            st.session_state["_trade_added"] = {
                                "title": f"{t} added to your log.",
                                "lines": [
                                    f"- **Quantity:** {fmt_qty(quantity)}",
                                    f"- **Entry:** {fmt_price(entry_price)} on {fmt_date(entry_date, euro_dates)}",
                                ],
                            }
                            st.rerun()
                        except Exception as _err:
                            st.error(f"Failed to save trade: {_err}")

                elif inst == "Option":
                    if not s_ticker.strip():
                        st.error("Underlying ticker is required.")
                    else:
                        try:
                            t            = s_ticker.upper().strip()
                            sel_ids      = [tag_name_to_id[n] for n in sel_tag_names]
                            leg_group_id = str(uuid.uuid4())[:8] if n_legs > 1 else None
                            added        = 0
                            for i in range(n_legs):
                                qty    = leg_qtys[i]
                                strike = leg_strikes[i]
                                price  = leg_prices[i]
                                if not qty or not strike or not price:
                                    continue
                                side     = "short" if leg_sides[i] == "Short" else "long"
                                opt_char = "C" if leg_types[i] == "Call" else "P"
                                leg_lbl  = f"{'Short' if side=='short' else 'Long'} {leg_types[i]} ${strike:.2f}"
                                add_trade(
                                    entry_date     = opt_entry_dt,
                                    ticker         = t,
                                    quantity       = float(qty),
                                    entry_price    = float(price),
                                    exit_date      = opt_exit_dt,
                                    exit_price     = float(opt_exit_price) if opt_exit_price else None,
                                    notes          = notes or None,
                                    stop_enabled   = False,
                                    opening_stop   = None,
                                    tag_ids        = sel_ids,
                                    instrument_type= "option",
                                    expiration     = leg_exps[i],
                                    strike         = float(strike),
                                    option_type    = opt_char,
                                    multiplier     = float(opt_mult),
                                    leg_group      = leg_group_id,
                                    leg_label      = leg_lbl,
                                    side           = side,
                                    spread_type    = (opt_spread_type if opt_spread_type and opt_spread_type != "—" else None),
                                    commission     = float(opt_commission) if opt_commission else 0.0,
                                    underlying_price_at_entry = float(opt_underlying_px) if opt_underlying_px else None,
                                    account_name   = opt_account,
                                )
                                added += 1
                            if added:
                                st.session_state["_trade_added"] = {
                                    "title": f"{t} option added to your log.",
                                    "lines": [
                                        f"- **Legs:** {added}",
                                        f"- **Entry date:** {fmt_date(opt_entry_dt, euro_dates)}",
                                    ],
                                }
                                st.rerun()
                            else:
                                st.error("No valid legs to save — check required fields.")
                        except Exception as _err:
                            st.error(f"Failed to save option trade: {_err}")

                else:  # Future
                    missing = []
                    if not s_ticker.strip(): missing.append("Symbol")
                    if not quantity:         missing.append("Contracts")
                    if not entry_price:      missing.append("Entry Price")
                    if missing:
                        st.error(f"Please fill in: {', '.join(missing)}")
                    else:
                        try:
                            t       = s_ticker.upper().strip()
                            sel_ids = [tag_name_to_id[n] for n in sel_tag_names]
                            add_trade(
                                entry_date, t,
                                float(quantity), float(entry_price),
                                exit_date,
                                float(exit_price) if exit_price else None,
                                notes or None,
                                False, None, sel_ids,
                                instrument_type="future",
                                multiplier=float(fut_mult),
                                commission=float(fut_commission) if fut_commission else 0.0,
                                account_name=fut_account,
                            )
                            st.session_state["_trade_added"] = {
                                "title": f"{t} futures trade added to your log.",
                                "lines": [
                                    f"- **Contracts:** {fmt_qty(quantity)}",
                                    f"- **Entry:** {fmt_price(entry_price)} on {fmt_date(entry_date, euro_dates)}",
                                ],
                            }
                            st.rerun()
                        except Exception as _err:
                            st.error(f"Failed to save futures trade: {_err}")

    # ── CSV Import ────────────────────────────────────────────────────────────

    with st.expander("📁  Import from CSV"):
        st.markdown(
            "Expected headers: `Entry Date`, `Ticker`, `Q`, `Entry Price`, `Tags`, "
            "`Initial Stop Loss`, `Current Stop`, `Exit Date`, `Exit Price`"
        )
        csv_file = st.file_uploader("Upload CSV", type=["csv"], key="csv_upload")
        if csv_file:
            try:
                csv_df = pd.read_csv(csv_file)
                st.dataframe(csv_df.head(5), width='stretch', hide_index=True)
                st.caption(f"{len(csv_df)} rows detected")
                if st.button("Import Trades", type="primary"):
                    n_ok, errs = import_trades_from_csv(csv_df)
                    if n_ok:
                        st.success(f"Imported {n_ok} trade(s).")
                    if errs:
                        st.warning("Some rows had issues:")
                        for e in errs:
                            st.caption(e)
                    if n_ok:
                        st.rerun()
            except Exception as e:
                st.error(f"Could not read CSV: {e}")

    # ── Multiple Buy / Sell ───────────────────────────────────────────────────

    trades_for_multi  = _cached_load_trades(st.session_state["_v_trades"])
    open_trades_multi = trades_for_multi[trades_for_multi.apply(_is_open, axis=1)]

    with st.expander("🔄  Multiple Buy / Sell"):
        if open_trades_multi.empty:
            st.info("No open trades available.")
        else:
            def _multi_label(row):
                return (f"{row['ticker']}  ·  {fmt_date(row['entry_date'], euro_dates)}"
                        f"  ·  {fmt_qty(row['quantity'])} @ {fmt_price(row['entry_price'])}"
                        f"  (ID {row['id']})")

            ml_left, ml_right = st.columns(2)

            with ml_left:
                st.markdown("##### ➕  Add to Position")
                ap_options = open_trades_multi.apply(_multi_label, axis=1).tolist()
                ap_label   = st.selectbox("Trade", options=ap_options, key="ap_select")
                ap_idx     = ap_options.index(ap_label)
                ap_row     = open_trades_multi.iloc[ap_idx]
                ap_id      = int(ap_row["id"])
                _ap_ticker = str(ap_row.get("ticker") or "").strip().upper()
                if _ap_ticker:
                    _ap_live = _get_single_live_price(_ap_ticker)
                    if _ap_live is not None:
                        st.markdown(
                            f"<div style='margin-bottom:6px'><b>{_ap_ticker}</b> &nbsp;"
                            f"<span style='color:#2ecc71;font-weight:700'>${_ap_live:,.2f}</span></div>",
                            unsafe_allow_html=True,
                        )
                ap_qty     = st.number_input("Shares/Contracts to Add", min_value=0.01, step=1.0,
                                             format="%.4f", value=None, key="ap_qty",
                                             placeholder="e.g. 100")
                ap_price   = st.number_input("Purchase Price", min_value=0.0001, step=0.01,
                                             format="%.4f", value=None, key="ap_price",
                                             placeholder="e.g. 150.00")
                ap_date    = st.date_input("Add Date", value=pd.Timestamp.today().date(), key="ap_date")
                if st.button("Add to Position", key="ap_submit", type="primary"):
                    if ap_qty is None or ap_price is None:
                        st.error("Shares/contracts and price are required.")
                    elif ap_qty <= 0 or ap_price <= 0:
                        st.error("Quantity and price must be greater than zero.")
                    else:
                        new_qty, new_avg = update_position(ap_id, float(ap_qty), float(ap_price),
                                                           add_date=str(ap_date))
                        _bust("_v_trades")
                        st.success(f"Updated: {fmt_qty(new_qty)} total @ {fmt_price(new_avg)} avg cost")
                        st.rerun()

                # ── Tax Lot View ───────────────────────────────────────────
                ap_lots = load_trade_lots(ap_id)
                if ap_lots:
                    st.markdown("**Tax Lots**")
                    _lot_df = pd.DataFrame(ap_lots)[["date", "quantity", "price", "lot_type", "notes"]]
                    _lot_df.columns = ["Date", "Qty", "Price", "Type", "Notes"]
                    _lot_df["Price"] = _lot_df["Price"].apply(fmt_price)
                    st.dataframe(_lot_df, width='stretch', hide_index=True, height=160)
                    with st.expander("🗑️ Delete a lot"):
                        _lot_opts = {
                            f"{l['date']}  {fmt_qty(l['quantity'])} @ {fmt_price(l['price'])} ({l['lot_type']})": l["id"]
                            for l in ap_lots
                        }
                        _del_lot = st.selectbox("Select lot", options=list(_lot_opts.keys()),
                                                index=None, placeholder="Choose…", key="ap_del_lot")
                        if _del_lot and st.button("Delete lot", key="ap_del_lot_btn", type="secondary"):
                            delete_trade_lot(_lot_opts[_del_lot])
                            st.rerun()

            with ml_right:
                st.markdown("##### 📤  Exit in Pieces")
                ep_label = st.selectbox("Trade", options=open_trades_multi.apply(_multi_label, axis=1).tolist(), key="ep_select")
                ep_idx   = open_trades_multi.apply(_multi_label, axis=1).tolist().index(ep_label)
                ep_row   = open_trades_multi.iloc[ep_idx]
                ep_id    = int(ep_row["id"])
                ep_max   = float(ep_row["quantity"] or 0)
                _ep_ticker = str(ep_row.get("ticker") or "").strip().upper()
                if _ep_ticker:
                    _ep_live = _get_single_live_price(_ep_ticker)
                    if _ep_live is not None:
                        st.markdown(
                            f"<div style='margin-bottom:6px'><b>{_ep_ticker}</b> &nbsp;"
                            f"<span style='color:#2ecc71;font-weight:700'>${_ep_live:,.2f}</span></div>",
                            unsafe_allow_html=True,
                        )
                ep_qty   = st.number_input(f"Shares to Exit (max {fmt_qty(ep_max)})", min_value=0.0, max_value=ep_max, step=1.0, format="%.0f", value=None, key="ep_qty")
                ep_price = st.number_input("Exit Price", min_value=0.0, step=0.01, format="%.2f", value=None, key="ep_price")
                ep_date  = st.date_input("Exit Date", key="ep_date")
                if st.button("Record Exit", key="ep_submit"):
                    if not ep_qty or not ep_price:
                        st.error("Shares and exit price are required.")
                    elif ep_qty > ep_max:
                        st.error(f"Cannot exit more than {fmt_qty(ep_max)} shares.")
                    else:
                        partial_exit_trade(ep_id, ep_qty, ep_price, ep_date)
                        st.success(f"Recorded exit of {fmt_qty(ep_qty)} @ {fmt_price(ep_price)}")
                        st.rerun()

    # ── Dividend Adjustment ───────────────────────────────────────────────────

    all_trades_for_div = _cached_load_trades(st.session_state["_v_trades"])
    open_div_trades    = all_trades_for_div[all_trades_for_div.apply(_is_open, axis=1)]

    with st.expander("💵  Dividend Adjustment"):
        st.caption(
            "Record dividends received on open positions. "
            "Each dividend is nested under its parent trade and reduces your effective cost basis."
        )
        if open_div_trades.empty:
            st.info("No open trades to attach dividends to.")
        else:
            def _div_trade_label(row):
                return (f"{row['ticker']}  ·  {fmt_date(row['entry_date'], euro_dates)}"
                        f"  ·  {fmt_qty(row['quantity'])} shares  (ID {row['id']})")

            # Search + select above the two-column layout so both sides share the same trade
            dv_opts    = open_div_trades.apply(_div_trade_label, axis=1).tolist()
            dv_search  = st.text_input("🔍 Search trade (ticker, date, or ID)",
                                        key="dv_search", placeholder="Type to filter…")
            dv_f_opts  = [o for o in dv_opts if dv_search.lower() in o.lower()] if dv_search else dv_opts
            dv_label   = st.selectbox("Select trade", options=dv_f_opts,
                                       key="dv_trade_sel", index=0 if dv_f_opts else None)

            if dv_label:
                dv_idx = dv_opts.index(dv_label)
                dv_row = open_div_trades.iloc[dv_idx]
                dv_id  = int(dv_row["id"])

                dv1, dv2 = st.columns(2)
                with dv1:
                    st.markdown("##### Record Dividend")
                    dv_date  = st.date_input("Ex-Dividend Date", value=pd.Timestamp.today().date(), key="dv_date")
                    dv_aps   = st.number_input("Amount per Share ($)", min_value=0.0, step=0.01,
                                               format="%.4f", value=None, key="dv_aps",
                                               placeholder="e.g. 0.25")
                    dv_qty   = st.number_input("Shares Held", min_value=0.0, step=1.0,
                                               format="%.4f", value=float(dv_row.get("quantity") or 0) or None,
                                               key="dv_qty",
                                               help="Pre-filled from the trade; edit if you held a different quantity on the ex-date.")
                    dv_notes = st.text_input("Notes", placeholder="optional", key="dv_notes")
                    if st.button("Record Dividend", key="dv_submit", type="primary"):
                        if dv_aps is None or dv_aps <= 0:
                            st.error("Amount per share is required and must be > 0.")
                        else:
                            add_trade_dividend(dv_id, str(dv_date), float(dv_aps),
                                               float(dv_qty) if dv_qty else None,
                                               notes=dv_notes or "")
                            st.success(f"Dividend recorded: {fmt_price(dv_aps)} / share"
                                       + (f" · {fmt_price(dv_aps * dv_qty)} total" if dv_qty else ""))
                            st.rerun()

                with dv2:
                    st.markdown("##### Dividend History")
                    # History automatically mirrors whichever trade is selected on the left
                    _divs = load_trade_dividends(dv_id)
                    if not _divs:
                        st.info("No dividends recorded for this trade yet.")
                    else:
                        _dv_df = pd.DataFrame(_divs)[["ex_date", "amount_per_share", "quantity",
                                                       "total_amount", "notes"]]
                        _dv_df.columns = ["Ex-Date", "$/Share", "Qty", "Total", "Notes"]
                        _dv_df["$/Share"] = _dv_df["$/Share"].apply(lambda v: fmt_price(v) if v else "—")
                        _dv_df["Total"]   = _dv_df["Total"].apply(lambda v: fmt_price(v) if v else "—")
                        st.dataframe(_dv_df, width='stretch', hide_index=True)
                        _dv_total = sum(d.get("total_amount") or 0 for d in _divs)
                        st.metric("Total Dividends Received", fmt_price(_dv_total))
                        with st.expander("🗑️ Delete a dividend"):
                            _dv_del_opts = {
                                f"{d['ex_date']} — {fmt_price(d.get('total_amount') or d['amount_per_share'])}": d["id"]
                                for d in _divs
                            }
                            _dv_del_sel = st.selectbox("Select", options=list(_dv_del_opts.keys()),
                                                        index=None, placeholder="Choose…", key="dv_del_sel")
                            if _dv_del_sel and st.button("Delete", key="dv_del_btn", type="secondary"):
                                delete_trade_dividend(_dv_del_opts[_dv_del_sel])
                                st.rerun()

    # ── Options Rolling ───────────────────────────────────────────────────────

    _all_option_trades = _cached_load_trades(st.session_state["_v_trades"])
    _option_trades     = _all_option_trades[_all_option_trades["instrument_type"] == "option"]
    if not _option_trades.empty:
        with st.expander("🔁  Roll Option Position"):
            st.caption(
                "Link trades into a roll chain. A roll is when you close an expiring option and open "
                "a new one — grouping them lets you track total aggregated P&L across all legs of the roll."
            )
            roll_col1, roll_col2 = st.columns(2)

            with roll_col1:
                st.markdown("##### Create / Extend Roll Group")
                _opt_labels = _option_trades.apply(
                    lambda r: f"{r['ticker']} {r.get('option_type','?')} ${r.get('strike','?')} "
                              f"exp {fmt_date(r.get('expiration'), euro_dates)} (ID {r['id']})",
                    axis=1,
                ).tolist()
                _roll_search   = st.text_input("🔍 Search legs (ticker, strike, ID)",
                                                key="roll_search", placeholder="Type to filter…")
                _roll_f_labels = [o for o in _opt_labels if _roll_search.lower() in o.lower()] \
                                 if _roll_search else _opt_labels
                _roll_sel = st.multiselect("Select option legs to group as a roll",
                                           options=_roll_f_labels, key="roll_sel")
                _roll_name = st.text_input("Roll group name (leave blank to auto-generate)",
                                           key="roll_name_input")
                if st.button("🔗  Group as Roll", key="roll_group_btn"):
                    if len(_roll_sel) < 2:
                        st.error("Select at least 2 legs to create a roll group.")
                    else:
                        _rg_name = (_roll_name.strip() or str(uuid.uuid4())[:8])
                        _sel_ids_roll = []
                        for _lbl in _roll_sel:
                            _ri = _opt_labels.index(_lbl)
                            _sel_ids_roll.append(int(_option_trades.iloc[_ri]["id"]))
                        with get_connection() as _conn:
                            for _rid in _sel_ids_roll:
                                _conn.execute("UPDATE trades SET roll_group=? WHERE id=?",
                                              (_rg_name, _rid))
                        _cached_load_trades.clear()
                        _bust("_v_trades")
                        st.success(f"Roll group '{_rg_name}' created with {len(_sel_ids_roll)} legs.")
                        st.rerun()

            with roll_col2:
                st.markdown("##### Existing Roll Groups")
                _rolled = _option_trades[_option_trades["roll_group"].notna()]
                if _rolled.empty:
                    st.caption("No roll groups yet.")
                else:
                    for _rg in _rolled["roll_group"].dropna().unique():
                        _rg_legs = _rolled[_rolled["roll_group"] == _rg]
                        _rg_pnl  = _rg_legs.apply(
                            lambda r: _pnl_numeric(r, {}), axis=1
                        ).dropna().sum()
                        st.markdown(
                            f"**{_rg}** — {len(_rg_legs)} legs · "
                            f"Net P&L: {fmt_pnl(_rg_pnl) if _rg_pnl else '—'}"
                        )
                        if st.button(f"Ungroup '{_rg}'", key=f"unroll_{_rg}"):
                            with get_connection() as _conn:
                                _conn.execute(
                                    "UPDATE trades SET roll_group=NULL WHERE roll_group=?", (_rg,)
                                )
                            _cached_load_trades.clear()
                            _bust("_v_trades")
                            st.rerun()

    # ── Trade Table ───────────────────────────────────────────────────────────

    trades = _cached_load_trades(st.session_state["_v_trades"])

    def trade_label(row):
        inst = str(row.get("instrument_type") or "stock").capitalize()
        return f"{row['ticker']}  ·  {fmt_date(row['entry_date'], euro_dates)}  ·  {inst}  (ID {row['id']})"

    if trades.empty:
        st.info("No trades yet. Use the form above to add your first trade.")
    else:

        # ── Filter bar ────────────────────────────────────────────────────────

        fr1c1, fr1c2, fr1c3 = st.columns(3)
        ticker_filter = fr1c1.multiselect("Ticker",
                            options=sorted(trades["ticker"].dropna().unique()),
                            placeholder="All tickers", key="filter_ticker")
        status_filter = fr1c2.selectbox("Status",        ["All", "Open", "Closed"], key="filter_status")
        pnl_filter    = fr1c3.selectbox("Winners/Losers", ["All", "Profit (+)", "Loss (-)"], key="filter_pnl")

        fr2c1, fr2c2, fr2c3, fr2c4 = st.columns([1, 1, 1, 0.45])
        tag_filter   = fr2c1.multiselect("Tags (any match)",
                            options=sorted(tag_name_to_id.keys()), placeholder="All tags", key="filter_tags")
        date_col_sel = fr2c2.selectbox("Filter date", ["Entry Date", "Exit Date"], key="filter_date_col")
        date_range   = fr2c3.date_input("Date range", key="filter_date_range")
        fr2c4.markdown("<div style='margin-top:1.6rem'></div>", unsafe_allow_html=True)
        if fr2c4.button("↺ Reset", key="reset_filters", help="Reset all filters to defaults",
                        width='stretch'):
            for _fk, _fv in _FILTER_DEFAULTS.items():
                st.session_state[_fk] = _fv
            st.rerun()

        # ── Apply filters ─────────────────────────────────────────────────────

        filtered = trades.copy()
        if ticker_filter:
            filtered = filtered[filtered["ticker"].isin(ticker_filter)]

        # Compute open/closed mask once; reused throughout display building below
        def _make_is_open_mask(df: pd.DataFrame) -> pd.Series:
            return df["exit_date"].isna()

        if status_filter == "Open":
            _m = _make_is_open_mask(filtered)
            filtered = filtered[_m]
        elif status_filter == "Closed":
            _m = _make_is_open_mask(filtered)
            filtered = filtered[~_m]
        if tag_filter:
            def _has_any_tag(tags_str):
                if not tags_str or pd.isna(tags_str): return False
                return any(t.strip() in tag_filter for t in tags_str.split(","))
            _tag_direct = filtered["tags"].apply(_has_any_tag)
            if "leg_group" in filtered.columns:
                _tag_groups = filtered.loc[
                    _tag_direct & filtered["leg_group"].notna() & (filtered["leg_group"].astype(str) != ""),
                    "leg_group",
                ].unique()
                filtered = filtered[_tag_direct | filtered["leg_group"].isin(_tag_groups)]
            else:
                filtered = filtered[_tag_direct]
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
            col_key    = "entry_date" if date_col_sel == "Entry Date" else "exit_date"
            dcol       = pd.to_datetime(filtered[col_key], errors="coerce")
            filtered   = filtered[(dcol >= start) & (dcol <= end)]

        # Compute mask on the final filtered set (after all row-level filters)
        is_open_mask    = _make_is_open_mask(filtered)

        def _live_eligible_mask(df: pd.DataFrame) -> "pd.Series":
            """True for rows where a live price fetch makes sense.
            Skips options/futures whose expiration is today or in the past — those
            contracts are expired and neither IB nor Yahoo will return a quote."""
            _open = _make_is_open_mask(df)
            if "expiration" not in df.columns:
                return _open
            _exp = pd.to_datetime(df["expiration"], errors="coerce")
            _has_exp = _exp.notna()
            _expired = _has_exp & (_exp.dt.normalize() < pd.Timestamp.today().normalize())
            return _open & ~_expired

        # Build live tickers for display (filtered view)
        live_ticker_ser  = filtered.apply(_get_live_ticker, axis=1)
        _eligible_mask   = _live_eligible_mask(filtered)
        # Fetch prices for ALL open positions (not just the filtered subset) so
        # the cache is complete regardless of which filters are currently active.
        _all_live_ser    = trades.apply(_get_live_ticker, axis=1)
        _all_elig_mask   = _live_eligible_mask(trades)
        live_symbols     = tuple(_all_live_ser[_all_elig_mask].dropna().unique())

        _n_live = len(live_symbols)
        if _n_live > 0 and st.session_state.get("_live_prices_loaded"):
            _est_s = max(2, _n_live // 6)
            _load_msg = (
                f"Fetching live prices for {_n_live} open position(s)…"
                + (f"  ·  large portfolios may take ~{_est_s}–{_est_s * 2}s on first load"
                   if _n_live > 15 else "")
            )
            with st.spinner(_load_msg):
                live_data = get_live_data(live_symbols)
                # Compute option greeks once, here, from the freshly-loaded prices —
                # NOT on every rerun (avoids repeated network round-trips and any
                # per-contract IB market-data blocking).
                try:
                    _open_for_greeks = trades[_make_is_open_mask(trades)]
                    st.session_state["_greeks_cache"] = compute_position_greeks(
                        _open_for_greeks, live_data
                    )
                except Exception:
                    st.session_state["_greeks_cache"] = {}
            # Persist so prices survive navigation away and back
            st.session_state["_live_data_cache"] = live_data
            # Clear flag so subsequent reruns (column changes, etc.) don't re-fetch
            st.session_state["_live_prices_loaded"] = False
        else:
            live_data = st.session_state.get("_live_data_cache", {})

        if pnl_filter != "All":
            pnl_vals = filtered.apply(lambda r: _pnl_numeric(r, live_data), axis=1)
            if pnl_filter == "Profit (+)":
                filtered = filtered[pnl_vals[filtered.index] > 0]
                is_open_mask    = _make_is_open_mask(filtered)
                live_ticker_ser = filtered.apply(_get_live_ticker, axis=1)
            elif pnl_filter == "Loss (-)":
                filtered = filtered[pnl_vals[filtered.index] < 0]
                is_open_mask    = _make_is_open_mask(filtered)
                live_ticker_ser = filtered.apply(_get_live_ticker, axis=1)

        # ── View toggle (Positions / Trades) + expand legs ────────────────────

        # Persist the view toggles across reruns. Sidebar actions like "Refresh
        # live prices" call st.rerun() before these widgets are instantiated, so
        # Streamlit drops their widget-keyed state — which made "Group by ticker"
        # snap back to off on a refetch. We mirror each toggle into a plain
        # (non-widget) key and restore it only when the widget key was dropped, so a
        # normal toggle click is never clobbered but an aborted rerun no longer
        # loses the choice. (Passing value= alongside key= is also avoided — it
        # triggers Streamlit's "value set via Session State API" warning.)
        for _tk in ("_positions_view", "_expand_legs"):
            _pk = _tk + "_persist"
            if _pk not in st.session_state:
                st.session_state[_pk] = False
            if _tk not in st.session_state:
                st.session_state[_tk] = st.session_state[_pk]

        _grp_col1, _grp_col2, _grp_col3 = st.columns([2, 2, 4])
        _positions_view = _grp_col1.toggle(
            "Group by ticker",
            key="_positions_view",
            help=(
                "**On** — aggregates all open trades for the same ticker into one row "
                "showing total quantity, weighted-average cost, and consolidated P&L. "
                "Click any row to drill down into individual tax lots and dividends.\n\n"
                "**Off** (default) — shows every trade entry as its own row."
            ),
        )
        _expand_legs = _grp_col2.toggle(
            "Expand individual legs",
            key="_expand_legs",
            help="When off, spread/roll legs are collapsed into one aggregated row per group. Toggle on to see all legs.",
        )
        # Mirror the live values back into the persist keys for the next rerun.
        st.session_state["_positions_view_persist"] = _positions_view
        st.session_state["_expand_legs_persist"]    = _expand_legs

        # ── Column selector ────────────────────────────────────────────────────

        import json as _json
        _raw_presets = get_setting("col_presets", "{}")
        try:
            _custom_presets: dict = _json.loads(_raw_presets)
        except Exception:
            _custom_presets = {}

        # Seed the visible-columns selection once per session so the multiselect is
        # driven purely by session_state (no `default=` param). Passing both a
        # default and a key that's already in session_state triggers Streamlit's
        # "value set via Session State API" warning and can drop the user's custom
        # column view on rerun (e.g. after the Refresh Live Prices button).
        if "visible_cols" not in st.session_state:
            _saved_vc = get_setting("col_order")
            _vc0 = _json.loads(_saved_vc) if _saved_vc else list(DEFAULT_COLS)
            _vc0 = [c for c in _vc0 if c in ALL_COLS] or list(DEFAULT_COLS)
            # One-time: surface the Spread Type column for layouts saved before it
            # existed. Guarded by a flag so a later manual removal stays removed.
            if get_setting("_spread_type_col_seeded", "") != "1":
                if "Spread Type" not in _vc0:
                    _ins = (_vc0.index("Quantity") + 1) if "Quantity" in _vc0 else len(_vc0)
                    _vc0.insert(_ins, "Spread Type")
                set_setting("col_order", _json.dumps(_vc0))
                set_setting("_spread_type_col_seeded", "1")
            st.session_state["visible_cols"] = _vc0

        # Apply a deferred column removal here — BEFORE the multiselect widget is
        # instantiated (Streamlit forbids mutating a widget's state afterwards).
        _rm_pending = st.session_state.pop("_col_remove_pending", None)
        if _rm_pending:
            st.session_state["visible_cols"] = [
                c for c in st.session_state.get("visible_cols", []) if c != _rm_pending
            ]
            if "col_order" in st.session_state:
                st.session_state["col_order"] = [
                    c for c in st.session_state["col_order"] if c != _rm_pending
                ]

        col_pop, _ = st.columns([1, 5])
        with col_pop:
            with st.popover("⚙️  Columns"):
                # ── Built-in presets ───────────────────────────────────────
                _pr1, _pr2, _pr3 = st.columns(3)
                if _pr1.button("Stock", key="preset_stock", width='stretch'):
                    st.session_state["visible_cols"] = PRESET_STOCK
                    st.session_state["col_order"]    = list(PRESET_STOCK)
                    st.rerun()
                if _pr2.button("Options", key="preset_options", width='stretch'):
                    st.session_state["visible_cols"] = PRESET_OPTIONS
                    st.session_state["col_order"]    = list(PRESET_OPTIONS)
                    st.rerun()
                if _pr3.button("Default", key="preset_default", width='stretch'):
                    st.session_state["visible_cols"] = DEFAULT_COLS
                    st.session_state["col_order"]    = list(DEFAULT_COLS)
                    st.rerun()

                # ── Saved custom presets ───────────────────────────────────
                if _custom_presets:
                    st.caption("Saved presets — click to apply · 💾 update · ✕ delete")
                    for _pname, _pcols in list(_custom_presets.items()):
                        _pb_col, _pu_col, _pd_col = st.columns([5, 1, 1])
                        if _pb_col.button(_pname, key=f"preset_custom_{_pname}", width='stretch'):
                            st.session_state["visible_cols"] = list(_pcols)
                            st.session_state["col_order"]    = list(_pcols)
                            st.rerun()
                        if _pu_col.button("💾", key=f"preset_upd_{_pname}", width='stretch',
                                          help=f"Overwrite “{_pname}” with the current columns & order"):
                            _co_now = st.session_state.get(
                                "col_order", st.session_state.get("visible_cols", DEFAULT_COLS))
                            _custom_presets[_pname] = list(_co_now)
                            set_setting("col_presets", _json.dumps(_custom_presets))
                            st.toast(f"Updated preset “{_pname}”.", icon="💾")
                            st.rerun()
                        if _pd_col.button("✕", key=f"preset_del_{_pname}", width='stretch',
                                          help=f"Delete “{_pname}”"):
                            del _custom_presets[_pname]
                            set_setting("col_presets", _json.dumps(_custom_presets))
                            st.rerun()

                # ── Column multiselect ─────────────────────────────────────
                visible_cols = st.multiselect("Visible columns", options=ALL_COLS,
                                              key="visible_cols")

                # ── Save current selection as new preset ───────────────────
                st.caption("Save current selection as preset")
                _sv1, _sv2 = st.columns([3, 1])
                _new_preset_name = _sv1.text_input("Preset name", label_visibility="collapsed",
                                                   placeholder="Preset name…", key="new_preset_name")
                if _sv2.button("Save", key="btn_save_preset", width='stretch'):
                    if _new_preset_name.strip():
                        # Save using current col_order so the preset preserves order
                        _co_now = st.session_state.get("col_order", st.session_state.get("visible_cols", DEFAULT_COLS))
                        _custom_presets[_new_preset_name.strip()] = list(_co_now)
                        set_setting("col_presets", _json.dumps(_custom_presets))
                        st.rerun()

                # ── Make the current view the startup default ──────────────
                st.divider()
                if st.button("📌  Set current view as my default", key="set_cols_default",
                             width='stretch',
                             help="Use these columns & order as the startup view every session"):
                    _co_now = st.session_state.get(
                        "col_order", st.session_state.get("visible_cols", DEFAULT_COLS))
                    set_setting("col_order", _json.dumps(list(_co_now)))
                    st.toast("Saved as your default startup view.", icon="📌")
                    st.rerun()

        # ── Column order tracking ──────────────────────────────────────────────
        # Multiselect always returns values in ALL_COLS order, so track insertion
        # order separately: newly-added columns append to the end.
        if "col_order" not in st.session_state:
            _saved_co = get_setting("col_order")
            st.session_state["col_order"] = (
                _json.loads(_saved_co)
                if _saved_co else list(st.session_state.get("visible_cols", DEFAULT_COLS))
            )
        _cur_vis_set  = set(st.session_state.get("visible_cols", DEFAULT_COLS))
        _cur_vis_list = st.session_state.get("visible_cols", DEFAULT_COLS)
        _col_order    = st.session_state["col_order"]
        # Retain existing order; append any newly-selected columns at the end
        _col_order = [c for c in _col_order if c in _cur_vis_set] + \
                     [c for c in _cur_vis_list if c not in _col_order]
        st.session_state["col_order"] = _col_order

        # ── Column reorder / remove expander ────────────────────────────────────
        if len(_col_order) >= 1:
            with st.expander("↕  Column order & visibility", expanded=False):
                st.caption("↑ / ↓ to reorder · ✕ to remove a column.")
                for _ci, _cn in enumerate(_col_order):
                    _rca, _rcb, _rcc, _rcd = st.columns([6, 0.7, 0.7, 0.7])
                    _rca.write(_cn)
                    if _ci > 0 and _rcb.button("↑", key=f"_co_up_{_ci}", help="Move up"):
                        _col_order[_ci - 1], _col_order[_ci] = _col_order[_ci], _col_order[_ci - 1]
                        st.session_state["col_order"] = _col_order
                        st.rerun()
                    if _ci < len(_col_order) - 1 and _rcc.button("↓", key=f"_co_dn_{_ci}", help="Move down"):
                        _col_order[_ci], _col_order[_ci + 1] = _col_order[_ci + 1], _col_order[_ci]
                        st.session_state["col_order"] = _col_order
                        st.rerun()
                    if len(_col_order) > 1 and _rcd.button("✕", key=f"_co_rm_{_ci}",
                                                           help=f"Remove “{_cn}”"):
                        # Defer the mutation — visible_cols is a widget already
                        # instantiated above; apply it at the top of the next run.
                        st.session_state["_col_remove_pending"] = _cn
                        st.rerun()
                if st.button("📌  Save as default", key="save_col_order_default",
                             help="Use this columns & order as the startup view every session"):
                    set_setting("col_order", _json.dumps(_col_order))
                    st.toast("Saved as your default startup view.", icon="📌")

        vis = _col_order

        # ── Lazy metadata ──────────────────────────────────────────────────────

        needs_meta = any(c in vis for c in ["Sector", "Industry", "Beta", "Correlation", "Stop Dist ATR"])
        if needs_meta and not filtered.empty:
            # Only underlying tickers (not OCC symbols) for metadata
            meta_tickers = tuple(filtered["ticker"].dropna().unique())
            metadata = get_ticker_metadata(meta_tickers) if meta_tickers else {}
        else:
            metadata = {}

        # ── Option greeks (computed once at price-load, mapped from cache here) ──
        # Signed position greeks → spread groups aggregate by simple summation.
        if ("Delta" in vis or "Theta" in vis) and not filtered.empty and "id" in filtered.columns:
            _gc = st.session_state.get("_greeks_cache", {})
            if _gc:
                _idser = filtered["id"]
                filtered["_delta_pos"] = _idser.map(
                    lambda i: (_gc.get(int(i)) or {}).get("delta") if pd.notna(i) else None
                )
                filtered["_theta_pos"] = _idser.map(
                    lambda i: (_gc.get(int(i)) or {}).get("theta") if pd.notna(i) else None
                )

        # ── Build display DataFrame ────────────────────────────────────────────

        def _fmt_stop(row):
            if not row["stop_enabled"]:
                return "No Stop"
            val = row["current_stop"] if row["current_stop"] is not None else row["opening_stop"]
            return fmt_price(val) if val is not None else "—"

        # Sort spread legs together (same leg_group adjacent), then by entry date
        if "leg_group" in filtered.columns:
            _tmp = filtered.copy()
            _tmp["_grp_sort"] = _tmp["leg_group"].fillna("").astype(str)
            _strike_col = _tmp["strike"] if "strike" in _tmp.columns else pd.Series(0, index=_tmp.index)
            _tmp = _tmp.assign(_strike_sort=_strike_col.fillna(0))
            filtered = _tmp.sort_values(
                ["_grp_sort", "entry_date", "_strike_sort"], na_position="last"
            ).drop(columns=["_grp_sort", "_strike_sort"]).reset_index(drop=True)
            # reset_index changes the integer index — recompute positional masks
            is_open_mask    = _make_is_open_mask(filtered)
            live_ticker_ser = filtered.apply(_get_live_ticker, axis=1)

        display = filtered.copy()
        display["Status"] = np.where(is_open_mask, "Open", "Closed")
        display["Stop Loss"] = display.apply(_fmt_stop, axis=1)
        display["Instrument"] = display["instrument_type"].apply(
            lambda v: {"stock": "Stock", "option": "Option", "future": "Future"}.get(str(v or "stock").lower(), "Stock")
        )
        # Vectorised P&L: map live tickers → prices, then compute in one pass
        _live_prices_ser = live_ticker_ser.map(lambda t: live_data.get(t, {}).get("price") if t else None)
        _qty   = pd.to_numeric(filtered["quantity"],    errors="coerce")
        _ep    = pd.to_numeric(filtered["entry_price"], errors="coerce")
        _xp    = pd.to_numeric(filtered["exit_price"],  errors="coerce")
        _mult  = pd.to_numeric(filtered["multiplier"],  errors="coerce").fillna(1.0)
        _sign  = np.where(filtered["side"].fillna("long").str.lower() == "short", -1.0, 1.0)
        _price = np.where(is_open_mask, _live_prices_ser.to_numpy(dtype=object), _xp.to_numpy(dtype=object))
        _price_num = pd.to_numeric(pd.Series(_price, index=filtered.index), errors="coerce")
        _raw   = (_price_num - _ep) * _qty * _mult * pd.Series(_sign, index=filtered.index)
        _valid = _qty.notna() & _ep.notna() & _price_num.notna()
        # Include dividends in P&L. For open trades with a live price, add to price-based
        # P&L. For open trades with no price yet, show dividends alone so the cost-basis
        # reduction is always visible (rather than hidden behind "—").
        _div_ids = filtered["id"].tolist()
        if _div_ids:
            _div_map_pnl = load_dividends_for_trades(_div_ids)
            _div_by_id   = {tid: sum(d.get("total_amount") or 0 for d in divs)
                            for tid, divs in _div_map_pnl.items()}
            _div_series  = filtered["id"].map(_div_by_id).fillna(0.0)
        else:
            _div_series = pd.Series(0.0, index=filtered.index)
        display["_pnl_num"] = np.where(
            _valid.values,
            _raw.values + _div_series.values,
            np.where(_div_series.values > 0, _div_series.values, np.nan),
        )

        display = display.rename(columns={
            "id":           "Trade ID",
            "entry_date":   "Entry Date",
            "ticker":       "Ticker",
            "quantity":     "Quantity",
            "entry_price":  "Entry Price",
            "exit_date":    "Exit Date",
            "exit_price":   "Exit Price",
            "tags":         "Tags",
            "notes":        "Notes",
            "opening_stop": "Opening Stop",
            "current_stop": "Current Stop",
        })

        display["Trade ID"]       = display["Trade ID"].astype(str)
        display["Entry Date"]     = filtered["entry_date"].apply(lambda v: fmt_date(v, euro_dates))
        display["Exit Date"]      = filtered["exit_date"].apply(lambda v: fmt_date(v, euro_dates))
        # Adjust displayed entry price (cost basis) by total dividends received per share
        _adj_ep_vals = np.where(
            (_qty.values > 0) & (_div_series.values > 0),
            _ep.values - _div_series.values / _qty.values,
            _ep.values,
        )
        display["Entry Price"] = [fmt_price(v) if pd.notna(v) else "—" for v in _adj_ep_vals]
        display["Quantity"]       = filtered["quantity"].apply(fmt_qty)
        display["Exit Price"]     = np.where(is_open_mask, "", filtered["exit_price"].apply(fmt_price))
        display["Live Price"]     = np.where(
            is_open_mask,
            live_ticker_ser.map(lambda t: fmt_price(live_data.get(t, {}).get("price")) if t else "—"),
            "—",
        )
        display["P&L"]            = display["_pnl_num"].apply(fmt_pnl)

        # ── Native currency columns (only when currency mode is on) ────────────
        _fx_mode     = settings.get("currency_mode", "0") == "1"
        _fx_native   = settings.get("native_currency", "USD")
        if _fx_mode and _fx_native != "USD":
            _live_fx = get_fx_rate(_fx_native)
            _cur_sym = {"AUD": "A$", "CAD": "C$", "EUR": "€"}.get(_fx_native, _fx_native)

            def _native_pnl(row):
                pnl_usd = row.get("_pnl_num")
                if pnl_usd is None or pd.isna(pnl_usd):
                    return "—"
                fx = _live_fx if _is_open(row) else float(row.get("fx_rate_exit") or _live_fx or 1.0)
                if not fx or fx == 0:
                    return "—"
                val = pnl_usd / fx
                return f"{_cur_sym}{val:+,.2f}"

            def _native_entry(row):
                ep, qty = row.get("entry_price"), row.get("quantity")
                fx = float(row.get("fx_rate_entry") or 1.0)
                if not ep or not qty or not fx:
                    return "—"
                return f"{_cur_sym}{float(ep)*float(qty)/fx:,.2f}"

            def _native_exit(row):
                if _is_open(row):
                    return "—"
                xp, qty = row.get("exit_price"), row.get("quantity")
                fx = float(row.get("fx_rate_exit") or 1.0)
                if not xp or not qty or not fx:
                    return "—"
                return f"{_cur_sym}{float(xp)*float(qty)/fx:,.2f}"

            display["P&L (Native)"]    = filtered.apply(_native_pnl,   axis=1)
            display["Entry (Native)"]  = filtered.apply(_native_entry,  axis=1)
            display["Exit (Native)"]   = filtered.apply(_native_exit,   axis=1)
            display["FX Rate Entry"]   = filtered["fx_rate_entry"].apply(
                lambda v: f"{float(v):.4f}" if v and not pd.isna(v) else "—"
            )

        display["Position Value"] = filtered.apply(
            lambda r: fmt_price(r["quantity"] * r["entry_price"] * (r.get("multiplier") or 1.0))
                      if r["quantity"] and r["entry_price"] else "—", axis=1
        )
        display["Opening Stop"] = filtered["opening_stop"].apply(fmt_price)
        def _fmt_current_stop(row):
            cs  = row.get("current_stop")
            tt  = str(row.get("trail_type") or "fixed")
            ta  = row.get("trail_amount")
            lbl = fmt_price(cs) if cs is not None else "—"
            if tt != "fixed" and ta and not pd.isna(ta):
                lbl += f" ▲{ta}{tt}"
            return lbl
        if "trail_type" in filtered.columns:
            display["Current Stop"] = filtered.apply(_fmt_current_stop, axis=1)
        else:
            display["Current Stop"] = filtered["current_stop"].apply(fmt_price)

        # ── Optional columns ───────────────────────────────────────────────────

        if "Days in Trade" in vis:
            _entry_dt  = pd.to_datetime(filtered["entry_date"], errors="coerce")
            _exit_dt   = pd.to_datetime(filtered["exit_date"],  errors="coerce")
            _days_open = (today_ts - _entry_dt).dt.days.astype("Int64")
            _days_held = (_exit_dt - _entry_dt).dt.days.astype("Int64")
            display["Days in Trade"] = np.where(
                is_open_mask,
                _days_open.where(_days_open.notna(), other=pd.NA).astype(str).replace("<NA>", "—"),
                _days_held.where(_days_held.notna(), other=pd.NA).astype(str).replace("<NA>", "—"),
            )

        if "Entry Value" in vis:
            display["Entry Value"] = filtered.apply(
                lambda r: fmt_price(r["quantity"] * r["entry_price"] * (r.get("multiplier") or 1.0))
                          if r["quantity"] and r["entry_price"] else "—", axis=1
            )

        need_cur_val = any(c in vis for c in ["Current Value", "% of Account"])
        if need_cur_val:
            _cv_qty  = pd.to_numeric(filtered["quantity"], errors="coerce")
            _cv_live = _live_prices_ser  # already computed above
            _cv_xp   = pd.to_numeric(filtered["exit_price"], errors="coerce")
            _cv_px   = np.where(is_open_mask, _cv_live, _cv_xp)
            _cv_px_s = pd.to_numeric(pd.Series(_cv_px, index=filtered.index), errors="coerce")
            filtered["_cur_val"] = np.where(_cv_qty.notna() & _cv_px_s.notna(),
                                            _cv_qty * _cv_px_s * _mult, np.nan)

        if "Current Value" in vis:
            display["Current Value"] = filtered["_cur_val"].apply(fmt_price)

        if "% of Account" in vis:
            # Options: size by *max risk* (worst-case loss at expiration) as % of
            # account. Stocks/other: size by current market value.
            def _pct_of_account(r):
                if not (acct_bal > 0):
                    return "—"
                if row_is_option(r):
                    mr = option_legs_max_risk([{
                        "type": r.get("option_type"), "strike": r.get("strike"),
                        "side": r.get("side"),        "qty":    r.get("quantity"),
                        "mult": r.get("multiplier"),  "entry_price": r.get("entry_price"),
                    }])
                    if mr is None:
                        return "∞"          # unbounded (naked short call)
                    return fmt_pct(mr / acct_bal * 100)
                if pd.notna(r.get("_cur_val")):
                    return fmt_pct(r["_cur_val"] / acct_bal * 100)
                return "—"
            display["% of Account"] = filtered.apply(_pct_of_account, axis=1)

        if "Ann. P&L" in vis:
            _ap_pnl    = pd.to_numeric(display["_pnl_num"], errors="coerce")
            _ap_entry  = pd.to_datetime(filtered["entry_date"], errors="coerce")
            _ap_exit   = pd.to_datetime(filtered["exit_date"],  errors="coerce")
            _ap_days   = np.where(is_open_mask,
                                  (today_ts - _ap_entry).dt.days,
                                  (_ap_exit - _ap_entry).dt.days)
            _ap_days_s = pd.to_numeric(pd.Series(_ap_days, index=filtered.index), errors="coerce")
            _ap_ann    = np.where(
                _ap_pnl.notna() & (_ap_days_s > 0),
                _ap_pnl / _ap_days_s * 365,
                np.nan,
            )
            display["Ann. P&L"] = pd.Series(_ap_ann, index=filtered.index).apply(
                lambda v: fmt_pnl(v) if pd.notna(v) else "—"
            )

        if "Realized P&L $" in vis:
            _rp_raw = (_xp - _ep) * _qty * _mult * pd.Series(_sign, index=filtered.index)
            _rp_valid = ~is_open_mask & _qty.notna() & _ep.notna() & _xp.notna()
            display["Realized P&L $"] = np.where(
                _rp_valid,
                _rp_raw.apply(fmt_pnl),
                "—",
            )

        if "Realized P&L %" in vis:
            _rpct_raw = (_xp - _ep) / _ep * 100 * pd.Series(_sign, index=filtered.index)
            _rpct_valid = ~is_open_mask & _ep.notna() & _xp.notna() & (_ep != 0)
            display["Realized P&L %"] = np.where(
                _rpct_valid,
                _rpct_raw.apply(fmt_signed_pct),
                "—",
            )

        need_urp = any(c in vis for c in ["Unrealized P&L %", "Unrealized Ann. Return %"])
        if need_urp:
            # Dividend-adjusted entry price (per share)
            _urp_adj_ep = pd.Series(
                np.where(
                    (_qty.values > 0) & (_div_series.values > 0),
                    _ep.values - _div_series.values / _qty.values,
                    _ep.values,
                ),
                index=filtered.index,
            )
            _urp_live  = pd.to_numeric(_live_prices_ser, errors="coerce")
            _urp_sign  = pd.Series(_sign, index=filtered.index)
            _urp_valid = is_open_mask & _urp_live.notna() & _urp_adj_ep.notna() & (_urp_adj_ep != 0)
            _urp_raw_pct = np.where(
                _urp_valid,
                (_urp_live - _urp_adj_ep) / _urp_adj_ep.abs() * 100 * _urp_sign,
                np.nan,
            )
            _urp_pct_ser = pd.Series(_urp_raw_pct, index=filtered.index)

        if "Unrealized P&L %" in vis:
            display["Unrealized P&L %"] = _urp_pct_ser.apply(
                lambda v: fmt_signed_pct(v) if pd.notna(v) else "—"
            )

        if "Unrealized Ann. Return %" in vis:
            _uarp_entry_dt = pd.to_datetime(filtered["entry_date"], errors="coerce")
            _uarp_days     = (today_ts - _uarp_entry_dt).dt.days
            _uarp_ann      = np.where(
                _urp_valid & (_uarp_days > 0),
                _urp_raw_pct / _uarp_days * 365,
                np.nan,
            )
            display["Unrealized Ann. Return %"] = pd.Series(_uarp_ann, index=filtered.index).apply(
                lambda v: fmt_signed_pct(v) if pd.notna(v) else "—"
            )

        if "Acct P&L %" in vis:
            display["Acct P&L %"] = filtered.apply(
                lambda r: fmt_signed_pct(display.loc[r.name, "_pnl_num"] / acct_bal * 100)
                          if pd.notna(display.loc[r.name, "_pnl_num"]) and acct_bal > 0 else "—", axis=1
            )

        need_day = any(c in vis for c in ["Day's Change", "Day Change %", "Day P&L", "Day P&L %"])
        if need_day:
            _dc_live  = live_ticker_ser.map(lambda t: live_data.get(t, {}).get("price"))
            _dc_prev  = live_ticker_ser.map(lambda t: live_data.get(t, {}).get("prev_close"))
            _dc_delta = pd.to_numeric(_dc_live, errors="coerce") - pd.to_numeric(_dc_prev, errors="coerce")
            filtered["_day_chg"] = np.where(is_open_mask & _dc_delta.notna(), _dc_delta, np.nan)

        if "Day's Change" in vis:
            display["Day's Change"] = filtered["_day_chg"].apply(lambda v: fmt_pnl(v) if pd.notna(v) else "—")

        if "Day Change %" in vis:
            _dcp_dc   = pd.to_numeric(filtered["_day_chg"], errors="coerce")
            _dcp_prev = pd.to_numeric(_dc_prev, errors="coerce")
            _dcp_pct  = np.where(
                _dcp_dc.notna() & _dcp_prev.notna() & (_dcp_prev != 0),
                _dcp_dc / _dcp_prev * 100,
                np.nan,
            )
            display["Day Change %"] = pd.Series(_dcp_pct, index=filtered.index).apply(
                lambda v: fmt_signed_pct(v) if pd.notna(v) else "—"
            )

        if "Day P&L" in vis:
            display["Day P&L"] = filtered.apply(
                lambda r: fmt_pnl(r.get("_day_chg") * r["quantity"] * float(r.get("multiplier") or 1.0))
                          if pd.notna(r.get("_day_chg")) and r["quantity"] else "—", axis=1
            )

        if "Day P&L %" in vis:
            def _day_pnl_pct(row):
                dc = row.get("_day_chg")
                qty, ep = row["quantity"], row["entry_price"]
                if not pd.notna(dc) or not qty or not ep: return "—"
                entry_val = qty * ep
                return fmt_signed_pct(dc * qty / entry_val * 100) if entry_val else "—"
            display["Day P&L %"] = filtered.apply(_day_pnl_pct, axis=1)

        need_stop_dist = any(c in vis for c in ["Stop Dist $", "Stop Dist %", "Stop Dist ATR",
                                                 "Locked-in Profit", "Open Risk"])
        if need_stop_dist or "Opening Risk" in vis:
            filtered["_live_p"] = np.where(is_open_mask, _live_prices_ser, np.nan)

        # Compute effective stop: trailing stop level (if trail_type != 'fixed') or current_stop
        def _eff_stop(row):
            tt = str(row.get("trail_type") or "fixed")
            ta = row.get("trail_amount")
            cs = row.get("current_stop")
            if tt == "fixed" or not ta or pd.isna(ta):
                return cs
            # Trailing — need highest high since entry
            hh = get_highest_high_since(row["ticker"],
                                        str(row["entry_date"])[:10] if row.get("entry_date") else None)
            if hh is None:
                return cs
            atr = metadata.get(row["ticker"], {}).get("atr14") if metadata else None
            side_val = str(row.get("side") or "long").lower()
            if side_val == "short":
                # For shorts: trail above the lowest low
                ll_val = get_highest_high_since(row["ticker"],
                                                str(row["entry_date"])[:10] if row.get("entry_date") else None)
                if tt == "$":
                    return ll_val + float(ta) if ll_val is not None else cs
                elif tt == "%":
                    return ll_val * (1 + float(ta) / 100) if ll_val is not None else cs
                elif tt == "ATR":
                    return (ll_val + float(ta) * atr) if ll_val is not None and atr else cs
            else:
                if tt == "$":
                    return hh - float(ta)
                elif tt == "%":
                    return hh * (1 - float(ta) / 100)
                elif tt == "ATR":
                    return (hh - float(ta) * atr) if atr else cs
            return cs

        if need_stop_dist and "trail_type" in filtered.columns:
            filtered["_eff_stop"] = filtered.apply(
                lambda r: _eff_stop(r) if is_open_mask[filtered.index.get_loc(r.name)] else r.get("current_stop"),
                axis=1,
            )
        else:
            filtered["_eff_stop"] = filtered["current_stop"]

        if "Locked-in Profit" in vis:
            _lk_cs  = pd.to_numeric(filtered["_eff_stop"],  errors="coerce")
            _lk_ep  = pd.to_numeric(filtered["entry_price"],   errors="coerce")
            _lk_qty = pd.to_numeric(filtered["quantity"],      errors="coerce")
            _lk_mul = pd.to_numeric(filtered["multiplier"],    errors="coerce").fillna(1.0)
            _lk_val = (_lk_cs - _lk_ep) * _lk_qty * _lk_mul
            _lk_ok  = is_open_mask & _lk_cs.notna() & _lk_ep.notna() & _lk_qty.notna()
            display["Locked-in Profit"] = np.where(_lk_ok, _lk_val.apply(fmt_pnl), "—")

        if "Open Risk" in vis:
            _or_pnl    = pd.to_numeric(display["_pnl_num"], errors="coerce")
            _or_cs     = pd.to_numeric(filtered["_eff_stop"],  errors="coerce")
            _or_ep     = pd.to_numeric(filtered["entry_price"],   errors="coerce")
            _or_qty    = pd.to_numeric(filtered["quantity"],      errors="coerce")
            _or_mul    = pd.to_numeric(filtered["multiplier"],    errors="coerce").fillna(1.0)
            _or_locked = np.where(
                _or_cs.notna() & _or_ep.notna() & _or_qty.notna(),
                (_or_cs - _or_ep) * _or_qty * _or_mul,
                0.0,
            )
            _or_risk = _or_pnl - pd.Series(_or_locked, index=filtered.index)
            _or_ok   = is_open_mask & _or_pnl.notna()
            display["Open Risk"] = np.where(_or_ok, _or_risk.apply(fmt_pnl), "—")

        if "Opening Risk" in vis:
            def _opening_risk(row):
                qty, ep, os_ = row["quantity"], row["entry_price"], row["opening_stop"]
                mult = float(row.get("multiplier") or 1.0)
                return fmt_price(qty * abs(ep - os_) * mult) if qty and ep and os_ else "—"
            display["Opening Risk"] = filtered.apply(_opening_risk, axis=1)

        if "Stop Dist $" in vis:
            display["Stop Dist $"] = filtered.apply(
                lambda r: fmt_price(r.get("_live_p") - r["_eff_stop"])
                          if pd.notna(r.get("_live_p")) and r["_eff_stop"] is not None else "—", axis=1
            )

        if "Stop Dist %" in vis:
            def _sd_pct(row):
                lp, cs = row.get("_live_p"), row["_eff_stop"]
                if not pd.notna(lp) or cs is None or lp == 0: return "—"
                return fmt_pct((lp - cs) / lp * 100)
            display["Stop Dist %"] = filtered.apply(_sd_pct, axis=1)

        if "Stop Dist ATR" in vis:
            def _sd_atr(row):
                lp, cs = row.get("_live_p"), row["_eff_stop"]
                if not pd.notna(lp) or cs is None: return "—"
                atr = metadata.get(row["ticker"], {}).get("atr14")
                return fmt_num((lp - cs) / atr) if atr else "—"
            display["Stop Dist ATR"] = filtered.apply(_sd_atr, axis=1)

        if metadata:
            if "Sector" in vis:
                display["Sector"]      = filtered["ticker"].apply(lambda t: metadata.get(t, {}).get("sector") or "—")
            if "Industry" in vis:
                display["Industry"]    = filtered["ticker"].apply(lambda t: metadata.get(t, {}).get("industry") or "—")
            if "Beta" in vis:
                display["Beta"]        = filtered["ticker"].apply(lambda t: fmt_num(metadata.get(t, {}).get("beta")))
            if "Correlation" in vis:
                display["Correlation"] = filtered["ticker"].apply(
                    lambda t: fmt_num(metadata.get(t, {}).get("correlation_spy"), decimals=3))

        # Options / Futures columns
        if "Contract" in vis:
            display["Contract"] = filtered.apply(_contract_sym, axis=1)
        if "Leg" in vis:
            display["Leg"] = filtered["leg_label"].apply(lambda v: str(v) if v and not pd.isna(v) else "—")
        if "Expiration" in vis:
            display["Expiration"] = filtered["expiration"].apply(lambda v: fmt_date(v, euro_dates) if v and not pd.isna(v) else "—")
        if "Strike" in vis:
            display["Strike"] = filtered["strike"].apply(fmt_price)
        if "Option Type" in vis:
            display["Option Type"] = filtered["option_type"].apply(
                lambda v: "Call" if str(v or "").upper().startswith("C")
                          else "Put" if str(v or "").upper().startswith("P") else "—"
            )
        if "Multiplier" in vis:
            display["Multiplier"] = filtered["multiplier"].apply(
                lambda v: fmt_num(float(v)) if v and not pd.isna(v) else "1"
            )
        if "Spread Group" in vis:
            display["Spread Group"] = filtered["leg_group"].apply(
                lambda v: str(v)[:8] if v and not pd.isna(v) else "—"
            )
        if "Spread Type" in vis:
            display["Spread Type"] = filtered["spread_type"].apply(
                lambda v: str(v) if v and not pd.isna(v) else "—"
            ) if "spread_type" in filtered.columns else "—"

        if "Underlying" in vis:
            import re as _re
            def _underlying(row):
                t = str(row.get("ticker") or "")
                if str(row.get("instrument_type") or "stock").lower() == "option":
                    m = _re.match(r'^([A-Z]{1,6})', t.upper())
                    return m.group(1) if m else t
                return t
            display["Underlying"] = filtered.apply(_underlying, axis=1)

        if "Delta" in vis:
            display["Delta"] = (
                filtered["_delta_pos"].apply(lambda v: fmt_num(v, 2) if pd.notna(v) else "—")
                if "_delta_pos" in filtered.columns else "—"
            )

        if "Theta" in vis:
            display["Theta"] = (
                filtered["_theta_pos"].apply(lambda v: fmt_num(v, 2) if pd.notna(v) else "—")
                if "_theta_pos" in filtered.columns else "—"
            )

        if "Commission" in vis:
            display["Commission"] = filtered["commission"].apply(
                lambda v: fmt_price(float(v)) if v is not None and not pd.isna(v) else "$0.00"
            ) if "commission" in filtered.columns else "$0.00"

        if "Ann. Return %" in vis:
            _arp_pnl   = pd.to_numeric(display["_pnl_num"], errors="coerce")
            _arp_entry = pd.to_datetime(filtered["entry_date"], errors="coerce")
            _arp_exit  = pd.to_datetime(filtered["exit_date"],  errors="coerce")
            _arp_ep    = pd.to_numeric(filtered["entry_price"], errors="coerce")
            _arp_qty   = pd.to_numeric(filtered["quantity"],    errors="coerce")
            _arp_mul   = pd.to_numeric(filtered.get("multiplier", pd.Series(1.0, index=filtered.index)), errors="coerce").fillna(1.0)
            _arp_days  = np.where(is_open_mask,
                                  (today_ts - _arp_entry).dt.days,
                                  (_arp_exit - _arp_entry).dt.days)
            _arp_days_s = pd.to_numeric(pd.Series(_arp_days, index=filtered.index), errors="coerce")
            _arp_cost  = (_arp_ep * _arp_qty * _arp_mul).abs()
            _arp_pct   = np.where(
                _arp_pnl.notna() & _arp_cost.notna() & (_arp_cost > 0) & (_arp_days_s > 0),
                _arp_pnl / _arp_cost * 100 / _arp_days_s * 365,
                np.nan,
            )
            display["Ann. Return %"] = pd.Series(_arp_pct, index=filtered.index).apply(
                lambda v: fmt_signed_pct(v) if pd.notna(v) else "—"
            )

        # Earnings column — auto-fetch with manual override for open trades
        if "Earnings" in vis:
            _earn_iom = is_open_mask  # close over the precomputed mask
            def _earnings_val(row):
                manual = row.get("earnings_date")
                if manual and not pd.isna(manual) and str(manual).strip():
                    return str(manual).strip()
                if _earn_iom[row.name]:
                    fetched = fetch_next_earnings(row["ticker"])
                    return fetched if fetched else "—"
                return "—"
            display["Earnings"] = filtered.apply(_earnings_val, axis=1)

        # ── Collapse spread/roll groups (when expand toggle is off) ─────────────

        # Snapshot before aggregation — spread summaries need the full leg data
        _pre_agg_filtered = filtered.copy()

        _group_row_ids: dict[int, list] = {}
        if not _expand_legs:
            # Build aggregated rows for each leg_group / roll_group
            _group_col = "leg_group" if "leg_group" in filtered.columns else None
            _roll_col  = "roll_group" if "roll_group" in filtered.columns else None
            _grouped_ids: set      = set()
            _agg_rows: list        = []
            _agg_member_ids: list  = []  # parallel: member trade IDs for each agg row

            for _gc in [_group_col, _roll_col]:
                if _gc is None:
                    continue
                for _grp_key in filtered[_gc].dropna().unique():
                    _grp_mask = filtered[_gc] == _grp_key
                    _grp_rows = display[_grp_mask.values]
                    _grp_filt = filtered[_grp_mask.values]
                    if len(_grp_rows) < 2:
                        continue
                    _grouped_ids.update(_grp_filt.index.tolist())
                    # Aggregate: sum PnL, use first ticker, first entry date
                    _agg_pnl  = _grp_rows["_pnl_num"].dropna().sum()
                    _agg_row  = {c: "—" for c in display.columns}
                    _agg_row["Trade ID"]    = f"[{_gc.replace('_group','')}] {_grp_key}"
                    # Status: open if any leg is still open
                    _any_open = _grp_filt.apply(_is_open, axis=1).any()
                    _agg_row["Status"]      = "Open" if _any_open else "Closed"
                    _agg_row["Ticker"]      = _grp_filt["ticker"].iloc[0]
                    # Instrument: reflect the kind of group
                    _grp_itype = str(_grp_filt["instrument_type"].iloc[0] if "instrument_type" in _grp_filt.columns else "stock").lower()
                    if _gc == "roll_group":
                        _agg_row["Instrument"] = "Option Roll"
                    elif _grp_itype == "option":
                        _agg_row["Instrument"] = "Option Spread"
                    else:
                        _agg_row["Instrument"] = "Spread"
                    _agg_row["Entry Date"]  = _grp_rows["Entry Date"].iloc[0]
                    _agg_row["Exit Date"]   = _grp_rows["Exit Date"].iloc[-1]
                    _agg_row["P&L"]         = fmt_pnl(_agg_pnl)
                    _agg_row["_pnl_num"]    = _agg_pnl
                    # Quantity: for spreads show the number of *spreads* (the per-leg
                    # contract count), which is what traders track — not the leg count,
                    # which is just the structure. Rolls keep the leg count.
                    if _gc == "leg_group":
                        _sp_units = spread_unit_count(_grp_filt["quantity"].tolist())
                        _agg_row["Quantity"] = (
                            fmt_qty(_sp_units) if _sp_units else f"{len(_grp_rows)} legs"
                        )
                    else:
                        _agg_row["Quantity"] = f"{len(_grp_rows)} legs"
                    # Spread Type: stored type wins; otherwise infer from leg structure
                    # so collapsed option spreads still show e.g. "Vertical" / "Iron Condor".
                    if "Spread Type" in _agg_row:
                        _stype_val = None
                        if "spread_type" in _grp_filt.columns and _grp_filt["spread_type"].notna().any():
                            _stype_val = _grp_filt["spread_type"].dropna().iloc[0]
                        if not _stype_val and _grp_itype == "option" and _gc == "leg_group":
                            _stype_val = _detect_spread_type(_grp_filt)
                        _agg_row["Spread Type"] = str(_stype_val) if _stype_val else "—"
                    # Net live price: sum each leg's market price with side polarity
                    if _any_open and live_data:
                        _grp_live_tkrs = live_ticker_ser[_grp_mask]
                        _grp_signs     = np.where(
                            _grp_filt["side"].fillna("long").str.lower() == "short", -1.0, 1.0
                        )
                        _leg_pxs = [
                            float(live_data[sym]["price"]) * sign
                            for sym, sign in zip(_grp_live_tkrs.values, _grp_signs)
                            if sym and live_data.get(sym, {}).get("price") is not None
                        ]
                        if len(_leg_pxs) == len(_grp_filt):
                            _agg_row["Live Price"] = fmt_price(sum(_leg_pxs))

                    # Aggregate position-value columns across legs (net, with side
                    # polarity — consistent with the net Live Price above).
                    _val_signs = np.where(
                        _grp_filt["side"].fillna("long").str.lower() == "short", -1.0, 1.0
                    )
                    # Current Value: net market value of the legs (with side polarity)
                    if "_cur_val" in _grp_filt.columns:
                        _leg_cv = pd.to_numeric(_grp_filt["_cur_val"], errors="coerce").to_numpy()
                        if not np.all(np.isnan(_leg_cv)):
                            _net_cv = float(np.nansum(_leg_cv * _val_signs))
                            _agg_row["Current Value"] = fmt_price(_net_cv)
                    # % of Account: option spreads sized by combined max risk
                    # (worst-case loss across all legs); other groups by net value.
                    if acct_bal > 0:
                        if _grp_itype == "option":
                            _mr = option_legs_max_risk([
                                {"type": _r.get("option_type"), "strike": _r.get("strike"),
                                 "side": _r.get("side"),        "qty":    _r.get("quantity"),
                                 "mult": _r.get("multiplier"),  "entry_price": _r.get("entry_price")}
                                for _, _r in _grp_filt.iterrows()
                            ])
                            if _mr is None:
                                _agg_row["% of Account"] = "∞"
                            elif _mr is not None:
                                _agg_row["% of Account"] = fmt_pct(_mr / acct_bal * 100)
                        elif "_cur_val" in _grp_filt.columns and not np.all(np.isnan(_leg_cv)):
                            _agg_row["% of Account"] = fmt_pct(_net_cv / acct_bal * 100)
                    # Entry Value: net debit/credit basis across legs
                    _leg_qty  = pd.to_numeric(_grp_filt["quantity"],    errors="coerce").to_numpy()
                    _leg_ep   = pd.to_numeric(_grp_filt["entry_price"], errors="coerce").to_numpy()
                    _leg_mult = pd.to_numeric(_grp_filt["multiplier"],  errors="coerce").fillna(1.0).to_numpy()
                    _leg_ev   = _leg_qty * _leg_ep * _leg_mult
                    if not np.all(np.isnan(_leg_ev)):
                        _agg_row["Entry Value"] = fmt_price(float(np.nansum(_leg_ev * _val_signs)))
                    # Acct P&L % from the summed P&L
                    if acct_bal > 0 and pd.notna(_agg_pnl):
                        _agg_row["Acct P&L %"] = fmt_signed_pct(_agg_pnl / acct_bal * 100)
                    # Days in Trade: legs share an entry date — use the first leg's value
                    if "Days in Trade" in _grp_rows.columns:
                        _agg_row["Days in Trade"] = _grp_rows["Days in Trade"].iloc[0]
                    # Net greeks: sum signed position greeks across legs
                    if "_delta_pos" in _grp_filt.columns:
                        _ds = pd.to_numeric(_grp_filt["_delta_pos"], errors="coerce")
                        if _ds.notna().any():
                            _agg_row["Delta"] = fmt_num(float(_ds.sum()), 2)
                    if "_theta_pos" in _grp_filt.columns:
                        _ts = pd.to_numeric(_grp_filt["_theta_pos"], errors="coerce")
                        if _ts.notna().any():
                            _agg_row["Theta"] = fmt_num(float(_ts.sum()), 2)

                    _agg_rows.append(_agg_row)
                    _agg_member_ids.append(_grp_filt["id"].tolist())

            if _agg_rows or _grouped_ids:
                # Keep non-grouped rows
                _non_grp_mask = ~display.index.isin(_grouped_ids)
                _non_grp_disp = display[_non_grp_mask]
                _non_grp_count = len(_non_grp_disp)
                _agg_df       = pd.DataFrame(_agg_rows, columns=display.columns) if _agg_rows else pd.DataFrame(columns=display.columns)
                display       = pd.concat([_non_grp_disp, _agg_df], ignore_index=True)
                display["Trade ID"] = display["Trade ID"].astype(str)
                filtered      = filtered[_non_grp_mask].reset_index(drop=True)
                # map display index → member trade IDs for each aggregate row
                _group_row_ids = {
                    _non_grp_count + j: ids for j, ids in enumerate(_agg_member_ids)
                }
                is_open_mask  = _make_is_open_mask(filtered)

        # ── Positions view ─────────────────────────────────────────────────────

        if _positions_view:
            # Build one aggregated row per ticker (open positions only)
            # Use pre-aggregation data so spread legs aren't invisible here
            _pos_rows = []
            _pos_ticker_ids: dict[str, list[int]] = {}  # ticker → list of trade ids
            _all_open = _pre_agg_filtered[_make_is_open_mask(_pre_agg_filtered)]

            for _tkr, _grp in _all_open.groupby("ticker"):
                _ids = _grp["id"].tolist()
                _pos_ticker_ids[_tkr] = _ids
                # Weighted-average cost from lots if available, else from trades
                _lots_map = load_lots_for_trades(_ids)
                _all_lots = [lot for llist in _lots_map.values() for lot in llist]
                if _all_lots:
                    _trade_side = {
                        int(row["id"]): (-1 if str(row.get("side", "")).lower() == "short" else 1)
                        for _, row in _grp.iterrows()
                    }
                    _open_lots_all = [l for l in _all_lots if l["lot_type"] != "exit"]
                    _signed_lot_qty  = sum(l["quantity"] * _trade_side.get(int(l["trade_id"]), 1) for l in _open_lots_all)
                    _signed_lot_cost = sum(l["quantity"] * _trade_side.get(int(l["trade_id"]), 1) * l["price"] for l in _open_lots_all)
                    if _signed_lot_qty != 0:
                        _total_qty = abs(_signed_lot_qty)
                        _avg_cost  = _signed_lot_cost / _signed_lot_qty
                    else:
                        _total_qty = sum(l["quantity"] for l in _open_lots_all if _trade_side.get(int(l["trade_id"]), 1) == 1)
                        _avg_cost  = (_signed_lot_cost / _total_qty) if _total_qty else 0.0
                    _n_adds     = sum(1 for l in _all_lots if l["lot_type"] == "add")
                else:
                    _signs      = _grp["side"].map(lambda s: -1 if str(s).lower() == "short" else 1).fillna(1)
                    _signed_qty = (_grp["quantity"].fillna(0) * _signs)
                    _net_qty    = float(_signed_qty.sum())
                    _net_cost   = float((_signed_qty * _grp["entry_price"].fillna(0)).sum())
                    if _net_qty != 0:
                        _total_qty = abs(_net_qty)
                        _avg_cost  = _net_cost / _net_qty
                    else:
                        # Balanced spread: use long-leg qty, net cost as basis
                        _total_qty = float(_grp.loc[_signs == 1, "quantity"].fillna(0).sum())
                        _avg_cost  = (_net_cost / _total_qty) if _total_qty else 0.0
                    _n_adds = 0

                # Dividends
                _divs_map = load_dividends_for_trades(_ids)
                _total_divs = sum(
                    d.get("total_amount") or 0
                    for dlist in _divs_map.values() for d in dlist
                )

                # Live price / P&L
                _live_key  = _tkr
                _live_px   = live_data.get(_live_key, {}).get("price")
                _cur_val   = (_live_px * _total_qty) if _live_px else None
                _entry_val = _avg_cost * _total_qty
                _pnl_val   = (_cur_val - _entry_val) if _cur_val is not None else None

                _pos_rows.append({
                    "Ticker":        _tkr,
                    "Qty":           fmt_qty(_total_qty),
                    "Avg Cost":      fmt_price(_avg_cost),
                    "Adds":          _n_adds,
                    "Live Price":    fmt_price(_live_px) if _live_px else "—",
                    "Current Value": fmt_price(_cur_val) if _cur_val else "—",
                    "Unrealized P&L": fmt_pnl(_pnl_val) if _pnl_val is not None else "—",
                    "Dividends Rcvd": fmt_price(_total_divs) if _total_divs else "—",
                    "_pnl_num":      _pnl_val,
                    "_ids_json":     str(_ids),   # store ids as string for drill-down
                })

            if not _pos_rows:
                st.info("No open positions.")
            else:
                _pos_df = pd.DataFrame(_pos_rows)
                _pos_display_cols = ["Ticker", "Qty", "Avg Cost", "Adds",
                                     "Live Price", "Current Value", "Unrealized P&L", "Dividends Rcvd"]
                _pos_event = st.dataframe(
                    _pos_df[_pos_display_cols],
                    width='stretch', hide_index=True,
                    on_select="rerun", selection_mode="single-row",
                    key="pos_table",
                )
                _pos_sel = _pos_event.selection.rows
                st.caption(f"{len(_pos_rows)} open position{'s' if len(_pos_rows) != 1 else ''}"
                           + (" · click a row to drill down" if not _pos_sel else ""))

                # ── Drill-down panel ──────────────────────────────────────────
                if _pos_sel:
                    _sel_pos_row  = _pos_df.iloc[_pos_sel[0]]
                    _sel_ticker   = _sel_pos_row["Ticker"]
                    _sel_ids      = _pos_ticker_ids.get(_sel_ticker, [])

                    st.markdown(f"#### 🔍  {_sel_ticker} — Position Detail")

                    _dd_lots_map = load_lots_for_trades(_sel_ids)
                    _dd_divs_map = load_dividends_for_trades(_sel_ids)

                    _dd_col1, _dd_col2 = st.columns([3, 2])

                    # Build side sign map once — used by lots table, summary, and trade IDs table
                    _dd_trades  = filtered[filtered["id"].isin(_sel_ids)]
                    _dd_signs   = _dd_trades["side"].map(lambda s: -1 if str(s).lower() == "short" else 1).fillna(1)
                    _trade_sign = dict(zip(_dd_trades["id"].astype(int), _dd_signs.values))

                    with _dd_col1:
                        st.markdown("**Tax Lots**")
                        _flat_lots = [
                            {**lot, "Trade ID": tid}
                            for tid, llist in _dd_lots_map.items()
                            for lot in llist
                        ]
                        if _flat_lots:
                            _lot_raw  = pd.DataFrame(_flat_lots)
                            _lot_disp = _lot_raw[["Trade ID", "date", "quantity", "price", "lot_type", "notes"]].copy()
                            _lot_disp.columns = ["Trade ID", "Date", "Qty", "Price", "Type", "Notes"]
                            # Apply sign: short legs show negative qty and cost basis
                            _lot_sign = _lot_raw["Trade ID"].astype(int).map(lambda tid: _trade_sign.get(tid, 1))
                            _lot_disp["Qty"]        = (_lot_raw["quantity"] * _lot_sign).apply(lambda v: int(v) if v == int(v) else v)
                            _lot_disp["Price"]      = _lot_raw["price"].apply(fmt_price)
                            _lot_disp["Cost Basis"] = (_lot_raw["quantity"] * _lot_sign * _lot_raw["price"]).apply(fmt_price)
                            st.dataframe(_lot_disp, width='stretch', hide_index=True)

                            # Summary under lots — use signed qty from trade side
                            _dd_sq       = (_dd_trades["quantity"].fillna(0) * _dd_signs)
                            _net_qty_dd  = float(_dd_sq.sum())
                            _net_cost_dd = float((_dd_sq * _dd_trades["entry_price"].fillna(0)).sum())
                            if _net_qty_dd != 0:
                                _total_qty_dd = abs(_net_qty_dd)
                                _avg_c        = _net_cost_dd / _net_qty_dd
                            else:
                                _total_qty_dd = float(_dd_trades.loc[_dd_signs == 1, "quantity"].fillna(0).sum())
                                _avg_c        = (_net_cost_dd / _total_qty_dd) if _total_qty_dd else 0.0
                            _total_basis  = _avg_c * _total_qty_dd
                            _ms1, _ms2, _ms3 = st.columns(3)
                            _ms1.metric("Total Qty",   fmt_qty(_total_qty_dd))
                            _ms2.metric("Avg Cost",    fmt_price(_avg_c))
                            _ms3.metric("Total Basis", fmt_price(_total_basis))
                        else:
                            st.info("No lot records — add lots via 'Add to Position' in the Multiple Buy/Sell section.")

                    with _dd_col2:
                        st.markdown("**Dividends**")
                        _flat_divs = [
                            {**d, "Trade ID": tid}
                            for tid, dlist in _dd_divs_map.items()
                            for d in dlist
                        ]
                        if _flat_divs:
                            _div_disp = pd.DataFrame(_flat_divs)[
                                ["ex_date", "amount_per_share", "quantity", "total_amount", "notes"]
                            ]
                            _div_disp.columns = ["Ex-Date", "$/Share", "Qty", "Total", "Notes"]
                            _div_disp["$/Share"] = _div_disp["$/Share"].apply(fmt_price)
                            _div_disp["Total"]   = _div_disp["Total"].apply(
                                lambda v: fmt_price(v) if v and not pd.isna(v) else "—"
                            )
                            st.dataframe(_div_disp, width='stretch', hide_index=True)
                            _div_total = sum(
                                (d.get("total_amount") or 0) for d in _flat_divs
                            )
                            st.metric("Total Dividends", fmt_price(_div_total))
                        else:
                            st.info("No dividends recorded for this position.")

                        st.markdown("**Individual Trade IDs**")
                        _id_df = filtered[filtered["id"].isin(_sel_ids)][
                            ["id", "entry_date", "quantity", "entry_price", "account_name", "side"]
                        ].copy()
                        _id_df.columns = ["ID", "Entry Date", "Qty", "Entry Price", "Account", "side"]
                        _id_df["Qty"]         = (_id_df["Qty"] * _id_df["side"].map(lambda s: -1 if str(s).lower() == "short" else 1)).apply(lambda v: int(v) if v == int(v) else v)
                        _id_df["Entry Date"]  = _id_df["Entry Date"].apply(lambda v: fmt_date(v, euro_dates))
                        _id_df["Entry Price"] = _id_df["Entry Price"].apply(fmt_price)
                        st.dataframe(_id_df.drop(columns=["side"]), width='stretch', hide_index=True)

            # Skip the normal trades table when positions view is active
            _skip_trades_table = True
        else:
            _skip_trades_table = False

        # ── Render table ───────────────────────────────────────────────────────

        safe_vis   = [c for c in vis if c in display.columns]
        _grp_keys  = (
            filtered["leg_group"].reset_index(drop=True)
            if "leg_group" in filtered.columns else None
        )
        styled     = _style_table(display[safe_vis], settings, group_keys=_grp_keys)
        selected_rows = []  # initialised here; overwritten below when trades table is rendered
        valid_rows = []
        valid_non_group_rows = []

        if not _positions_view:
            # Resolve pending selection changes BEFORE the widget is instantiated.
            if st.session_state.pop("_reset_table_sel", False):
                st.session_state["trade_table"] = {"selection": {"rows": [], "columns": []}}
            if st.session_state.pop("_select_all_pending", False):
                st.session_state["trade_table"] = {"selection": {"rows": list(range(len(display))), "columns": []}}

            event = st.dataframe(styled, width='stretch', hide_index=True,
                                 on_select="rerun", selection_mode="multi-row",
                                 key="trade_table")

            selected_rows = event.selection.rows

            valid_rows = [i for i in selected_rows if i < len(display)]
            valid_non_group_rows = [i for i in valid_rows if i not in _group_row_ids and i < len(filtered)]

            def _resolve_ids(indices):
                ids = []
                for i in indices:
                    if i in _group_row_ids:
                        ids.extend(int(x) for x in _group_row_ids[i])
                    elif i < len(filtered):
                        ids.append(int(filtered.iloc[i]["id"]))
                return ids

            if valid_rows:
                st.session_state["_bulk_sel_ids"] = _resolve_ids(valid_rows)
            else:
                st.session_state.pop("_bulk_sel_ids", None)

            _cap_c1, _cap_c2, _cap_c3 = st.columns([4, 1, 1])
            _cap_c1.caption(
                f"{len(filtered)} trade{'s' if len(filtered) != 1 else ''}"
                + (f"  ·  {len(selected_rows)} selected" if selected_rows else "")
            )
            if _cap_c2.button("☑  Select All", key="select_all_btn", help="Select all visible rows"):
                st.session_state["_select_all_pending"] = True
                st.rerun()
            if selected_rows and _cap_c3.button("✕  Clear", key="clear_sel_btn", help="Clear selection"):
                st.session_state["_reset_table_sel"] = True
                st.rerun()

            # Inline drill-down: quick-edit + lots + dividends when a single non-group row is selected
            if len(valid_non_group_rows) == 1:
                _dd_id  = int(filtered.iloc[valid_non_group_rows[0]]["id"])
                _dd_row = filtered.iloc[valid_non_group_rows[0]]
                _dd_current_tag_names = [
                    tag_id_to_name[tid]
                    for tid in get_trade_tag_ids(_dd_id)
                    if tid in tag_id_to_name
                ]
                with st.form(f"quick_edit_{_dd_id}", clear_on_submit=False):
                    qe1, qe2, qe3 = st.columns(3)
                    _qe_entry_date = qe1.date_input(
                        "Entry Date",
                        value=pd.to_datetime(_dd_row["entry_date"]).date()
                              if _dd_row.get("entry_date") and not pd.isna(_dd_row["entry_date"]) else None,
                        key=f"qe_ed_{_dd_id}",
                    )
                    _qe_ticker = qe2.text_input("Ticker", value=str(_dd_row.get("ticker") or ""),
                                                key=f"qe_tk_{_dd_id}")
                    _qe_qty = qe3.number_input("Quantity", min_value=0.0, step=1.0, format="%.4f",
                                               value=float(_dd_row["quantity"]) if _dd_row.get("quantity") else None,
                                               key=f"qe_qty_{_dd_id}")
                    qe4, qe5, qe6 = st.columns(3)
                    _qe_entry_price = qe4.number_input("Entry Price", min_value=0.0, step=0.01, format="%.4f",
                                                        value=float(_dd_row["entry_price"]) if _dd_row.get("entry_price") else None,
                                                        key=f"qe_ep_{_dd_id}")
                    _qe_exit_date = qe5.date_input(
                        "Exit Date",
                        value=pd.to_datetime(_dd_row["exit_date"]).date()
                              if _dd_row.get("exit_date") and not pd.isna(_dd_row["exit_date"]) else None,
                        key=f"qe_xd_{_dd_id}",
                    )
                    _qe_exit_price = qe6.number_input("Exit Price", min_value=0.0, step=0.01, format="%.4f",
                                                       value=float(_dd_row["exit_price"])
                                                             if _dd_row.get("exit_price") and not pd.isna(_dd_row["exit_price"]) else None,
                                                       key=f"qe_xp_{_dd_id}")
                    _qe_sel_tag_names = st.multiselect(
                        "Tags",
                        options=list(tag_name_to_id.keys()),
                        default=_dd_current_tag_names,
                        key=f"qe_tags_{_dd_id}",
                        placeholder="Add tags…",
                    )
                    if st.form_submit_button("💾  Save Quick Edit", width='stretch'):
                        _qe_tag_ids = [tag_name_to_id[n] for n in _qe_sel_tag_names if n in tag_name_to_id]
                        _qe_cs = float(_dd_row["current_stop"]) if _dd_row.get("current_stop") and not pd.isna(_dd_row.get("current_stop", float("nan"))) else None
                        update_trade(
                            _dd_id,
                            _qe_exit_date,
                            float(_qe_exit_price) if _qe_exit_price else None,
                            _dd_row.get("notes") or None,
                            _qe_cs,
                            bool(_dd_row.get("stop_enabled", 1)),
                            _qe_tag_ids,
                            entry_date=_qe_entry_date,
                            ticker=_qe_ticker.strip() if _qe_ticker.strip() else None,
                            quantity=float(_qe_qty) if _qe_qty else None,
                            entry_price=float(_qe_entry_price) if _qe_entry_price else None,
                        )
                        st.toast("Trade updated.", icon="✅")
                        st.rerun()
                _dd_lots = load_trade_lots(_dd_id)
                _dd_divs = load_trade_dividends(_dd_id)
                _lot_col, _div_col = st.columns(2)
                with _lot_col:
                    st.markdown("**Tax Lots**")
                    if _dd_lots:
                        _lots_df = pd.DataFrame(
                            _dd_lots,
                            columns=["id", "trade_id", "date", "quantity", "price", "lot_type", "notes"]
                        )
                        st.dataframe(
                            _lots_df[["date", "lot_type", "quantity", "price"]].rename(
                                columns={"lot_type": "Type", "quantity": "Qty", "price": "Price"}
                            ),
                            width='stretch', hide_index=True
                        )
                    else:
                        st.caption("No lots recorded.")
                with _div_col:
                    st.markdown("**Dividends**")
                    if _dd_divs:
                        _divs_df = pd.DataFrame(
                            _dd_divs,
                            columns=["id", "trade_id", "ex_date", "amount_per_share",
                                     "quantity", "total_amount", "notes"]
                        )
                        st.dataframe(
                            _divs_df[["ex_date", "amount_per_share", "quantity", "total_amount"]].rename(
                                columns={"ex_date": "Ex-Date", "amount_per_share": "$/Share",
                                         "quantity": "Qty", "total_amount": "Total"}
                            ),
                            width='stretch', hide_index=True
                        )
                    else:
                        st.caption("No dividends recorded.")

        # ── Bulk Actions ───────────────────────────────────────────────────────

        st.markdown("**Bulk Actions**")
        ba1, ba2, ba3, ba4 = st.columns([1, 1, 1, 2])

        # Delete selected rows (if any) or all filtered trades
        _bulk_all_ids = filtered["id"].tolist() if not filtered.empty else []
        _sel_ids      = st.session_state.get("_bulk_sel_ids", [])
        _target_ids   = _sel_ids if _sel_ids else _bulk_all_ids
        _bulk_n       = len(_target_ids)
        _del_label    = f"🗑️  Delete Selected ({_bulk_n})" if _sel_ids else f"🗑️  Delete All ({_bulk_n})"
        _del_key      = "_bulk_del_confirm"
        if not st.session_state.get(_del_key):
            if ba1.button(_del_label, disabled=_bulk_n == 0):
                st.session_state[_del_key] = True
                st.rerun()
        else:
            ba1.warning(f"Delete {_bulk_n} trade{'s' if _bulk_n != 1 else ''}?")
            _dc1, _dc2 = ba1.columns(2)
            if _dc1.button("Yes", key="bulk_del_yes"):
                bulk_delete_trades(_target_ids)
                st.session_state[_del_key] = False
                st.session_state["_reset_table_sel"] = True
                st.rerun()
            if _dc2.button("No", key="bulk_del_no"):
                st.session_state[_del_key] = False
                st.rerun()

        csv_data = filtered.to_csv(index=False)
        ba2.download_button("📥  Export CSV", data=csv_data,
                            file_name="selected_trades.csv", mime="text/csv")
        if valid_rows and len(valid_non_group_rows) == 1 and ba3.button("📊  Chart"):
            st.session_state["chart_trade_id"] = int(filtered.iloc[valid_non_group_rows[0]]["id"])
        bulk_tag_names = ba4.multiselect("Tag all filtered",
                                         options=list(tag_name_to_id.keys()), key="bulk_tag")
        if bulk_tag_names and ba4.button("Apply Tags"):
            for tid in _bulk_all_ids:
                for tag_name in bulk_tag_names:
                    add_tag_to_trade(tid, tag_name_to_id[tag_name])
            st.rerun()

            # ── Spread linking (2+ rows selected) ──────────────────────────
            if len(valid_non_group_rows) >= 2:
                sel_ids = [int(filtered.iloc[i]["id"]) for i in valid_non_group_rows]
                sel_groups = (
                    filtered.iloc[valid_non_group_rows]["leg_group"].dropna().unique().tolist()
                    if "leg_group" in filtered.columns else []
                )
                all_same_group = (
                    len(sel_groups) == 1
                    and all(
                        filtered.iloc[i].get("leg_group") == sel_groups[0]
                        for i in valid_non_group_rows
                    )
                )

                st.markdown("**Spread Linking**")
                sl1, sl2 = st.columns([1, 3])

                if all_same_group:
                    if sl1.button("🔓  Ungroup Spread"):
                        update_spread_group(sel_ids, None, None)
                        st.rerun()

                with sl2:
                    _SPREAD_TYPES_BULK = ["Vertical", "Straddle", "Strangle", "Iron Condor", "Butterfly", "Calendar", "Custom"]
                    bulk_spread_type = st.selectbox("Spread Type", ["—"] + _SPREAD_TYPES_BULK, key="bulk_spread_type")

                if sl1.button("🔗  Group as Spread"):
                    grp = str(uuid.uuid4())[:8]
                    stype = bulk_spread_type if bulk_spread_type != "—" else None
                    update_spread_group(sel_ids, grp, stype)
                    st.rerun()

        # ── Spread Summaries ───────────────────────────────────────────────────

        if "leg_group" in _pre_agg_filtered.columns:
            _spread_rows = _pre_agg_filtered[
                _pre_agg_filtered["leg_group"].notna() & (_pre_agg_filtered["leg_group"].astype(str) != "")
            ]
            if not _spread_rows.empty:
                st.markdown("---")
                st.markdown("**Spread Summaries**")
                _sum_rows  = []
                _grp_index = {}   # grp → legs DataFrame for the detail view
                _today_dt  = pd.Timestamp.today().normalize()
                for grp, legs in _spread_rows.groupby("leg_group"):
                    if len(legs) < 2:
                        continue
                    is_open_legs = legs.apply(_is_open, axis=1)
                    status       = "Open" if is_open_legs.any() else "Closed"
                    # Stored spread type, or auto-detect
                    stype_val = None
                    if "spread_type" in legs.columns and legs["spread_type"].notna().any():
                        stype_val = legs["spread_type"].dropna().iloc[0]
                    stype_display = stype_val if stype_val else _detect_spread_type(legs)

                    # P&L split: unrealized (open legs) vs realised (closed legs)
                    _u_vals = [_pnl_numeric(r, live_data) for _, r in legs[is_open_legs].iterrows()]
                    _r_vals = [_pnl_numeric(r, live_data) for _, r in legs[~is_open_legs].iterrows()]
                    _u_has_data    = any(v is not None for v in _u_vals)
                    _r_has_data    = any(v is not None for v in _r_vals)
                    unrealized_pnl = sum(v for v in _u_vals if v is not None) if _u_has_data else None
                    realized_pnl   = sum(v for v in _r_vals if v is not None) if _r_has_data else None
                    combined_pnl   = (unrealized_pnl or 0) + (realized_pnl or 0)

                    # Greeks: sum of all legs
                    total_delta = None
                    total_theta = None
                    if "delta" in legs.columns:
                        _d = pd.to_numeric(legs["delta"], errors="coerce").dropna()
                        if not _d.empty:
                            total_delta = float(_d.sum())
                    if "theta" in legs.columns:
                        _t = pd.to_numeric(legs["theta"], errors="coerce").dropna()
                        if not _t.empty:
                            total_theta = float(_t.sum())

                    # DTE: nearest expiration among open legs
                    dte_str = "—"
                    if "expiration" in legs.columns:
                        _open_exp = legs.loc[is_open_legs, "expiration"].dropna()
                        if not _open_exp.empty:
                            _min_exp = pd.to_datetime(_open_exp, errors="coerce").min()
                            if pd.notna(_min_exp):
                                _dte_days = (_min_exp.normalize() - _today_dt).days
                                dte_str = f"{_dte_days}d"

                    _sum_rows.append({
                        "Ticker":          legs["ticker"].iloc[0],
                        "Spread Type":     stype_display,
                        "Legs":            len(legs),
                        "Status":          status,
                        "Delta":           fmt_num(total_delta, 4) if total_delta is not None else "—",
                        "Theta":           fmt_num(total_theta, 4) if total_theta is not None else "—",
                        "Unrealized P&L":  fmt_pnl(unrealized_pnl) if unrealized_pnl is not None else "—",
                        "Realized P&L":    fmt_pnl(realized_pnl)   if realized_pnl   is not None else "—",
                        "Total P&L":       fmt_pnl(combined_pnl) if (_u_has_data or _r_has_data) else "—",
                        "DTE":             dte_str,
                        "_grp":            str(grp),   # hidden key for detail lookup
                    })
                    _grp_index[str(grp)] = legs.copy()

                # ── One expander per spread (inline expand arrow) ─────────
                for _sr in _sum_rows:
                    _exp_title = (
                        f"**{_sr['Ticker']}**  ·  {_sr['Spread Type']}  ·  "
                        f"{_sr['Legs']} legs  ·  {_sr['Status']}  ·  "
                        f"P&L: {_sr['Total P&L']}"
                        + (f"  ·  DTE: {_sr['DTE']}" if _sr['DTE'] != "—" else "")
                    )
                    with st.expander(_exp_title, expanded=False):
                        # Summary metrics row
                        _em1, _em2, _em3, _em4, _em5 = st.columns(5)
                        _em1.metric("Delta",          _sr["Delta"])
                        _em2.metric("Theta",          _sr["Theta"])
                        _em3.metric("Unrealized P&L", _sr["Unrealized P&L"])
                        _em4.metric("Realized P&L",   _sr["Realized P&L"])
                        _em5.metric("DTE",            _sr["DTE"])

                        # Legs table — only include columns that exist
                        _leg_rows = _grp_index[_sr["_grp"]]
                        _leg_col_map = {
                            "ticker":       "Ticker",
                            "leg_label":    "Label",
                            "side":         "Side",
                            "quantity":     "Qty",
                            "entry_price":  "Entry",
                            "exit_price":   "Exit",
                            "expiration":   "Expiration",
                            "strike":       "Strike",
                            "option_type":  "Type",
                            "delta":        "Delta",
                            "theta":        "Theta",
                        }
                        _avail = {k: v for k, v in _leg_col_map.items()
                                  if k in _leg_rows.columns}
                        _leg_disp = _leg_rows[list(_avail.keys())].copy()
                        _leg_disp = _leg_disp.rename(columns=_avail)

                        # Apply sign to Qty: sells are negative, buys positive
                        if "Qty" in _leg_disp and "Side" in _leg_disp:
                            def _signed_qty(r):
                                try:
                                    q = int(r["Qty"]) if r["Qty"] is not None and not pd.isna(r["Qty"]) else 0
                                    s = str(r.get("Side") or "").lower()
                                    return f"-{abs(q):,}" if s in ("sell", "short", "s") else f"+{abs(q):,}"
                                except Exception:
                                    return str(r["Qty"])
                            _leg_disp["Qty"] = _leg_disp.apply(_signed_qty, axis=1)

                        if "Entry" in _leg_disp:
                            _leg_disp["Entry"] = _leg_disp["Entry"].apply(fmt_price)
                        if "Exit" in _leg_disp:
                            _leg_disp["Exit"] = _leg_disp["Exit"].apply(
                                lambda v: fmt_price(v) if v is not None and not pd.isna(v) else "—"
                            )
                        if "Expiration" in _leg_disp:
                            _leg_disp["Expiration"] = _leg_disp["Expiration"].apply(
                                lambda v: fmt_date(v, euro_dates) if v is not None and not pd.isna(v) else "—"
                            )
                        if "Strike" in _leg_disp:
                            _leg_disp["Strike"] = _leg_disp["Strike"].apply(fmt_price)
                        if "Delta" in _leg_disp:
                            _leg_disp["Delta"] = _leg_disp["Delta"].apply(
                                lambda v: fmt_num(float(v), 4) if v is not None and not pd.isna(v) else "—"
                            )
                        if "Theta" in _leg_disp:
                            _leg_disp["Theta"] = _leg_disp["Theta"].apply(
                                lambda v: fmt_num(float(v), 4) if v is not None and not pd.isna(v) else "—"
                            )
                        st.dataframe(_leg_disp, width='stretch', hide_index=True)

    # ── Trade Chart ───────────────────────────────────────────────────────────

    if not trades.empty:
        chart_open = bool(st.session_state.get("chart_trade_id"))
        with st.expander("📊  Trade Chart", expanded=chart_open):

            chart_labels = trades.apply(trade_label, axis=1).tolist()

            # Default to session-state trade or first
            default_chart_idx = 0
            preset_id = st.session_state.get("chart_trade_id")
            if preset_id is not None:
                preset_matches = trades[trades["id"] == preset_id]
                if not preset_matches.empty:
                    preset_lbl = trade_label(preset_matches.iloc[0])
                    if preset_lbl in chart_labels:
                        default_chart_idx = chart_labels.index(preset_lbl)

            chart_lbl = st.selectbox("Select trade", chart_labels,
                                     index=default_chart_idx, key="chart_trade_sel")
            chart_row = trades.iloc[chart_labels.index(chart_lbl)]

            # Always chart the underlying ticker (not OCC symbol)
            chart_ticker = chart_row["ticker"]
            entry_d      = pd.to_datetime(chart_row["entry_date"])
            exit_d       = pd.to_datetime(chart_row["exit_date"]) if (
                               chart_row["exit_date"] and not pd.isna(chart_row["exit_date"])
                           ) else today_ts

            chart_end = (exit_d + pd.Timedelta(days=5)).strftime("%Y-%m-%d")

            # Time frame selector — controls how much history is shown before chart_end
            _tf_cols = st.columns([3, 2])
            with _tf_cols[1]:
                _tf_labels = ["Auto", "1M", "3M", "6M", "1Y", "2Y"]
                _chart_tf  = st.radio(
                    "Time frame", _tf_labels, horizontal=True,
                    index=0, key="chart_tf",
                    help="Auto = 3 months before entry; others = lookback from exit date",
                )
            if _chart_tf == "Auto":
                chart_start = (entry_d - pd.DateOffset(months=3)).strftime("%Y-%m-%d")
            else:
                _tf_months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "2Y": 24}[_chart_tf]
                chart_start = (exit_d - pd.DateOffset(months=_tf_months)).strftime("%Y-%m-%d")

            # Sector ETF
            sector     = get_ticker_sector(chart_ticker)
            sector_etf = SECTOR_ETF_MAP.get(sector) if sector else None

            overlay_opts = ["SPY", "QQQ"]
            if sector_etf and sector_etf not in overlay_opts:
                overlay_opts.append(f"{sector_etf} ({sector})")

            with _tf_cols[0]:
                selected_overlays = st.multiselect("Overlays", overlay_opts, default=[], key="chart_overlays")
                selected_smas = st.multiselect(
                    "Moving averages (SMA)", [20, 50, 150, 200], default=[],
                    key="chart_smas",
                    help="Simple moving averages of the closing price, drawn on the price axis",
                )

            chart_df = load_chart_data(chart_ticker, chart_start, chart_end)

            if chart_df.empty:
                st.warning(f"No price data found for {chart_ticker}.")
            else:
                fig = go.Figure()

                # Candlestick — main series
                fig.add_candlestick(
                    x=chart_df.index,
                    open=chart_df["Open"],
                    high=chart_df["High"],
                    low=chart_df["Low"],
                    close=chart_df["Close"],
                    name=chart_ticker,
                    increasing_line_color="#2ecc71",
                    decreasing_line_color="#e74c3c",
                    showlegend=True,
                )

                # Volume — colored bars on a dedicated bottom panel (yaxis y3)
                if "Volume" in chart_df.columns and chart_df["Volume"].notna().any():
                    _vol_colors = [
                        "rgba(46, 204, 113, 0.45)" if c >= o else "rgba(231, 76, 60, 0.45)"
                        for o, c in zip(chart_df["Open"], chart_df["Close"])
                    ]
                    fig.add_bar(
                        x=chart_df.index,
                        y=chart_df["Volume"],
                        marker_color=_vol_colors,
                        name="Volume",
                        yaxis="y3",
                        showlegend=False,
                        hovertemplate="Vol %{y:,.0f}<extra></extra>",
                    )

                # Simple moving averages — drawn on the price axis. Fetch extra
                # history before the visible window so longer SMAs (e.g. 200) are
                # valid from the chart's left edge instead of starting blank.
                if selected_smas:
                    _sma_colors = {20: "#f1c40f", 50: "#1abc9c", 150: "#9b59b6", 200: "#e84393"}
                    _max_p = max(selected_smas)
                    _sma_start = (
                        pd.Timestamp(chart_start) - pd.Timedelta(days=int(_max_p * 1.6) + 15)
                    ).strftime("%Y-%m-%d")
                    _sma_src = load_chart_data(chart_ticker, _sma_start, chart_end)
                    if not _sma_src.empty and "Close" in _sma_src.columns:
                        _vis_start = pd.Timestamp(chart_start)
                        for _p in sorted(selected_smas):
                            _sma = _sma_src["Close"].rolling(_p).mean()
                            _sma = _sma[_sma.index >= _vis_start]
                            fig.add_scatter(
                                x=_sma.index, y=_sma, mode="lines",
                                name=f"SMA {_p}",
                                line=dict(width=1.3, color=_sma_colors.get(_p)),
                                hovertemplate=f"SMA {_p} " + "%{y:.2f}<extra></extra>",
                            )

                # Trade-window shading
                # Pass dates as strings — plotly's annotation arithmetic breaks with Timestamps in pandas ≥2.x
                trade_is_open = _is_open(chart_row)
                entry_s = entry_d.strftime("%Y-%m-%d")
                exit_s  = exit_d.strftime("%Y-%m-%d")
                fig.add_vrect(
                    x0=entry_s, x1=exit_s,
                    fillcolor="rgba(52, 152, 219, 0.12)",
                    layer="below", line_width=0,
                )
                # add_vline with annotation_text triggers plotly's _mean() on string x-values — use shape+annotation instead
                fig.add_shape(type="line", x0=entry_s, x1=entry_s, y0=0, y1=1,
                              xref="x", yref="paper",
                              line=dict(dash="dash", color="#3498db", width=1))
                fig.add_annotation(x=entry_s, y=1, xref="x", yref="paper",
                                   text="Entry", showarrow=False, xanchor="left",
                                   font=dict(color="#3498db"), yshift=4)
                if not trade_is_open:
                    fig.add_shape(type="line", x0=exit_s, x1=exit_s, y0=0, y1=1,
                                  xref="x", yref="paper",
                                  line=dict(dash="dash", color="#e67e22", width=1))
                    fig.add_annotation(x=exit_s, y=1, xref="x", yref="paper",
                                       text="Exit", showarrow=False, xanchor="right",
                                       font=dict(color="#e67e22"), yshift=4)

                # Mark entry / exit price levels. Skipped for option legs, which are
                # priced in premium and don't sit on the underlying's price scale.
                _chart_inst = str(chart_row.get("instrument_type") or "stock")
                if _chart_inst != "option":
                    _entry_px = chart_row.get("entry_price")
                    if _entry_px is not None and not pd.isna(_entry_px):
                        _entry_px = float(_entry_px)
                        fig.add_shape(type="line", x0=entry_s, x1=exit_s,
                                      y0=_entry_px, y1=_entry_px, xref="x", yref="y",
                                      line=dict(dash="dot", color="#3498db", width=1))
                        fig.add_scatter(
                            x=[entry_d], y=[_entry_px], mode="markers",
                            marker=dict(symbol="diamond", size=11, color="#3498db",
                                        line=dict(color="#ffffff", width=1)),
                            name="Entry price", showlegend=False,
                            hovertemplate=f"Entry ${_entry_px:,.2f}<extra></extra>",
                        )
                        fig.add_annotation(x=entry_s, y=_entry_px, xref="x", yref="y",
                                           text=f"Entry ${_entry_px:,.2f}", showarrow=False,
                                           xanchor="right", xshift=-6,
                                           font=dict(size=10, color="#3498db"),
                                           bgcolor="rgba(0,0,0,0.35)")
                    _exit_px = chart_row.get("exit_price")
                    if not trade_is_open and _exit_px is not None and not pd.isna(_exit_px):
                        _exit_px = float(_exit_px)
                        fig.add_shape(type="line", x0=entry_s, x1=exit_s,
                                      y0=_exit_px, y1=_exit_px, xref="x", yref="y",
                                      line=dict(dash="dot", color="#e67e22", width=1))
                        fig.add_scatter(
                            x=[exit_d], y=[_exit_px], mode="markers",
                            marker=dict(symbol="diamond", size=11, color="#e67e22",
                                        line=dict(color="#ffffff", width=1)),
                            name="Exit price", showlegend=False,
                            hovertemplate=f"Exit ${_exit_px:,.2f}<extra></extra>",
                        )
                        fig.add_annotation(x=exit_s, y=_exit_px, xref="x", yref="y",
                                           text=f"Exit ${_exit_px:,.2f}", showarrow=False,
                                           xanchor="left", xshift=6,
                                           font=dict(size=10, color="#e67e22"),
                                           bgcolor="rgba(0,0,0,0.35)")

                # Overlays — plotted as % change from their first close on a
                # dedicated right-hand axis. Previously they were rebased onto the
                # underlying's price and shared the candlestick's y-axis, so any
                # overlay whose range differed stretched the axis and squashed the
                # candles. A separate %-axis lets the candles auto-scale on their
                # own while the comparison stays clearly readable.
                _overlay_drawn = False
                for ov in selected_overlays:
                    ov_ticker = ov.split(" ")[0]
                    ov_df = load_chart_data(ov_ticker, chart_start, chart_end)
                    if ov_df.empty:
                        continue
                    ov_first = float(ov_df["Close"].iloc[0])
                    if ov_first == 0:
                        continue
                    ov_pct = (ov_df["Close"] / ov_first - 1.0) * 100.0
                    fig.add_scatter(
                        x=ov_df.index,
                        y=ov_pct,
                        mode="lines",
                        name=f"{ov_ticker} %",
                        line=dict(width=1.5),
                        yaxis="y2",
                        hovertemplate="%{y:.2f}%<extra>" + ov_ticker + "</extra>",
                    )
                    _overlay_drawn = True

                # Add-to-position markers (triangles at each additional buy lot)
                _chart_lots = load_trade_lots(int(chart_row["id"]))
                _add_lots = [l for l in _chart_lots if l["lot_type"] == "add"]
                if _add_lots:
                    _lot_dates  = []
                    _lot_prices = []
                    _lot_labels = []
                    for _l in _add_lots:
                        _lot_date_str = _l["date"]
                        _lot_qty      = _l["quantity"]
                        _lot_price    = _l["price"]
                        # Find the chart close on or after the lot date to position the marker
                        _lot_ts = pd.Timestamp(_lot_date_str)
                        _chart_after = chart_df[chart_df.index >= _lot_ts]
                        if not _chart_after.empty:
                            _lot_dates.append(_chart_after.index[0])
                        else:
                            _lot_dates.append(_lot_ts)
                        _lot_prices.append(_lot_price)
                        _lot_labels.append(f"Add {_lot_qty:g} @ {_lot_price:.2f}")
                    fig.add_scatter(
                        x=_lot_dates,
                        y=_lot_prices,
                        mode="markers+text",
                        marker=dict(
                            symbol="triangle-up",
                            size=14,
                            color="#f39c12",
                            line=dict(color="#e67e22", width=1.5),
                        ),
                        text=_lot_labels,
                        textposition="top center",
                        textfont=dict(size=10, color="#f39c12"),
                        name="Add to Position",
                        hovertemplate="%{text}<extra></extra>",
                    )

                trade_status = "Open" if trade_is_open else "Closed"
                fig.update_layout(
                    title=f"{chart_ticker}  ·  "
                          f"{fmt_date(chart_row['entry_date'], euro_dates)} → "
                          f"{fmt_date(chart_row['exit_date'] if not trade_is_open else str(today_ts.date()), euro_dates)}"
                          f"  ({trade_status})",
                    xaxis_rangeslider_visible=False,
                    hovermode="x unified",
                    height=600,
                    # Price candles occupy the top ~75%; volume sits in the bottom panel
                    yaxis=dict(domain=[0.26, 1.0], title="Price"),
                    yaxis3=dict(
                        domain=[0.0, 0.18], title="Volume",
                        showgrid=False, side="left",
                    ),
                    bargap=0.1,
                )
                if _overlay_drawn:
                    # Right-hand %-axis for the overlays; move the legend up so it
                    # doesn't collide with the axis title.
                    fig.update_layout(
                        yaxis2=dict(
                            title="Overlay % change",
                            overlaying="y", side="right",
                            showgrid=False, zeroline=True,
                            zerolinecolor="rgba(255,255,255,0.18)",
                            ticksuffix="%",
                        ),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                    xanchor="left", x=0),
                    )
                # Collapse non-trading days (weekends) so the chart tracks like a
                # standard trading chart instead of showing flat weekend gaps.
                fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
                st.plotly_chart(fig, width='stretch')

            # ── Chart notes ───────────────────────────────────────────────────
            st.markdown("#### Chart Notes")
            _chart_id   = int(chart_row["id"])
            _cur_cnotes = str(chart_row.get("chart_notes") or "")
            _new_cnotes = st.text_area("Notes for this chart", value=_cur_cnotes,
                                       height=100, key="chart_notes_input",
                                       placeholder="Observations, patterns, setups…")
            if st.button("Save Chart Notes", key="save_chart_notes"):
                update_chart_notes(_chart_id, _new_cnotes)
                st.success("Chart notes saved.")
                st.rerun()

    # ── Edit Trade ────────────────────────────────────────────────────────────

    if not trades.empty:
        with st.expander("✏️  Edit Trade"):
            _et_all_labels = trades.apply(trade_label, axis=1).tolist()
            _et_search     = st.text_input("🔍 Search (ticker, date, or ID)", key="et_search",
                                            placeholder="Type to filter…")
            _et_f_labels   = [o for o in _et_all_labels if _et_search.lower() in o.lower()] \
                              if _et_search else _et_all_labels
            selected_label = st.selectbox("Select trade", options=_et_f_labels,
                                          index=0 if _et_f_labels else None, key="et_select")
            selected_idx   = _et_all_labels.index(selected_label) if selected_label else 0
            row            = trades.iloc[selected_idx]
            trade_id       = int(row["id"])
            inst_type      = str(row.get("instrument_type") or "stock").lower()

            current_tag_ids   = get_trade_tag_ids(trade_id)
            current_tag_names = [tag_id_to_name[i] for i in current_tag_ids if i in tag_id_to_name]

            with st.form("edit_trade"):
                st.markdown("**Core Fields**")
                ee1, ee2, ee3, ee4 = st.columns(4)
                edit_entry_date = ee1.date_input(
                    "Entry Date",
                    value=pd.to_datetime(row["entry_date"]).date()
                          if row["entry_date"] and not pd.isna(row["entry_date"]) else None,
                )
                edit_ticker = ee2.text_input("Ticker", value=str(row["ticker"] or ""))
                edit_qty    = ee3.number_input("Quantity", min_value=0.0, step=1.0, format="%.4f",
                                               value=float(row["quantity"]) if row["quantity"] else None)
                edit_entry_price = ee4.number_input(
                    "Entry Price", min_value=0.0, step=0.01, format="%.4f",
                    value=float(row["entry_price"]) if row["entry_price"] else None,
                )
                ec1, ec2 = st.columns(2)
                edit_exit_date = ec1.date_input(
                    "Exit Date",
                    value=pd.to_datetime(row["exit_date"]).date()
                          if row["exit_date"] and not pd.isna(row["exit_date"]) else None,
                )
                edit_exit_price = ec2.number_input(
                    "Exit Price", min_value=0.0, step=0.01, format="%.4f",
                    value=float(row["exit_price"]) if row["exit_price"] else None,
                )

                # Account and commission
                ea1, ea2, ea3 = st.columns(3)
                _cur_acct = str(row.get("account_name") or "Default")
                _acct_opts = list(set(all_accounts + [_cur_acct]))
                edit_account    = ea1.selectbox("Account", options=_acct_opts,
                                               index=_acct_opts.index(_cur_acct) if _cur_acct in _acct_opts else 0,
                                               key="edit_acct")
                edit_commission = ea2.number_input("Commission ($)", min_value=0.0, step=0.01, format="%.2f",
                                                   value=float(row["commission"]) if row.get("commission") else 0.0,
                                                   key="edit_comm")
                edit_side = ea3.selectbox("Side", ["long", "short"],
                                          index=0 if str(row.get("side") or "long").lower() == "long" else 1,
                                          key="edit_side")

                edit_tags  = st.multiselect("Tags", options=list(tag_name_to_id.keys()),
                                            default=current_tag_names)
                edit_notes = st.text_area("Notes", value=row["notes"] or "", height=80)

                # Instrument-specific fields
                if inst_type == "stock":
                    st.markdown("**Stop Loss**")
                    es1, es2, es3, es4 = st.columns([1, 2, 2, 1])
                    edit_stop_en  = es1.checkbox("Enabled", value=bool(row["stop_enabled"]))
                    opening_val   = float(row["opening_stop"]) if row["opening_stop"] else None
                    current_val   = float(row["current_stop"]) if row["current_stop"] is not None else opening_val
                    edit_opening_stop = es2.number_input("Opening Stop", min_value=0.0, step=0.01,
                                                          format="%.4f", value=opening_val,
                                                          help="Initial stop set at entry.")
                    edit_current_stop = es3.number_input("Current Stop", min_value=0.0, step=0.01,
                                                          format="%.4f", value=current_val)
                    _cur_trail_en = str(row.get("trail_type") or "fixed") != "fixed"
                    edit_trailing_en = es4.checkbox("Trailing", value=_cur_trail_en, key="edit_trailing_en")
                    if edit_trailing_en:
                        _etr1, _etr2 = st.columns(2)
                        _cur_trail_type = str(row.get("trail_type") or "$")
                        if _cur_trail_type == "fixed":
                            _cur_trail_type = "$"
                        _trail_opts = ["$", "%", "ATR"]
                        edit_trail_type   = _etr1.selectbox("Trail Unit", _trail_opts,
                                                             index=_trail_opts.index(_cur_trail_type) if _cur_trail_type in _trail_opts else 0,
                                                             key="edit_trail_type")
                        _cur_trail_amount = float(row["trail_amount"]) if row.get("trail_amount") and not pd.isna(row["trail_amount"]) else None
                        edit_trail_amount = _etr2.number_input("Trail Amount", min_value=0.0, step=0.01,
                                                                format="%.2f", value=_cur_trail_amount,
                                                                key="edit_trail_amount")
                    else:
                        edit_trail_type, edit_trail_amount = "fixed", None
                    edit_expiration = edit_strike = edit_option_type = edit_multiplier = None

                elif inst_type == "option":
                    st.markdown("**Option Details**")
                    eo1, eo2, eo3, eo4 = st.columns(4)
                    _raw_exp = row.get("expiration")
                    _exp_val = pd.to_datetime(_raw_exp).date() if _raw_exp and not pd.isna(_raw_exp) else None
                    edit_expiration = eo1.date_input("Expiration", value=_exp_val, key="edit_exp")
                    edit_strike     = eo2.number_input("Strike", min_value=0.0, step=0.5, format="%.2f",
                                                       value=float(row["strike"]) if row.get("strike") else None,
                                                       key="edit_strike")
                    _opt_choices = ["Call", "Put"]
                    _opt_idx = 0 if str(row.get("option_type") or "C").upper().startswith("C") else 1
                    edit_opt_type_raw = eo3.selectbox("C/P", _opt_choices, index=_opt_idx, key="edit_opttype")
                    edit_option_type  = "C" if edit_opt_type_raw == "Call" else "P"
                    edit_multiplier   = eo4.number_input("Multiplier", min_value=0.1, step=1.0, format="%.0f",
                                                          value=float(row["multiplier"]) if row.get("multiplier") else 100.0,
                                                          key="edit_mult")
                    _und_px = row.get("underlying_price_at_entry")
                    edit_underlying_px = st.number_input("Underlying Price at Entry", min_value=0.0,
                                                         step=0.01, format="%.2f",
                                                         value=float(_und_px) if _und_px and not pd.isna(_und_px) else None,
                                                         key="edit_und_px")
                    edit_stop_en = False
                    edit_current_stop = edit_opening_stop = None
                    st.caption(f"Contract: **{_contract_sym(row)}**")

                else:  # future
                    st.markdown("**Future Details**")
                    edit_multiplier = st.number_input("Multiplier", min_value=0.1, step=1.0, format="%.0f",
                                                      value=float(row["multiplier"]) if row.get("multiplier") else 50.0,
                                                      key="edit_fut_mult")
                    edit_stop_en = False
                    edit_current_stop = edit_opening_stop = edit_expiration = edit_strike = edit_option_type = None

                # Earnings date override
                st.markdown("**Earnings Date Override**")
                _auto_earn = fetch_next_earnings(row["ticker"]) if _is_open(row) else None
                _manual_earn = row.get("earnings_date")
                _earn_help = f"Auto-fetched: {_auto_earn}" if _auto_earn else "No upcoming earnings found automatically."
                _earn_default = None
                if _manual_earn and not pd.isna(_manual_earn) and str(_manual_earn).strip():
                    try:
                        _earn_default = pd.to_datetime(_manual_earn).date()
                    except Exception:
                        pass
                elif _auto_earn:
                    try:
                        _earn_default = pd.to_datetime(_auto_earn).date()
                    except Exception:
                        pass
                edit_earnings = st.date_input("Earnings Date", value=_earn_default,
                                              help=_earn_help, key="edit_earnings_dt")

                st.caption("Ctrl+Enter to submit")
                if st.form_submit_button("Save Changes", width='stretch'):
                    edit_tag_ids = [tag_name_to_id[n] for n in edit_tags]
                    update_trade(
                        trade_id,
                        edit_exit_date, edit_exit_price,
                        edit_notes, edit_current_stop, edit_stop_en, edit_tag_ids,
                        entry_date=edit_entry_date,
                        ticker=edit_ticker if edit_ticker.strip() else None,
                        quantity=edit_qty,
                        entry_price=edit_entry_price,
                        opening_stop=edit_opening_stop if inst_type == "stock" else None,
                        expiration=edit_expiration,
                        strike=edit_strike,
                        option_type=edit_option_type,
                        multiplier=edit_multiplier,
                        side=edit_side,
                        commission=edit_commission,
                        account_name=edit_account,
                        trail_type=edit_trail_type if inst_type == "stock" else None,
                        trail_amount=float(edit_trail_amount) if inst_type == "stock" and edit_trail_amount else None,
                    )
                    if inst_type == "option" and "edit_underlying_px" in locals():
                        with get_connection() as _conn:
                            _conn.execute("UPDATE trades SET underlying_price_at_entry=? WHERE id=?",
                                         (edit_underlying_px or None, trade_id))
                    earn_str = edit_earnings.isoformat() if edit_earnings else ""
                    update_earnings_override(trade_id, earn_str)
                    st.success("Trade updated.")
                    st.rerun()

            st.markdown("**Attachments**")
            existing_atts = load_attachments(trade_id)
            if existing_atts:
                for att in existing_atts:
                    ac1, ac2 = st.columns([6, 1])
                    ac1.write(att["filename"])
                    if ac2.button("✕", key=f"del_att_{att['id']}", help="Remove"):
                        delete_attachment(att["id"], att["filepath"])
                        st.rerun()
            else:
                st.caption("No attachments yet.")
            new_files = st.file_uploader("Add files", accept_multiple_files=True,
                                         type=["png", "jpg", "jpeg", "gif", "pdf", "webp"],
                                         key=f"edit_att_{trade_id}")
            if new_files and st.button("Upload Files"):
                for f in new_files:
                    save_attachment(trade_id, f)
                st.rerun()

    # ── Delete Trade ──────────────────────────────────────────────────────────

    if not trades.empty:
        with st.expander("🗑️  Delete Trade"):
            _dt_all_labels = trades.apply(trade_label, axis=1).tolist()
            _dt_search     = st.text_input("🔍 Search (ticker, date, or ID)", key="dt_search",
                                            placeholder="Type to filter…")
            _dt_f_labels   = [o for o in _dt_all_labels if _dt_search.lower() in o.lower()] \
                              if _dt_search else _dt_all_labels
            del_label = st.selectbox("Select trade to delete", options=_dt_f_labels,
                                     index=0 if _dt_f_labels else None, key="del_select")
            del_idx   = _dt_all_labels.index(del_label) if del_label else 0
            del_id    = int(trades.iloc[del_idx]["id"])
            st.warning("This cannot be undone.")
            confirmed = st.checkbox("I confirm I want to permanently delete this trade", key="del_confirm")
            if st.button("Delete Trade", type="primary", disabled=not confirmed):
                delete_trade(del_id)
                if st.session_state.get("chart_trade_id") == del_id:
                    del st.session_state["chart_trade_id"]
                st.rerun()


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — TRADING TOOLS
# ════════════════════════════════════════════════════════════════════════════════

elif page == "🛠️  Trading Tools":

    # ── Existing: Position Size + Risk/Reward ─────────────────────────────────
    tool_left, tool_right = st.columns(2)

    with tool_left:
        st.subheader("Position Size Calculator")
        ps1, ps2 = st.columns(2)
        account_size = ps1.number_input("Account Size ($)", min_value=0.0, step=1000.0,
                                        format="%.2f", value=None)
        risk_pct     = ps1.number_input("Risk per Trade (%)", min_value=0.0, max_value=100.0,
                                        step=0.1, format="%.2f", value=1.0)
        ps_entry     = ps2.number_input("Entry Price ($)", min_value=0.0, step=0.01, format="%.2f", value=None)
        ps_stop      = ps2.number_input("Stop Price ($)", min_value=0.0, step=0.01, format="%.2f", value=None)
        if account_size and risk_pct and ps_entry and ps_stop and ps_entry != ps_stop:
            dollar_risk    = account_size * (risk_pct / 100)
            risk_per_share = abs(ps_entry - ps_stop)
            shares         = dollar_risk / risk_per_share
            m1, m2, m3 = st.columns(3)
            m1.metric("Max Shares",     fmt_qty(shares))
            m2.metric("Dollar Risk",    fmt_price(dollar_risk))
            m3.metric("Position Value", fmt_price(shares * ps_entry))

    with tool_right:
        st.subheader("Risk / Reward Calculator")
        rr1, rr2, rr3 = st.columns(3)
        rr_entry  = rr1.number_input("Entry ($)",  min_value=0.0, step=0.01, format="%.2f", value=None)
        rr_stop   = rr2.number_input("Stop ($)",   min_value=0.0, step=0.01, format="%.2f", value=None)
        rr_target = rr3.number_input("Target ($)", min_value=0.0, step=0.01, format="%.2f", value=None)
        if rr_entry and rr_stop and rr_target and rr_entry != rr_stop:
            risk_pts     = abs(rr_entry - rr_stop)
            reward_pts   = abs(rr_target - rr_entry)
            rr_ratio     = reward_pts / risk_pts
            m1, m2, m3   = st.columns(3)
            m1.metric("Risk",      fmt_price(risk_pts),   f"{risk_pts/rr_entry*100:.2f}%")
            m2.metric("Reward",    fmt_price(reward_pts), f"{reward_pts/rr_entry*100:.2f}%")
            m3.metric("R:R Ratio", f"1 : {rr_ratio:.2f}")

    st.markdown("""
<style>
[data-testid="stExpander"] > details > summary ~ div {
    padding: 1rem 1.25rem 1.5rem;
}
</style>
""", unsafe_allow_html=True)

    st.divider()

    # ── Row 1: ATR Calculator | Stop Calculator ───────────────────────────────
    _tc1, _tc2 = st.columns(2, gap="large")

    with _tc1:
        with st.expander("📐  ATR Calculator", expanded=True):
            at1, at2 = st.columns([2, 1])
            atr_ticker = at1.text_input("Ticker", placeholder="e.g. AAPL", key="atr_ticker")
            atr_period = at2.number_input("Period", min_value=1, max_value=100, value=14, step=1,
                                          format="%d", key="atr_period")
            if atr_ticker.strip():
                try:
                    _atr_raw = yf.download(atr_ticker.strip().upper(),
                                           period=f"{atr_period + 10}d",
                                           auto_adjust=True, progress=False)
                    if isinstance(_atr_raw.columns, pd.MultiIndex):
                        _atr_raw.columns = _atr_raw.columns.get_level_values(0)
                    if not _atr_raw.empty and len(_atr_raw) >= atr_period:
                        _h  = _atr_raw["High"]
                        _lo = _atr_raw["Low"]
                        _c  = _atr_raw["Close"]
                        _pc = _c.shift(1)
                        _tr = pd.concat([(_h - _lo).abs(), (_h - _pc).abs(), (_lo - _pc).abs()], axis=1).max(axis=1)
                        _atr_val  = float(_tr.rolling(atr_period).mean().dropna().iloc[-1])
                        _last_px  = float(_c.iloc[-1])
                        _atr_pct  = _atr_val / _last_px * 100
                        atr_mult = st.number_input(
                            "ATR Multiplier", min_value=0.1, max_value=20.0,
                            step=0.5, format="%.1f", value=2.0, key="atr_calc_mult",
                            help="Multiply ATR to calculate stop distance or breakout range.",
                        )
                        am1, am2, am3 = st.columns(3)
                        am1.metric("Last Price",            fmt_price(_last_px))
                        am2.metric(f"ATR ({atr_period})",   fmt_price(_atr_val))
                        am3.metric("ATR %",                 f"{_atr_pct:.2f}%")
                        am4, am5, am6 = st.columns(3)
                        _atr_mult_val = _atr_val * atr_mult
                        _long_stop    = _last_px - _atr_mult_val
                        _short_stop   = _last_px + _atr_mult_val
                        am4.metric(f"ATR × {atr_mult:.1f}",   fmt_price(_atr_mult_val),
                                   help="Stop distance in dollars at this multiplier.")
                        am5.metric("Long Stop Price",           fmt_price(_long_stop),
                                   help=f"Entry − ATR × {atr_mult:.1f}")
                        am6.metric("Short Stop Price",          fmt_price(_short_stop),
                                   help=f"Entry + ATR × {atr_mult:.1f}")
                        st.session_state["_tool_atr"]      = _atr_val
                        st.session_state["_tool_last_px"]  = _last_px
                    else:
                        st.warning("Not enough data to compute ATR for that period.")
                except Exception as _e:
                    st.error(f"Could not fetch data: {_e}")

    with _tc2:
        with st.expander("🛑  Stop Calculator", expanded=True):
            sc_mode  = st.radio("Mode", ["% Stop", "ATR Stop"], horizontal=True, key="sc_mode")
            sc_side  = st.radio("Side", ["Long", "Short"],      horizontal=True, key="sc_side")
            sc_entry = st.number_input("Entry Price ($)", min_value=0.0, step=0.01,
                                       format="%.2f", value=None, key="sc_entry")
            if sc_mode == "% Stop":
                sc_pct = st.number_input("Stop %", min_value=0.0, max_value=100.0,
                                         step=0.1, format="%.2f", value=2.0, key="sc_pct")
                if sc_entry and sc_pct:
                    _dir = -1 if sc_side == "Long" else 1
                    _stop_px = sc_entry * (1 + _dir * sc_pct / 100)
                    _dist_d  = abs(sc_entry - _stop_px)
                    sm1, sm2, sm3 = st.columns(3)
                    sm1.metric("Stop Price",   fmt_price(_stop_px))
                    sm2.metric("Distance $",  fmt_price(_dist_d))
                    sm3.metric("Distance %",  f"{sc_pct:.2f}%")
                    st.session_state["_tool_stop_px"] = _stop_px
            else:
                _saved_atr = st.session_state.get("_tool_atr")
                sc_atr = st.number_input("ATR ($)", min_value=0.0, step=0.01, format="%.2f",
                                         value=float(_saved_atr) if _saved_atr else None,
                                         help="Auto-filled from ATR Calculator",
                                         key="sc_atr")
                sc_mult = st.number_input("ATR Multiplier", min_value=0.1, step=0.1,
                                          format="%.1f", value=1.5, key="sc_mult")
                if sc_entry and sc_atr and sc_mult:
                    _dir = -1 if sc_side == "Long" else 1
                    _stop_px = sc_entry + _dir * sc_atr * sc_mult
                    _dist_d  = abs(sc_entry - _stop_px)
                    _dist_pct = _dist_d / sc_entry * 100
                    sm1, sm2, sm3 = st.columns(3)
                    sm1.metric("Stop Price",  fmt_price(_stop_px))
                    sm2.metric("Distance $",  fmt_price(_dist_d))
                    sm3.metric("Distance %",  f"{_dist_pct:.2f}%")
                    st.session_state["_tool_stop_px"] = _stop_px

    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

    # ── Row 2: Share Count (Max Loss) | Share Count (Allocation) ─────────────
    _tc3, _tc4 = st.columns(2, gap="large")

    with _tc3:
        with st.expander("📊  Share Count — Max Loss Based", expanded=True):
            ml_acct  = st.number_input("Account Size ($)", min_value=0.0, step=1000.0,
                                       format="%.2f", value=None, key="ml_acct")
            ml_mode  = st.radio("Max Loss as", ["$ Amount", "% of Account"],
                                 horizontal=True, key="ml_mode")
            if ml_mode == "$ Amount":
                ml_loss = st.number_input("Max Loss ($)", min_value=0.0, step=100.0,
                                          format="%.2f", value=None, key="ml_loss_d")
            else:
                ml_pct  = st.number_input("Max Loss (%)", min_value=0.0, max_value=100.0,
                                          step=0.1, format="%.2f", value=1.0, key="ml_loss_p")
                ml_loss = (ml_acct * ml_pct / 100) if ml_acct and ml_pct else None
            ml_entry = st.number_input("Entry Price ($)", min_value=0.0, step=0.01,
                                       format="%.2f", value=None, key="ml_entry")
            _saved_stop = st.session_state.get("_tool_stop_px")
            ml_stop  = st.number_input("Stop Price ($)", min_value=0.0, step=0.01,
                                       format="%.2f",
                                       value=float(_saved_stop) if _saved_stop else None,
                                       help="Auto-filled from Stop Calculator",
                                       key="ml_stop")
            if ml_loss and ml_entry and ml_stop and abs(ml_entry - ml_stop) > 0:
                _risk_ps = abs(ml_entry - ml_stop)
                _shares  = ml_loss / _risk_ps
                _pos_val = _shares * ml_entry
                _acct_pct = _pos_val / ml_acct * 100 if ml_acct else None
                mm1, mm2 = st.columns(2)
                mm1.metric("Shares",         fmt_qty(_shares))
                mm2.metric("Dollar Risk",    fmt_price(ml_loss))
                mm3, mm4 = st.columns(2)
                mm3.metric("Position Value", fmt_price(_pos_val))
                mm4.metric("% of Account",   fmt_pct(_acct_pct) if _acct_pct else "—")

    with _tc4:
        with st.expander("💰  Share Count — Allocation Based", expanded=True):
            ab_acct = st.number_input("Account Size ($)", min_value=0.0, step=1000.0,
                                      format="%.2f", value=None, key="ab_acct")
            ab_mode = st.radio("Allocation as", ["$ Amount", "% of Portfolio"],
                                horizontal=True, key="ab_mode")
            if ab_mode == "$ Amount":
                ab_alloc = st.number_input("Allocation ($)", min_value=0.0, step=1000.0,
                                           format="%.2f", value=None, key="ab_alloc_d")
            else:
                ab_pct   = st.number_input("Allocation (%)", min_value=0.0, max_value=100.0,
                                           step=0.5, format="%.2f", value=5.0, key="ab_alloc_p")
                ab_alloc = (ab_acct * ab_pct / 100) if ab_acct and ab_pct else None
            ab_entry = st.number_input("Entry Price ($)", min_value=0.0, step=0.01,
                                       format="%.2f", value=None, key="ab_entry")
            ab_stop  = st.number_input("Stop Price (optional, $)", min_value=0.0, step=0.01,
                                       format="%.2f", value=None, key="ab_stop")
            if ab_alloc and ab_entry and ab_entry > 0:
                _shares  = ab_alloc / ab_entry
                am1, am2 = st.columns(2)
                am1.metric("Shares",         fmt_qty(_shares))
                am2.metric("Position Value", fmt_price(ab_alloc))
                if ab_stop and abs(ab_entry - ab_stop) > 0:
                    _risk_d   = _shares * abs(ab_entry - ab_stop)
                    _risk_pct = _risk_d / ab_acct * 100 if ab_acct else None
                    am3, am4  = st.columns(2)
                    am3.metric("Dollar Risk",  fmt_price(_risk_d))
                    am4.metric("Risk % Acct", fmt_pct(_risk_pct) if _risk_pct else "—")


    # ── Portfolio Allocation Plan ─────────────────────────────────────────────
    st.divider()
    st.subheader("🗂️  Portfolio Allocation Plan")
    st.markdown(
        "> **Important:** The *Total Loss Limit* below is **not** your client's entire net worth — "
        "it is only the portion they have consciously set aside for active trading or investing. "
        "The rest of their wealth (super, property, long-term index funds, emergency reserves) "
        "is completely separate and should never be touched regardless of trading outcomes."
    )
    st.caption(
        "This framework answers one question: *if active trading doesn't work out for me, "
        "how do I make sure I don't blow up my financial life in the process?*  "
        "It does that by chopping your trading budget into equal **Resets** — think of them "
        "as re-buys in a poker tournament. You play one Reset at a time. If you lose it all, "
        "you stop, reflect, and decide whether to start the next Reset. You never dip into "
        "the next Reset while the current one is running. Within each Reset, you divide your "
        "budget across enough trades to get a statistically meaningful sample — so your results "
        "actually tell you something real about your edge, rather than just luck."
    )

    st.markdown("---")
    _pa1, _pa2, _pa3 = st.columns(3)

    _pa_total_loss = _pa1.number_input(
        "Total Loss Limit ($)",
        min_value=0.0, step=1000.0, format="%.2f", value=None,
        key="pa_total_loss",
        help=(
            "The absolute maximum you are prepared to lose from your **active trading allocation** "
            "before stepping away from active trading permanently. "
            "Reaching this number means the experiment is over — not the end of your financial life, "
            "just the end of active trading. Set it at a level you can genuinely live with losing."
        ),
    )
    _pa_resets = _pa2.number_input(
        "Total Resets",
        min_value=1, max_value=100, step=1, value=5,
        key="pa_resets",
        help=(
            "How many discrete attempts (Resets) you divide your Total Loss Limit into. "
            "Think of each Reset as one 'season' of trading with its own budget. "
            "Losing a full Reset is your signal to pause, review, and decide consciously "
            "whether to start the next one — not to chase losses. "
            "More Resets = smaller per-Reset budget = more conservative each attempt. "
            "3–10 Resets is a sensible range for most traders."
        ),
    )
    _pa_conf_trades = _pa3.number_input(
        "Trades for Statistical Confidence",
        min_value=5, max_value=1000, step=5, value=20,
        key="pa_conf_trades",
        help=(
            "How many trades you need before your win rate and average P&L reflect genuine skill "
            "rather than short-run luck. "
            "**20 trades** is the practical minimum — results below this are essentially noise. "
            "**50–100 trades** gives high confidence. "
            "The app uses this number to calculate the maximum you should risk per trade, "
            "guaranteeing you can always complete a full confidence sample within one Reset."
        ),
    )

    if _pa_total_loss and _pa_total_loss > 0 and _pa_resets and _pa_conf_trades:
        _per_reset     = _pa_total_loss / _pa_resets
        _per_trade_max = _per_reset / _pa_conf_trades

        st.markdown("---")
        _pr1, _pr2, _pr3, _pr4 = st.columns(4)

        _pr1.metric(
            "Per Reset Loss Limit",
            fmt_price(_per_reset),
            help=(
                f"Total Loss Limit ÷ {_pa_resets} Resets. "
                "This is your entire budget for one trading attempt. "
                "If your account drops by this amount from its Reset starting value, "
                "stop all new trades immediately and take at least 2–4 weeks to review "
                "before deciding whether to start the next Reset."
            ),
        )
        _pr2.metric(
            "Max Risk per Trade",
            fmt_price(_per_trade_max),
            help=(
                f"Per Reset Loss Limit ÷ {_pa_conf_trades} trades. "
                "This is the most you should lose on any single trade within a Reset. "
                "Staying at or below this number guarantees you can always complete "
                f"at least {_pa_conf_trades} trades before exhausting the Reset budget — "
                "enough for your results to be statistically meaningful."
            ),
        )
        _pr3.metric(
            "Reset Budget as % of Total",
            f"{100 / _pa_resets:.1f}%",
            help="Each Reset represents this fraction of your total active-trading allocation.",
        )
        _pr4.metric(
            "Max Risk per Trade as % of Reset",
            f"{1 / _pa_conf_trades * 100:.2f}%",
            help=(
                f"Risk per trade as a percentage of the Reset budget. "
                "Keeping each trade small relative to the Reset is what guarantees "
                "you survive long enough to accumulate a meaningful track record."
            ),
        )

        st.markdown("---")
        st.markdown("##### How this works — plain English")
        st.markdown(
            f"""
| Step | What to do |
|---|---|
| **Before you start** | Fund your trading account with **{fmt_price(_per_reset)}** (Reset 1 of {_pa_resets}). Keep the remaining {fmt_price(_pa_total_loss - _per_reset)} untouched in a separate account or investment. |
| **Each trade** | Risk no more than **{fmt_price(_per_trade_max)}** on a single position — this is your stop-loss dollar amount, not your position size. |
| **After {_pa_conf_trades} trades** | Review your results. A positive expected value after {_pa_conf_trades}+ trades is genuine signal. Adjust your strategy if needed, then continue. |
| **If you lose the full Reset ({fmt_price(_per_reset)})** | Stop. Do not fund the account further yet. Take at least 2–4 weeks to review every trade, identify what went wrong, and make a deliberate decision about whether to start Reset {2 if _pa_resets > 1 else 1}. |
| **If you exhaust all {_pa_resets} Resets** | You have reached your Total Loss Limit of **{fmt_price(_pa_total_loss)}**. This was the agreed price of finding out whether active trading works for you. Your broader financial position is intact. Step away permanently from active trading — passive index investing is always available. |
"""
        )

        st.info(
            f"💡  **Quick check:** your max risk per trade of {fmt_price(_per_trade_max)} means "
            f"you need a position where the distance to your stop × shares = {fmt_price(_per_trade_max)}. "
            f"Use the **Position Size Calculator** and **Stop Calculator** above to find the right share count.",
            icon="💡",
        )

# ════════════════════════════════════════════════════════════════════════════════
# PAGE — EQUITY CURVE
# ════════════════════════════════════════════════════════════════════════════════

elif page == "📈  Equity Curve":
    import xml.etree.ElementTree as _ET
    import io as _io

    _eq_entries = _cached_load_equity_entries(st.session_state["_v_equity"])

    render_tour_panel("📈  Equity Curve")

    _ec_tab_chart, _ec_tab_entry, _ec_tab_import, _ec_tab_flex = st.tabs(
        ["📈 Chart", "✏️ Manual Entry", "📥 Import", "🔗 IB Flex Import"]
    )

    # ── Chart tab ─────────────────────────────────────────────────────────────
    with _ec_tab_chart:
        if not _eq_entries:
            st.info("No equity entries yet. Add entries on the Manual Entry tab or import them.")
        else:
            _ec_df = pd.DataFrame(_eq_entries)
            _ec_df["date"] = pd.to_datetime(_ec_df["date"])
            _ec_df = _ec_df.sort_values("date").reset_index(drop=True)
            _ec_df["contributions"] = _ec_df["contributions"].fillna(0.0)
            _ec_df["withdrawals"]   = _ec_df["withdrawals"].fillna(0.0)

            # Cumulative TWR: chain daily sub-period returns, stripping out cash flows
            _prev_bal = _ec_df["balance"].shift(1)
            _prev_bal.iloc[0] = _ec_df["balance"].iloc[0]  # base day: 0% return
            _denominator = _prev_bal + _ec_df["contributions"] - _ec_df["withdrawals"]
            _period_ret  = np.where(_denominator != 0, _ec_df["balance"] / _denominator - 1, 0.0)
            _period_ret[0] = 0.0  # first entry is the baseline
            _ec_df["twr_pct"] = (pd.Series(_period_ret + 1).cumprod() - 1) * 100

            # ── Controls row 1: benchmarks + view ────────────────────────────
            _ctrl_l, _ctrl_r, _ctrl_s = st.columns([2, 1, 1])
            with _ctrl_l:
                bench_options       = ["SPY", "QQQ", "IWM", "LQD", "JNK", "^VIX"]
                selected_benchmarks = st.multiselect(
                    "Benchmarks", bench_options, default=[],
                    format_func=lambda _t: "VIX" if _t == "^VIX" else _t,
                    help="Normalised to the same start for comparison · VIX is shown on the right axis",
                )
            with _ctrl_r:
                _ec_view = st.radio(
                    "View", ["% Return (TWR)", "Balance ($)"],
                    horizontal=True, key="ec_view_mode",
                )
            with _ctrl_s:
                _ec_smooth = st.slider(
                    "Line smoothing", 0, 100, 0, 5, key="ec_smooth",
                    help="Visually smooths the equity line — it does not average the data",
                )

            # ── Controls row 2: date range ────────────────────────────────────
            _dr_min = _ec_df["date"].min().date()
            _dr_max = _ec_df["date"].max().date()
            _dr_l, _dr_r = st.columns(2)
            _ec_date_from = _dr_l.date_input(
                "From", value=_dr_min, min_value=_dr_min, max_value=_dr_max, key="ec_dr_from"
            )
            _ec_date_to = _dr_r.date_input(
                "To", value=_dr_max, min_value=_dr_min, max_value=_dr_max, key="ec_dr_to"
            )

            # Filter to selected range (TWR already computed on full dataset above)
            _ec_plot_df = _ec_df[
                (_ec_df["date"] >= pd.Timestamp(_ec_date_from)) &
                (_ec_df["date"] <= pd.Timestamp(_ec_date_to))
            ].copy()

            if _ec_plot_df.empty:
                st.warning("No entries in the selected date range.")
            else:
                _show_twr = (_ec_view == "% Return (TWR)")
                _ec_start_str = str(_ec_plot_df["date"].iloc[0].date())
                _ec_start_bal = float(_ec_plot_df["balance"].iloc[0])

                if selected_benchmarks:
                    fetch_benchmark_data(selected_benchmarks, _ec_start_str)

                _ma_days = 20
                if _show_twr:
                    _plot_series = _ec_plot_df["twr_pct"]
                else:
                    _plot_series = _ec_plot_df["balance"]
                _eq_indexed = pd.Series(_plot_series.values, index=_ec_plot_df["date"])
                _ma20_vals  = _eq_indexed.rolling(f"{_ma_days}D", min_periods=1).mean()
                _ec_plot_df["MA20"] = _ma20_vals.values

                fig = go.Figure()
                if _ec_smooth > 0 and len(_ec_plot_df) >= 3:
                    # Force ns resolution both ways — pandas 2.x may store the date
                    # column as datetime64[us], and a unit mismatch on the round-trip
                    # would map the smoothed dates back to 1970.
                    _date_ns = _ec_plot_df["date"].astype("datetime64[ns]").astype("int64")
                    _sx, _sy = smooth_line_xy(
                        _date_ns.to_numpy(),
                        np.asarray(_plot_series, dtype=float),
                        _ec_smooth / 100.0,
                    )
                    _port_x   = pd.to_datetime(_sx.astype("int64"))  # _sx is in ns
                    _port_y   = _sy
                    _port_mode = "lines"
                else:
                    _port_x, _port_y, _port_mode = _ec_plot_df["date"], _plot_series, "lines+markers"
                fig.add_scatter(
                    x=_port_x, y=_port_y,
                    mode=_port_mode, name="Portfolio",
                    line=dict(color="#2ecc71", width=2, shape="spline", smoothing=1.2),
                    marker=dict(size=5),
                )
                fig.add_scatter(
                    x=_ec_plot_df["date"], y=_ec_plot_df["MA20"],
                    mode="lines", name="20-Day MA",
                    line=dict(color="#f39c12", width=1.5, dash="dot", shape="spline"),
                )
                if len(_ec_plot_df) >= 2:
                    fig.add_annotation(
                        x=_ec_plot_df["date"].iloc[-1], y=_ec_plot_df["MA20"].iloc[-1],
                        text="MA20", showarrow=False, xanchor="left", yanchor="middle",
                        font=dict(color="#f39c12", size=11), xshift=6,
                    )

                _vix_drawn = False
                for bench in selected_benchmarks:
                    if bench == "^VIX":
                        # VIX is a volatility index, not a price benchmark — plot its
                        # raw level on the right axis instead of rebasing onto equity.
                        vs = load_benchmark_series("^VIX", _ec_start_str, _ec_start_bal,
                                                   normalize=False)
                        if not vs.empty:
                            fig.add_scatter(
                                x=vs.index, y=vs.values, mode="lines", name="VIX",
                                line=dict(color="#9b59b6", width=1.4, dash="dot",
                                          shape="spline", smoothing=0.8),
                                yaxis="y2",
                                hovertemplate="VIX %{y:.2f}<extra></extra>",
                            )
                            _vix_drawn = True
                        continue
                    bs = load_benchmark_series(bench, _ec_start_str, _ec_start_bal)
                    if not bs.empty:
                        if _show_twr:
                            bs = (bs / bs.iloc[0] - 1) * 100
                        fig.add_scatter(
                            x=bs.index, y=bs.values, mode="lines", name=bench,
                            line=dict(shape="spline", smoothing=0.8),
                        )

                if _show_twr:
                    _ytitle   = "Return (%)"
                    _yprefix  = ""
                    _ysuffix  = "%"
                    _yformat  = ".2f"
                    _ec_title = "Equity Curve — Time-Weighted Return"
                else:
                    _ytitle   = "Portfolio Value ($)"
                    _yprefix  = "$"
                    _ysuffix  = ""
                    _yformat  = ",.0f"
                    _ec_title = "Equity Curve"

                fig.update_layout(
                    title=_ec_title, xaxis_title="Date",
                    yaxis_title=_ytitle, hovermode="x unified",
                    yaxis_tickprefix=_yprefix, yaxis_ticksuffix=_ysuffix,
                    yaxis_tickformat=_yformat,
                    paper_bgcolor=_CHT_BG, plot_bgcolor=_CHT_BG,
                    font=dict(color=_CHT_FONT),
                    xaxis=dict(gridcolor=_CHT_GRID),
                    yaxis=dict(gridcolor=_CHT_GRID),
                )
                if _vix_drawn:
                    fig.update_layout(
                        yaxis2=dict(
                            title="VIX", overlaying="y", side="right",
                            showgrid=False, rangemode="tozero",
                        )
                    )
                st.plotly_chart(fig, width='stretch')

                # ── Core scalars ──────────────────────────────────────────────
                _first_bal    = float(_ec_plot_df["balance"].iloc[0])
                _last_bal     = float(_ec_plot_df["balance"].iloc[-1])
                _net_contribs = float(_ec_plot_df["contributions"].sum() - _ec_plot_df["withdrawals"].sum())
                _twr_total    = float(_ec_plot_df["twr_pct"].iloc[-1])
                _peak_twr     = float(_ec_plot_df["twr_pct"].max())
                _trough_twr   = float(_ec_plot_df.loc[_ec_plot_df["twr_pct"].idxmax():, "twr_pct"].min())
                _max_dd       = _peak_twr - _trough_twr

                # ── Daily sub-period returns for the filtered range ────────────
                _ec_plot_prev  = _ec_plot_df["balance"].shift(1)
                _ec_plot_denom = _ec_plot_prev + _ec_plot_df["contributions"] - _ec_plot_df["withdrawals"]
                _ec_plot_pret  = np.where(_ec_plot_denom > 0, _ec_plot_df["balance"] / _ec_plot_denom - 1, 0.0)
                _daily_ret_ser = pd.Series(
                    _ec_plot_pret[1:], index=_ec_plot_df["date"].iloc[1:]
                )  # drop first (0% baseline)

                # ── Annualised return (CAGR) ──────────────────────────────────
                _n_days = max(1, (_ec_plot_df["date"].iloc[-1] - _ec_plot_df["date"].iloc[0]).days)
                _cagr   = ((1 + _twr_total / 100) ** (365.25 / _n_days) - 1) * 100

                # ── Annualised std dev ─────────────────────────────────────────
                _std_ann = (float(_daily_ret_ser.std(ddof=1)) * np.sqrt(252) * 100
                            if len(_daily_ret_ser) > 1 else float("nan"))

                # ── Risk-Free Rate (slider with auto-fetched default) ──────────
                _rfr_fetched = fetch_risk_free_rate()   # decimal, cached 1h
                st.markdown("---")
                _rfr_col, _rfr_info = st.columns([3, 1])
                with _rfr_col:
                    _rfr_pct = st.slider(
                        "Risk-Free Rate (% annual)",
                        min_value=0.0, max_value=10.0,
                        value=round(_rfr_fetched * 100, 2),
                        step=0.25,
                        key="ec_rfr_slider",
                        help="Used for Sharpe & Sortino. Auto-loaded from the 3-month T-bill (^IRX). Drag to override.",
                    )
                _rfr_info.metric("3-Mo T-Bill", f"{_rfr_fetched*100:.2f}%",
                                 help="Live rate from ^IRX (yfinance). Refreshes hourly.")
                _rfr = _rfr_pct / 100.0   # as decimal
                _daily_rfr = _rfr / 252.0

                # ── Sharpe ────────────────────────────────────────────────────
                _excess_daily  = _daily_ret_ser - _daily_rfr
                _sharpe = (
                    float(_excess_daily.mean() / _excess_daily.std(ddof=1) * np.sqrt(252))
                    if len(_excess_daily) > 1 and _excess_daily.std(ddof=1) > 0
                    else float("nan")
                )

                # ── Sortino ───────────────────────────────────────────────────
                # Downside deviation uses only days below RFR; annualise the ratio
                _downside = _daily_ret_ser[_daily_ret_ser < _daily_rfr] - _daily_rfr
                _sortino = (
                    float((_daily_ret_ser.mean() - _daily_rfr) * np.sqrt(252)
                          / np.sqrt((_downside**2).mean()))
                    if len(_downside) > 1 and (_downside**2).mean() > 0
                    else float("nan")
                )

                # ── Calmar ────────────────────────────────────────────────────
                _calmar = (
                    float((_cagr / 100) / (_max_dd / 100))
                    if _max_dd > 0 else float("nan")
                )

                # ── Best / Worst day and week ──────────────────────────────────
                _best_day  = float(_daily_ret_ser.max() * 100) if not _daily_ret_ser.empty else float("nan")
                _worst_day = float(_daily_ret_ser.min() * 100) if not _daily_ret_ser.empty else float("nan")
                _weekly_rets = ((1 + _daily_ret_ser).resample("W").prod() - 1) * 100
                _best_week  = float(_weekly_rets.max()) if not _weekly_rets.empty else float("nan")
                _worst_week = float(_weekly_rets.min()) if not _weekly_rets.empty else float("nan")

                def _fmt_stat(v, suffix="%", prec=2):
                    return f"{v:+.{prec}f}{suffix}" if not np.isnan(v) else "N/A"
                def _fmt_ratio(v, prec=2):
                    return f"{v:.{prec}f}" if not np.isnan(v) else "N/A"

                # ── Row 1: balance / TWR overview ─────────────────────────────
                _sm1, _sm2, _sm3, _sm4 = st.columns(4)
                _sm1.metric("Current Balance", f"${_last_bal:,.2f}")
                _sm2.metric("TWR (period)", f"{_twr_total:+.2f}%")
                _sm3.metric("Net Contributions", f"${_net_contribs:,.2f}")
                _sm4.metric("Max Drawdown", f"{_max_dd:.2f}%")

                # ── Row 2: return quality ──────────────────────────────────────
                _ra1, _ra2, _ra3, _ra4, _ra5 = st.columns(5)
                _ra1.metric("Annualized Return",  _fmt_stat(_cagr),
                            help="CAGR over the selected date range (TWR compounded to 1 year).")
                _ra2.metric("Std Dev (ann.)", _fmt_stat(_std_ann),
                            help="Annualised standard deviation of daily sub-period returns (×√252).")
                _ra3.metric("Sharpe Ratio", _fmt_ratio(_sharpe),
                            help="(Ann. excess return above RFR) ÷ ann. σ. >1 = good, >2 = excellent.")
                _ra4.metric("Sortino Ratio", _fmt_ratio(_sortino),
                            help="Like Sharpe but σ is computed only on days below the RFR — rewards upside volatility.")
                _ra5.metric("Calmar Ratio", _fmt_ratio(_calmar),
                            help="Annualized return ÷ max drawdown. >1 = return more than compensates the worst drawdown.")

                # ── Row 3: extremes ───────────────────────────────────────────
                _ex1, _ex2, _ex3, _ex4 = st.columns(4)
                _ex1.metric("Best Day",   _fmt_stat(_best_day))
                _ex2.metric("Worst Day",  _fmt_stat(_worst_day))
                _ex3.metric("Best Week",  _fmt_stat(_best_week))
                _ex4.metric("Worst Week", _fmt_stat(_worst_week))

                # ── Histogram of daily returns ─────────────────────────────────
                st.markdown("---")
                st.markdown("#### Return Distribution")
                if len(_daily_ret_ser) >= 3:
                    _hist_data = (_daily_ret_ser * 100).dropna()
                    _hist_mean = float(_hist_data.mean())
                    _hist_fig  = go.Figure()
                    _hist_fig.add_trace(go.Histogram(
                        x=_hist_data,
                        nbinsx=min(40, max(10, len(_hist_data) // 3)),
                        name="Daily Returns",
                        marker_color="#4e8ef7",
                        opacity=0.8,
                    ))
                    _hist_fig.add_vline(x=0, line_width=2, line_dash="dash",
                                        line_color="#e74c3c",
                                        annotation_text="0%", annotation_position="top right",
                                        annotation_font_color="#e74c3c")
                    _hist_fig.add_vline(x=_hist_mean, line_width=1.5, line_dash="dot",
                                        line_color="#f39c12",
                                        annotation_text=f"mean {_hist_mean:+.2f}%",
                                        annotation_position="top left",
                                        annotation_font_color="#f39c12")
                    _hist_fig.update_layout(
                        xaxis_title="Daily Return (%)", yaxis_title="Days",
                        paper_bgcolor=_CHT_BG, plot_bgcolor=_CHT_BG,
                        font=dict(color=_CHT_FONT),
                        xaxis=dict(gridcolor=_CHT_GRID, ticksuffix="%"),
                        yaxis=dict(gridcolor=_CHT_GRID),
                        showlegend=False,
                        height=300,
                        margin=dict(t=20, b=40),
                    )
                    st.plotly_chart(_hist_fig, width='stretch')
                else:
                    st.info("Need at least 3 data points to show the return distribution.")

                # ── Monthly returns table ──────────────────────────────────────
                st.markdown("---")
                st.markdown("#### Monthly Returns")
                if len(_daily_ret_ser) >= 5:
                    _monthly_rets = ((1 + _daily_ret_ser).resample("ME").prod() - 1) * 100
                    _mo_df = pd.DataFrame({
                        "Year":   _monthly_rets.index.year,
                        "Month":  _monthly_rets.index.month,
                        "Return": _monthly_rets.values,
                    })
                    _month_abbr = ["Jan","Feb","Mar","Apr","May","Jun",
                                   "Jul","Aug","Sep","Oct","Nov","Dec"]
                    _mo_df["MonthAbbr"] = _mo_df["Month"].apply(lambda m: _month_abbr[m-1])
                    _mo_pivot = _mo_df.pivot(index="Year", columns="MonthAbbr", values="Return")
                    # Keep months in calendar order for columns that exist
                    _mo_pivot = _mo_pivot.reindex(
                        columns=[m for m in _month_abbr if m in _mo_pivot.columns]
                    )
                    # Annual totals column
                    _mo_pivot["Annual"] = (
                        (1 + _mo_df.groupby("Year")["Return"].apply(
                            lambda s: (s / 100 + 1).prod() - 1
                        )) - 1
                    ) * 100

                    # Optional benchmark overlay
                    _mo_show_bench = False
                    if selected_benchmarks:
                        _mo_show_bench = st.toggle(
                            "Show benchmark monthly returns", value=False, key="ec_mo_bench_toggle"
                        )

                    def _color_ret(val):
                        if pd.isna(val): return ""
                        return "color: #2ecc71" if val > 0 else "color: #e74c3c"

                    _mo_fmt = {c: "{:+.1f}%" for c in _mo_pivot.columns}
                    st.dataframe(
                        _mo_pivot.style
                            .format(_mo_fmt, na_rep="—")
                            .map(_color_ret),
                        width='stretch',
                    )

                    if _mo_show_bench and selected_benchmarks:
                        for _bench in selected_benchmarks:
                            _bs = load_benchmark_series(
                                _bench, _ec_start_str, _ec_start_bal
                            )
                            if _bs.empty:
                                continue
                            _bs_rets = (_bs.pct_change().dropna())
                            _bs_mo   = ((1 + _bs_rets).resample("ME").prod() - 1) * 100
                            _bs_df   = pd.DataFrame({
                                "Year":  _bs_mo.index.year,
                                "Month": _bs_mo.index.month,
                                "Return":_bs_mo.values,
                            })
                            _bs_df["MonthAbbr"] = _bs_df["Month"].apply(lambda m: _month_abbr[m-1])
                            _bs_pivot = _bs_df.pivot(index="Year", columns="MonthAbbr", values="Return")
                            _bs_pivot = _bs_pivot.reindex(
                                columns=[m for m in _month_abbr if m in _bs_pivot.columns]
                            )
                            _bs_pivot["Annual"] = (
                                (1 + _bs_df.groupby("Year")["Return"].apply(
                                    lambda s: (s / 100 + 1).prod() - 1
                                )) - 1
                            ) * 100
                            st.caption(f"**{_bench}** monthly returns")
                            st.dataframe(
                                _bs_pivot.style
                                    .format(_mo_fmt, na_rep="—")
                                    .map(_color_ret),
                                width='stretch',
                            )
                else:
                    st.info("Need at least 5 data points to compute monthly returns.")

                # ── Daily balance table ───────────────────────────────────────
                _db_head_col, _db_clr_col = st.columns([4, 1])
                _db_head_col.markdown("#### Daily Balances")
                with _db_clr_col:
                    with st.popover("🗑️  Clear All", use_container_width=True):
                        st.warning("Permanently delete **all** equity entries?", icon="⚠️")
                        if st.button("Yes, clear all", type="primary",
                                     use_container_width=True, key="chart_clear_equity_btn"):
                            clear_equity_entries()
                            _cached_load_equity_entries.clear()
                            _bust("_v_equity")
                            st.rerun()
                _tbl = _ec_plot_df[["date", "balance", "contributions", "withdrawals", "twr_pct"]].copy()
                _tbl["Daily Change ($)"] = _tbl["balance"].diff().fillna(0.0)
                _tbl["Daily Return (%)"] = (
                    (_tbl["balance"] / (_tbl["balance"].shift(1)
                     + _tbl["contributions"] - _tbl["withdrawals"]) - 1) * 100
                ).fillna(0.0)
                # Flag rows that look like missing contributions: >15% single-day move
                # with no cash flow recorded — these are the primary cause of curve spikes.
                _tbl["⚠️"] = np.where(
                    (_tbl["Daily Return (%)"].abs() > 15)
                    & (_tbl["contributions"] == 0)
                    & (_tbl["withdrawals"]   == 0),
                    "⚠️ check", "",
                )
                _tbl = _tbl.rename(columns={
                    "date":          "Date",
                    "balance":       "Balance ($)",
                    "contributions": "Contributions ($)",
                    "withdrawals":   "Withdrawals ($)",
                    "twr_pct":       "Cum. TWR (%)",
                })
                _tbl["Date"] = _tbl["Date"].dt.strftime("%Y-%m-%d")
                _tbl = _tbl[[
                    "Date", "Balance ($)", "Daily Change ($)", "Daily Return (%)",
                    "Cum. TWR (%)", "Contributions ($)", "Withdrawals ($)", "⚠️"
                ]].sort_values("Date", ascending=False).reset_index(drop=True)
                _n_suspect = (_tbl["⚠️"] != "").sum()
                if _n_suspect:
                    st.warning(
                        f"⚠️ **{_n_suspect} row(s) flagged** — a >15% single-day balance "
                        "change with no contributions or withdrawals recorded. "
                        "These are likely caused by deposits/withdrawals that were imported "
                        "without cash-flow data. Edit those entries in the **Manual Entry** "
                        "tab to add the correct contributions/withdrawals.",
                        icon="⚠️",
                    )
                st.dataframe(
                    _tbl.style
                        .format({
                            "Balance ($)":        "${:,.2f}",
                            "Daily Change ($)":   "${:+,.2f}",
                            "Daily Return (%)":   "{:+.2f}%",
                            "Cum. TWR (%)":       "{:+.2f}%",
                            "Contributions ($)":  "${:,.2f}",
                            "Withdrawals ($)":    "${:,.2f}",
                        })
                        .map(
                            lambda v: "color: #2ecc71" if isinstance(v, str) and (
                                v.startswith("+") or v.startswith("$+")
                            ) else "color: #e74c3c" if isinstance(v, str) and "-" in v else "",
                            subset=["Daily Change ($)", "Daily Return (%)", "Cum. TWR (%)"],
                        ),
                    width='stretch', hide_index=True,
                )

    # ── Manual Entry tab ──────────────────────────────────────────────────────
    with _ec_tab_entry:
        with st.form("ec_manual_form", clear_on_submit=True):
            _ef1, _ef2, _ef3, _ef4 = st.columns(4)
            _ec_date   = _ef1.date_input("Date *", value=pd.Timestamp.today().date(), key="ec_date")
            _ec_bal    = _ef2.number_input("EOD Balance ($) *", min_value=0.0, step=100.0,
                                           format="%.2f", value=None, key="ec_bal")
            _ec_contr  = _ef3.number_input("Contributions ($)", min_value=0.0, step=100.0,
                                           format="%.2f", value=None, key="ec_contr")
            _ec_withdr = _ef4.number_input("Withdrawals ($)",   min_value=0.0, step=100.0,
                                           format="%.2f", value=None, key="ec_withdr")
            _ec_submit = st.form_submit_button("Add / Update Entry", width='stretch', type="primary")

        if _ec_submit:
            if not _ec_bal:
                st.error("EOD Balance is required.")
            else:
                upsert_equity_entry(
                    str(_ec_date),
                    float(_ec_bal),
                    float(_ec_contr or 0.0),
                    float(_ec_withdr or 0.0),
                )
                _cached_load_equity_entries.clear()
                _bust("_v_equity")
                st.toast(f"Entry saved for {_ec_date}", icon="✅")
                st.rerun()

        if _eq_entries:
            st.markdown("---")
            _clr_ec_col, _ = st.columns([1, 5])
            with _clr_ec_col:
                with st.popover("🗑️  Clear All Entries", width='stretch'):
                    st.warning("This will permanently delete **all equity entries**.", icon="⚠️")
                    if st.button("Yes, delete all", type="primary", width='stretch', key="confirm_clear_equity"):
                        clear_equity_entries()
                        _cached_load_equity_entries.clear()
                        _bust("_v_equity")
                        st.rerun()

            _ec_disp = pd.DataFrame(_eq_entries)[["date", "balance", "contributions", "withdrawals"]].copy()
            _ec_disp.columns = ["Date", "Balance ($)", "Contributions ($)", "Withdrawals ($)"]
            _ec_disp = _ec_disp.sort_values("Date", ascending=False).reset_index(drop=True)
            st.dataframe(_ec_disp, width='stretch', hide_index=True)

            st.markdown("**Delete an entry**")
            _del_opts = {f"{e['date']} — ${e['balance']:,.2f}": e["id"] for e in sorted(_eq_entries, key=lambda x: x["date"], reverse=True)}
            _del_sel  = st.selectbox("Select entry to delete", options=list(_del_opts.keys()), index=None,
                                     placeholder="Choose entry…", key="ec_del_sel")
            if _del_sel and st.button("Delete selected entry", type="secondary", key="ec_del_btn"):
                delete_equity_entry(_del_opts[_del_sel])
                _cached_load_equity_entries.clear()
                _bust("_v_equity")
                st.rerun()

    # ── Import tab ────────────────────────────────────────────────────────────
    with _ec_tab_import:
        st.markdown("#### CSV Import")
        st.caption("Expected columns: `date`, `balance`, `contributions` (optional), `withdrawals` (optional)")
        _csv_file = st.file_uploader("Upload CSV", type=["csv"], key="ec_csv_upload")
        if _csv_file:
            try:
                _csv_df = pd.read_csv(_csv_file)
                _csv_df.columns = [c.strip().lower() for c in _csv_df.columns]
                if "date" not in _csv_df.columns or "balance" not in _csv_df.columns:
                    st.error("CSV must have 'date' and 'balance' columns.")
                else:
                    def _parse_equity_dates(series):
                        """Try US then Euro date parsing; fall back to pandas infer."""
                        s = series.astype(str).str.strip()
                        # Explicit DDMMYYYY or DDMMYY without separators
                        for fmt in ("%d%m%Y", "%d%m%y"):
                            try:
                                parsed = pd.to_datetime(s, format=fmt)
                                return parsed.dt.strftime("%Y-%m-%d")
                            except Exception:
                                pass
                        # With separators — try dayfirst=False (US) then dayfirst=True (Euro)
                        for dayfirst in (False, True):
                            try:
                                parsed = pd.to_datetime(s, dayfirst=dayfirst)
                                return parsed.dt.strftime("%Y-%m-%d")
                            except Exception:
                                pass
                        return pd.to_datetime(s, infer_datetime_format=True).dt.strftime("%Y-%m-%d")
                    _csv_df["date"] = _parse_equity_dates(_csv_df["date"])
                    _csv_df["balance"]       = pd.to_numeric(_csv_df["balance"],       errors="coerce")
                    _csv_df["contributions"] = pd.to_numeric(_csv_df.get("contributions", 0), errors="coerce").fillna(0.0)
                    _csv_df["withdrawals"]   = pd.to_numeric(_csv_df.get("withdrawals",   0), errors="coerce").fillna(0.0)
                    _csv_df = _csv_df.dropna(subset=["balance"]).sort_values("date").reset_index(drop=True)
                    # Spike detection: warn when a large balance jump has no cash flow recorded
                    _csv_prev  = _csv_df["balance"].shift(1)
                    _csv_denom = _csv_prev + _csv_df["contributions"] - _csv_df["withdrawals"]
                    _csv_iret  = np.where(_csv_denom > 0, (_csv_df["balance"] / _csv_denom - 1) * 100, 0.0)
                    _csv_df["_impl_ret"] = np.where(_csv_df.index == 0, 0.0, _csv_iret)
                    _csv_spike = (
                        (_csv_df["_impl_ret"].abs() > 15)
                        & (_csv_df["contributions"] == 0)
                        & (_csv_df["withdrawals"]   == 0)
                    )
                    if _csv_spike.any():
                        _csv_spike_lines = "\n".join(
                            f"- **{r['date']}**: implied {r['_impl_ret']:+.1f}% (balance ${r['balance']:,.2f})"
                            for _, r in _csv_df[_csv_spike].iterrows()
                        )
                        st.warning(
                            f"⚠️ **{_csv_spike.sum()} day(s) show a balance jump >15% with no "
                            "recorded contributions or withdrawals.** "
                            "If a deposit occurred on these dates, add it to the CSV to avoid equity curve spikes.\n\n"
                            + _csv_spike_lines
                        )
                    st.dataframe(_csv_df[["date","balance","contributions","withdrawals"]], width='stretch', hide_index=True)
                    if st.button(f"Import {len(_csv_df)} entries from CSV", type="primary", key="ec_csv_import_btn"):
                        for _, _r in _csv_df.iterrows():
                            upsert_equity_entry(_r["date"], float(_r["balance"]),
                                                float(_r["contributions"]), float(_r["withdrawals"]))
                        _cached_load_equity_entries.clear()
                        _bust("_v_equity")
                        st.success(f"Imported {len(_csv_df)} entries.")
                        st.rerun()
            except Exception as _csv_err:
                st.error(f"CSV parse error: {_csv_err}")

        st.markdown("---")
        st.markdown("#### IB Activity Statement XML Import")
        st.caption("Upload an IB Activity Statement XML. Reads `EquitySummaryByReportDateInBase` elements.")
        _xml_file = st.file_uploader("Upload XML", type=["xml"], key="ec_xml_upload")
        if _xml_file:
            try:
                _xml_root = _ET.parse(_io.BytesIO(_xml_file.read())).getroot()

                # ── Parse cash transactions so deposits/withdrawals are attributed
                # correctly. Without this, deposits look like trading profit and
                # cause massive spikes in the equity curve (TWR denominator error).
                _xml_deps: dict[str, float] = {}
                _xml_wths: dict[str, float] = {}
                for _txn in _xml_root.iter("CashTransaction"):
                    # Skip summary rows — IB emits each transaction twice
                    if _txn.get("levelOfDetail", "").upper() == "SUMMARY":
                        continue
                    _ttype = (_txn.get("type") or "").lower()
                    try:
                        _tamt = float(_txn.get("amount", 0) or 0)
                    except (ValueError, TypeError):
                        _tamt = 0.0
                    _traw = _txn.get("reportDate") or _txn.get("dateTime", "")
                    try:
                        _tdate = pd.to_datetime(str(_traw)[:10]).strftime("%Y-%m-%d")
                    except Exception:
                        continue
                    if "deposit" in _ttype and _tamt > 0:
                        _xml_deps[_tdate] = _xml_deps.get(_tdate, 0.0) + _tamt
                    elif "withdrawal" in _ttype and _tamt < 0:
                        _xml_wths[_tdate] = _xml_wths.get(_tdate, 0.0) + abs(_tamt)

                # ── Build daily rows with correct contributions/withdrawals ──────
                _xml_rows = []
                for _el in _xml_root.iter("EquitySummaryByReportDateInBase"):
                    _rdate = _el.get("reportDate") or _el.get("date")
                    _total = _el.get("total")
                    if _rdate and _total:
                        try:
                            _iso = pd.to_datetime(_rdate).strftime("%Y-%m-%d")
                            _xml_rows.append({
                                "date":          _iso,
                                "balance":       float(_total),
                                "contributions": _xml_deps.get(_iso, 0.0),
                                "withdrawals":   _xml_wths.get(_iso, 0.0),
                            })
                        except Exception:
                            pass

                if not _xml_rows:
                    st.warning("No `EquitySummaryByReportDateInBase` records found in the XML.")
                else:
                    _xml_df = (
                        pd.DataFrame(_xml_rows)
                        .drop_duplicates("date")
                        .sort_values("date")
                        .reset_index(drop=True)
                    )

                    # ── Spike detection: warn before user imports ─────────────
                    _xprev   = _xml_df["balance"].shift(1)
                    _xdenom  = _xprev + _xml_df["contributions"] - _xml_df["withdrawals"]
                    _xret    = np.where(_xdenom > 0, (_xml_df["balance"] / _xdenom - 1) * 100, 0.0)
                    _xml_df["_impl_ret"] = np.where(
                        _xml_df.index == 0, 0.0, _xret
                    )
                    _spike_mask = (
                        (_xml_df["_impl_ret"].abs() > 15)
                        & (_xml_df["contributions"] == 0)
                        & (_xml_df["withdrawals"]   == 0)
                    )
                    if _spike_mask.any():
                        _spike_lines = "\n".join(
                            f"- **{r['date']}**: implied {r['_impl_ret']:+.1f}% "
                            f"(balance ${r['balance']:,.2f})"
                            for _, r in _xml_df[_spike_mask].iterrows()
                        )
                        st.warning(
                            f"⚠️ **{_spike_mask.sum()} day(s) show a balance jump >15% with no "
                            "recorded contributions or withdrawals.**\n\n"
                            "If you deposited or withdrew money on these dates, the equity curve "
                            "will show a false spike. Check whether your XML includes `CashTransaction` "
                            "nodes, or add the deposit/withdrawal manually after importing.\n\n"
                            + _spike_lines
                        )

                    st.dataframe(
                        _xml_df[["date", "balance", "contributions", "withdrawals"]],
                        width='stretch', hide_index=True,
                    )
                    if st.button(f"Import {len(_xml_df)} entries from XML", type="primary", key="ec_xml_import_btn"):
                        for _, _r in _xml_df.iterrows():
                            upsert_equity_entry(
                                _r["date"], float(_r["balance"]),
                                float(_r["contributions"]), float(_r["withdrawals"]),
                            )
                        _cached_load_equity_entries.clear()
                        _bust("_v_equity")
                        st.success(f"Imported {len(_xml_df)} entries.")
                        st.rerun()
            except Exception as _xml_err:
                st.error(f"XML parse error: {_xml_err}")

    # ── IB Flex Import tab ────────────────────────────────────────────────────
    with _ec_tab_flex:
        st.markdown("#### Import Balance History from IB Flex")
        st.caption(
            "Fetches daily portfolio value (NAV) and any deposits/withdrawals from your "
            "IB Flex report — the same token and query ID you configured in **Broker Sync → Flex Query**. "
            "Each day becomes one equity-curve entry."
        )

        _ec_flex_tok = settings.get("flex_token", "").strip()
        _ec_flex_qid = settings.get("flex_query_id", "").strip()
        _ec_flex_configured = bool(_ec_flex_tok) and bool(_ec_flex_qid)

        if not _ec_flex_configured:
            st.warning(
                "No Flex token / query ID saved yet. "
                "Go to **Broker Sync → Flex Query** to add them, then come back here."
            )

        # ── Date range ────────────────────────────────────────────────────────
        _ec_fx_today = pd.Timestamp.today().date()
        _ec_fx_ts    = pd.Timestamp.today()
        _ec_fx_c1, _ec_fx_c2, _ec_fx_c3, _ec_fx_c4, _ec_fx_c5, _ec_fx_c6, _ec_fx_c7 = st.columns(7)
        if _ec_fx_c1.button("MTD",         key="ecfx_preset_mtd", width='stretch'):
            st.session_state["ecfx_from"] = _ec_fx_today.replace(day=1)
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()
        if _ec_fx_c2.button("QTD",         key="ecfx_preset_qtd", width='stretch'):
            _q_start_month = ((_ec_fx_today.month - 1) // 3) * 3 + 1
            st.session_state["ecfx_from"] = _ec_fx_today.replace(month=_q_start_month, day=1)
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()
        if _ec_fx_c3.button("YTD",         key="ecfx_preset_ytd", width='stretch'):
            st.session_state["ecfx_from"] = _ec_fx_today.replace(month=1, day=1)
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()
        if _ec_fx_c4.button("Last Month",  key="ecfx_preset_1m",  width='stretch'):
            st.session_state["ecfx_from"] = _ec_fx_today - pd.Timedelta(days=30)
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()
        if _ec_fx_c5.button("Last 3 Mo",   key="ecfx_preset_3m",  width='stretch'):
            st.session_state["ecfx_from"] = _ec_fx_today - pd.Timedelta(days=90)
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()
        if _ec_fx_c6.button("Last Year",   key="ecfx_preset_1y",  width='stretch'):
            st.session_state["ecfx_from"] = _ec_fx_today - pd.Timedelta(days=365)
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()
        if _ec_fx_c7.button("All Time",    key="ecfx_preset_all", width='stretch'):
            st.session_state["ecfx_from"] = pd.Timestamp("2010-01-01").date()
            st.session_state["ecfx_to"]   = _ec_fx_today
            st.rerun()

        _ecfx_d1, _ecfx_d2 = st.columns(2)
        _ecfx_from = _ecfx_d1.date_input(
            "From", key="ecfx_from",
            value=st.session_state.get("ecfx_from", _ec_fx_today - pd.Timedelta(days=30)),
        )
        _ecfx_to = _ecfx_d2.date_input(
            "To", key="ecfx_to",
            value=st.session_state.get("ecfx_to", _ec_fx_today),
        )

        # ── Fetch button ──────────────────────────────────────────────────────
        _ecfx_btn_col, _ = st.columns([1, 2])
        if _ecfx_btn_col.button(
            "📥  Fetch Balance History", width='stretch', key="ecfx_fetch_btn",
            disabled=not _ec_flex_configured,
        ):
            with st.spinner("Contacting IB Flex Web Service… this can take up to 2 minutes."):
                _ecfx_report = _ib_mod.fetch_flex_report(_ec_flex_tok, _ec_flex_qid)
            if _ecfx_report.get("error"):
                st.error(f"Flex error: {_ecfx_report['error']}")
            else:
                _ecfx_nav_found = _ecfx_report.get("daily_nav", [])
                _ecfx_txns_found = _ecfx_report.get("cash_transactions", [])
                if _ecfx_nav_found:
                    st.session_state["_ecfx_nav"] = _ecfx_nav_found
                    st.rerun()
                else:
                    st.warning(
                        f"Report fetched successfully but contained **0 daily NAV entries**. "
                        f"({len(_ecfx_txns_found)} cash transaction(s) were found.)\n\n"
                        "To fix this, edit your IB Flex Query and enable at least one of these sections:\n"
                        "1. IB Account Management → Reports → Flex Queries → edit your query\n"
                        "2. Under *Select sections*, enable **Change in NAV** *(preferred)*, "
                        "**Equity Summary by Report Date**, or **Net Asset Value**\n"
                        "3. Save the query and fetch again.\n\n"
                        "Alternatively, upload the XML file directly using the uploader below."
                    )

        # ── XML upload fallback ───────────────────────────────────────────────
        st.markdown("**Or upload a Flex Statement XML directly:**")
        _ecfx_xml = st.file_uploader(
            "Upload Flex XML", type=["xml"], key="ecfx_xml_upload",
            label_visibility="collapsed",
        )
        if _ecfx_xml is not None:
            _ecfx_parsed = _ib_mod._parse_flex_xml(
                _ecfx_xml.read().decode("utf-8", errors="replace")
            )
            if _ecfx_parsed.get("error"):
                st.error(f"XML error: {_ecfx_parsed['error']}")
            else:
                st.session_state["_ecfx_nav"] = _ecfx_parsed.get("daily_nav", [])
                st.success(f"Loaded {len(st.session_state['_ecfx_nav'])} daily NAV entries from file.")

        # ── Preview & import ──────────────────────────────────────────────────
        _ecfx_nav_all = st.session_state.get("_ecfx_nav", [])
        if _ecfx_nav_all:
            # Filter to selected date range
            _ecfx_nav = [
                r for r in _ecfx_nav_all
                if str(_ecfx_from) <= r["date"] <= str(_ecfx_to)
            ]
            st.caption(
                f"{len(_ecfx_nav)} of {len(_ecfx_nav_all)} day(s) in range "
                f"({_ecfx_from} → {_ecfx_to})."
                + (" Adjust the date range above to include more." if len(_ecfx_nav) < len(_ecfx_nav_all) else "")
            )
            if _ecfx_nav:
                _ecfx_prev_df = pd.DataFrame(_ecfx_nav)[["date", "balance", "contributions", "withdrawals"]].copy()
                _ecfx_prev_df.columns = ["Date", "Balance ($)", "Contributions ($)", "Withdrawals ($)"]
                st.dataframe(_ecfx_prev_df, width='stretch', hide_index=True)

                _ecfx_imp_col, _ecfx_clr_col = st.columns(2)
                if _ecfx_imp_col.button(
                    f"✅  Import {len(_ecfx_nav)} Entries", width='stretch',
                    type="primary", key="ecfx_import_btn",
                ):
                    for _nr in _ecfx_nav:
                        upsert_equity_entry(
                            _nr["date"],
                            float(_nr["balance"]),
                            float(_nr.get("contributions", 0.0)),
                            float(_nr.get("withdrawals",   0.0)),
                        )
                    _cached_load_equity_entries.clear()
                    _bust("_v_equity")
                    st.session_state.pop("_ecfx_nav", None)
                    st.success(f"Imported {len(_ecfx_nav)} equity entries. The chart may take a moment to populate.")
                    st.rerun()
                if _ecfx_clr_col.button("✕  Clear", width='stretch', key="ecfx_clear_btn"):
                    st.session_state.pop("_ecfx_nav", None)
                    st.rerun()
            else:
                st.info("No NAV entries fall within the selected date range.")


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — TRADING PLAN
# ════════════════════════════════════════════════════════════════════════════════

elif page == "📝  Trading Plan":
    import time as _time_mod

    st.header("Trading Plan")

    # ── session defaults ──────────────────────────────────────────────────────
    _tp_defaults = {
        "tp_ticker":        "",
        "tp_sentiment":     "Neutral",
        "tp_rationale":     "",
        "tp_fundamentals":  "",
        "tp_technicals":    "",
        "tp_trade_type":    "Swing",
        "tp_hold_time":     "",
        "tp_entry_signal":  "",
        "tp_confirm1":      "",
        "tp_confirm2":      "",
        "tp_entry_price":   None,
        "tp_profit_target": None,
        "tp_stop_loss":     None,
    }
    for _k, _v in _tp_defaults.items():
        st.session_state.setdefault(_k, _v)

    # ── live price helper with 60 s auto-refresh ──────────────────────────────
    @st.cache_data(ttl=60, show_spinner=False)
    def _tp_fetch_price(ticker: str):
        try:
            raw = yf.download(ticker, period="2d", auto_adjust=True, progress=False)
            closes = raw["Close"].dropna() if not isinstance(raw.columns, pd.MultiIndex) else raw["Close"][ticker].dropna()
            if len(closes) >= 1:
                return float(closes.iloc[-1]), float(closes.iloc[-2]) if len(closes) >= 2 else float(closes.iloc[-1])
        except Exception:
            pass
        return None, None

    @st.cache_data(ttl=3600, show_spinner=False)
    def _tp_fetch_earnings(ticker: str):
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None:
                return None
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed:
                    return pd.to_datetime(ed[0]).date()
                if ed is not None:
                    return pd.to_datetime(ed).date()
            if isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
                return pd.to_datetime(cal.loc["Earnings Date"].iloc[0]).date()
        except Exception:
            pass
        return None

    # ════════════════════════════════════════════════════════════════════════
    # Section 1 — Ticker & Sentiment
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("1 · Ticker & Sentiment")

    _tp_c1, _tp_c2, _tp_c3, _tp_c4 = st.columns([2, 2, 2, 2])

    _tp_ticker_input = _tp_c1.text_input(
        "Ticker", value=st.session_state["tp_ticker"],
        placeholder="e.g. AAPL", key="tp_ticker_widget",
    ).upper().strip()

    if _tp_ticker_input != st.session_state["tp_ticker"]:
        st.session_state["tp_ticker"] = _tp_ticker_input
        _tp_fetch_price.clear()
        _tp_fetch_earnings.clear()
        st.rerun()

    _tp_sentiment = _tp_c2.selectbox(
        "Sentiment", ["Bullish", "Bearish", "Neutral"],
        index=["Bullish", "Bearish", "Neutral"].index(st.session_state["tp_sentiment"]),
        key="tp_sentiment_widget",
    )
    st.session_state["tp_sentiment"] = _tp_sentiment

    # Live price display
    _tp_ticker = st.session_state["tp_ticker"]
    if _tp_ticker:
        _tp_price, _tp_prev = _tp_fetch_price(_tp_ticker)
        if _tp_price is not None:
            _tp_chg    = _tp_price - _tp_prev
            _tp_chg_pct = _tp_chg / _tp_prev * 100 if _tp_prev else 0.0
            _tp_arrow  = "▲" if _tp_chg >= 0 else "▼"
            _tp_colour = "#2ecc71" if _tp_chg >= 0 else "#e74c3c"
            _tp_c3.markdown(
                f"**Live Price**<br>"
                f"<span style='font-size:1.6rem;font-weight:700;color:{_tp_colour}'>${_tp_price:,.2f}</span>"
                f"&nbsp;<span style='color:{_tp_colour};font-size:0.95rem'>{_tp_arrow} {_tp_chg:+.2f} ({_tp_chg_pct:+.2f}%)</span>"
                f"<br><span style='font-size:0.72rem;color:#888'>auto-refresh 60s</span>",
                unsafe_allow_html=True,
            )
        else:
            _tp_c3.warning(f"No price data for {_tp_ticker}")

        # Earnings date
        _tp_earnings = _tp_fetch_earnings(_tp_ticker)
        if _tp_earnings is not None:
            _tp_today   = pd.Timestamp.today().date()
            _tp_ed_days = (_tp_earnings - _tp_today).days
            if _tp_ed_days >= 0:
                _tp_ed_label = f"**{_tp_earnings}** ({_tp_ed_days}d away)"
                _tp_ed_badge = "#f39c12" if _tp_ed_days <= 14 else "#3498db"
            else:
                _tp_ed_label = f"**{_tp_earnings}** ({abs(_tp_ed_days)}d ago)"
                _tp_ed_badge = "#888"
            _tp_c4.markdown(
                f"**Earnings Date**<br>"
                f"<span style='font-size:1rem;color:{_tp_ed_badge}'>{_tp_ed_label}</span>",
                unsafe_allow_html=True,
            )
        else:
            _tp_c4.markdown("**Earnings Date**<br><span style='color:#888'>N/A</span>", unsafe_allow_html=True)

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # Section 2 — Thesis
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("2 · Thesis")
    _tp_th1, _tp_th2, _tp_th3 = st.columns(3)

    _tp_rationale = _tp_th1.text_area(
        "Trigger / Rationale",
        value=st.session_state["tp_rationale"],
        height=130, placeholder="Why are you considering this trade?",
        key="tp_rationale_widget",
    )
    st.session_state["tp_rationale"] = _tp_rationale

    _tp_fund = _tp_th2.text_area(
        "Fundamentals Notes",
        value=st.session_state["tp_fundamentals"],
        height=130, placeholder="Revenue, earnings, guidance, valuation…",
        key="tp_fundamentals_widget",
    )
    st.session_state["tp_fundamentals"] = _tp_fund

    _tp_tech = _tp_th3.text_area(
        "Technicals Notes",
        value=st.session_state["tp_technicals"],
        height=130, placeholder="Chart pattern, key levels, indicators…",
        key="tp_technicals_widget",
    )
    st.session_state["tp_technicals"] = _tp_tech

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # Section 3 — Investment / Trade Setup
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("3 · Investment / Trade Setup")
    _tp_s3a, _tp_s3b = st.columns(2)

    _tp_trade_type = _tp_s3a.selectbox(
        "Investment / Trade Type",
        ["Day Trade", "Swing", "Position", "Long-Term Invest", "Options Play"],
        index=["Day Trade", "Swing", "Position", "Long-Term Invest", "Options Play"].index(
            st.session_state["tp_trade_type"]
        ),
        key="tp_trade_type_widget",
    )
    st.session_state["tp_trade_type"] = _tp_trade_type

    _tp_hold_time = _tp_s3b.text_input(
        "Target Hold Time",
        value=st.session_state["tp_hold_time"],
        placeholder="e.g. 3–5 days, 6 months, until earnings…",
        key="tp_hold_time_widget",
    )
    st.session_state["tp_hold_time"] = _tp_hold_time

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # Section 4 — Entry Criteria
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("4 · Entry Criteria")
    _tp_e1, _tp_e2, _tp_e3 = st.columns(3)

    _tp_entry_signal = _tp_e1.text_area(
        "Entry Signal",
        value=st.session_state["tp_entry_signal"],
        height=110, placeholder="What triggers the entry? (e.g. break of $X, candle close above MA…)",
        key="tp_entry_signal_widget",
    )
    st.session_state["tp_entry_signal"] = _tp_entry_signal

    _tp_confirm1 = _tp_e2.text_area(
        "Confirmation #1",
        value=st.session_state["tp_confirm1"],
        height=110, placeholder="Volume, sector confirmation, breadth…",
        key="tp_confirm1_widget",
    )
    st.session_state["tp_confirm1"] = _tp_confirm1

    _tp_confirm2 = _tp_e3.text_area(
        "Confirmation #2",
        value=st.session_state["tp_confirm2"],
        height=110, placeholder="Second supporting signal…",
        key="tp_confirm2_widget",
    )
    st.session_state["tp_confirm2"] = _tp_confirm2

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # Section 5 — Levels & R:R
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("5 · Levels & Risk / Reward")
    _tp_l1, _tp_l2, _tp_l3, _tp_l4 = st.columns(4)

    _tp_entry_price = _tp_l1.number_input(
        "Planned Entry Price ($)",
        min_value=0.0, step=0.01, format="%.4f",
        value=st.session_state["tp_entry_price"],
        key="tp_entry_price_widget",
    )
    st.session_state["tp_entry_price"] = _tp_entry_price if _tp_entry_price else None

    _tp_profit_target = _tp_l2.number_input(
        "Profit Target ($)",
        min_value=0.0, step=0.01, format="%.4f",
        value=st.session_state["tp_profit_target"],
        key="tp_profit_target_widget",
    )
    st.session_state["tp_profit_target"] = _tp_profit_target if _tp_profit_target else None

    _tp_stop_loss = _tp_l3.number_input(
        "Stop Loss ($)",
        min_value=0.0, step=0.01, format="%.4f",
        value=st.session_state["tp_stop_loss"],
        key="tp_stop_loss_widget",
    )
    st.session_state["tp_stop_loss"] = _tp_stop_loss if _tp_stop_loss else None

    # Self-populating R:R
    _tp_ep  = st.session_state["tp_entry_price"]
    _tp_pt  = st.session_state["tp_profit_target"]
    _tp_sl  = st.session_state["tp_stop_loss"]
    if _tp_ep and _tp_pt and _tp_sl and _tp_ep != _tp_sl:
        _tp_reward = abs(_tp_pt - _tp_ep)
        _tp_risk   = abs(_tp_ep - _tp_sl)
        _tp_rr     = _tp_reward / _tp_risk if _tp_risk > 0 else None
        if _tp_rr is not None:
            _tp_rr_colour = "#2ecc71" if _tp_rr >= 2 else ("#f39c12" if _tp_rr >= 1 else "#e74c3c")
            _tp_l4.markdown(
                f"**R : R Ratio**<br>"
                f"<span style='font-size:1.8rem;font-weight:700;color:{_tp_rr_colour}'>{_tp_rr:.2f} : 1</span><br>"
                f"<span style='font-size:0.78rem;color:#888'>"
                f"Reward ${_tp_reward:.2f} · Risk ${_tp_risk:.2f}"
                f"</span>",
                unsafe_allow_html=True,
            )
        else:
            _tp_l4.markdown("**R : R Ratio**<br><span style='color:#888'>—</span>", unsafe_allow_html=True)
    else:
        _tp_l4.markdown(
            "**R : R Ratio**<br><span style='color:#888'>Fill entry, target & stop</span>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # Section 6 — Attachments
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("6 · Attachments")
    st.caption("Files are staged here and saved permanently when you log the plan.")

    st.session_state.setdefault("tp_pending_attachments", [])

    _tp_uploaded = st.file_uploader(
        "Upload chart, screenshot, or document",
        accept_multiple_files=True,
        key="tp_file_uploader",
        label_visibility="collapsed",
    )
    # Merge newly uploaded files into pending list (deduplicate by name)
    if _tp_uploaded:
        _existing_names = {a["name"] for a in st.session_state["tp_pending_attachments"]}
        for _uf in _tp_uploaded:
            if _uf.name not in _existing_names:
                st.session_state["tp_pending_attachments"].append(
                    {"name": _uf.name, "data": _uf.getbuffer().tobytes()}
                )
                _existing_names.add(_uf.name)

    if st.session_state["tp_pending_attachments"]:
        for _pai, _pa in enumerate(list(st.session_state["tp_pending_attachments"])):
            _pac1, _pac2 = st.columns([8, 1])
            _pac1.markdown(f"📎 `{_pa['name']}` — {len(_pa['data']) / 1024:.1f} KB")
            if _pac2.button("✕", key=f"tp_rm_attach_{_pai}", help="Remove"):
                st.session_state["tp_pending_attachments"].pop(_pai)
                st.rerun()
    else:
        st.caption("No attachments staged yet.")

    st.divider()

    # ════════════════════════════════════════════════════════════════════════
    # Section 7 — Save & Saved Plans
    # ════════════════════════════════════════════════════════════════════════
    st.subheader("7 · Save & Saved Plans")

    _tp_sa1, _tp_sa2 = st.columns([1, 5])
    if _tp_sa1.button("💾  Log This Plan", type="primary", width='stretch', key="tp_save_btn"):
        if not st.session_state.get("tp_ticker"):
            st.error("Ticker is required to log a plan.")
        else:
            _tp_ep  = st.session_state["tp_entry_price"]
            _tp_pt  = st.session_state["tp_profit_target"]
            _tp_sl  = st.session_state["tp_stop_loss"]
            _tp_rr_save = None
            if _tp_ep and _tp_pt and _tp_sl and _tp_ep != _tp_sl:
                _r = abs(_tp_pt - _tp_ep)
                _k = abs(_tp_ep - _tp_sl)
                _tp_rr_save = _r / _k if _k > 0 else None

            _new_plan_id = save_trading_plan({
                "ticker":        st.session_state["tp_ticker"],
                "sentiment":     st.session_state["tp_sentiment"],
                "rationale":     st.session_state["tp_rationale"],
                "fundamentals":  st.session_state["tp_fundamentals"],
                "technicals":    st.session_state["tp_technicals"],
                "trade_type":    st.session_state["tp_trade_type"],
                "hold_time":     st.session_state["tp_hold_time"],
                "entry_signal":  st.session_state["tp_entry_signal"],
                "confirm1":      st.session_state["tp_confirm1"],
                "confirm2":      st.session_state["tp_confirm2"],
                "entry_price":   _tp_ep,
                "profit_target": _tp_pt,
                "stop_loss":     _tp_sl,
                "rr_ratio":      _tp_rr_save,
            })
            for _pa in st.session_state["tp_pending_attachments"]:
                save_plan_attachment(_new_plan_id, _pa["name"], _pa["data"])
            st.session_state["tp_pending_attachments"] = []
            _cached_load_trading_plans.clear()
            _bust("_v_plans")
            st.toast(f"Plan logged for {st.session_state['tp_ticker']}", icon="💾")
            st.rerun()

    if _tp_sa2.button("🗑️  Clear Plan", key="tp_clear_btn", width='stretch'):
        for _k, _v in _tp_defaults.items():
            st.session_state[_k] = _v
        st.session_state["tp_pending_attachments"] = []
        st.rerun()

    # ── Saved plan log ────────────────────────────────────────────────────────
    _saved_plans = _cached_load_trading_plans(st.session_state["_v_plans"])
    if _saved_plans:
        st.markdown(f"**{len(_saved_plans)} saved plan(s)**")
        for _sp in _saved_plans:
            _sp_rr   = f"{_sp['rr_ratio']:.2f}:1" if _sp.get("rr_ratio") else "—"
            _sp_sent = _sp.get("sentiment", "")
            _sp_sent_icon = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(_sp_sent, "")
            _sp_label = (
                f"{_sp_sent_icon} **{_sp['ticker'] or '—'}**  ·  {_sp.get('trade_type','')}"
                f"  ·  R:R {_sp_rr}  ·  *{str(_sp.get('saved_at',''))[:16]}*"
            )
            with st.expander(_sp_label, expanded=False):
                _sv1, _sv2, _sv3 = st.columns(3)
                _sv1.markdown(f"**Sentiment:** {_sp_sent}")
                _sv2.markdown(f"**Hold Time:** {_sp.get('hold_time') or '—'}")
                _sp_ep_str = f"${_sp['entry_price']:.4f}" if _sp.get('entry_price') else "—"
                _sv3.markdown(f"**Entry Price:** {_sp_ep_str}")
                _sv4, _sv5, _sv6 = st.columns(3)
                _sp_pt_str = f"${_sp['profit_target']:.4f}" if _sp.get('profit_target') else "—"
                _sp_sl_str = f"${_sp['stop_loss']:.4f}" if _sp.get('stop_loss') else "—"
                _sv4.markdown(f"**Profit Target:** {_sp_pt_str}")
                _sv5.markdown(f"**Stop Loss:** {_sp_sl_str}")
                _sv6.markdown(f"**R:R Ratio:** {_sp_rr}")

                if _sp.get("rationale"):
                    st.markdown(f"**Trigger / Rationale:** {_sp['rationale']}")
                if _sp.get("fundamentals"):
                    st.markdown(f"**Fundamentals:** {_sp['fundamentals']}")
                if _sp.get("technicals"):
                    st.markdown(f"**Technicals:** {_sp['technicals']}")
                if _sp.get("entry_signal"):
                    st.markdown(f"**Entry Signal:** {_sp['entry_signal']}")
                _confs = [_sp.get("confirm1"), _sp.get("confirm2")]
                _confs = [c for c in _confs if c]
                if _confs:
                    st.markdown("**Confirmations:** " + "  ·  ".join(_confs))

                # Attachments
                _sp_attaches = load_plan_attachments(_sp["id"])
                if _sp_attaches:
                    st.markdown("**Attachments:**")
                    for _spa in _sp_attaches:
                        _spa_c1, _spa_c2, _spa_c3 = st.columns([5, 2, 1])
                        _spa_c1.markdown(f"📎 `{_spa['filename']}`")
                        try:
                            _spa_bytes = Path(_spa["filepath"]).read_bytes()
                            _spa_c2.download_button(
                                "Download", data=_spa_bytes,
                                file_name=_spa["filename"],
                                key=f"tp_dl_{_spa['id']}",
                                width='stretch',
                            )
                        except Exception:
                            _spa_c2.caption("File missing")
                        if _spa_c3.button("✕", key=f"tp_del_att_{_spa['id']}", help="Remove attachment"):
                            delete_plan_attachment(_spa["id"])
                            _cached_load_trading_plans.clear()
                            _bust("_v_plans")
                            st.rerun()

                # Load plan into editor / delete
                _sp_btn1, _sp_btn2, _ = st.columns([2, 2, 6])
                if _sp_btn1.button("📂  Load into Editor", key=f"tp_load_{_sp['id']}", width='stretch'):
                    st.session_state["tp_ticker"]        = _sp.get("ticker", "")
                    st.session_state["tp_sentiment"]     = _sp.get("sentiment", "Neutral")
                    st.session_state["tp_rationale"]     = _sp.get("rationale", "")
                    st.session_state["tp_fundamentals"]  = _sp.get("fundamentals", "")
                    st.session_state["tp_technicals"]    = _sp.get("technicals", "")
                    st.session_state["tp_trade_type"]    = _sp.get("trade_type", "Swing")
                    st.session_state["tp_hold_time"]     = _sp.get("hold_time", "")
                    st.session_state["tp_entry_signal"]  = _sp.get("entry_signal", "")
                    st.session_state["tp_confirm1"]      = _sp.get("confirm1", "")
                    st.session_state["tp_confirm2"]      = _sp.get("confirm2", "")
                    st.session_state["tp_entry_price"]   = _sp.get("entry_price")
                    st.session_state["tp_profit_target"] = _sp.get("profit_target")
                    st.session_state["tp_stop_loss"]     = _sp.get("stop_loss")
                    st.session_state["tp_pending_attachments"] = []
                    st.rerun()
                if _sp_btn2.button("🗑️  Delete Plan", key=f"tp_del_{_sp['id']}", width='stretch'):
                    delete_trading_plan(_sp["id"])
                    _cached_load_trading_plans.clear()
                    _bust("_v_plans")
                    st.rerun()
    else:
        st.caption("No plans logged yet. Fill in the sections above and click **Log This Plan**.")


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — STATISTICS
# ════════════════════════════════════════════════════════════════════════════════

elif page == "📊  Statistics":
    trades_st = _cached_load_trades(st.session_state["_v_trades"])
    if trades_st.empty:
        st.info("No trades yet.")
    else:
        st.markdown("#### Filters")
        sf1, sf2, sf3, sf4 = st.columns(4)
        st_instrument = sf1.selectbox(
            "Instrument", ["All", "Stocks", "Options", "Futures"],
            key="st_instrument",
            help="Options and Futures are separated by default; combine here if needed.",
        )
        st_ticker    = sf2.multiselect("Ticker", options=sorted(trades_st["ticker"].dropna().unique()),
                                       key="st_ticker", placeholder="All tickers")
        st_status    = sf3.selectbox("Status", ["Closed only", "All (incl. open)", "Open only"],
                                     key="st_status")
        st_tags      = sf4.multiselect("Tags (any match)", options=sorted(tag_name_to_id.keys()),
                                       key="st_tags", placeholder="All tags")
        sf5, sf6     = st.columns([1, 2])
        st_date_col  = sf5.selectbox("Date column", ["Exit Date", "Entry Date"], key="st_datecol")

        # ── Date range quick-selectors ────────────────────────────────────────
        _today_d  = pd.Timestamp.today().date()
        _dr_cols  = sf6.columns(5)
        _dr_label = None
        if _dr_cols[0].button("YTD",       key="st_dr_ytd"):  _dr_label = "ytd"
        if _dr_cols[1].button("MTD",       key="st_dr_mtd"):  _dr_label = "mtd"
        if _dr_cols[2].button("30 Days",   key="st_dr_30"):   _dr_label = "30d"
        if _dr_cols[3].button("7 Days",    key="st_dr_7"):    _dr_label = "7d"
        if _dr_cols[4].button("All Time",  key="st_dr_all"):  _dr_label = "all"
        if _dr_label:
            from datetime import date as _date_cls
            if   _dr_label == "ytd": st.session_state["st_dr_start"] = _date_cls(_today_d.year, 1, 1)
            elif _dr_label == "mtd": st.session_state["st_dr_start"] = _date_cls(_today_d.year, _today_d.month, 1)
            elif _dr_label == "30d": st.session_state["st_dr_start"] = _today_d - pd.Timedelta(days=30)
            elif _dr_label == "7d":  st.session_state["st_dr_start"] = _today_d - pd.Timedelta(days=7)
            else:                    st.session_state["st_dr_start"] = None
            st.rerun()

        _dr_preset_start = st.session_state.get("st_dr_start")
        if _dr_preset_start:
            _dr_default = [_dr_preset_start, _today_d]
        else:
            _dr_default = []
        st_daterange = st.date_input("Date range", value=_dr_default, key="st_daterange")

        # ── Display options ───────────────────────────────────────────────────
        _opt_c1, _opt_c2, _opt_c3, _opt_c4 = st.columns(4)
        _pnl_mode = _opt_c1.radio(
            "P&L Display", ["$", "%", "Acct. %"],
            index=1, horizontal=True, key="st_pnl_mode",
            help=(
                "**$** — raw dollar P&L. Best for a pure stock portfolio where all "
                "positions are roughly the same size.\n\n"
                "**%** — return as a % of what the position cost "
                "(entry price × qty × multiplier). Best for options, where a $200 "
                "gain on a $500 contract is very different from $200 on a $20,000 stock.\n\n"
                "**Acct. %** — return as a % of your total account balance. Puts every "
                "trade on the same playing field regardless of size or instrument — ideal "
                "for a mixed portfolio of stocks and options, because it shows how much "
                "each trade actually moved the needle for your account."
            ),
        )
        _use_pct = _pnl_mode != "$"
        _mean_method = _opt_c2.selectbox(
            "Mean Method", ["Mean", "10% Trimmed Mean"], index=0, key="st_mean_method",
            help=(
                "**Mean**: simple arithmetic average of winners/losers.\n\n"
                "**10% Trimmed Mean**: removes the top 10% and bottom 10% of each group "
                "(winners and losers treated separately), then averages the remainder. "
                "Reduces distortion from outlier trades."
            ),
        )
        _net_comm    = _opt_c3.toggle("Net of Commission",  value=True,  key="st_net_comm",
                                       help="Subtract commission from P&L in all stats")
        _agg_spreads = _opt_c4.toggle("Aggregate Spreads",  value=True,  key="st_agg_spreads",
                                       help="Combine spread legs into one trade for all stats")

        st.caption(f"Using account balance: **{fmt_price(acct_bal)}** — change in ⚙️ Settings tab.")
        st.divider()

        sf = trades_st.copy()
        # Instrument filter
        if st_instrument == "Stocks":
            sf = sf[sf["instrument_type"].isna() | (sf["instrument_type"] == "stock")]
        elif st_instrument == "Options":
            sf = sf[sf["instrument_type"] == "option"]
        elif st_instrument == "Futures":
            sf = sf[sf["instrument_type"] == "future"]
        # Other filters
        if st_ticker: sf = sf[sf["ticker"].isin(st_ticker)]
        if st_status == "Closed only":  sf = sf[~sf.apply(_is_open, axis=1)]
        elif st_status == "Open only":  sf = sf[sf.apply(_is_open, axis=1)]
        if st_tags:
            def _has_any_tag_st(tags_str):
                if not tags_str or pd.isna(tags_str): return False
                return any(t.strip() in st_tags for t in tags_str.split(","))
            _tag_direct_st = sf["tags"].apply(_has_any_tag_st)
            if "leg_group" in sf.columns:
                _tag_groups_st = sf.loc[
                    _tag_direct_st & sf["leg_group"].notna() & (sf["leg_group"].astype(str) != ""),
                    "leg_group",
                ].unique()
                sf = sf[_tag_direct_st | sf["leg_group"].isin(_tag_groups_st)]
            else:
                sf = sf[_tag_direct_st]
        if isinstance(st_daterange, (list, tuple)) and len(st_daterange) == 2:
            start, end = pd.Timestamp(st_daterange[0]), pd.Timestamp(st_daterange[1])
            dc   = "exit_date" if st_date_col == "Exit Date" else "entry_date"
            dcol = pd.to_datetime(sf[dc], errors="coerce")
            sf   = sf[(dcol >= start) & (dcol <= end)]

        if sf.empty:
            st.info("No trades match the current filters.")
        else:
            _sf_open = sf.apply(_is_open, axis=1)
            if "expiration" in sf.columns:
                _sf_exp     = pd.to_datetime(sf["expiration"], errors="coerce")
                _sf_expired = _sf_exp.notna() & (_sf_exp.dt.normalize() < pd.Timestamp.today().normalize())
                _sf_open    = _sf_open & ~_sf_expired
            open_t_st  = tuple(sf.loc[_sf_open].apply(_get_live_ticker, axis=1).dropna().unique())
            ld_st      = get_live_data(open_t_st) if open_t_st else {}
            sf["_pnl"] = sf.apply(lambda r: _pnl_numeric(r, ld_st), axis=1)
            sf["_date"] = sf["exit_date"].where(sf["exit_date"].notna(), sf["entry_date"])

            # Commission deduction
            if _net_comm and "commission" in sf.columns:
                sf["_pnl"] = sf["_pnl"] - sf["commission"].fillna(0)

            # Spread aggregation: collapse legs sharing a leg_group into one row
            if _agg_spreads and "leg_group" in sf.columns:
                grouped_rows = []
                has_group = sf["leg_group"].notna() & (sf["leg_group"].astype(str) != "")
                for grp, legs in sf[has_group].groupby("leg_group"):
                    if len(legs) < 2:
                        continue
                    agg_pnl  = legs["_pnl"].sum() if legs["_pnl"].notna().any() else None
                    agg_date = legs["_date"].dropna().max()
                    rep = legs.iloc[0].copy()
                    rep["_pnl"]  = agg_pnl
                    rep["_date"] = agg_date
                    # Merge tags from all legs so the aggregated row is fully tagged
                    _merged_tags = ", ".join(sorted({
                        t.strip()
                        for ts in legs["tags"].dropna()
                        for t in str(ts).split(",")
                        if t.strip()
                    }))
                    rep["tags"] = _merged_tags or None
                    grouped_rows.append(rep)
                if grouped_rows:
                    multi_grps = {r["leg_group"] for r in grouped_rows}
                    ungrouped  = sf[~(has_group & sf["leg_group"].isin(multi_grps))]
                    sf = pd.concat([ungrouped, pd.DataFrame(grouped_rows)], ignore_index=True)

            pnl_avail = sf.dropna(subset=["_pnl"]).copy()
            if pnl_avail.empty:
                st.info("P&L cannot be computed for the selected trades.")
            else:
                pnl_series   = pnl_avail["_pnl"].astype(float)
                dates_series = pnl_avail["_date"]
                stats        = compute_stats(tuple(pnl_series), tuple(dates_series), acct_bal)

                # ── % conversion helper ───────────────────────────────────────
                def _pct_of_trade(row, pnl_val):
                    ep   = row.get("entry_price")
                    qty  = row.get("quantity")
                    mult = float(row.get("multiplier") or 1.0)
                    base = abs(float(ep) * float(qty) * mult) if ep and qty else None
                    return (pnl_val / base * 100) if base and pnl_val is not None else None

                if _pnl_mode == "%":
                    pnl_avail["_pnl_disp"] = pnl_avail.apply(
                        lambda r: _pct_of_trade(r, r["_pnl"]), axis=1)
                elif _pnl_mode == "Acct. %":
                    if not acct_bal:
                        st.warning("Set your account balance in ⚙️ Settings to use Acct. % mode.")
                    pnl_avail["_pnl_disp"] = pnl_avail["_pnl"].apply(
                        lambda v: (v / acct_bal * 100) if acct_bal and v is not None else None)

                if _pnl_mode in ("%", "Acct. %"):
                    _pct_series = pnl_avail["_pnl_disp"].dropna().astype(float)
                    _eff_series = _pct_series
                    def _mv(v, prefix="", decimals=2):
                        return "N/A" if v is None else f"{v:,.{decimals}f}%"
                    _eff_winners = _eff_series[_eff_series > 0]
                    _eff_losers  = _eff_series[_eff_series < 0]
                    _avg_winner_v = float(_eff_winners.mean())   if not _eff_winners.empty else None
                    _avg_loser_v  = float(_eff_losers.mean())    if not _eff_losers.empty  else None
                    _med_winner_v = float(_eff_winners.median()) if not _eff_winners.empty else None
                    _med_loser_v  = float(_eff_losers.median())  if not _eff_losers.empty  else None
                    _std_winner_v = float(_eff_winners.std())    if len(_eff_winners) > 1  else None
                    _std_loser_v  = float(_eff_losers.std())     if len(_eff_losers) > 1   else None
                    _lw_v = float(_eff_winners.max()) if not _eff_winners.empty else None
                    _ll_v = float(_eff_losers.min())  if not _eff_losers.empty  else None
                else:
                    _eff_series   = pnl_series
                    _eff_winners  = _eff_series[_eff_series > 0]
                    _eff_losers   = _eff_series[_eff_series < 0]
                    _avg_winner_v = float(stats["avg_winner"]) if stats["avg_winner"] is not None else None
                    _avg_loser_v  = float(stats["avg_loser"])  if stats["avg_loser"]  is not None else None
                    _med_winner_v = float(_eff_winners.median()) if not _eff_winners.empty else None
                    _med_loser_v  = float(_eff_losers.median())  if not _eff_losers.empty  else None
                    _std_winner_v = float(stats["std_winner"]) if stats["std_winner"] is not None else None
                    _std_loser_v  = float(stats["std_loser"])  if stats["std_loser"]  is not None else None
                    _lw_v = float(pnl_series[pnl_series > 0].max()) if (pnl_series > 0).any() else None
                    _ll_v = float(pnl_series[pnl_series < 0].min()) if (pnl_series < 0).any() else None
                    def _mv(v, prefix="$", decimals=2):
                        return "N/A" if v is None else f"{prefix}{v:,.{decimals}f}"

                # ── Trimmed mean (10% each side, per group) ───────────────────
                _use_trimmed = (_mean_method == "10% Trimmed Mean")

                def _trimmed_group_mean(arr, pct=0.10):
                    if arr is None or len(arr) == 0:
                        return None
                    s = np.sort(arr)
                    n = max(1, int(len(s) * pct)) if len(s) >= 5 else 0
                    trimmed = s[n : len(s) - n] if n else s
                    return float(np.mean(trimmed)) if len(trimmed) > 0 else None

                if _use_trimmed:
                    _avg_winner_disp = _mv(_trimmed_group_mean(_eff_winners.values))
                    _avg_loser_disp  = _mv(_trimmed_group_mean(_eff_losers.values))
                else:
                    _avg_winner_disp = _mv(_avg_winner_v)
                    _avg_loser_disp  = _mv(_avg_loser_v)

                # ── EV and annualized return ──────────────────────────────────
                _n_total = len(_eff_series)
                _n_win   = int((_eff_series > 0).sum())
                _wr      = _n_win / _n_total if _n_total else 0
                _ev      = _wr * (_avg_winner_v or 0) + (1 - _wr) * (_avg_loser_v or 0) if _avg_winner_v is not None or _avg_loser_v is not None else None

                # Average days in trade (closed trades only)
                _pnl_dates = pd.to_datetime(pnl_avail["_date"], errors="coerce")
                _entry_dts = pd.to_datetime(pnl_avail["entry_date"], errors="coerce")
                _days_held = (_pnl_dates - _entry_dts).dt.days.dropna()
                _avg_days  = float(_days_held.mean()) if not _days_held.empty else None
                _ann_ev    = _ev * (365 / _avg_days) if _ev is not None and _avg_days and _avg_days > 0 else None

                _mode_label = {"$": "", "%": "· % returns", "Acct. %": "· Acct. % returns"}.get(_pnl_mode, "")
                st.markdown(f"**{len(pnl_avail)} trade(s) in analysis**  "
                            f"{_mode_label}  "
                            f"{'· 10% trimmed mean (per group)' if _use_trimmed else ''}")

                # ── Performance ───────────────────────────────────────────────
                st.markdown("##### Performance")
                _w_label = "Avg Winner" + (" (trimmed)" if _use_trimmed else "")
                _l_label = "Avg Loser"  + (" (trimmed)" if _use_trimmed else "")
                # Row 1: win rate + average/median for winners and losers
                r1 = st.columns(5)
                r1[0].metric("Win Rate", f"{_wr*100:.1f}%")
                r1[1].metric(_w_label, _avg_winner_disp,
                             help="10% trimmed: removes top+bottom 10% of winners before averaging." if _use_trimmed else None)
                r1[2].metric("Median Winner", _mv(_med_winner_v),
                             help="Middle value of all winning trades when sorted by P&L. Less sensitive to outliers than the average.")
                r1[3].metric(_l_label, _avg_loser_disp,
                             help="10% trimmed: removes top+bottom 10% of losers before averaging." if _use_trimmed else None)
                r1[4].metric("Median Loser", _mv(_med_loser_v),
                             help="Middle value of all losing trades when sorted by P&L. Less sensitive to outliers than the average.")
                # Row 2: dispersion + extremes
                r2 = st.columns(4)
                r2[0].metric("Std Dev — Winners", _mv(_std_winner_v),
                             help="How consistent your winning trades are. A low number means your winners tend to be similar in size. A high number means they're all over the place — some tiny, some huge.")
                r2[1].metric("Std Dev — Losers",  _mv(_std_loser_v),
                             help="How consistent your losing trades are. A low number means your losses are predictable and controlled. A high number means you occasionally take a much bigger hit than usual.")
                r2[2].metric("Largest Winner", _mv(_lw_v),
                             help="Best single trade result.")
                r2[3].metric("Largest Loser",  _mv(_ll_v),
                             help="Worst single trade result.")

                # ── EV row ────────────────────────────────────────────────────
                st.markdown("##### Expected Value")
                _ev_cols = st.columns(4)
                _ev_cols[0].metric(
                    "EV per Trade",
                    _mv(_ev) if _ev is not None else "N/A",
                    help="EV = win_rate × avg_winner + (1 − win_rate) × avg_loser",
                )
                _ev_cols[1].metric(
                    "Avg Days in Trade",
                    f"{_avg_days:.1f}" if _avg_days else "N/A",
                )
                _ev_cols[2].metric(
                    "Expected Ann. Return",
                    _mv(_ann_ev) if _ann_ev is not None else "N/A",
                    help="EV per trade × (365 ÷ avg days in trade). Uses calendar days.",
                )
                _total_comm = float(pnl_avail["commission"].fillna(0).sum()) if "commission" in pnl_avail.columns else 0.0
                _ev_cols[3].metric(
                    "Total Commission",
                    fmt_price(_total_comm),
                    help="Sum of all commissions in the filtered set.",
                )

                # Performance charts — two side-by-side bar charts
                if _avg_winner_v is not None or _avg_loser_v is not None:
                    _aw = _avg_winner_v or 0
                    _al = _avg_loser_v  or 0
                    _y_prefix = "" if _pnl_mode != "$" else "$"
                    _y_suffix = "%" if _pnl_mode != "$" else ""
                    _y_fmt    = ".2f" if _pnl_mode != "$" else ",.0f"
                    _chart_layout = dict(
                        height=280, showlegend=False,
                        margin=dict(t=40, b=10, l=10, r=10),
                        paper_bgcolor=_CHT_BG, plot_bgcolor=_CHT_BG,
                        font=dict(color=_CHT_FONT),
                        bargap=0.55,
                        yaxis_tickprefix=_y_prefix, yaxis_ticksuffix=_y_suffix,
                        yaxis_tickformat=_y_fmt,
                        yaxis=dict(gridcolor=_CHT_GRID),
                        xaxis=dict(tickfont=dict(size=12)),
                    )

                    _ch_left, _ch_right = st.columns(2)

                    # Left: Avg Winner / Avg Loser
                    _fig_avg = go.Figure()
                    _fig_avg.add_bar(x=["Avg Winner"], y=[_aw], marker_color="#2ecc71")
                    _fig_avg.add_bar(x=["Avg Loser"],  y=[_al], marker_color="#e74c3c")
                    _fig_avg.update_layout(
                        title=f"Average Win / Loss ({_pnl_mode})",
                        **_chart_layout,
                    )
                    _ch_left.plotly_chart(_fig_avg, width='stretch')

                    # Right: Largest Winner / Largest Loser
                    _fig_ext = go.Figure()
                    if _lw_v is not None:
                        _fig_ext.add_bar(x=["Largest Winner"], y=[_lw_v], marker_color="#27ae60")
                    if _ll_v is not None:
                        _fig_ext.add_bar(x=["Largest Loser"],  y=[_ll_v], marker_color="#c0392b")
                    _fig_ext.update_layout(
                        title=f"Largest Win / Loss ({_pnl_mode})",
                        **_chart_layout,
                    )
                    _ch_right.plotly_chart(_fig_ext, width='stretch')

                # Scatter plot — P&L over time, respects $ / % mode
                if not pnl_avail.empty:
                    _sc_dates = pd.to_datetime(pnl_avail["_date"], errors="coerce")
                    if _pnl_mode != "$" and "_pnl_disp" in pnl_avail.columns:
                        _sc_pnl = pnl_avail["_pnl_disp"].values
                        _sc_y_label = f"P&L ({_pnl_mode})"
                        _sc_hover   = [f"{t}<br>{p:,.2f}%" for t, p in zip(pnl_avail["ticker"].values, _sc_pnl)]
                        _sc_tick_sfx = "%"
                        _sc_tick_pfx = ""
                        _sc_tick_fmt = ".2f"
                    else:
                        _sc_pnl     = pnl_avail["_pnl"].values
                        _sc_y_label = "P&L ($)"
                        _sc_hover   = [f"{t}<br>${p:,.2f}" for t, p in zip(pnl_avail["ticker"].values, _sc_pnl)]
                        _sc_tick_sfx = ""
                        _sc_tick_pfx = "$"
                        _sc_tick_fmt = ",.0f"

                    _sc_colors = ["#2ecc71" if v is not None and not pd.isna(v) and v >= 0
                                  else "#e74c3c" for v in _sc_pnl]
                    _sc_sizes  = [max(8, min(40, abs(float(v)) ** 0.45)) if v is not None and not pd.isna(v) else 8
                                  for v in _sc_pnl]
                    _fig_sc = go.Figure()
                    _fig_sc.add_scatter(
                        x=_sc_dates, y=_sc_pnl,
                        mode="markers",
                        marker=dict(color=_sc_colors, size=_sc_sizes, line=dict(width=0.5, color="#0d1117")),
                        text=_sc_hover,
                        hoverinfo="text+x",
                        name="Trade P&L",
                    )
                    _fig_sc.add_hline(y=0, line=dict(color="#888", dash="dot", width=1))

                    # Linear regression trend line
                    try:
                        _reg_x = np.array([d.value if hasattr(d, "value") else
                                           pd.Timestamp(d).value for d in _sc_dates])
                        _reg_y = np.array([float(v) for v in _sc_pnl], dtype=float)
                        _valid  = ~np.isnan(_reg_y) & ~np.isnan(_reg_x)
                        if _valid.sum() >= 2:
                            _m, _b = np.polyfit(_reg_x[_valid], _reg_y[_valid], 1)
                            _x_sorted = np.sort(_reg_x[_valid])
                            _reg_line  = _m * _x_sorted + _b
                            _x_dates   = pd.to_datetime(_x_sorted)
                            _fig_sc.add_scatter(
                                x=_x_dates, y=_reg_line,
                                mode="lines",
                                line=dict(color="#f39c12", width=2, dash="solid"),
                                name="Trend (linear)",
                                hoverinfo="skip",
                            )
                    except Exception:
                        pass

                    _fig_sc.update_layout(
                        title="Trade P&L Over Time",
                        xaxis_title="Date", yaxis_title=_sc_y_label,
                        height=300, showlegend=True,
                        legend=dict(bgcolor=_CHT_LEG, font=dict(size=11, color=_CHT_LEG_FONT)),
                        margin=dict(t=36, b=10, l=10, r=10),
                        paper_bgcolor=_CHT_BG, plot_bgcolor=_CHT_BG,
                        font=dict(color=_CHT_FONT),
                        xaxis=dict(gridcolor=_CHT_GRID),
                        yaxis=dict(gridcolor=_CHT_GRID, tickprefix=_sc_tick_pfx,
                                   ticksuffix=_sc_tick_sfx, tickformat=_sc_tick_fmt),
                        hovermode="closest",
                    )
                    st.plotly_chart(_fig_sc, width='stretch')

                st.divider()

                # ── Risk-Adjusted Returns ─────────────────────────────────────
                st.markdown("##### Risk-Adjusted Returns")
                r2 = st.columns(6)
                r2[0].metric("Sharpe Ratio",
                             f"{stats['sharpe']:.3f}" if stats["sharpe"] is not None else "N/A",
                             help=(
                                 "Daily-annualised: mean daily return ÷ σ daily × √252.\n\n"
                                 "**Reference ranges (long-term annualised):**\n"
                                 "- S&P 500 (SPY): 0.5 – 0.7 · Excellent for the index\n"
                                 "- Nasdaq (QQQ): 0.4 – 0.8 · Higher return, higher vol\n"
                                 "- Active traders targeting: > 1.0\n\n"
                                 "Set Account Balance in ⚙️ Settings to enable."
                             ))
                r2[1].metric("Sortino Ratio",
                             f"{stats['sortino']:.3f}" if stats["sortino"] is not None else "N/A",
                             help=(
                                 "Daily-annualised: mean daily return ÷ downside σ × √252.\n\n"
                                 "**Reference ranges:**\n"
                                 "- S&P 500 (SPY): 0.7 – 1.0\n"
                                 "- Nasdaq (QQQ): 0.6 – 1.2\n"
                                 "- Active traders targeting: > 1.5\n\n"
                                 "Set Account Balance in ⚙️ Settings to enable."
                             ))
                r2[2].metric("Calmar Ratio",
                             f"{stats['calmar']:.3f}" if stats["calmar"] is not None else "N/A",
                             help="Annualised return ÷ Max Drawdown. SPY reference: 0.3–0.6 (long-term avg). Set Account Balance in Settings to enable.")
                r2[3].metric("VaR 95%",
                             f"${stats['var_95']:,.2f}" if stats["var_95"] is not None else "N/A",
                             help="Historical Value at Risk (95%): in 95% of trades your loss will not exceed this $ amount.")
                r2[4].metric(
                    "Max Drawdown %",
                    f"{stats['max_dd_pct']:.2f}%" if stats.get("max_dd_pct") is not None else "N/A",
                    help="Peak-to-trough drawdown of cumulative trade P&L as % of account balance (account-level).",
                )
                r2[5].metric("Recovery Time",
                             (f"{stats['recovery_days']} days"
                              if stats.get("recovery_days") is not None else "Not yet recovered")
                             if stats.get("max_dd") is not None else "N/A")
                if not acct_bal:
                    st.warning("Account Balance is 0 — Sharpe, Sortino, and Calmar require a balance. Set it in ⚙️ Settings.", icon="⚠️")

                # ── Sector breakdown pie chart ─────────────────────────────────
                _unique_tix = list(pnl_avail["ticker"].dropna().unique())
                if _unique_tix:
                    _sector_data: dict[str, dict] = {"count": {}, "pnl": {}}
                    for _t in _unique_tix:
                        _sec = get_ticker_sector(_t) or "Unknown"
                        _t_rows = pnl_avail[pnl_avail["ticker"] == _t]
                        _sector_data["count"][_sec]  = _sector_data["count"].get(_sec, 0) + len(_t_rows)
                        _sector_data["pnl"][_sec]    = _sector_data["pnl"].get(_sec, 0.0) + float(_t_rows["_pnl"].sum())
                    _pie_mode = st.radio("Sector chart by", ["Trade Count", "Total P&L"],
                                         horizontal=True, key="st_pie_mode", label_visibility="collapsed")
                    _pie_vals_raw = _sector_data["count"] if _pie_mode == "Trade Count" else _sector_data["pnl"]
                    _pie_vals = {k: v for k, v in _pie_vals_raw.items() if v > 0}
                    if _pie_vals:
                        _fig_pie = go.Figure(go.Pie(
                            labels=list(_pie_vals.keys()),
                            values=list(_pie_vals.values()),
                            hole=0.35,
                            textinfo="label+percent",
                            hovertemplate="%{label}<br>%{value}<extra></extra>",
                        ))
                        _fig_pie.update_layout(
                            title=f"Sector Breakdown — {_pie_mode}",
                            height=340, showlegend=True,
                            margin=dict(t=40, b=10, l=10, r=10),
                            paper_bgcolor=_CHT_BG,
                            font=dict(color=_CHT_FONT),
                            legend=dict(bgcolor=_CHT_LEG),
                        )
                        st.plotly_chart(_fig_pie, width='stretch')

                # ── Rolling Sharpe / Sortino chart ────────────────────────────
                if len(pnl_series) >= 25:
                    _window = 20
                    _rets   = (pnl_series / acct_bal).values if acct_bal else None
                    if _rets is not None:
                        _roll_sh, _roll_so, _roll_idx = [], [], []
                        for _i in range(_window, len(_rets) + 1):
                            _w = _rets[_i - _window : _i]
                            _mr  = float(np.mean(_w))
                            _std = float(np.std(_w, ddof=1)) if len(_w) > 1 else 0
                            _neg = _w[_w < 0]
                            _sd  = float(np.std(_neg, ddof=1)) if len(_neg) > 1 else 0
                            _roll_sh.append(_mr / _std  if _std  > 0 else float("nan"))
                            _roll_so.append(_mr / _sd   if _sd   > 0 else float("nan"))
                            _roll_idx.append(_i)
                        _fig_roll = go.Figure()
                        _fig_roll.add_scatter(x=_roll_idx, y=_roll_sh, name="Your Sharpe",
                                              line=dict(color="#3498db", width=2.5))
                        _fig_roll.add_scatter(x=_roll_idx, y=_roll_so, name="Your Sortino",
                                              line=dict(color="#e67e22", width=2.5))

                        # SPY / QQQ long-run reference bands
                        _bm_start_rs = str(dates_series.min())[:10] if len(dates_series) else None
                        _bm_end_rs   = str(dates_series.max())[:10] if len(dates_series) else None
                        if _bm_start_rs and _bm_end_rs and _bm_start_rs != _bm_end_rs:
                            for _bm_sym, _sh_col, _so_col in [
                                ("SPY", "rgba(46,204,113,0.55)", "rgba(46,204,113,0.25)"),
                                ("QQQ", "rgba(155,89,182,0.55)", "rgba(155,89,182,0.25)"),
                            ]:
                                _bm_s = compute_benchmark_stats(_bm_sym, _bm_start_rs, _bm_end_rs)
                                if _bm_s:
                                    _bm_sh_val = _bm_s.get("sharpe")
                                    _bm_so_val = _bm_s.get("sortino")
                                    if _bm_sh_val and not np.isnan(_bm_sh_val):
                                        _fig_roll.add_hline(
                                            y=_bm_sh_val, line=dict(color=_sh_col, dash="dash", width=1.5),
                                            annotation_text=f"{_bm_sym} Sharpe {_bm_sh_val:.2f}",
                                            annotation_position="right",
                                            annotation=dict(font_size=10, font_color=_sh_col),
                                        )
                                    if _bm_so_val and not np.isnan(_bm_so_val):
                                        _fig_roll.add_hline(
                                            y=_bm_so_val, line=dict(color=_so_col, dash="dot", width=1.5),
                                            annotation_text=f"{_bm_sym} Sortino {_bm_so_val:.2f}",
                                            annotation_position="right",
                                            annotation=dict(font_size=10, font_color=_so_col),
                                        )

                        _fig_roll.add_hline(y=0, line=dict(color="#888", dash="dot"))
                        _fig_roll.update_layout(
                            title=f"Rolling Sharpe & Sortino ({_window}-trade window) vs SPY / QQQ",
                            xaxis_title="Trade #", yaxis_title="Ratio",
                            height=340, hovermode="x unified",
                            margin=dict(t=50, b=10),
                            paper_bgcolor=_CHT_BG, plot_bgcolor=_CHT_BG,
                            font=dict(color=_CHT_FONT),
                            xaxis=dict(gridcolor=_CHT_GRID),
                            yaxis=dict(gridcolor=_CHT_GRID),
                            legend=dict(bgcolor=_CHT_LEG),
                        )
                        st.plotly_chart(_fig_roll, width='stretch')
                        st.caption(
                            "Dashed lines = SPY (green) & QQQ (purple) Sharpe/Sortino over the same period. "
                            "Your rolling ratios beat the benchmark when above the reference lines."
                        )

                # ── Benchmark comparison ───────────────────────────────────────
                with st.expander("📊  Benchmark Comparison (SPY / QQQ / IWM / LQD / JNK)"):
                    _bm_start = str(dates_series.min())[:10] if len(dates_series) else None
                    _bm_end   = str(dates_series.max())[:10] if len(dates_series) else None
                    if _bm_start and _bm_end and _bm_start != _bm_end:
                        _bm_rows = []
                        for _bm in ["SPY", "QQQ", "IWM", "LQD", "JNK"]:
                            _bm_s = compute_benchmark_stats(_bm, _bm_start, _bm_end)
                            if _bm_s:
                                _bm_rows.append({
                                    "Benchmark": _bm,
                                    "Sharpe (ann.)":  f"{_bm_s['sharpe']:.3f}"  if not np.isnan(_bm_s.get("sharpe",  float("nan"))) else "N/A",
                                    "Sortino (ann.)": f"{_bm_s['sortino']:.3f}" if not np.isnan(_bm_s.get("sortino", float("nan"))) else "N/A",
                                    "Calmar (ann.)":  f"{_bm_s['calmar']:.3f}"  if not np.isnan(_bm_s.get("calmar",  float("nan"))) else "N/A",
                                    "Max DD %":       f"{_bm_s['max_dd_pct']:.1f}%" if "max_dd_pct" in _bm_s else "N/A",
                                })
                        # Add your own row
                        _my_sharpe  = f"{stats['sharpe']:.3f}"  if stats.get("sharpe")  is not None else "N/A"
                        _my_sortino = f"{stats['sortino']:.3f}" if stats.get("sortino") is not None else "N/A"
                        _my_calmar  = f"{stats['calmar']:.3f}"  if stats.get("calmar")  is not None else "N/A"
                        _my_mdd     = f"{stats['max_dd'] / acct_bal * 100:.1f}%" if stats.get("max_dd") and acct_bal else "N/A"
                        _bm_rows.insert(0, {
                            "Benchmark": "📋 Your Trades",
                            "Sharpe (ann.)":  _my_sharpe,
                            "Sortino (ann.)": _my_sortino,
                            "Calmar (ann.)":  _my_calmar,
                            "Max DD %":       _my_mdd,
                        })
                        st.dataframe(pd.DataFrame(_bm_rows), width='stretch', hide_index=True)
                        st.caption("All metrics are daily-annualised (same basis as benchmarks).")
                    else:
                        st.info("Select a date range in the filters above to enable benchmark comparison.")

                # ── Tag comparison table ──────────────────────────────────────
                st.divider()
                st.markdown("##### Tag Comparison")
                _cmp_tag_names = sorted({
                    t.strip()
                    for ts in pnl_avail["tags"].dropna()
                    for t in str(ts).split(",")
                    if t.strip()
                })
                if _cmp_tag_names:
                    _cmp_rows = []
                    for _tname in _cmp_tag_names:
                        _t_mask = pnl_avail["tags"].apply(
                            lambda ts, tn=_tname: bool(ts) and not pd.isna(ts)
                            and any(x.strip() == tn for x in str(ts).split(","))
                        )
                        _t_df = pnl_avail[_t_mask]
                        if _t_df.empty:
                            continue
                        _t_raw = _t_df["_pnl"].astype(float)
                        if _pnl_mode in ("%", "Acct. %") and "_pnl_disp" in _t_df.columns:
                            _t_eff = _t_df["_pnl_disp"].astype(float)
                        else:
                            _t_eff = _t_raw
                        _t_pos = _t_eff[_t_raw > 0]
                        _t_neg = _t_eff[_t_raw < 0]
                        _t_n  = len(_t_raw)
                        _t_nw = int((_t_raw > 0).sum())
                        _t_wr = _t_nw / _t_n if _t_n else 0
                        _t_aw = (_trimmed_group_mean(_t_pos.values) if _use_trimmed
                                 else float(_t_pos.mean()) if not _t_pos.empty else None)
                        _t_al = (_trimmed_group_mean(_t_neg.values) if _use_trimmed
                                 else float(_t_neg.mean()) if not _t_neg.empty else None)
                        _t_mw = float(_t_pos.median()) if not _t_pos.empty else None
                        _t_ml = float(_t_neg.median()) if not _t_neg.empty else None
                        _t_lw = float(_t_pos.max())    if not _t_pos.empty else None
                        _t_ll = float(_t_neg.min())    if not _t_neg.empty else None
                        _t_ev = (
                            _t_wr * (_t_aw or 0) + (1 - _t_wr) * (_t_al or 0)
                            if _t_aw is not None or _t_al is not None else None
                        )
                        _t_days = (
                            pd.to_datetime(_t_df["_date"], errors="coerce")
                            - pd.to_datetime(_t_df["entry_date"], errors="coerce")
                        ).dt.days.dropna()
                        _t_avg_days_v = float(_t_days.mean()) if not _t_days.empty else None
                        _t_ann_ev     = (
                            _t_ev * (365 / _t_avg_days_v)
                            if _t_ev is not None and _t_avg_days_v and _t_avg_days_v > 0
                            else None
                        )
                        _t_total_raw  = float(_t_raw.sum())
                        _cmp_rows.append({
                            "Tag":             _tname,
                            "Trades":          _t_n,
                            "Win Rate":        f"{_t_wr*100:.1f}%",
                            "Avg Winner":      _mv(_t_aw),
                            "Avg Loser":       _mv(_t_al),
                            "Median Winner":   _mv(_t_mw),
                            "Median Loser":    _mv(_t_ml),
                            "Largest Winner":  _mv(_t_lw),
                            "Largest Loser":   _mv(_t_ll),
                            "EV / Trade":      _mv(_t_ev) if _t_ev is not None else "N/A",
                            "Avg Days":        f"{_t_avg_days_v:.1f}" if _t_avg_days_v else "N/A",
                            "Ann. Return":     _mv(_t_ann_ev) if _t_ann_ev is not None else "N/A",
                            "Total P&L ($)":   fmt_price(_t_total_raw),
                            # raw numeric for styling only — excluded from display
                            "_ev_raw":         _t_ev,
                            "_pnl_raw":        _t_total_raw,
                            "_ann_raw":        _t_ann_ev,
                        })
                    if _cmp_rows:
                        _cmp_df = pd.DataFrame(_cmp_rows)
                        _style_cols = ["EV / Trade", "Ann. Return", "Total P&L ($)"]
                        _raw_map    = {
                            "EV / Trade":    "_ev_raw",
                            "Ann. Return":   "_ann_raw",
                            "Total P&L ($)": "_pnl_raw",
                        }

                        def _cmp_color(col_name):
                            raw_col = _raw_map[col_name]
                            def _styler(val):
                                row_idx = _cmp_df.index[_cmp_df[col_name] == val]
                                if row_idx.empty:
                                    return ""
                                raw = _cmp_df.loc[row_idx[0], raw_col]
                                if raw is None or pd.isna(raw):
                                    return ""
                                return "color: #27ae60; font-weight: 600" if raw > 0 else (
                                    "color: #e74c3c; font-weight: 600" if raw < 0 else ""
                                )
                            return _styler

                        _display_df = _cmp_df.drop(columns=["_ev_raw", "_pnl_raw", "_ann_raw"])
                        _styled = _display_df.style
                        for _sc in _style_cols:
                            if _sc in _display_df.columns:
                                _styled = _styled.map(_cmp_color(_sc), subset=[_sc])
                        st.dataframe(_styled, hide_index=True, width='stretch')
                    else:
                        st.info("No tagged trades in the current filter.")
                else:
                    st.info("No tagged trades in the current filter.")


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — TAGS
# ════════════════════════════════════════════════════════════════════════════════

elif page == "📖  Glossary":
    st.title("📖  Glossary")
    st.caption("Reference for the platforms, brokers, indicators, order types, metrics, and terms used throughout the app.")
    st.markdown(GLOSSARY_MD)

elif page == "🏷️  Tags":
    tag_list = _cached_load_tags(st.session_state["_v_tags"])

    render_tour_panel("🏷️  Tags")

    # ── Clear All button ──────────────────────────────────────────────────────
    _tag_tab_manage, _tag_tab_bulk = st.tabs(["🏷️  Manage Tags", "📋  Bulk Tag Editor"])

    # ── Tab 1: Manage Tags (existing behaviour) ───────────────────────────────
    with _tag_tab_manage:
        if tag_list:
            _clr_col, _ = st.columns([1, 4])
            with _clr_col:
                with st.popover("🗑️  Clear All Tags", width='stretch'):
                    st.warning("This will permanently delete **all tags** and remove them from all trades.", icon="⚠️")
                    if st.button("Yes, delete all tags", type="primary", width='stretch', key="confirm_clear_tags"):
                        clear_all_tags()
                        st.rerun()

        if tag_list:
            st.markdown("#### Existing Tags")
            for tag in tag_list:
                editing = st.session_state.get(f"_edit_tag_{tag['id']}", False)
                if editing:
                    with st.form(key=f"edit_tag_form_{tag['id']}"):
                        ef1, ef2 = st.columns([2, 3])
                        edited_name = ef1.text_input("Name", value=tag["name"], key=f"et_name_{tag['id']}")
                        edited_desc = ef2.text_input("Description", value=tag["description"] or "", key=f"et_desc_{tag['id']}")
                        sb1, sb2 = st.columns(2)
                        if sb1.form_submit_button("Save", type="primary", use_container_width=True):
                            if edited_name.strip():
                                update_tag(tag["id"], edited_name, edited_desc)
                                st.session_state[f"_edit_tag_{tag['id']}"] = False
                                st.rerun()
                            else:
                                st.error("Name is required.")
                        if sb2.form_submit_button("Cancel", use_container_width=True):
                            st.session_state[f"_edit_tag_{tag['id']}"] = False
                            st.rerun()
                else:
                    tc1, tc2, tc3 = st.columns([5, 1, 1])
                    tc1.markdown(f"**{tag['name']}**  \n{tag['description'] or ''}")
                    if tc2.button("✎", key=f"edit_tag_{tag['id']}", help="Edit tag"):
                        st.session_state[f"_edit_tag_{tag['id']}"] = True
                        st.rerun()
                    with tc3.popover("✕", help="Delete tag"):
                        st.warning(f"Delete **{tag['name']}**? It will be removed from all trades.", icon="⚠️")
                        if st.button("Yes, delete", type="primary",
                                     key=f"confirm_del_tag_{tag['id']}", width='stretch'):
                            delete_tag(tag["id"])
                            st.rerun()
            st.divider()
        else:
            st.info("No tags yet.")

        st.markdown("#### Add New Tag")
        with st.form("add_tag", clear_on_submit=True):
            new_tag_name = st.text_input("Name", placeholder="e.g. Breakout")
            new_tag_desc = st.text_area("Description", placeholder="e.g. Range breakout momentum plays", height=80)
            if st.form_submit_button("Add Tag", width='stretch'):
                if new_tag_name.strip():
                    add_tag(new_tag_name, new_tag_desc)
                    st.rerun()
                else:
                    st.error("Name is required.")

    # ── Tab 2: Bulk Tag Editor ────────────────────────────────────────────────
    with _tag_tab_bulk:
        if not tag_list:
            st.info("No tags defined yet — add tags on the **Manage Tags** tab first.")
        else:
            st.caption(
                "Toggle checkboxes to add or remove tags across many trades at once. "
                "Nothing is saved until you click **Save Changes**."
            )

            # Filters
            _be_f1, _be_f2, _be_f3 = st.columns([1, 2, 2])
            _be_status  = _be_f1.selectbox("Status", ["All", "Open", "Closed"], key="be_status")
            _be_ticker  = _be_f2.text_input("Ticker", placeholder="Filter by ticker…", key="be_ticker").strip().upper()
            _be_tag_sel = _be_f3.selectbox(
                "Show only trades tagged with…",
                ["(all trades)"] + [t["name"] for t in tag_list],
                key="be_tag_filter",
            )
            _be_untagged_only = st.checkbox("Untagged trades only", key="be_untagged_only", value=False)

            # Load + filter
            _be_all = _cached_load_trades(st.session_state["_v_trades"]).copy()
            _be_all = _be_all.reset_index(drop=True)

            if _be_status == "Open":
                _be_all = _be_all[_be_all.apply(_is_open, axis=1)].reset_index(drop=True)
            elif _be_status == "Closed":
                _be_all = _be_all[~_be_all.apply(_is_open, axis=1)].reset_index(drop=True)

            if _be_ticker:
                _be_all = _be_all[_be_all["ticker"].str.upper() == _be_ticker].reset_index(drop=True)

            # Tag-presence filter: read trade_tags once
            with get_connection() as _be_conn:
                _be_tt_rows = _be_conn.execute("SELECT trade_id, tag_id FROM trade_tags").fetchall()
            _be_all_tt: dict = {}
            for _r in _be_tt_rows:
                _be_all_tt.setdefault(_r[0], set()).add(_r[1])

            if _be_untagged_only:
                # A spread is "untagged" when none of its legs have any tag
                def _is_untagged(tid):
                    return not _be_all_tt.get(tid)
                _be_direct_untag = _be_all["id"].map(_is_untagged)
                if "leg_group" in _be_all.columns:
                    # For spreads: include all legs only when ALL legs are untagged
                    _be_tagged_grps = _be_all.loc[
                        ~_be_direct_untag & _be_all["leg_group"].notna() & (_be_all["leg_group"].astype(str) != ""),
                        "leg_group",
                    ].unique()
                    _be_all = _be_all[
                        _be_direct_untag & ~_be_all["leg_group"].isin(_be_tagged_grps)
                    ].reset_index(drop=True)
                else:
                    _be_all = _be_all[_be_direct_untag].reset_index(drop=True)

            if _be_tag_sel != "(all trades)":
                _be_filter_tag_id = next((t["id"] for t in tag_list if t["name"] == _be_tag_sel), None)
                if _be_filter_tag_id:
                    _be_direct = _be_all["id"].map(lambda tid: _be_filter_tag_id in _be_all_tt.get(tid, set()))
                    if "leg_group" in _be_all.columns:
                        _be_matched_grps = _be_all.loc[
                            _be_direct & _be_all["leg_group"].notna() & (_be_all["leg_group"].astype(str) != ""),
                            "leg_group",
                        ].unique()
                        _be_all = _be_all[_be_direct | _be_all["leg_group"].isin(_be_matched_grps)].reset_index(drop=True)
                    else:
                        _be_all = _be_all[_be_direct].reset_index(drop=True)

            if _be_all.empty:
                st.info("No trades match the current filters.")
            else:
                # Build display rows, collapsing spread legs into a single row per group
                _has_lg = "leg_group" in _be_all.columns
                # Pre-build group map so the loop never does per-row filtering
                _be_grp_map: dict[str, pd.DataFrame] = {}
                if _has_lg:
                    for _gk, _gdf in _be_all.groupby("leg_group", dropna=True):
                        _be_grp_map[str(_gk)] = _gdf

                _be_trade_id_groups: list[list[int]] = []  # one list of IDs per display row
                _be_rows = []
                _seen_groups: set = set()

                for _, _r in _be_all.iterrows():
                    _lg_raw = _r.get("leg_group") if _has_lg else None
                    _lg = str(_lg_raw).strip() if (_lg_raw is not None and not pd.isna(_lg_raw)) else ""
                    if _lg and _lg in _be_grp_map and _lg not in _seen_groups:
                        _seen_groups.add(_lg)
                        _legs    = _be_grp_map[_lg]
                        _leg_ids = _legs["id"].tolist()
                        _stype   = str(_legs.iloc[0].get("spread_type") or "").strip()
                        _tickers = "/".join(dict.fromkeys(_legs["ticker"].dropna().tolist()))
                        _row = {
                            "Date":   str(_legs["entry_date"].dropna().min() or ""),
                            "Ticker": _tickers,
                            "Type":   "Spread",
                            "Status": "Open" if any(_legs.apply(_is_open, axis=1)) else "Closed",
                            "Detail": _stype if _stype else f"{len(_legs)}-leg",
                        }
                        # Checkbox = True only when ALL legs carry the tag (consistent state)
                        _tset_inter = set.intersection(*[_be_all_tt.get(_lid, set()) for _lid in _leg_ids])
                        for _t in tag_list:
                            _row[_t["name"]] = _t["id"] in _tset_inter
                        _be_trade_id_groups.append(_leg_ids)
                        _be_rows.append(_row)
                    elif not _lg:
                        _tid_s = _r["id"]
                        _itype = str(_r.get("instrument_type") or "stock").lower()
                        _detail = ""
                        if _itype == "option":
                            _exp  = str(_r.get("expiration") or "")
                            _strk = _r.get("strike")
                            _ot   = str(_r.get("option_type") or "").upper()[:1]
                            _detail = f"{_exp} ${_strk:.0f}{_ot}" if _strk else _exp
                        _row = {
                            "Date":   str(_r.get("entry_date") or ""),
                            "Ticker": _r["ticker"],
                            "Type":   {"stock": "Stock", "option": "Option", "future": "Future"}.get(_itype, "Stock"),
                            "Status": "Open" if _is_open(_r) else "Closed",
                            "Detail": _detail,
                        }
                        for _t in tag_list:
                            _row[_t["name"]] = _t["id"] in _be_all_tt.get(_tid_s, set())
                        _be_trade_id_groups.append([_tid_s])
                        _be_rows.append(_row)
                    # else: already emitted this leg_group — skip

                _be_display = pd.DataFrame(_be_rows)
                _n_spreads  = sum(1 for g in _be_trade_id_groups if len(g) > 1)
                _be_caption = f"{len(_be_rows)} entr{'ies' if len(_be_rows) != 1 else 'y'} shown"
                if _n_spreads:
                    _be_caption += f" ({_n_spreads} spread{'s' if _n_spreads != 1 else ''} collapsed — tags apply to all legs)"
                st.caption(_be_caption + ".")

                _be_edited = st.data_editor(
                    _be_display,
                    use_container_width=True,
                    hide_index=True,
                    disabled=["Date", "Ticker", "Type", "Status", "Detail"],
                    column_config={
                        _t["name"]: st.column_config.CheckboxColumn(_t["name"], default=False)
                        for _t in tag_list
                    },
                    key=f"bulk_tag_editor_{_be_status}_{_be_ticker}_{_be_tag_sel}",
                )

                if st.button("💾  Save Changes", type="primary", key="be_save"):
                    with st.spinner("Saving…"):
                        _be_changes = 0
                        for _ri, _erow in _be_edited.iterrows():
                            for _tid in _be_trade_id_groups[_ri]:
                                _cur = _be_all_tt.get(_tid, set())
                                for _t in tag_list:
                                    _was = _t["id"] in _cur
                                    _now = bool(_erow.get(_t["name"], False))
                                    if _was and not _now:
                                        remove_tag_from_trade(_tid, _t["id"])
                                        _be_changes += 1
                                    elif not _was and _now:
                                        add_tag_to_trade(_tid, _t["id"])
                                        _be_changes += 1
                        _cached_load_trades.clear()
                        _bust("_v_trades")
                    if _be_changes:
                        st.toast(f"Saved — {_be_changes} tag assignment(s) updated.", icon="✅")
                        st.rerun()
                    else:
                        st.info("No changes detected.")


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — BROKER SYNC
# ════════════════════════════════════════════════════════════════════════════════

elif page == "🔗  Broker Sync":
    st.header("Broker Sync")

    render_tour_panel("🔗  Broker Sync")

    # ── Demo mode warning ─────────────────────────────────────────────────────
    if is_demo:
        st.warning(
            "📴 **Offline Mode** — Broker auto-sync and auto-connect are disabled. "
            "Manual button actions below still work. Switch to **Connected to Broker** mode in ⚙️ Settings to enable auto-sync.",
            icon="ℹ️",
        )

    # ── Broker selector ───────────────────────────────────────────────────────
    st.markdown("#### Select Broker")
    _cur_broker = settings.get("broker", "ib")
    _bc1, _bc2, _bc3 = st.columns(3)
    _ib_selected = _bc1.button(
        "✅  Interactive Brokers" if _cur_broker == "ib" else "Interactive Brokers",
        width='stretch',
        type="primary" if _cur_broker == "ib" else "secondary",
        key="broker_ib_btn",
    )
    _schwab_selected = _bc2.button(
        "Charles Schwab",
        width='stretch',
        disabled=True,
        key="broker_schwab_btn",
        help="Schwab integration — coming soon.",
    )
    _fidelity_selected = _bc3.button(
        "Fidelity",
        width='stretch',
        disabled=True,
        key="broker_fidelity_btn",
        help="Fidelity integration — coming soon.",
    )

    if _ib_selected and _cur_broker != "ib":
        set_setting("broker", "ib")
        st.rerun()

    # Future broker note
    st.markdown(
        "> **📅 Coming Soon:** **Charles Schwab** and **Fidelity** integrations are planned for a future release. "
        "Balance sync, trade import, and live price feeds will be supported via their respective APIs."
    )

    if _cur_broker == "ib":
        # Show connection status badge
        _conn_status = st.session_state.get("_ib_connected")
        if _conn_status is True:
            st.success(f"Connected — {st.session_state.get('_ib_connect_msg', 'IB TWS/Gateway reachable')}")
        elif _conn_status is False:
            st.error(f"Not connected — {st.session_state.get('_ib_connect_msg', 'Could not reach IB TWS/Gateway')}")

        # ── How-to-connect explainer (auto-opens when not connected) ──────────
        with st.expander("🛟  How to connect — step by step", expanded=(_conn_status is False)):
            st.success(
                "**Your information stays private.** Trade Log talks only to the TWS / "
                "IB Gateway program **already running on this same computer**, over the "
                "local address `127.0.0.1` (\"localhost\"). Nothing is sent over the "
                "internet, and Trade Log never sees your IB username or password — it "
                "just reads data from the session you've already logged into. The "
                "connection is **read-only**: it cannot place trades or move money.",
                icon="🔒",
            )
            st.markdown(
                "Follow these steps once. Most people are connected in under two minutes:\n\n"
                "**1. Open TWS or IB Gateway and log in.**  \n"
                "It must be running on *this* computer at the same time as Trade Log. "
                "*(This is the program Trade Log will talk to.)*\n\n"
                "**2. Turn on the API.**  \n"
                "In **TWS**: *Edit → Global Configuration → API → Settings*. "
                "In **IB Gateway**: *Configure → Settings → API → Settings*. "
                "Tick **“Enable ActiveX and Socket Clients.”** "
                "*(This lets a program on your own machine read data — it's off by default.)*\n\n"
                "**3. Confirm the Socket Port** shown on that same screen, and make sure "
                "it matches the **Port** field below:\n"
                "- `7497` — TWS paper (practice) account\n"
                "- `7496` — TWS live account\n"
                "- `4002` — IB Gateway paper account\n"
                "- `4001` — IB Gateway live account\n\n"
                "*(The port is just the “channel number” the two programs use to talk on "
                "your computer.)*\n\n"
                "**4. (Recommended) Allow localhost.**  \n"
                "Leave **“Allow connections from localhost only”** ticked, and optionally "
                "add `127.0.0.1` to **Trusted IPs**. "
                "*(This keeps the door open only to programs on your own machine, and "
                "skips the “accept connection?” popup each time.)*\n\n"
                "**5. Set the fields below** and click **🔌 Test Connection**:\n"
                "- **Host:** `127.0.0.1`  *(your own computer)*\n"
                "- **Port:** the number from step 3\n"
                "- **Client ID:** any unused number — `1` is fine "
                "*(just a label so TWS can tell apps apart)*\n\n"
                "**6. Approve the connection if asked.**  \n"
                "The very first time, TWS may pop up **“Accept incoming connection?”** — "
                "click **Yes / Allow**. *(That's TWS confirming you trust this app — you do.)*"
            )
            st.info(
                "Still seeing *“Not connected”*? The usual culprits: TWS/Gateway isn't "
                "running, the **Port** here doesn't match the one in TWS, the API "
                "checkbox in step 2 isn't ticked, or a TWS popup is waiting for you to "
                "click **Yes**. No Interactive Brokers account? You can ignore this "
                "whole section and log trades manually.",
                icon="💡",
            )

    st.divider()

    if not _ib_mod.is_available():
        st.warning("ib_insync is not installed. Run `pip install ib_insync nest_asyncio` then restart the app.")
        st.info("Flex Query (HTTP-based) does not require ib_insync and will still work below.")

    # ── IB Connection Settings ────────────────────────────────────────────────
    st.markdown("#### Connection Settings")
    bs_ib_host        = settings.get("ib_host",              "127.0.0.1")
    bs_ib_port        = int(settings.get("ib_port",          "7497") or 7497)
    bs_ib_cid         = int(settings.get("ib_client_id",     "1")    or 1)
    bs_ib_live        = settings.get("ib_use_live_prices",   "0") == "1"
    bs_ib_sync        = settings.get("ib_auto_sync_balance", "0") == "1"
    bs_ib_autoconnect = settings.get("ib_auto_connect",      "0") == "1"

    with st.form("ib_conn_form"):
        ib_c1, ib_c2, ib_c3 = st.columns([3, 2, 1])
        new_ib_host = ib_c1.text_input("IB Host", value=bs_ib_host,
                                        help="TWS / Gateway host — usually 127.0.0.1")
        new_ib_port = ib_c2.number_input("Port", value=bs_ib_port,
                                          min_value=1, max_value=65535, step=1, format="%d",
                                          help="7497 = paper, 7496 = live (TWS) | 4002 = paper, 4001 = live (Gateway)")
        new_ib_cid  = ib_c3.number_input("Client ID", value=bs_ib_cid,
                                          min_value=0, max_value=999, step=1, format="%d")
        new_ib_autoconnect = st.toggle(
            "Auto-connect to IB on launch",
            value=bs_ib_autoconnect,
            help="Attempt a connection test automatically when the app starts.",
        )
        new_ib_live = st.toggle("Use IB for live prices (falls back to Yahoo Finance)",
                                 value=bs_ib_live)
        new_ib_sync = st.toggle("Auto-sync account balance from IB on page load",
                                 value=bs_ib_sync)
        ib_form_cols = st.columns([1, 1])
        _save_ib = ib_form_cols[0].form_submit_button("💾  Save IB Settings", width='stretch')
        _test_ib = ib_form_cols[1].form_submit_button("🔌  Test Connection",  width='stretch')

        if _save_ib:
            set_setting("ib_host",              new_ib_host)
            set_setting("ib_port",              str(int(new_ib_port)))
            set_setting("ib_client_id",         str(int(new_ib_cid)))
            set_setting("ib_use_live_prices",   "1" if new_ib_live else "0")
            set_setting("ib_auto_sync_balance", "1" if new_ib_sync else "0")
            set_setting("ib_auto_connect",      "1" if new_ib_autoconnect else "0")
            st.session_state["_ib_cfg"] = {
                "host": new_ib_host, "port": int(new_ib_port),
                "cid": int(new_ib_cid), "use_live": new_ib_live,
            }
            st.session_state.pop("_ib_auto_synced",       None)
            st.session_state.pop("_ib_auto_connect_done", None)  # re-run auto-connect on next load
            st.success("IB settings saved.")
            st.rerun()

        if _test_ib:
            if not _ib_mod.is_available():
                st.error("ib_insync is not installed.")
            else:
                _ok, _msg = _ib_mod.test_connection(new_ib_host, int(new_ib_port), int(new_ib_cid))
                if _ok:
                    st.success(_msg)
                else:
                    st.error(_msg)

    st.divider()

    # ── Flex Query ────────────────────────────────────────────────────────────
    st.markdown("#### Flex Query")
    st.caption(
        "Fetch historical account data (balance, deposits, withdrawals, dividends) "
        "directly from IB via a Flex Query — no TWS connection required. "
        "Set up a Flex Query in [IB Account Management](https://www.interactivebrokers.com/en/software/am3/am3.htm) "
        "under **Reports → Flex Queries**, then paste the token and query ID below."
    )

    bs_flex_token    = settings.get("flex_token",    "")
    bs_flex_query_id = settings.get("flex_query_id", "")

    with st.form("flex_settings_form"):
        fx_c1, fx_c2 = st.columns([3, 2])
        new_flex_token    = fx_c1.text_input("Flex Token",  value=bs_flex_token,
                                              type="password",
                                              help="Found in IB Account Management → Reports → Flex Queries → Create/Manage Tokens")
        new_flex_query_id = fx_c2.text_input("Query ID",    value=bs_flex_query_id,
                                              help="The numeric ID of your Flex Query")
        fl_c1, fl_c2 = st.columns([1, 1])
        _save_flex  = fl_c1.form_submit_button("💾  Save Flex Settings", width='stretch')
        _fetch_flex = fl_c2.form_submit_button("📥  Fetch via Flex Query", width='stretch')

        if _save_flex:
            set_setting("flex_token",    new_flex_token)
            set_setting("flex_query_id", new_flex_query_id)
            st.success("Flex Query settings saved.")

        if _fetch_flex:
            if not new_flex_token.strip() or not new_flex_query_id.strip():
                st.error("Enter both a Flex Token and Query ID before fetching.")
            else:
                with st.spinner("Contacting IB Flex Web Service… this can take up to 2 minutes."):
                    _flex_result = _ib_mod.fetch_flex_report(
                        new_flex_token.strip(), new_flex_query_id.strip()
                    )
                if _flex_result.get("error"):
                    st.error(f"Flex Query error: {_flex_result['error']}")
                    st.info("If this keeps failing, use **Upload XML File** below — "
                            "download the report from IB's portal and upload it directly.")
                else:
                    st.session_state["_flex_result"] = _flex_result
                    st.success("Flex report fetched successfully.")

    # Manual XML upload — reliable fallback when the live API is uncooperative
    st.markdown("##### Or Upload XML Directly")
    st.caption(
        "Download your Flex Statement XML from "
        "[IB Account Management](https://www.interactivebrokers.com/en/software/am3/am3.htm) "
        "→ Reports → Flex Queries → Run, then upload it here."
    )
    _xml_file = st.file_uploader("Upload Flex Statement XML", type=["xml"],
                                  key="flex_xml_upload", label_visibility="collapsed")
    if _xml_file is not None:
        _uploaded_xml = _xml_file.read().decode("utf-8", errors="replace")
        _upload_result = _ib_mod._parse_flex_xml(_uploaded_xml)
        if _upload_result.get("error"):
            st.error(f"XML parse error: {_upload_result['error']}")
        else:
            st.session_state["_flex_result"] = _upload_result

    # Display Flex results outside the form so buttons inside work
    _flex_data = st.session_state.get("_flex_result")
    if _flex_data:
        _fa = _flex_data.get("account_summary", {})
        _ft = _flex_data.get("cash_transactions", [])

        # Metrics row
        fm1, fm2, fm3, fm4 = st.columns(4)
        fm1.metric("Net Liquidation",  f"${_fa.get('net_liquidation', 0):,.2f}")
        fm2.metric("Cash",             f"${_fa.get('cash', 0):,.2f}")
        fm3.metric("Total Deposits",   f"${_fa.get('total_deposits', 0):,.2f}")
        fm4.metric("Total Withdrawals",f"${_fa.get('total_withdrawals', 0):,.2f}")

        if st.button("⬆️  Update Account Balance from Flex Data", key="flex_update_bal"):
            _nl = _fa.get("net_liquidation", 0)
            if _nl:
                set_setting("account_balance", str(_nl))
                st.session_state["_live_balance_set"] = True
                st.success(f"Account balance updated: ${_nl:,.2f}")
                st.rerun()
            else:
                st.warning("Net liquidation value is zero or missing in the Flex report.")

        if _ft:
            st.markdown("##### Cash Transactions")
            st.dataframe(
                pd.DataFrame(_ft),
                width='stretch',
                hide_index=True,
                column_config={
                    "date":        st.column_config.TextColumn("Date",        width="small"),
                    "type":        st.column_config.TextColumn("Type",        width="medium"),
                    "amount":      st.column_config.NumberColumn("Amount",    format="$%.2f", width="small"),
                    "currency":    st.column_config.TextColumn("Currency",    width="small"),
                    "description": st.column_config.TextColumn("Description", width="large"),
                },
            )
        else:
            st.info("No cash transactions found in this Flex report.")

        st.caption("Trade import is in the **Import Trades from IB** section below.")

    st.divider()

    # ── Account Balance Sync (live API) ───────────────────────────────────────
    st.markdown("#### Account Balance Sync")
    st.caption(
        "Pulls the current net liquidation value directly from TWS/Gateway (requires active connection). "
        + ("**📴 Offline mode:** this button is available but auto-sync is disabled." if is_demo else "")
    )
    if st.button("⬇️  Pull Account Balance from IB", width='content'):
        if not _ib_mod.is_available():
            st.error("ib_insync is not installed.")
        else:
            try:
                with _ib_mod.IBClient(bs_ib_host, bs_ib_port, bs_ib_cid) as _ib:
                    _acct = _ib.get_account_summary()
                if _acct.get("net_liquidation"):
                    set_setting("account_balance", str(_acct["net_liquidation"]))
                    st.session_state["_live_balance_set"] = True
                    st.success(f"Account balance updated: ${_acct['net_liquidation']:,.2f}")
                    st.rerun()
                else:
                    st.warning("Could not retrieve NetLiquidation from IB.")
            except Exception as _e:
                st.error(f"IB error: {_e}")

    st.divider()

    # ── Import Trades from IB ─────────────────────────────────────────────────
    st.markdown("#### Import Trades from IB")
    st.caption("Two ways to get your IB trades into the log — pick based on what you need.")

    # ── Option 1: Today's session ──────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 🕐 Today's Trades (Current Session)")
        st.markdown(
            "Connects directly to TWS/Gateway right now and pulls every fill from "
            "**your current session** — typically just today's trades.\n\n"
            "**Important limitation:** IB's live connection can only see trades made "
            "since you last opened TWS or Gateway. It has no access to yesterday, last "
            "week, or any earlier history. If you need older trades, use Full History below.\n\n"
            "*Requires TWS or IB Gateway to be open and connected (see settings above).*"
        )
        if st.button("📥  Fetch Today's Fills", key="ib_fetch_btn", width='content'):
            if not _ib_mod.is_available():
                st.error("ib_insync is not installed.")
            else:
                try:
                    with _ib_mod.IBClient(bs_ib_host, bs_ib_port, bs_ib_cid) as _ib:
                        _execs, _exec_errors = _ib.get_executions(
                            str(pd.Timestamp.today().date())
                        )
                    if _exec_errors:
                        st.warning(
                            f"{len(_exec_errors)} fill(s) could not be processed:\n" +
                            "\n".join(f"• {e}" for e in _exec_errors)
                        )
                    if not _execs:
                        st.info("No fills found in the current session.")
                    else:
                        _trade_previews = _ib_mod.parse_ib_executions_to_trades(_execs)
                        st.session_state["_ib_preview"] = _trade_previews
                        st.success(
                            f"Found {len(_trade_previews)} trade(s) from "
                            f"{len(_execs)} fill(s). Review below and click Import."
                        )
                except Exception as _e:
                    st.error(f"IB error: {_e}")

        _preview = st.session_state.get("_ib_preview")
        if _preview:
            st.caption(f"{len(_preview)} trade(s) ready to import:")
            _prev_df = pd.DataFrame(_preview).drop(
                columns=["notes", "stop_enabled", "opening_stop", "tag_ids",
                         "current_stop", "side", "leg_label"], errors="ignore"
            )
            st.dataframe(_prev_df, width='stretch', hide_index=True)
            _imp_c1, _imp_c2 = st.columns(2)
            if _imp_c1.button("✅  Import All Trades", width='stretch', key="ib_import_all"):
                _imported = 0
                _ib_dupes = 0
                for _td in _preview:
                    try:
                        if is_duplicate_trade(
                            _td.get("ticker", ""),
                            _td.get("entry_date"),
                            _td.get("quantity"),
                            _td.get("entry_price"),
                            _td.get("instrument_type", "stock"),
                            _td.get("expiration"),
                            _td.get("strike"),
                        ):
                            _ib_dupes += 1
                        else:
                            add_trade(**{k: _td[k] for k in [
                                "entry_date", "ticker", "quantity", "entry_price",
                                "exit_date", "exit_price", "notes", "stop_enabled",
                                "opening_stop", "tag_ids", "current_stop",
                                "instrument_type", "expiration", "strike",
                                "option_type", "multiplier", "leg_group", "leg_label", "side",
                            ] if k in _td})
                            _imported += 1
                    except Exception:
                        pass
                st.session_state.pop("_ib_preview", None)
                if _ib_dupes:
                    st.info(f"{_ib_dupes} duplicate(s) skipped — already in the log.")
                st.success(f"Imported {_imported} trade(s).")
                st.rerun()
            if _imp_c2.button("✕  Cancel", width='stretch', key="ib_import_cancel"):
                st.session_state.pop("_ib_preview", None)
                st.rerun()

    # ── Option 2: Full History ─────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("##### 📅 Full History (Any Date Range)")
        st.markdown(
            "Pulls your complete trade history directly from **IB's servers** — last "
            "week, last month, or further back. **TWS does not need to be running.**\n\n"
            "IB has a feature called a **Flex Report** — think of it as a secure "
            "export of your account history that you can request any time from IB's "
            "website. You set it up once, and then this button fetches it automatically "
            "whenever you need it."
        )

        _flex_tok = settings.get("flex_token", "").strip()
        _flex_qid = settings.get("flex_query_id", "").strip()
        _flex_configured = bool(_flex_tok) and bool(_flex_qid)

        with st.expander(
            "⚙️  Setup — " + ("configured ✓" if _flex_configured else "required before first use")
        ):
            st.markdown(
                "**One-time setup — takes about 2 minutes:**\n\n"
                "1. Log in to your IB account at "
                "[interactivebrokers.com](https://www.interactivebrokers.com)\n"
                "2. Go to **Reports → Flex Queries → Create New Flex Query**\n"
                "3. Give it a name, add the **Trades** section, and save. "
                "Note the **Query ID** number shown next to it.\n"
                "4. Go to **Reports → Flex Queries → Manage Tokens**, "
                "create a new token, and copy it.\n"
                "5. Paste both below and click Save — you're done."
            )
            with st.form("flex_settings_import_form"):
                _fsi_c1, _fsi_c2 = st.columns([3, 2])
                _new_flex_tok = _fsi_c1.text_input(
                    "Flex Token", value=_flex_tok, type="password",
                    help="From IB: Reports → Flex Queries → Manage Tokens"
                )
                _new_flex_qid = _fsi_c2.text_input(
                    "Query ID", value=_flex_qid,
                    help="The numeric ID shown next to your Flex Query"
                )
                if st.form_submit_button("💾  Save", width='content'):
                    set_setting("flex_token",    _new_flex_tok)
                    set_setting("flex_query_id", _new_flex_qid)
                    st.success("Saved.")
                    st.rerun()

            st.markdown("---")
            st.markdown(
                "**Can't get the automatic fetch to work?** "
                "Download the XML file manually from IB "
                "(Reports → Flex Queries → Run → Download) and upload it here:"
            )
            _xml_file_imp = st.file_uploader(
                "Upload Flex Statement XML", type=["xml"],
                key="flex_xml_upload_imp", label_visibility="collapsed"
            )
            if _xml_file_imp is not None:
                _xml_imp_result = _ib_mod._parse_flex_xml(
                    _xml_file_imp.read().decode("utf-8", errors="replace")
                )
                if _xml_imp_result.get("error"):
                    st.error(f"XML error: {_xml_imp_result['error']}")
                else:
                    st.session_state["_flex_result"] = _xml_imp_result
                    st.success("File loaded. Set a date range below and import.")
                    st.rerun()

        _flex_today = pd.Timestamp.today().date()
        _imp2_date_from = st.session_state.get(
            "flex_filter_from", _flex_today - pd.Timedelta(days=30)
        )
        _imp2_date_to = st.session_state.get("flex_filter_to", _flex_today)

        if _flex_configured or st.session_state.get("_flex_result"):
            _fpr1, _fpr2, _fpr3, _fpr4 = st.columns(4)
            if _fpr1.button("Last Week",  key="imp2_preset_week",  width='stretch'):
                st.session_state["flex_filter_from"] = _flex_today - pd.Timedelta(weeks=1)
                st.session_state["flex_filter_to"]   = _flex_today
                st.rerun()
            if _fpr2.button("Last Month", key="imp2_preset_month", width='stretch'):
                st.session_state["flex_filter_from"] = _flex_today - pd.Timedelta(days=30)
                st.session_state["flex_filter_to"]   = _flex_today
                st.rerun()
            if _fpr3.button("Last 3 Mo",  key="imp2_preset_3m",   width='stretch'):
                st.session_state["flex_filter_from"] = _flex_today - pd.Timedelta(days=90)
                st.session_state["flex_filter_to"]   = _flex_today
                st.rerun()
            if _fpr4.button("All Time",   key="imp2_preset_all",  width='stretch'):
                st.session_state["flex_filter_from"] = pd.Timestamp("2010-01-01").date()
                st.session_state["flex_filter_to"]   = _flex_today
                st.rerun()

            _flt2_c1, _flt2_c2 = st.columns(2)
            _imp2_date_from = _flt2_c1.date_input(
                "From",
                value=_imp2_date_from,
                key="flex_filter_from",
            )
            _imp2_date_to = _flt2_c2.date_input(
                "To",
                value=_imp2_date_to,
                key="flex_filter_to",
            )

            _fetch2_col, _ = st.columns([1, 2])
            if _fetch2_col.button("📥  Fetch Full History", width='stretch', key="imp2_fetch_btn"):
                if not _flex_configured:
                    st.error("Complete the setup above (token + query ID) first.")
                else:
                    with st.spinner(
                        "Contacting IB's servers… this can take up to 2 minutes."
                    ):
                        _new_flex = _ib_mod.fetch_flex_report(_flex_tok, _flex_qid)
                    if _new_flex.get("error"):
                        st.error(f"Fetch error: {_new_flex['error']}")
                        st.info(
                            "If this keeps failing, download the XML from IB manually "
                            "and upload it via the Setup section above."
                        )
                    else:
                        st.session_state["_flex_result"] = _new_flex
                        st.success("History fetched. Review below and click Import.")
                        st.rerun()
        else:
            st.info("Complete the setup above to enable full history import.")

        _flex_imp_data = st.session_state.get("_flex_result")
        if _flex_imp_data:
            _flex_trades_all = _flex_imp_data.get("trades", [])
            if _flex_trades_all:
                def _flex_in_range(t):
                    d = t.get("entry_date")
                    if d is None:
                        return True
                    try:
                        d_iso = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
                        return str(_imp2_date_from) <= d_iso <= str(_imp2_date_to)
                    except Exception:
                        return True

                _flex_trades = [t for t in _flex_trades_all if _flex_in_range(t)]
                st.caption(
                    f"{len(_flex_trades)} of {len(_flex_trades_all)} trade(s) in range "
                    f"({_imp2_date_from} → {_imp2_date_to}). "
                    "Open positions have no exit date/price."
                )
                _flex_trades_df = pd.DataFrame(_flex_trades).drop(
                    columns=["notes", "stop_enabled", "opening_stop", "current_stop",
                             "tag_ids", "leg_group", "leg_label"], errors="ignore"
                ) if _flex_trades else pd.DataFrame()
                if not _flex_trades_df.empty:
                    st.dataframe(_flex_trades_df, width='stretch', hide_index=True)
                else:
                    st.info("No trades in the selected date range.")

                _import_label2 = (
                    f"✅  Import {len(_flex_trades)} Trade(s)"
                    if len(_flex_trades) < len(_flex_trades_all)
                    else f"✅  Import All {len(_flex_trades_all)} Trade(s)"
                )
                _fc1, _fc2 = st.columns(2)
                if _flex_trades and _fc1.button(_import_label2, width='stretch', key="flex_import_trades"):
                    import time as _t
                    from pathlib import Path as _Path
                    try:
                        _imp_dir = _Path(__file__).parent / "imports"
                        _imp_dir.mkdir(exist_ok=True)
                        _ts_str = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
                        pd.DataFrame(_flex_trades).to_csv(
                            _imp_dir / f"flex_{_ts_str}.csv", index=False
                        )
                    except Exception:
                        pass
                    _total         = len(_flex_trades)
                    _flex_imported = 0
                    _flex_errors   = []
                    _prog          = st.progress(0, text="Starting import…")
                    _eta_txt       = st.empty()
                    _start         = _t.time()
                    _flex_dupes    = 0
                    _flex_closed   = 0
                    for _i, _ftd in enumerate(_flex_trades):
                        try:
                            # Close-only: open fill was outside the Flex date range.
                            # Find the existing open trade by ticker+qty and close it.
                            if _ftd.get("close_only"):
                                _co_match = find_open_trade_by_ticker_qty(
                                    _ftd.get("ticker", ""),
                                    _ftd.get("quantity"),
                                    _ftd.get("instrument_type", "stock"),
                                    _ftd.get("expiration"),
                                    _ftd.get("strike"),
                                )
                                if _co_match:
                                    update_trade(
                                        _co_match,
                                        exit_date=_ftd["exit_date"],
                                        exit_price=_ftd["exit_price"],
                                        notes=_ftd.get("notes"),
                                        current_stop=None,
                                        stop_enabled=False,
                                        tag_ids=[],
                                    )
                                    _flex_closed += 1
                                else:
                                    _flex_errors.append(
                                        f"{_ftd.get('ticker','?')}: close fill found "
                                        f"but no matching open trade (qty {_ftd.get('quantity')})"
                                    )
                                _done    = _i + 1
                                _elapsed = _t.time() - _start
                                _eta     = (_elapsed / _done) * (_total - _done)
                                _prog.progress(_done / _total, text=f"Importing {_done}/{_total} — {_ftd.get('ticker','')}")
                                _eta_txt.caption(f"Elapsed: {_elapsed:.1f}s  ·  ETA: {_eta:.0f}s remaining")
                                continue
                            if is_duplicate_trade(
                                _ftd.get("ticker", ""),
                                _ftd.get("entry_date"),
                                _ftd.get("quantity"),
                                _ftd.get("entry_price"),
                                _ftd.get("instrument_type", "stock"),
                                _ftd.get("expiration"),
                                _ftd.get("strike"),
                            ):
                                if _ftd.get("exit_date") and _ftd.get("exit_price") is not None:
                                    _open_id = find_open_trade_id(
                                        _ftd.get("ticker", ""),
                                        _ftd.get("entry_date"),
                                        _ftd.get("quantity"),
                                        _ftd.get("entry_price"),
                                        _ftd.get("instrument_type", "stock"),
                                        _ftd.get("expiration"),
                                        _ftd.get("strike"),
                                    )
                                    if _open_id:
                                        update_trade(
                                            _open_id,
                                            exit_date=_ftd["exit_date"],
                                            exit_price=_ftd["exit_price"],
                                            notes=_ftd.get("notes"),
                                            current_stop=None,
                                            stop_enabled=False,
                                            tag_ids=[],
                                        )
                                        _flex_closed += 1
                                    else:
                                        _flex_dupes += 1
                                else:
                                    _flex_dupes += 1
                            else:
                                add_trade(**{k: _ftd[k] for k in [
                                    "entry_date", "ticker", "quantity", "entry_price",
                                    "exit_date", "exit_price", "notes", "stop_enabled",
                                    "opening_stop", "tag_ids", "current_stop",
                                    "instrument_type", "expiration", "strike",
                                    "option_type", "multiplier", "leg_group", "leg_label", "side",
                                    "exchange",
                                ] if k in _ftd})
                                _flex_imported += 1
                        except Exception as _e:
                            _flex_errors.append(f"{_ftd.get('ticker','?')}: {_e}")
                        _done    = _i + 1
                        _elapsed = _t.time() - _start
                        _eta     = (_elapsed / _done) * (_total - _done)
                        _prog.progress(
                            _done / _total,
                            text=f"Importing {_done}/{_total} — {_ftd.get('ticker','')}"
                        )
                        _eta_txt.caption(
                            f"Elapsed: {_elapsed:.1f}s  ·  ETA: {_eta:.0f}s remaining"
                        )
                    _prog.progress(1.0, text="Import complete.")
                    _eta_txt.empty()
                    if _flex_errors:
                        st.warning(
                            f"{len(_flex_errors)} trade(s) failed:\n" +
                            "\n".join(f"• {e}" for e in _flex_errors[:5])
                        )
                    if _flex_dupes:
                        st.info(f"{_flex_dupes} duplicate(s) skipped — already in the log.")
                    if _flex_closed:
                        st.info(
                            f"{_flex_closed} existing open trade(s) updated with closing data."
                        )
                    st.success(f"Imported {_flex_imported} trade(s).")
                    # Check which newly-imported non-US tickers can't be resolved on Yahoo Finance.
                    # Those positions will show no live P&L until a closing price is entered manually.
                    _unvalidated = []
                    _seen_for_validation: set = set()
                    for _ftd in _flex_trades:
                        if _ftd.get("close_only"):
                            continue
                        _vtk  = _ftd.get("ticker", "")
                        _vexc = _ftd.get("exchange", "")
                        _vkey = (_vtk, _vexc)
                        if _vtk and _vexc and _vkey not in _seen_for_validation:
                            _seen_for_validation.add(_vkey)
                            if not validate_ticker(_vtk, _vexc):
                                _unvalidated.append(f"{_vtk} ({_vexc})")
                    if _unvalidated:
                        st.warning(
                            "The following tickers could not be validated on Yahoo Finance — "
                            "live prices won't be available for these positions. "
                            "You will need to enter the closing price manually. "
                            "These trades will be excluded from P&L results until a closing price is recorded.\n\n"
                            + "\n".join(f"• {t}" for t in _unvalidated)
                        )
                    st.rerun()
                if _fc2.button("🗑️  Clear", width='stretch', key="flex_clear"):
                    del st.session_state["_flex_result"]
                    st.rerun()
            else:
                st.info("No trades found in the fetched data.")

    # ── Find Duplicate Imports ─────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 🔍 Find Duplicate Imports")
    st.caption(
        "Scans your trade log for trades that look like the same fill imported "
        "more than once — matching on ticker, side, entry date, quantity, and "
        "entry price. Nothing is deleted until you review each group and confirm."
    )

    if st.button("🔍  Scan for duplicates", key="dupe_scan_btn"):
        _groups = find_duplicate_trade_groups()
        st.session_state["_dupe_groups"]  = _groups
        st.session_state["_dupe_scanned"] = True
        st.session_state["_dupe_del_confirm"] = False
        # Seed deletion defaults once: keep the lowest-id copy, suggest deleting
        # the rest. Seeding session_state (instead of passing value= alongside
        # key=) keeps each checkbox sticky across reruns without warnings.
        for _g in _groups:
            for _mi, _m in enumerate(sorted(_g["trades"], key=lambda t: t["id"])):
                st.session_state[f"_dupe_del_{_m['id']}"] = _mi > 0

    if st.session_state.get("_dupe_scanned"):
        _dupe_groups = st.session_state.get("_dupe_groups", [])
        if not _dupe_groups:
            st.success("No duplicate trades found. ✅")
        else:
            _n_extra = sum(len(g["trades"]) - 1 for g in _dupe_groups)
            st.warning(
                f"Found {len(_dupe_groups)} duplicate group(s) — {_n_extra} trade(s) "
                "look like redundant copies. Review and check the ones to delete."
            )
            _del_ids: list = []
            for _g in _dupe_groups:
                _members = sorted(_g["trades"], key=lambda t: t["id"])
                _head    = _members[0]
                _exp_label = (
                    f"**{_head['ticker']}** · {_head.get('side') or 'long'} · "
                    f"{fmt_qty(_head['quantity'])} @ {fmt_price(_head['entry_price'])} · "
                    f"{str(_head.get('entry_date') or '')[:10]} · {len(_members)} copies"
                )
                with st.expander(_exp_label, expanded=True):
                    for _m in _members:
                        _exit_txt = (
                            f" · exit {str(_m['exit_date'])[:10]} @ {fmt_price(_m['exit_price'])}"
                            if _m.get("exit_date") else " · open"
                        )
                        _note_txt = (_m.get("notes") or "").strip()
                        if len(_note_txt) > 70:
                            _note_txt = _note_txt[:70] + "…"
                        _checked = st.checkbox(
                            f"ID {_m['id']}{_exit_txt}" + (f" · {_note_txt}" if _note_txt else ""),
                            key=f"_dupe_del_{_m['id']}",
                        )
                        if _checked:
                            _del_ids.append(int(_m["id"]))

            st.divider()
            if _del_ids:
                if not st.session_state.get("_dupe_del_confirm"):
                    if st.button(f"🗑️  Delete {len(_del_ids)} selected duplicate(s)",
                                 key="dupe_del_btn", type="primary"):
                        st.session_state["_dupe_del_confirm"] = True
                        st.rerun()
                else:
                    st.error(
                        f"Permanently delete {len(_del_ids)} trade(s)? "
                        "This also removes their lots, dividends, and tags. Cannot be undone."
                    )
                    _dcc1, _dcc2 = st.columns(2)
                    if _dcc1.button("Yes, delete", key="dupe_del_yes"):
                        bulk_delete_trades(_del_ids)
                        st.session_state["_dupe_del_confirm"] = False
                        st.session_state.pop("_dupe_groups",  None)
                        st.session_state.pop("_dupe_scanned", None)
                        st.success(f"Deleted {len(_del_ids)} duplicate trade(s).")
                        st.rerun()
                    if _dcc2.button("Cancel", key="dupe_del_no"):
                        st.session_state["_dupe_del_confirm"] = False
                        st.rerun()
            else:
                st.info("No copies checked — tick the trade(s) you want to remove above.")


# ════════════════════════════════════════════════════════════════════════════════
# PAGE — SETTINGS
# ════════════════════════════════════════════════════════════════════════════════

elif page == "⚙️  Settings":
    st.header("Settings")

    render_tour_panel("⚙️  Settings")

    if not st.session_state.get("_tour_active"):
        _rt_col, _ = st.columns([1, 3])
        if _rt_col.button("🧭  Replay setup tutorial", width="stretch", key="settings_replay_tour"):
            _start_tour()

    s_acct_val    = float(settings.get("account_balance",    0))
    s_equity_val  = float(settings.get("starting_equity",    100000))
    s_date_str    = settings.get("starting_date", "")
    s_pct_yellow  = float(settings.get("pct_account_yellow", 5))
    s_pct_red     = float(settings.get("pct_account_red",    10))
    s_stop_unit   = settings.get("stop_dist_unit", "%")
    s_stop_yellow = float(settings.get("stop_dist_yellow",   5))
    s_stop_red    = float(settings.get("stop_dist_red",      2))
    s_euro        = settings.get("euro_dates", "0") == "1"

    # ── Theme ─────────────────────────────────────────────────────────────────
    with st.form("settings_theme_form"):
        st.markdown("#### Theme")
        _theme_options = list(THEMES.keys())
        _theme_labels  = [THEMES[k]["label"] for k in _theme_options]
        _cur_theme_idx = _theme_options.index(_theme_key) if _theme_key in _theme_options else 0
        _new_theme_idx = st.radio(
            "App theme",
            options=range(len(_theme_options)),
            format_func=lambda i: _theme_labels[i],
            index=_cur_theme_idx,
            horizontal=True,
        )
        if st.form_submit_button("💾  Save Theme", width='stretch'):
            set_setting("app_theme", _theme_options[_new_theme_idx])
            _bust("_v_settings")
            st.success(f"Theme set to {_theme_labels[_new_theme_idx]}. Reloading…")
            st.rerun()

    st.divider()

    # ── Display ───────────────────────────────────────────────────────────────
    with st.form("settings_display_form"):
        st.markdown("#### Display")
        new_euro = st.toggle("Euro dates (DD/MM/YYYY)",
                             value=s_euro,
                             help="Changes date display format across the entire app.")
        if st.form_submit_button("💾  Save Display Settings", width='stretch'):
            set_setting("euro_dates", "1" if new_euro else "0")
            st.success("Display settings saved.")
            st.rerun()

    st.divider()

    # ── Row Color Coding ──────────────────────────────────────────────────────
    with st.form("settings_color_form"):
        st.markdown("#### Row Color Coding")
        st.caption(
            "Highlight rows in the Trade Log based on whether each trade is "
            "open/closed and profitable/underwater. Colors apply to text or the entire row."
        )
        _rc_en  = settings.get("row_color_enabled", "0") == "1"
        _rc_sty = settings.get("row_color_style",   "text")
        _rc_op  = settings.get("color_open_profit",   "#2ecc71")
        _rc_ol  = settings.get("color_open_loss",     "#e74c3c")
        _rc_cp  = settings.get("color_closed_profit", "#27ae60")
        _rc_cl  = settings.get("color_closed_loss",   "#c0392b")
        rcc1, rcc2 = st.columns([1, 2])
        new_rc_en  = rcc1.toggle("Enable color coding", value=_rc_en)
        new_rc_sty = rcc2.radio("Apply to", ["text", "row"],
                                 index=0 if _rc_sty == "text" else 1,
                                 format_func=lambda x: "Text color" if x == "text" else "Row background",
                                 horizontal=True)
        if new_rc_en:
            rp1, rp2, rp3, rp4 = st.columns(4)
            new_rc_op = rp1.color_picker("Open — Profit",  value=_rc_op)
            new_rc_ol = rp2.color_picker("Open — Loss",    value=_rc_ol)
            new_rc_cp = rp3.color_picker("Closed — Profit", value=_rc_cp)
            new_rc_cl = rp4.color_picker("Closed — Loss",  value=_rc_cl)
        else:
            new_rc_op, new_rc_ol, new_rc_cp, new_rc_cl = _rc_op, _rc_ol, _rc_cp, _rc_cl
        if st.form_submit_button("💾  Save Color Settings", width='stretch'):
            set_setting("row_color_enabled",    "1" if new_rc_en else "0")
            set_setting("row_color_style",      new_rc_sty)
            set_setting("color_open_profit",    new_rc_op)
            set_setting("color_open_loss",      new_rc_ol)
            set_setting("color_closed_profit",  new_rc_cp)
            set_setting("color_closed_loss",    new_rc_cl)
            st.success("Color settings saved.")
            st.rerun()

    st.divider()

    # ── Multi-Currency ────────────────────────────────────────────────────────
    with st.form("settings_currency_form"):
        st.markdown("#### Multi-Currency")
        st.caption(
            "Enable if your clients trade USD-denominated securities in a non-USD account. "
            "Entry and exit prices are always recorded in USD. The app will also show "
            "P&L converted to the native currency using live and historical FX rates.\n\n"
            "Supported: **AUD**, **CAD**, **EUR**. FX rates sourced from Yahoo Finance."
        )
        _cur_mode_val  = settings.get("currency_mode", "0") == "1"
        _cur_native    = settings.get("native_currency", "USD")
        cx1, cx2 = st.columns(2)
        new_currency_mode   = cx1.toggle("Show native currency P&L",
                                          value=_cur_mode_val,
                                          help="Adds FX-adjusted P&L columns to the trade table.")
        new_native_currency = cx2.selectbox(
            "Client native currency",
            options=["USD", "AUD", "CAD", "EUR"],
            index=["USD", "AUD", "CAD", "EUR"].index(_cur_native) if _cur_native in ["USD","AUD","CAD","EUR"] else 0,
            help=(
                "The currency the client holds their account in. "
                "When a trade is entered the app will record the FX rate at that time."
            ),
        )
        if st.form_submit_button("💾  Save Currency Settings", width='stretch'):
            set_setting("currency_mode",     "1" if new_currency_mode else "0")
            set_setting("native_currency",   new_native_currency)
            st.success("Currency settings saved.")
            st.rerun()
        if _cur_mode_val and _cur_native != "USD":
            _live_fx = get_fx_rate(_cur_native)
            st.info(f"Live rate: 1 {_cur_native} = {_live_fx:.4f} USD  (updates hourly)")

    st.divider()

    # ── Account & Equity ──────────────────────────────────────────────────────
    with st.form("settings_account_form"):
        st.markdown("#### Account & Equity")
        ac1, ac2 = st.columns(2)
        new_acct_bal  = ac1.number_input("Account Balance ($)", min_value=0.0, step=1000.0,
                                         format="%.2f", value=s_acct_val,
                                         help="Used for % of Account column, Sharpe & Sortino")
        new_start_eq  = ac2.number_input("Starting Equity ($)", min_value=0.0, step=1000.0,
                                         format="%.2f", value=s_equity_val,
                                         help="Equity curve and benchmark normalisation starting value")

        use_custom_date = st.checkbox("Set custom starting date for equity curve", value=bool(s_date_str))
        if use_custom_date:
            try:
                date_default = pd.to_datetime(s_date_str).date()
            except Exception:
                date_default = pd.Timestamp.today().date()
            new_start_date = st.date_input("Starting Date", value=date_default)
        else:
            new_start_date = None

        if st.form_submit_button("💾  Save Account & Equity", width='stretch'):
            set_setting("account_balance", str(new_acct_bal))
            set_setting("starting_equity", str(new_start_eq))
            set_setting("starting_date",   new_start_date.isoformat() if new_start_date else "")
            st.success("Account & equity settings saved.")
            st.rerun()

    st.divider()

    # ── Alert Thresholds ──────────────────────────────────────────────────────
    with st.form("settings_thresholds_form"):
        st.markdown("#### Alert Thresholds")

        st.markdown("**% of Account**")
        st.caption("Cells in **% of Account** turn yellow / red when position size exceeds these thresholds.")
        pa1, pa2 = st.columns(2)
        new_pct_yellow = pa1.number_input("Yellow threshold (%)", min_value=0.0, step=0.5, format="%.1f", value=s_pct_yellow)
        new_pct_red    = pa2.number_input("Red threshold (%)",    min_value=0.0, step=0.5, format="%.1f", value=s_pct_red)

        st.markdown("**Distance from Stop**")
        st.caption("**Stop Dist** cells turn yellow / red when price is dangerously close to the stop.")
        sd1, sd2, sd3 = st.columns(3)
        new_stop_unit   = sd1.selectbox("Unit", ["%", "$", "ATR"],
                                        index=["%", "$", "ATR"].index(s_stop_unit))
        new_stop_yellow = sd2.number_input("Yellow threshold", min_value=0.0, step=0.1, format="%.2f", value=s_stop_yellow)
        new_stop_red    = sd3.number_input("Red threshold",    min_value=0.0, step=0.1, format="%.2f", value=s_stop_red)

        if st.form_submit_button("💾  Save Thresholds", width='stretch'):
            set_setting("pct_account_yellow", str(new_pct_yellow))
            set_setting("pct_account_red",    str(new_pct_red))
            set_setting("stop_dist_unit",     new_stop_unit)
            set_setting("stop_dist_yellow",   str(new_stop_yellow))
            set_setting("stop_dist_red",      str(new_stop_red))
            st.success("Threshold settings saved.")
            st.rerun()

    st.divider()

    # ── Email Alerts ──────────────────────────────────────────────────────────
    st.markdown("#### Email Alerts — Earnings Notifications")
    st.caption("Configure SMTP to receive email alerts when open positions have upcoming earnings.")

    s_smtp_host  = settings.get("smtp_host",            "")
    s_smtp_port  = settings.get("smtp_port",            "587")
    s_smtp_user  = settings.get("smtp_user",            "")
    s_smtp_pass  = settings.get("smtp_pass",            "")
    s_smtp_to    = settings.get("smtp_to",              "")
    s_email_thr  = int(settings.get("email_threshold_days", "5") or 5)

    with st.form("email_settings_form"):
        em1, em2 = st.columns([3, 1])
        new_smtp_host = em1.text_input("SMTP Host",     value=s_smtp_host, placeholder="smtp.gmail.com")
        new_smtp_port = em2.number_input("Port",        value=int(s_smtp_port or 587),
                                         min_value=1, max_value=65535, step=1, format="%d")
        new_smtp_user = st.text_input("SMTP Username",  value=s_smtp_user, placeholder="you@example.com")
        new_smtp_pass = st.text_input("SMTP Password",  value=s_smtp_pass, type="password",
                                      help="For Gmail, use an App Password (not your account password).")
        new_smtp_to   = st.text_input("Send Alerts To", value=s_smtp_to,   placeholder="you@example.com")
        new_email_thr = st.number_input("Alert threshold (trading days to earnings)",
                                        min_value=1, max_value=60, value=s_email_thr, step=1, format="%d")
        if st.form_submit_button("💾  Save Email Settings", width='stretch'):
            set_setting("smtp_host",            new_smtp_host)
            set_setting("smtp_port",            str(int(new_smtp_port)))
            set_setting("smtp_user",            new_smtp_user)
            set_setting("smtp_pass",            new_smtp_pass)
            set_setting("smtp_to",              new_smtp_to)
            set_setting("email_threshold_days", str(int(new_email_thr)))
            st.success("Email settings saved.")
            st.rerun()

    # Test / manual send buttons
    eb1, eb2 = st.columns(2)
    if eb1.button("📧  Send Test Email", width='stretch'):
        _test_settings = get_all_settings()
        _err = send_earnings_email(
            [{"ticker": "TEST", "earnings_date": str(pd.Timestamp.today().date()), "bdays": 0}],
            _test_settings,
        )
        if _err:
            st.error(f"Failed: {_err}")
        else:
            st.success("Test email sent!")

    if eb2.button("📬  Check Earnings & Send Alerts Now", width='stretch'):
        _open_trades = _cached_load_trades(st.session_state["_v_trades"])
        _open_trades = _open_trades[_open_trades.apply(_is_open, axis=1)]
        _thr  = int(get_setting("email_threshold_days", "5") or 5)
        _alerts = []
        for _, _r in _open_trades.iterrows():
            _manual = _r.get("earnings_date")
            _ed = (_manual if _manual and not pd.isna(_manual) and str(_manual).strip()
                   else fetch_next_earnings(_r["ticker"]))
            if _ed:
                try:
                    _bd = int(np.busday_count(pd.Timestamp.today().date(),
                                              pd.to_datetime(_ed).date()))
                    if 0 <= _bd <= _thr:
                        _alerts.append({"ticker": _r["ticker"], "earnings_date": _ed, "bdays": _bd})
                except Exception:
                    pass
        if _alerts:
            _cur_settings = get_all_settings()
            _err = send_earnings_email(_alerts, _cur_settings)
            if _err:
                st.error(f"Email failed: {_err}")
            else:
                set_setting("email_last_sent", str(pd.Timestamp.today().date()))
                st.success(f"Sent alert for {len(_alerts)} position(s).")
        else:
            st.info(f"No open positions have earnings within {_thr} trading days.")

    st.divider()

    # ── App Mode ──────────────────────────────────────────────────────────────
    with st.form("settings_mode_form"):
        st.markdown("#### App Mode")
        st.caption(
            "**Offline mode** is safe — no broker calls are made automatically. "
            "**Connected to Broker** enables auto-connect and auto-sync features on the Broker Sync page."
        )
        _cur_mode  = settings.get("app_mode", "demo")
        _mode_opts = ["demo", "live"]
        new_mode   = st.radio(
            "Mode",
            _mode_opts,
            index=_mode_opts.index(_cur_mode) if _cur_mode in _mode_opts else 0,
            format_func=lambda m: "📴  Offline (safe, no broker calls)" if m == "demo" else "🟢  Connected to Broker (auto-sync enabled)",
            horizontal=True,
        )
        if st.form_submit_button("💾  Save App Mode", width='stretch'):
            set_setting("app_mode", new_mode)
            st.success(f"App mode set to {'Connected to Broker' if new_mode == 'live' else 'Offline'}. Restart or reload to apply badge.")
            st.rerun()

    st.divider()

    # ── Commission Defaults ───────────────────────────────────────────────────
    with st.form("settings_commission_form"):
        st.markdown("#### Commission Defaults")
        st.caption(
            "Default commissions pre-filled in the trade entry form. "
            "You can override per trade. Set to 0 if you trade commission-free."
        )
        _oc_col, _fc_col, _sc_col = st.columns(3)
        new_def_comm = _sc_col.number_input(
            "Stocks — per trade ($)",
            min_value=0.0, step=0.01, format="%.2f",
            value=_default_commission,
            help="Flat commission for stock trades. Override individually in the Add Trade form.",
        )
        _opts_comm_val  = float(settings.get("options_commission", "0.65") or 0.65)
        _futs_comm_val  = float(settings.get("futures_commission", "2.25") or 2.25)
        new_opts_comm = _oc_col.number_input(
            "Options — per contract ($)",
            min_value=0.0, step=0.01, format="%.2f",
            value=_opts_comm_val,
            help="Commission charged per option contract (typically $0.50–$1.00 at most brokers).",
        )
        new_futs_comm = _fc_col.number_input(
            "Futures — per contract ($)",
            min_value=0.0, step=0.01, format="%.2f",
            value=_futs_comm_val,
            help="Round-turn commission per futures contract (varies by broker and product).",
        )
        if st.form_submit_button("💾  Save Commission Defaults", width='stretch'):
            set_setting("default_commission",  str(new_def_comm))
            set_setting("options_commission",  str(new_opts_comm))
            set_setting("futures_commission",  str(new_futs_comm))
            st.success("Commission defaults saved.")
            st.rerun()

    st.divider()

    # ── Accounts Management ───────────────────────────────────────────────────
    st.markdown("#### Accounts")
    st.caption(
        "Accounts let you track trades across multiple brokerage accounts. "
        "The 'Default' account cannot be deleted."
    )
    _accts_now = _cached_load_accounts(st.session_state["_v_accounts"])
    for _acct_name in _accts_now:
        _ac1, _ac2 = st.columns([6, 1])
        _ac1.markdown(f"**{_acct_name}**")
        if _acct_name != "Default":
            if _ac2.button("✕", key=f"del_acct_{_acct_name}", help="Delete account"):
                delete_account(_acct_name)
                st.rerun()

    st.markdown("**Add Account**")
    with st.form("add_account_form", clear_on_submit=True):
        new_acct_name = st.text_input("Account Name", placeholder="e.g. Schwab IRA, IB Margin…")
        if st.form_submit_button("Add Account", width='stretch'):
            if new_acct_name.strip():
                add_account(new_acct_name.strip())
                st.rerun()
            else:
                st.error("Account name is required.")

    st.divider()

    # ── Database ──────────────────────────────────────────────────────────────
    st.markdown("#### Database")
    from db import DB_PATH as _db_path, BACKUP_DIR as _backup_dir, _do_backup as _manual_backup
    import datetime as _dt
    st.caption(
        f"Data file: `{_db_path}`  \n"
        "To keep personal data out of git, `tradelog.db` is listed in `.gitignore`. "
        "Use the buttons below to download or restore a backup."
    )
    _db_col1, _db_col2, _db_col3 = st.columns(3)
    if _db_path.exists():
        _db_size_kb = _db_path.stat().st_size / 1024
        st.caption(f"Current size: **{_db_size_kb:.1f} KB**")
        with open(_db_path, "rb") as _f:
            _db_bytes = _f.read()
        _db_col1.download_button(
            "⬇️  Download DB",
            data=_db_bytes,
            file_name=f"tradelog-{_dt.date.today().isoformat()}.db",
            mime="application/octet-stream",
            width='stretch',
        )
    if _db_col2.button("📦  Backup Now", width='stretch'):
        _manual_backup()
        _latest = _backup_dir / f"backup-{_dt.date.today().isoformat()}.db"
        if _latest.exists():
            st.success(f"Backed up to `{_latest.name}`")
        else:
            st.info("Database is too large for automatic backup (>10 MB). Download manually above.")

    # List existing backups
    _backups = sorted(_backup_dir.glob("backup-*.db"), reverse=True)
    if _backups:
        st.markdown("**Existing backups:**")
        _restore_pending = st.session_state.get("_restore_pending_bp")
        if _restore_pending:
            st.warning(
                f"⚠️ Restore **{_restore_pending}**? "
                "All changes made since this backup will be permanently lost.",
            )
            _rc1, _rc2 = st.columns(2)
            if _rc1.button("✅  Yes, restore", type="primary", width='stretch'):
                import shutil as _shu
                _bp_path = _backup_dir / _restore_pending
                if _bp_path.exists():
                    _shu.copy2(_bp_path, _db_path)
                    st.session_state.pop("_restore_pending_bp", None)
                    st.success("Backup restored. Reloading…")
                    st.rerun()
                else:
                    st.error("Backup file not found.")
            if _rc2.button("✕  Cancel", width='stretch'):
                st.session_state.pop("_restore_pending_bp", None)
                st.rerun()
        for _bp in _backups[:10]:
            _bp_kb = _bp.stat().st_size / 1024
            _bc1, _bc2, _bc3, _bc4 = st.columns([4, 2, 1, 1])
            _bc1.markdown(f"`{_bp.name}`")
            _bc2.caption(f"{_bp_kb:.1f} KB")
            with open(_bp, "rb") as _f:
                _bp_bytes = _f.read()
            _bc3.download_button("⬇️", data=_bp_bytes, file_name=_bp.name,
                                 mime="application/octet-stream",
                                 key=f"dl_backup_{_bp.name}")
            if _bc4.button("↩️", key=f"restore_{_bp.name}", help="Restore this backup"):
                st.session_state["_restore_pending_bp"] = _bp.name
                st.rerun()

