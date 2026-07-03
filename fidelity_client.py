"""
Fidelity statement (PDF) parser.

Fidelity has no open trading API for retail, so instead of an OAuth/REST client
(like ``schwab_client``) this module reads a **monthly brokerage statement PDF**
the user drops into the Broker Sync page and turns it into the same unified
report dict every other broker integration produces::

    {
        "account_summary":   {"net_liquidation", "cash",
                              "total_deposits", "total_withdrawals", "period"},
        "cash_transactions": [{date, type, amount, description}],
        "trades":            [ add_trade()-compatible dicts ],
        "daily_nav":         [{date, balance, contributions, withdrawals}],
        "error":             None | "message",
    }

Trade aggregation is delegated to ``ib_client.fills_to_trades`` — the same
battle-tested routine IB Flex and Schwab use — so **scale-in / scale-out is
handled identically**: multiple partial buys collapse into one weighted-average
entry and multiple partial sells into one weighted-average exit per position
cycle (a cycle = position going from flat back to flat).

Parsing a PDF is inherently format-sensitive. Everything below is defensive
(never raises; returns an ``error`` string) and the Broker Sync UI always shows a
preview plus the raw extracted text so the user can verify before importing. The
regexes target Fidelity's standard statement wording ("You Bought"/"You Sold",
"Electronic Funds Transfer", "Ending Account Value", …); tune the constants near
the top if a particular statement layout isn't picked up.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

_SRC_DIR     = Path(__file__).parent
_IMPORTS_DIR = _SRC_DIR / "imports"
_IMPORTS_DIR.mkdir(exist_ok=True)

_PDF_AVAILABLE = False
try:
    import pdfplumber  # type: ignore
    _PDF_AVAILABLE = True
except ImportError:
    pass

import ib_client as _ib  # reuse fills_to_trades / _to_date


def is_available() -> bool:
    """True if the PDF stack needed to read a statement is importable."""
    return _PDF_AVAILABLE


# ── Wording Fidelity uses on statements (edit here to tune) ─────────────────────

# Transaction verbs → whether the fill is a buy (adds/opens long) or sell.
_BUY_WORDS  = ("YOU BOUGHT", "BOUGHT", "PURCHASE", "REINVESTMENT", "YOU REINVESTED")
_SELL_WORDS = ("YOU SOLD", "SOLD", "SALE", "REDEMPTION")

# Cash-flow lines that add money to the account (contributions / deposits).
_DEPOSIT_WORDS = (
    "ELECTRONIC FUNDS TRANSFER RECEIVED", "DIRECT DEPOSIT", "DEPOSIT",
    "TRANSFER OF ASSETS", "CONTRIBUTION", "FUNDS RECEIVED", "MONEY LINE PAID",
    "INCOMING", "CHECK RECEIVED", "WIRE RECEIVED", "JOURNALED IN",
)
# Cash-flow lines that remove money (withdrawals / distributions of cash).
_WITHDRAWAL_WORDS = (
    "ELECTRONIC FUNDS TRANSFER PAID", "WITHDRAWAL", "DISTRIBUTION",
    "MONEY LINE", "CHECK PAID", "WIRE SENT", "JOURNALED OUT",
    "DIRECT DEBIT", "FUNDS PAID",
)

# Ending / beginning account value labels.
_ENDING_VALUE_WORDS = (
    "ENDING ACCOUNT VALUE", "ENDING NET ACCOUNT VALUE", "NET ACCOUNT VALUE",
    "ENDING VALUE", "TOTAL ACCOUNT VALUE",
)
_BEGINNING_VALUE_WORDS = ("BEGINNING ACCOUNT VALUE", "BEGINNING NET ACCOUNT VALUE", "BEGINNING VALUE")

# A ticker shown in parentheses, e.g. "APPLE INC (AAPL)".
_PAREN_SYMBOL = re.compile(r"\(([A-Z][A-Z.\-]{0,6})\)")
# A number that may carry thousands separators / a leading $ / trailing minus.
_NUM = r"-?\$?\(?-?[\d,]+\.\d{2,6}\)?-?"
_MONEY = re.compile(r"-?\$?\(?-?[\d,]+\.\d{2}\)?-?")


# ── Number / date helpers ───────────────────────────────────────────────────────

def _to_float(tok: str) -> float | None:
    """Parse a statement number. Handles $, commas, and both () and trailing-minus
    negatives. Returns None if not numeric."""
    if tok is None:
        return None
    s = str(tok).strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s.endswith("-"):
        neg, s = True, s[:-1]
    s = s.replace("$", "").replace(",", "").replace("+", "").strip()
    if s.startswith("-"):
        neg, s = True, s[1:]
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def _norm_date(raw: str, default_year: int | None = None) -> str | None:
    """Normalise a statement date to ISO ``YYYY-MM-DD``.

    Accepts ``MM/DD/YYYY``, ``MM/DD/YY``, ``MM/DD`` (year filled from
    ``default_year``), and ``Month DD, YYYY``. Returns None if unparseable.
    """
    if not raw:
        return None
    s = raw.strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", s)
    if m:
        mo, da, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        if yr is None:
            if default_year is None:
                return None
            year = default_year
        else:
            year = int(yr)
            if year < 100:
                year += 2000
        try:
            return datetime.date(year, mo, da).isoformat()
        except ValueError:
            return None
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$", s)
    if m:
        mo = _MONTHS.get(m.group(1).lower())
        if mo:
            try:
                return datetime.date(int(m.group(3)), mo, int(m.group(2))).isoformat()
            except ValueError:
                return None
    return None


# ── PDF text extraction ─────────────────────────────────────────────────────────

def extract_text(pdf_bytes: bytes) -> tuple[str, str]:
    """Return (full_text, error). Concatenates every page's text."""
    if not _PDF_AVAILABLE:
        return "", ("The 'pdfplumber' library is not installed — run "
                    "'pip install pdfplumber' (it's in requirements.txt).")
    try:
        import io
        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text(x_tolerance=1.5) or "")
        text = "\n".join(parts)
        if not text.strip():
            return "", ("No text could be read from this PDF. If it's a scanned "
                        "image statement, it needs OCR first — Fidelity's own "
                        "downloaded statements are text PDFs and should work.")
        return text, ""
    except Exception as e:
        return "", f"Could not read the PDF: {e}"


# ── Statement period / account value ────────────────────────────────────────────

def _find_statement_period(text: str) -> tuple[str | None, str | None]:
    """Return (start_iso, end_iso) for the statement's reporting period."""
    # e.g. "January 1, 2026 - January 31, 2026" or "01/01/2026 - 01/31/2026"
    patterns = [
        r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})\s*(?:-|–|through|to)\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|–|through|to)\s*(\d{1,2}/\d{1,2}/\d{2,4})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return _norm_date(m.group(1)), _norm_date(m.group(2))
    return None, None


def _find_account_value(text: str, words: tuple) -> float | None:
    """Find the dollar amount on the first line matching any of ``words``."""
    up = text.upper()
    for w in words:
        idx = up.find(w)
        if idx == -1:
            continue
        # Look at the rest of that line for the last money token.
        line_end = text.find("\n", idx)
        segment = text[idx: line_end if line_end != -1 else idx + 200]
        monies = _MONEY.findall(segment)
        if monies:
            v = _to_float(monies[-1])
            if v is not None:
                return v
    return None


# ── Trade fills ─────────────────────────────────────────────────────────────────

def _parse_trade_fills(text: str, year: int | None) -> list[dict]:
    """Scan every line for a securities-bought/sold fill.

    A fill line carries: a date, a buy/sell verb, a ticker (parenthesised),
    a share quantity, a per-share price, and a total amount. We locate the verb,
    read the ticker, then take the trailing numeric tokens as qty / price / amount.
    Options are skipped (Fidelity option descriptions don't fit this share-based
    shape cleanly); stocks/ETFs/funds are captured.
    """
    fills: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        up = line.upper()

        if any(w in up for w in _BUY_WORDS):
            side, oc = "long", "O"
        elif any(w in up for w in _SELL_WORDS):
            side, oc = "short", "C"
        else:
            continue

        # Ticker: prefer a parenthesised all-caps symbol.
        msym = _PAREN_SYMBOL.search(line)
        if not msym:
            continue
        ticker = msym.group(1).upper().strip()
        if not ticker or ticker in ("CUSIP", "USD"):
            continue

        # Date: first MM/DD or MM/DD/YYYY on the line.
        mdate = re.search(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", line)
        date_iso = _norm_date(mdate.group(1), year) if mdate else None
        if not date_iso:
            continue

        # Numeric tokens after the ticker → quantity, price, amount (last three).
        tail = line[msym.end():]
        nums = re.findall(_NUM, tail)
        vals = [v for v in (_to_float(n) for n in nums) if v is not None]
        if len(vals) < 3:
            # Some layouts put the amount before the symbol; fall back to the
            # whole line's trailing numbers.
            nums = re.findall(_NUM, line)
            vals = [v for v in (_to_float(n) for n in nums) if v is not None]
        if len(vals) < 3:
            continue

        qty, price, amount = abs(vals[-3]), abs(vals[-2]), vals[-1]
        if qty <= 0 or price <= 0:
            continue

        fills.append({
            "date":            date_iso,
            "datetime":        date_iso + "T00:00:00",
            "ticker":          ticker,
            "exchange":        "",
            "instrument_type": "stock",
            "side":            side,
            "quantity":        qty,
            "price":           price,
            "expiration":      None,
            "strike":          None,
            "option_type":     None,
            "multiplier":      1.0,
            "open_close":      oc,
            "commission":      0.0,
            "fifo_pnl":        0.0,
            "trade_id":        "",
            "txn_type":        "TRADE",
        })
    return fills


# ── Cash flow ────────────────────────────────────────────────────────────────────

def _parse_cash_transactions(text: str, year: int | None) -> list[dict]:
    """Extract deposits (contributions) and withdrawals from cash-activity lines."""
    txns: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        up = line.upper()

        is_dep = any(w in up for w in _DEPOSIT_WORDS)
        is_wth = any(w in up for w in _WITHDRAWAL_WORDS)
        # A withdrawal word takes precedence when both match ("...TRANSFER PAID"
        # contains "TRANSFER" wording that could look like a deposit).
        if is_wth:
            ttype = "withdrawal"
        elif is_dep:
            ttype = "deposit"
        else:
            continue
        # Skip section headers / summary lines with no dollar amount.
        mdate = re.search(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", line)
        date_iso = _norm_date(mdate.group(1), year) if mdate else None
        monies = _MONEY.findall(line)
        vals = [v for v in (_to_float(m) for m in monies) if v is not None]
        if not vals or date_iso is None:
            continue
        amount = abs(vals[-1])
        if amount == 0:
            continue
        txns.append({
            "date":        date_iso,
            "type":        ttype,
            "amount":      amount if ttype == "deposit" else -amount,
            "description": re.sub(r"\s{2,}", " ", line)[:120],
        })
    return txns


# ── Orchestrator ─────────────────────────────────────────────────────────────────

_EMPTY = lambda err=None: {
    "account_summary": {"net_liquidation": 0.0, "cash": 0.0,
                        "total_deposits": 0.0, "total_withdrawals": 0.0, "period": None},
    "cash_transactions": [], "trades": [], "daily_nav": [], "error": err,
}


def parse_statement(pdf_bytes: bytes, filename: str = "") -> dict:
    """Parse a Fidelity statement PDF into the unified broker-report dict."""
    text, err = extract_text(pdf_bytes)
    if err:
        return _EMPTY(err)

    # Persist the extracted text for troubleshooting (best effort).
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "statement")
        (_IMPORTS_DIR / f"fidelity_{ts}_{safe}.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass

    start_iso, end_iso = _find_statement_period(text)
    year = int(end_iso[:4]) if end_iso else (int(start_iso[:4]) if start_iso else None)

    fills   = _parse_trade_fills(text, year)
    trades  = _ib.fills_to_trades(fills, "Fidelity Statement") if fills else []
    cash    = _parse_cash_transactions(text, year)

    ending    = _find_account_value(text, _ENDING_VALUE_WORDS)
    beginning = _find_account_value(text, _BEGINNING_VALUE_WORDS)

    total_dep = sum(t["amount"] for t in cash if t["amount"] > 0)
    total_wth = sum(-t["amount"] for t in cash if t["amount"] < 0)

    # Daily NAV: a monthly statement gives one month-end value. Attach that as a
    # single equity entry on the statement end date, with the month's aggregated
    # contributions / withdrawals so the equity curve stays consistent.
    daily_nav: list[dict] = []
    if ending is not None and end_iso:
        daily_nav.append({
            "date":          end_iso,
            "balance":       ending,
            "contributions": total_dep,
            "withdrawals":   total_wth,
        })

    account_summary = {
        "net_liquidation":   ending if ending is not None else 0.0,
        "cash":              0.0,
        "beginning_value":   beginning if beginning is not None else 0.0,
        "total_deposits":    total_dep,
        "total_withdrawals": total_wth,
        "period":            (start_iso, end_iso),
    }
    return {
        "account_summary":   account_summary,
        "cash_transactions": cash,
        "trades":            trades,
        "daily_nav":         daily_nav,
        "error":             None,
        "raw_text":          text,
        "fill_count":        len(fills),
    }
