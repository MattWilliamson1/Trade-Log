"""
Interactive Brokers client wrapper using ib_insync.

Each public method connects, queries, and disconnects to avoid persistent
connections across Streamlit reruns. Falls back gracefully if IB is not
available or not configured.
"""

from __future__ import annotations

import datetime
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_IMPORTS_DIR = Path(__file__).parent / "imports"
_IMPORTS_DIR.mkdir(exist_ok=True)

_IB_AVAILABLE = False
try:
    import nest_asyncio
    nest_asyncio.apply()
    from ib_insync import IB, Stock, Option, Future, Contract, util  # type: ignore
    _IB_AVAILABLE = True
except ImportError:
    pass

_connect_lock = threading.Lock()


def is_available() -> bool:
    return _IB_AVAILABLE


class IBClient:
    """Short-lived IB connection: connect → query → disconnect."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self.host      = host
        self.port      = int(port)
        self.client_id = int(client_id)
        self._ib: Any  = None

    def __enter__(self):
        if not _IB_AVAILABLE:
            raise RuntimeError("ib_insync is not installed")
        with _connect_lock:
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id, timeout=10)
            self._ib.sleep(0.5)
        return self

    def __exit__(self, *_):
        try:
            if self._ib and self._ib.isConnected():
                self._ib.disconnect()
        except Exception:
            pass
        self._ib = None

    # ── Live prices ────────────────────────────────────────────────────────────

    def get_live_prices(self, tickers: list[str]) -> dict[str, dict]:
        """Return {ticker: {"price": float, "prev_close": float}} for each ticker."""
        result: dict[str, dict] = {}
        if not self._ib:
            return result

        contracts = []
        ticker_map: dict[Any, str] = {}
        for sym in tickers:
            try:
                # OCC option symbol: 6+ char root + 6-digit date + C/P + 8-digit strike
                if re.match(r'^[A-Z]{1,6}\d{6}[CP]\d{8}$', sym):
                    root   = re.match(r'^([A-Z]+)', sym).group(1)
                    dstr   = sym[len(root):len(root)+6]
                    pc     = sym[len(root)+6]
                    strike = int(sym[len(root)+7:]) / 1000.0
                    expiry = "20" + dstr
                    right  = 'C' if pc == 'C' else 'P'
                    # Try SMART first (works for equity options); fall back to CBOE
                    # for cash-settled index options (SPX, VIX, NDX, RUT, etc.)
                    qualified = self._ib.qualifyContracts(
                        Option(root, expiry, strike, right, 'SMART')
                    )
                    if not qualified:
                        qualified = self._ib.qualifyContracts(
                            Option(root, expiry, strike, right, 'CBOE')
                        )
                else:
                    c = Stock(sym, 'SMART', 'USD')
                    qualified = self._ib.qualifyContracts(c)
                if qualified:
                    ticker_map[id(qualified[0])] = sym
                    contracts.append(qualified[0])
            except Exception:
                pass

        if not contracts:
            return result

        tickers_obj = self._ib.reqTickers(*contracts)
        for t in tickers_obj:
            sym = ticker_map.get(id(t.contract))
            if sym is None:
                sym = getattr(t.contract, 'symbol', None)
            if sym is None:
                continue

            import math as _math

            def _valid(v):
                try:
                    return v is not None and not _math.isnan(float(v)) and float(v) > 0
                except (TypeError, ValueError):
                    return False

            # Priority: last trade → close → bid/ask midpoint
            if _valid(t.last):
                price = float(t.last)
            elif _valid(t.close):
                price = float(t.close)
            elif _valid(t.bid) and _valid(t.ask):
                price = (float(t.bid) + float(t.ask)) / 2
            else:
                price = None

            prev_close = float(t.close) if _valid(t.close) else None
            result[sym] = {"price": price, "prev_close": prev_close}
        return result

    # ── Account summary ────────────────────────────────────────────────────────

    def get_account_summary(self) -> dict:
        """Return account-level metrics: net_liquidation, cash, unrealized_pnl."""
        if not self._ib:
            return {}
        summary = self._ib.accountSummary()
        result: dict[str, float] = {}
        key_map = {
            "NetLiquidation":    "net_liquidation",
            "TotalCashValue":    "cash",
            "UnrealizedPnL":     "unrealized_pnl",
            "RealizedPnL":       "realized_pnl",
        }
        for item in summary:
            mapped = key_map.get(item.tag)
            if mapped:
                try:
                    result[mapped] = float(item.value)
                except (ValueError, TypeError):
                    pass
        return result

    # ── Trade executions ───────────────────────────────────────────────────────

    def get_executions(self, start_date: str) -> tuple[list[dict], list[str]]:
        """
        Return (rows, errors) where rows is a list of execution dicts from IB fills
        since start_date (ISO string) and errors lists any per-fill processing failures.
        Each row has: time, ticker, instrument_type, side, quantity, price,
                      expiration, strike, option_type, multiplier, leg_group.
        Note: reqExecutions only returns fills from the current TWS session.
        """
        if not self._ib:
            return [], []
        from ib_insync import ExecutionFilter  # type: ignore
        ef = ExecutionFilter()
        ef.time = start_date.replace("-", "") + " 00:00:00"  # yyyymmdd hh:mm:ss
        trades = self._ib.reqExecutions(ef)

        rows: list[dict] = []
        errors: list[str] = []
        for trade in trades:
            ex  = trade.execution
            con = trade.contract
            try:
                if _is_bag_contract(con):
                    continue  # combo aggregate — individual legs are included separately
                itype = _contract_type(con)
                rows.append({
                    "time":          str(ex.time),
                    "date":          str(ex.time)[:10],
                    "ticker":        con.symbol,
                    "instrument_type": itype,
                    "side":          "long" if ex.side == "BOT" else "short",
                    "quantity":      abs(float(ex.shares)),
                    "price":         float(ex.avgPrice),
                    "expiration":    con.lastTradeDateOrContractMonth if itype == "option" else None,
                    "strike":        float(con.strike) if itype == "option" else None,
                    "option_type":   "call" if con.right == "C" else "put" if itype == "option" else None,
                    "multiplier":    float(con.multiplier) if con.multiplier else 1.0,
                    "leg_group":     str(ex.permId) if ex.permId else None,
                    "perm_id":       ex.permId,
                    "exec_id":       ex.execId,
                })
            except Exception as e:
                label = getattr(con, "symbol", None) or getattr(ex, "execId", "unknown")
                errors.append(f"{label}: {e}")
        return rows, errors

    # ── Cash transactions ──────────────────────────────────────────────────────

    def get_cash_transactions(self, start_date: str) -> list[dict]:
        """
        Return deposits, withdrawals, dividends, and interest from IB
        since start_date (ISO string).
        """
        if not self._ib:
            return []
        try:
            # Flex query alternative: use statement of funds
            fund_stmts = self._ib.reqPnLSingle  # not the right call, use below
        except Exception:
            pass

        # IB doesn't expose cash transactions via the live API in a simple way.
        # We use the account ledger as a proxy.
        result: list[dict] = []
        try:
            positions = self._ib.portfolio()
            _ = positions  # not directly useful here
            summary   = self._ib.accountSummary()
            for item in summary:
                if item.tag in ("Deposits", "Withdrawals"):
                    try:
                        txn_type = item.tag.rstrip("s").lower()
                        result.append({
                            "date":        datetime.date.today().isoformat(),
                            "type":        txn_type,
                            "amount":      abs(float(item.value)),
                            "description": f"IB account {item.tag}",
                            "source":      "ib",
                        })
                    except Exception:
                        pass
        except Exception:
            pass
        return result

    # ── Greeks refresh ─────────────────────────────────────────────────────────

    def get_option_greeks(self, tickers_options: list[dict]) -> dict[int, dict]:
        """
        For a list of option trades [{trade_id, ticker, expiration, strike, option_type}],
        return {trade_id: {"delta": float, "theta": float}}.
        """
        if not self._ib:
            return {}
        result: dict[int, dict] = {}
        for item in tickers_options:
            try:
                root   = item["ticker"]
                expiry = str(item["expiration"]).replace("-", "")[:8]
                strike = float(item["strike"])
                right  = "C" if str(item.get("option_type", "")).upper().startswith("C") else "P"
                c = Option(root, expiry, strike, right, 'SMART')
                qualified = self._ib.qualifyContracts(c)
                if not qualified:
                    continue
                [ticker_obj] = self._ib.reqTickers(qualified[0])
                if ticker_obj.modelGreeks:
                    result[item["trade_id"]] = {
                        "delta": ticker_obj.modelGreeks.delta,
                        "theta": ticker_obj.modelGreeks.theta,
                    }
            except Exception:
                pass
        return result


# ── Flex Query (HTTP, no IB connection needed) ─────────────────────────────────

_FLEX_SEND_URL = (
    "https://ndcdyn.interactivebrokers.com"
    "/AccountManagement/FlexWebService/SendRequest"
    "?t={token}&q={query_id}&v=3"
)
_FLEX_GET_URL = "{url}?q={ref}&v=3"
_FLEX_HEADERS = {"User-Agent": "Mozilla/5.0"}


_FLEX_EMPTY = lambda err=None: {
    "account_summary": {"net_liquidation": 0.0, "cash": 0.0,
                        "total_deposits": 0.0, "total_withdrawals": 0.0},
    "cash_transactions": [], "trades": [], "daily_nav": [], "error": err,
}


def fetch_flex_report(token: str, query_id: str) -> dict:
    """
    Fetch an IB Flex Query report and return structured data.

    IB's Flex Web Service requires >=10 s before the first GetStatement call.
    Rapid re-polls return 'Invalid request' (an anti-hammering guard, not a hard
    error), so we use exponential back-off: 10, 15, 20, 30, 45 s between attempts.
    """
    try:
        # Step 1 — trigger report generation
        req1 = urllib.request.Request(
            _FLEX_SEND_URL.format(token=token, query_id=query_id),
            headers=_FLEX_HEADERS,
        )
        with urllib.request.urlopen(req1, timeout=30) as resp:
            xml1 = resp.read().decode("utf-8")

        try:
            root1 = ET.fromstring(xml1)
        except ET.ParseError:
            return _FLEX_EMPTY(f"Could not parse step-1 response: {xml1[:300]}")

        status = root1.findtext("Status") or ""
        if status != "Success":
            msg = root1.findtext("ErrorMessage") or xml1[:300]
            return _FLEX_EMPTY(f"IB rejected the request: {msg}")

        ref_code = (root1.findtext("ReferenceCode") or "").strip()
        stmt_url  = (root1.findtext("Url") or "").strip()
        if not ref_code or not stmt_url:
            return _FLEX_EMPTY(f"No reference code in step-1 response: {xml1[:300]}")

        _debug_step1 = f"Step 1 OK — ref={ref_code!r}, url={stmt_url!r}"

        # Step 2 — poll with exponential back-off
        # IB docs omit the token from step 2, but many users report that 1020
        # ("Invalid request") on step 2 is resolved by including it anyway.
        waits = [10, 15, 20, 30, 45]  # seconds between attempts, up to ~2 min total
        last_error = "Report not ready after all retries."
        for wait in waits:
            time.sleep(wait)
            step2_url = f"{stmt_url}?q={ref_code}&v=3&t={token}"
            _debug_step2 = f"Step 2 URL: {stmt_url}?q={ref_code}&v=3&t=<token>"
            req2 = urllib.request.Request(step2_url, headers=_FLEX_HEADERS)
            with urllib.request.urlopen(req2, timeout=60) as resp:
                xml2 = resp.read().decode("utf-8")

            try:
                root2 = ET.fromstring(xml2)
            except ET.ParseError:
                last_error = f"Could not parse step-2 response: {xml2[:200]}"
                continue

            if root2.tag == "FlexQueryResponse":
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                try:
                    (_IMPORTS_DIR / f"flex_{ts}.xml").write_text(xml2, encoding="utf-8")
                except Exception:
                    pass
                return _parse_flex_xml(xml2)

            s2      = root2.findtext("Status") or ""
            err_msg = root2.findtext("ErrorMessage") or ""

            if s2 in ("Processing", "Warn") or "generation in progress" in err_msg.lower():
                # Report still generating — back off and retry
                last_error = f"Report not ready after all retries (last status: {s2})."
                continue

            if s2 == "Fail":
                err_code = root2.findtext("ErrorCode") or ""
                hint = ""
                if err_code == "1020":
                    hint = (
                        "\n\nError 1020 ('Invalid request') — token may be expired/invalid "
                        "or the query ID is wrong. In IB Account Management → Settings → "
                        "Flex Queries, regenerate your token and confirm the Query ID matches "
                        "what's saved in Settings here."
                    )
                last_error = (
                    f"{_debug_step1}\n{_debug_step2}\n\n"
                    f"Step 2 status: {s2}  ErrorCode: {err_code}  Message: {err_msg}"
                    f"{hint}\n\n"
                    f"Full step-2 response: {xml2[:400]}"
                )
                # 1020 is a hard auth failure — no point retrying
                if err_code == "1020":
                    break
                continue

            # Unexpected status — treat as transient and retry
            last_error = f"Unexpected status '{s2}': {err_msg or xml2[:200]}"
            continue

        return _FLEX_EMPTY(last_error)

    except Exception as exc:
        return _FLEX_EMPTY(str(exc))


def _yyyymmdd_to_iso(v: str) -> str:
    """Convert IB date strings to 'YYYY-MM-DD'.

    Handles: 'YYYYMMDD', 'YYYYMMDD;HHmmss', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS'.
    """
    s = str(v or "").strip()
    # Already ISO — YYYY-MM-DD (with optional time suffix)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # IB compact format YYYYMMDD (with optional ;HHmmss suffix)
    compact = s[:8]
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return s


def _parse_flex_xml(xml_text: str) -> dict:
    """Parse Flex Statement XML into account_summary + cash_transactions + trades."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"account_summary": {}, "cash_transactions": [], "trades": [], "error": f"XML parse error: {e}"}

    # ── Account summary: use the last <ChangeInNAV endingValue="..."> ──────────
    # The query returns one FlexStatement per day; the last one is most recent.
    acct: dict = {"net_liquidation": 0.0, "cash": 0.0,
                  "total_deposits": 0.0, "total_withdrawals": 0.0}
    for node in root.iter("ChangeInNAV"):
        try:
            acct["net_liquidation"] = float(node.get("endingValue", 0) or 0)
        except (ValueError, TypeError):
            pass

    # ── Cash transactions ──────────────────────────────────────────────────────
    txns: list[dict] = []
    for node in root.iter("CashTransaction"):
        txn_type = node.get("type", "")
        if not txn_type:
            continue
        # IB emits each transaction twice: once as SUMMARY (accountId="-") and once as
        # DETAIL (real account). Skip SUMMARY to avoid doubling contribution amounts.
        if node.get("levelOfDetail", "").upper() == "SUMMARY":
            continue
        try:
            amount = float(node.get("amount", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        # Accumulate deposit/withdrawal totals
        tl = txn_type.lower()
        if "deposit" in tl:
            acct["total_deposits"] += max(amount, 0)
        if "withdrawal" in tl:
            acct["total_withdrawals"] += abs(min(amount, 0))

        raw_date = node.get("reportDate") or node.get("dateTime", "")
        txns.append({
            "date":        _yyyymmdd_to_iso(raw_date),
            "type":        txn_type,
            "amount":      amount,
            "currency":    node.get("currency", "USD"),
            "description": node.get("description", ""),
        })

    txns.sort(key=lambda x: x["date"], reverse=True)

    # ── Daily NAV (ChangeInNAV per reporting date) ──────────────────────────────
    daily_nav = parse_flex_nav(root, txns)

    # ── Trades ─────────────────────────────────────────────────────────────────
    trades = parse_flex_trades(root)

    return {"account_summary": acct, "cash_transactions": txns, "trades": trades,
            "daily_nav": daily_nav, "error": None}


def parse_flex_nav(root: ET.Element, cash_txns: list[dict] | None = None) -> list[dict]:
    """
    Build a daily NAV list from a parsed Flex Statement root element.

    Each entry: {date (ISO), balance (float), contributions (float), withdrawals (float)}

    Balance comes from <ChangeInNAV endingValue="..."> — one element per reporting day.
    Contributions/withdrawals are aggregated from cash_txns (already parsed CashTransaction
    nodes) so we don't double-parse. Falls back to the <ChangeInNAV depositsWithdrawals>
    attribute when cash_txns is None.
    """
    # Build deposits/withdrawals per date from already-parsed cash transactions
    deps_by_date: dict[str, float] = {}
    wths_by_date: dict[str, float] = {}
    if cash_txns:
        for t in cash_txns:
            d   = t.get("date", "")
            amt = t.get("amount", 0.0) or 0.0
            tl  = (t.get("type") or "").lower()
            if "deposit" in tl and amt > 0:
                deps_by_date[d] = deps_by_date.get(d, 0.0) + amt
            elif "withdrawal" in tl and amt < 0:
                wths_by_date[d] = wths_by_date.get(d, 0.0) + abs(amt)

    nav_by_date: dict[str, dict] = {}

    def _add_nav_entry(iso_date: str, balance: float, node=None):
        if not iso_date or balance == 0:
            return
        contributions = deps_by_date.get(iso_date, 0.0)
        withdrawals   = wths_by_date.get(iso_date, 0.0)
        if contributions == 0.0 and withdrawals == 0.0 and node is not None:
            try:
                net_dw = float(node.get("depositsWithdrawals", 0) or 0)
                if net_dw > 0:
                    contributions = net_dw
                elif net_dw < 0:
                    withdrawals = abs(net_dw)
            except (ValueError, TypeError):
                pass
        nav_by_date[iso_date] = {
            "date":          iso_date,
            "balance":       balance,
            "contributions": contributions,
            "withdrawals":   withdrawals,
        }

    # Primary source: ChangeInNAV (requires that section enabled in Flex Query)
    for node in root.iter("ChangeInNAV"):
        raw_date = node.get("reportDate") or node.get("toDate") or node.get("date") or ""
        iso_date = _yyyymmdd_to_iso(raw_date)
        try:
            balance = float(node.get("endingValue", 0) or 0)
        except (ValueError, TypeError):
            continue
        _add_nav_entry(iso_date, balance, node)

    # Fallback 1: EquitySummaryByReportDateInBase (always present in most Flex reports)
    if not nav_by_date:
        for node in root.iter("EquitySummaryByReportDateInBase"):
            raw_date = node.get("reportDate") or node.get("date") or ""
            iso_date = _yyyymmdd_to_iso(raw_date)
            try:
                balance = float(node.get("total", 0) or 0)
            except (ValueError, TypeError):
                continue
            _add_nav_entry(iso_date, balance)

    # Fallback 2: NetAssetValue section
    if not nav_by_date:
        for node in root.iter("NetAssetValue"):
            raw_date = node.get("reportDate") or node.get("date") or ""
            iso_date = _yyyymmdd_to_iso(raw_date)
            try:
                balance = float(node.get("total", 0) or node.get("endingValue", 0) or 0)
            except (ValueError, TypeError):
                continue
            _add_nav_entry(iso_date, balance)

    return sorted(nav_by_date.values(), key=lambda x: x["date"])


def parse_flex_trades(root_or_xml) -> list[dict]:
    """
    Parse <Trade> elements from a Flex Statement (ET.Element or XML string).
    Uses openCloseIndicator ('O'/'C') to correctly identify entries and exits,
    including short positions (where BUY is the close, not the open).

    Returns a list of dicts compatible with add_trade() kwargs.
    """
    if isinstance(root_or_xml, str):
        try:
            root = ET.fromstring(root_or_xml)
        except ET.ParseError:
            return []
    else:
        root = root_or_xml

    from collections import defaultdict

    # Collect all fills with normalised fields
    fills: list[dict] = []
    for node in root.iter("Trade"):
        try:
            qty = float(node.get("quantity", 0) or 0)
            if qty == 0:
                continue
            price     = float(node.get("tradePrice", 0) or 0)
            commission = float(node.get("ibCommission", 0) or 0)
            fifo_pnl  = float(node.get("fifoPnlRealized", 0) or 0)
            put_call  = node.get("putCall", "") or ""
            asset_cat = (node.get("assetCategory") or "").upper()
            if asset_cat == "BAG":
                # Combo/spread aggregate row — individual legs are included separately
                continue
            if asset_cat == "FUT":
                _instrument_type = "future"
            elif asset_cat == "FOP" or put_call:
                _instrument_type = "option"
            else:
                _instrument_type = "stock"
            fills.append({
                "date":            _yyyymmdd_to_iso(node.get("tradeDate", "")),
                "datetime":        node.get("dateTime", ""),
                "ticker":          node.get("underlyingSymbol", "") or node.get("symbol", ""),
                "instrument_type": _instrument_type,
                "side":            "long" if (node.get("buySell", "") == "BUY") else "short",
                "quantity":        abs(qty),
                "price":           price,
                "expiration":      _yyyymmdd_to_iso(node.get("expiry", "")) if node.get("expiry") else None,
                "strike":          float(node.get("strike") or 0) or None,
                "option_type":     "call" if put_call == "C" else "put" if put_call == "P" else None,
                "multiplier":      float(node.get("multiplier", 1) or 1),
                "open_close":      node.get("openCloseIndicator", "O"),  # 'O' or 'C'
                "commission":      commission,
                "fifo_pnl":        fifo_pnl,
                "trade_id":        node.get("tradeID", ""),
                "txn_type":        node.get("transactionType", ""),
            })
        except Exception:
            pass

    # Group by instrument key
    buckets: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(fills, key=lambda x: x["datetime"]):
        key = "_".join([
            f["ticker"],
            str(f.get("expiration") or ""),
            str(f.get("strike") or ""),
            str(f.get("option_type") or ""),
        ])
        buckets[key].append(f)

    def _split_cycles(fills: list[dict]) -> list[list[dict]]:
        """Split an ordered fill list into trade cycles.

        A cycle ends when the running net quantity returns to zero (position
        fully closed).  Each cycle becomes one trade record, so re-entries in
        the same ticker across different dates are not blended together.
        """
        cycles: list[list[dict]] = []
        current: list[dict] = []
        net = 0.0
        for f in fills:  # already sorted by datetime
            current.append(f)
            if f["open_close"] == "O":
                net += f["quantity"]
            else:
                net -= f["quantity"]
            if abs(net) < 0.001:  # position fully closed → end of cycle
                cycles.append(current)
                current, net = [], 0.0
        if current:
            cycles.append(current)
        return cycles

    trades: list[dict] = []
    for key, all_bucket_fills in buckets.items():
      for bucket_fills in _split_cycles(all_bucket_fills):
        open_fills  = [f for f in bucket_fills if f["open_close"] == "O"]
        # "C;O" = IB roll fill (closes existing lot, opens new one same session) — treat as close
        close_fills = [f for f in bucket_fills if f["open_close"] in ("C", "C;O")]

        if not open_fills:
            if not close_fills:
                continue
            _itype_co = close_fills[0]["instrument_type"]
            if _itype_co == "option":
                # Options combo legs: IB sometimes tags new-position fills as "C".
                # Treat as opening fills (legacy behaviour).
                open_fills  = close_fills
                close_fills = []
            else:
                # Stock/future: the open fill is outside the Flex date range.
                # Return a close_only record — the importer will find and update
                # the matching open trade in the log without needing entry details.
                _co_qty   = sum(f["quantity"] for f in close_fills)
                _co_price = (sum(f["quantity"] * f["price"] for f in close_fills) / _co_qty
                             if _co_qty else 0)
                _co_comm  = sum(f["commission"] for f in close_fills)
                _co_pnl   = sum(f["fifo_pnl"] for f in close_fills)
                _co_notes = ["Imported via Flex Query (close fill — open outside date range)"]
                if _co_comm:
                    _co_notes.append(f"Commission: ${_co_comm:.4f}")
                if _co_pnl:
                    _co_notes.append(f"FIFO P&L: ${_co_pnl:.2f}")
                trades.append({
                    "entry_date":      None,
                    "ticker":          close_fills[0]["ticker"],
                    "quantity":        _co_qty,
                    "entry_price":     None,
                    "exit_date":       _to_date(close_fills[-1]["date"]),
                    "exit_price":      round(_co_price, 6) if _co_price else None,
                    "notes":           " | ".join(_co_notes),
                    "stop_enabled":    False,
                    "opening_stop":    None,
                    "current_stop":    None,
                    "tag_ids":         [],
                    "instrument_type": _itype_co,
                    "expiration":      close_fills[0]["expiration"],
                    "strike":          close_fills[0]["strike"],
                    "option_type":     close_fills[0]["option_type"],
                    "multiplier":      close_fills[0]["multiplier"],
                    "side":            close_fills[0]["side"],
                    "leg_group":       None,
                    "leg_label":       None,
                    "close_only":      True,
                })
                continue

        # Aggregate open fills → one entry (weighted-average price, sum qty)
        total_open_qty   = sum(f["quantity"] for f in open_fills)
        avg_open_price   = (sum(f["quantity"] * f["price"] for f in open_fills) / total_open_qty
                            if total_open_qty else 0)
        open_commission  = sum(f["commission"] for f in open_fills)
        open_side        = open_fills[0]["side"]  # long or short
        entry_date       = open_fills[0]["date"]
        first_fill       = open_fills[0]

        # Aggregate close fills → one exit (if any)
        exit_date  = None
        exit_price = None
        if close_fills:
            total_close_qty  = sum(f["quantity"] for f in close_fills)
            avg_close_price  = (sum(f["quantity"] * f["price"] for f in close_fills) / total_close_qty
                                if total_close_qty else 0)
            close_commission = sum(f["commission"] for f in close_fills)
            exit_date        = close_fills[-1]["date"]
            exit_price       = avg_close_price
        else:
            close_commission = 0.0

        total_commission = open_commission + close_commission
        notes_parts = [f"Imported via Flex Query"]
        if total_commission:
            notes_parts.append(f"Commission: ${total_commission:.4f}")
        if close_fills:
            fifo = sum(f["fifo_pnl"] for f in close_fills)
            if fifo:
                notes_parts.append(f"FIFO P&L: ${fifo:.2f}")

        trades.append({
            "entry_date":      _to_date(entry_date),
            "ticker":          first_fill["ticker"],
            "quantity":        total_open_qty,
            "entry_price":     round(avg_open_price, 6),
            "exit_date":       _to_date(exit_date),
            "exit_price":      round(exit_price, 6) if exit_price is not None else None,
            "notes":           " | ".join(notes_parts),
            "stop_enabled":    False,
            "opening_stop":    None,
            "current_stop":    None,
            "tag_ids":         [],
            "instrument_type": first_fill["instrument_type"],
            "expiration":      first_fill["expiration"],
            "strike":          first_fill["strike"],
            "option_type":     first_fill["option_type"],
            "multiplier":      first_fill["multiplier"],
            "side":            open_side,
            "leg_group":       None,
            "leg_label":       None,
        })

    # Auto-group option legs that share the same underlying + entry_date + expiration
    # (these are almost certainly legs of the same spread entered on the same day)
    from collections import defaultdict as _dd
    import uuid as _uuid2
    spread_buckets: dict[tuple, list[int]] = _dd(list)
    for i, t in enumerate(trades):
        if t["instrument_type"] == "option" and t.get("expiration"):
            key = (t["ticker"], str(t.get("entry_date") or ""), str(t["expiration"]))
            spread_buckets[key].append(i)

    for key, indices in spread_buckets.items():
        if len(indices) < 2:
            continue
        grp = str(_uuid2.uuid4())[:8]
        for i in indices:
            t = trades[i]
            side_str  = "Long" if t["side"] == "long" else "Short"
            opt_str   = "Call" if str(t.get("option_type") or "").lower().startswith("c") else "Put"
            strike    = t.get("strike") or 0
            t["leg_group"] = grp
            t["leg_label"] = f"{side_str} {opt_str} ${strike:.2f}"

    return trades


# ── Helpers ────────────────────────────────────────────────────────────────────

def _contract_type(con) -> str:
    t = getattr(con, "secType", "STK")
    return {"STK": "stock", "OPT": "option", "FUT": "future", "FOP": "option"}.get(t, "stock")


def _is_bag_contract(con) -> bool:
    return getattr(con, "secType", "") == "BAG"


def test_connection(host: str, port: int, client_id: int = 1) -> tuple[bool, str]:
    """Return (success, message). Safe to call from Streamlit."""
    if not _IB_AVAILABLE:
        return False, "ib_insync is not installed. Run: pip install ib_insync nest_asyncio"
    try:
        with IBClient(host, port, client_id):
            return True, "Connected to IB Gateway / TWS successfully."
    except Exception as e:
        return False, f"Connection failed: {e}"


def _to_date(v):
    """Convert IB date string to datetime.date, or return None."""
    if v is None:
        return None
    try:
        import pandas as pd
        return pd.to_datetime(str(v)[:10]).date()
    except Exception:
        return None


def parse_ib_executions_to_trades(executions: list[dict]) -> list[dict]:
    """
    Match BOT/SLD pairs from IB executions into open/close trade records.
    Groups by ticker + expiration + strike + option_type.
    Returns list of dicts compatible with add_trade() kwargs.
    """
    from collections import defaultdict
    import uuid as _uuid

    # Group by instrument identity
    buckets: dict[str, list[dict]] = defaultdict(list)
    for ex in sorted(executions, key=lambda x: x["time"]):
        key = "_".join([
            ex["ticker"],
            str(ex.get("expiration") or ""),
            str(ex.get("strike") or ""),
            str(ex.get("option_type") or ""),
        ])
        buckets[key].append(ex)

    trades: list[dict] = []
    for key, fills in buckets.items():
        open_fills: list[dict]  = []
        close_fills: list[dict] = []
        for f in fills:
            if f["side"] == "long":
                open_fills.append(f)
            else:
                close_fills.append(f)

        # Pair opens (BOT) with closes (SLD used as exit for a long)
        used_closes: set[int] = set()
        for i, op in enumerate(open_fills):
            matched_close: dict | None = None
            for j, cl in enumerate(close_fills):
                if j not in used_closes and cl["date"] >= op["date"] and abs(cl["quantity"] - op["quantity"]) < 0.001:
                    matched_close = cl
                    used_closes.add(j)
                    break
            leg_group = str(op.get("leg_group") or _uuid.uuid4())
            trade = {
                "entry_date":      _to_date(op["date"]),
                "ticker":          op["ticker"],
                "quantity":        op["quantity"],
                "entry_price":     op["price"],
                "exit_date":       _to_date(matched_close["date"])  if matched_close else None,
                "exit_price":      matched_close["price"] if matched_close else None,
                "notes":           f"Imported from IB (execId: {op.get('exec_id', '')})",
                "stop_enabled":    False,
                "opening_stop":    None,
                "tag_ids":         [],
                "current_stop":    None,
                "instrument_type": op["instrument_type"],
                "expiration":      op.get("expiration"),
                "strike":          op.get("strike"),
                "option_type":     op.get("option_type"),
                "multiplier":      op.get("multiplier", 1.0),
                "leg_group":       leg_group,
                "leg_label":       f"Leg {i + 1}",
                "side":            op["side"],
            }
            trades.append(trade)

        # Any SLD fills not consumed as exits are new short-open positions
        for j, cl in enumerate(close_fills):
            if j in used_closes:
                continue
            leg_group = str(cl.get("leg_group") or _uuid.uuid4())
            trades.append({
                "entry_date":      _to_date(cl["date"]),
                "ticker":          cl["ticker"],
                "quantity":        cl["quantity"],
                "entry_price":     cl["price"],
                "exit_date":       None,
                "exit_price":      None,
                "notes":           f"Imported from IB (execId: {cl.get('exec_id', '')})",
                "stop_enabled":    False,
                "opening_stop":    None,
                "tag_ids":         [],
                "current_stop":    None,
                "instrument_type": cl["instrument_type"],
                "expiration":      cl.get("expiration"),
                "strike":          cl.get("strike"),
                "option_type":     cl.get("option_type"),
                "multiplier":      cl.get("multiplier", 1.0),
                "leg_group":       leg_group,
                "leg_label":       f"Leg {len(open_fills) + j + 1}",
                "side":            "short",
            })

    return trades
