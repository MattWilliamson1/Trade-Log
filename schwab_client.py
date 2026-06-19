"""
Charles Schwab Trader API client.

Hand-rolled OAuth2 (authorization-code) + REST using ``requests`` so we avoid a
heavy dependency and can fit Streamlit's "paste the redirect URL back" auth flow
(schwab-py's helpers block on ``input()`` or stand up a local web server, neither
of which works inside a Streamlit rerun loop).

Shape mirrors ``ib_client``: short-lived calls, graceful fallback when not
configured, and parse helpers that return ``add_trade()``-compatible dicts. Trade
aggregation is delegated to ``ib_client.fills_to_trades`` so Flex and Schwab share
one battle-tested grouping routine.

App Key / Secret / callback URL live in the app's settings (DB) and are passed in
to each call. Only the OAuth tokens are persisted here, in ``schwab_token.json``
next to the source files (git-ignored).
"""

from __future__ import annotations

import base64
import datetime
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

_SRC_DIR     = Path(__file__).parent
_IMPORTS_DIR = _SRC_DIR / "imports"
_IMPORTS_DIR.mkdir(exist_ok=True)
_TOKEN_PATH  = _SRC_DIR / "schwab_token.json"

_REQUESTS_AVAILABLE = False
try:
    import requests  # type: ignore
    _REQUESTS_AVAILABLE = True
except ImportError:
    pass

import ib_client as _ib  # reuse fills_to_trades / _to_date

# ── Endpoints ──────────────────────────────────────────────────────────────────
_AUTH_URL  = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
_API_BASE  = "https://api.schwabapi.com"

# Schwab access tokens live 30 min; refresh tokens 7 days.
_REFRESH_TOKEN_TTL = 7 * 24 * 3600


def is_available() -> bool:
    """True if the HTTP stack needed to talk to Schwab is importable."""
    return _REQUESTS_AVAILABLE


# ── Token storage ────────────────────────────────────────────────────────────--

def load_token() -> dict | None:
    if not _TOKEN_PATH.exists():
        return None
    try:
        return json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_token(tok: dict) -> None:
    try:
        _TOKEN_PATH.write_text(json.dumps(tok, indent=2), encoding="utf-8")
    except Exception:
        pass


def clear_token() -> None:
    try:
        _TOKEN_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def has_token() -> bool:
    return load_token() is not None


def token_status() -> dict:
    """Summarise the stored token for the UI without exposing secrets.

    Returns {connected, access_valid, refresh_valid, expires_in, refresh_days_left}.
    """
    tok = load_token()
    if not tok:
        return {"connected": False, "access_valid": False, "refresh_valid": False,
                "expires_in": 0, "refresh_days_left": 0}
    now = time.time()
    exp = float(tok.get("expires_at", 0) or 0)
    rexp = float(tok.get("refresh_expires_at", 0) or 0)
    return {
        "connected":         True,
        "access_valid":      now < exp,
        "refresh_valid":     now < rexp,
        "expires_in":        max(0, int(exp - now)),
        "refresh_days_left": max(0, round((rexp - now) / 86400, 1)),
    }


# ── OAuth ───────────────────────────────────────────────────────────────────--

def build_auth_url(app_key: str, callback: str) -> str:
    """The URL the user opens to log in to Schwab and authorise this app."""
    params = {
        "response_type": "code",
        "client_id":     app_key,
        "redirect_uri":  callback,
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _basic_auth_header(app_key: str, secret: str) -> str:
    raw = f"{app_key}:{secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("utf-8")


def extract_code(redirected_url: str) -> str | None:
    """Pull the ``code`` query parameter out of the URL Schwab redirected to.

    Accepts either the full ``https://127.0.0.1:8182/?code=...&session=...`` URL
    or a bare code pasted by the user.
    """
    s = (redirected_url or "").strip()
    if not s:
        return None
    if "code=" not in s:
        # User may have pasted just the code itself.
        return s if " " not in s else None
    try:
        qs = urllib.parse.urlparse(s).query
        code = urllib.parse.parse_qs(qs).get("code", [None])[0]
        return code
    except Exception:
        return None


def exchange_code(app_key: str, secret: str, callback: str,
                  redirected_url: str) -> tuple[bool, str]:
    """Exchange the authorization code for tokens and persist them."""
    if not _REQUESTS_AVAILABLE:
        return False, "The 'requests' library is not installed."
    code = extract_code(redirected_url)
    if not code:
        return False, ("Could not find an authorization code in what you pasted. "
                       "Paste the full URL from your browser's address bar after "
                       "logging in (it should contain 'code=').")
    try:
        resp = requests.post(
            _TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(app_key, secret),
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            data={
                "grant_type":   "authorization_code",
                "code":         code,
                "redirect_uri": callback,
            },
            timeout=30,
        )
    except Exception as e:
        return False, f"Network error contacting Schwab: {e}"

    if resp.status_code != 200:
        return False, _token_error(resp)

    try:
        data = resp.json()
    except Exception:
        return False, f"Unexpected token response: {resp.text[:300]}"

    now = time.time()
    save_token({
        "access_token":       data.get("access_token"),
        "refresh_token":      data.get("refresh_token"),
        "token_type":         data.get("token_type", "Bearer"),
        "scope":              data.get("scope", ""),
        "expires_at":         now + float(data.get("expires_in", 1800)) - 30,
        "refresh_expires_at": now + _REFRESH_TOKEN_TTL,
    })
    return True, "Connected to Schwab successfully."


def _refresh(app_key: str, secret: str) -> tuple[bool, str]:
    tok = load_token()
    if not tok or not tok.get("refresh_token"):
        return False, "No refresh token stored — please authorise again."
    if time.time() >= float(tok.get("refresh_expires_at", 0) or 0):
        return False, "Your Schwab authorisation has expired (7-day limit). Please re-authorise."
    try:
        resp = requests.post(
            _TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(app_key, secret),
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            data={
                "grant_type":    "refresh_token",
                "refresh_token": tok["refresh_token"],
            },
            timeout=30,
        )
    except Exception as e:
        return False, f"Network error refreshing token: {e}"

    if resp.status_code != 200:
        return False, _token_error(resp)
    try:
        data = resp.json()
    except Exception:
        return False, f"Unexpected refresh response: {resp.text[:300]}"

    now = time.time()
    tok["access_token"] = data.get("access_token")
    if data.get("refresh_token"):
        tok["refresh_token"] = data["refresh_token"]
    tok["expires_at"] = now + float(data.get("expires_in", 1800)) - 30
    save_token(tok)
    return True, "Token refreshed."


def _token_error(resp) -> str:
    try:
        j = resp.json()
        msg = j.get("error_description") or j.get("error") or resp.text[:300]
    except Exception:
        msg = resp.text[:300]
    hint = ""
    if resp.status_code in (400, 401):
        hint = ("\n\nCheck that your App Key and Secret are correct and that the "
                "callback URL matches exactly what you registered at "
                "developer.schwab.com (https://127.0.0.1:8182).")
    return f"Schwab returned {resp.status_code}: {msg}{hint}"


def get_access_token(app_key: str, secret: str) -> tuple[str | None, str]:
    """Return (access_token, error). Refreshes transparently if expired."""
    tok = load_token()
    if not tok:
        return None, "Not connected to Schwab yet — authorise in Broker Sync."
    if time.time() < float(tok.get("expires_at", 0) or 0) and tok.get("access_token"):
        return tok["access_token"], ""
    ok, msg = _refresh(app_key, secret)
    if not ok:
        return None, msg
    return load_token().get("access_token"), ""


# ── REST helpers ────────────────────────────────────────────────────────────--

def _api_get(path: str, app_key: str, secret: str,
             params: dict | None = None) -> tuple[Any, str]:
    """GET an API path with a valid bearer token. Returns (json, error)."""
    if not _REQUESTS_AVAILABLE:
        return None, "The 'requests' library is not installed."
    token, err = get_access_token(app_key, secret)
    if not token:
        return None, err
    try:
        resp = requests.get(
            f"{_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params or {},
            timeout=30,
        )
    except Exception as e:
        return None, f"Network error: {e}"
    if resp.status_code == 401:
        return None, "Schwab rejected the token (401). Try re-authorising in Broker Sync."
    if resp.status_code == 403:
        return None, ("Schwab returned 403 (forbidden) — this API product may not be "
                      "enabled for your app, or the account isn't authorised.")
    if resp.status_code != 200:
        try:
            j = resp.json()
            detail = j.get("message") or j.get("error") or resp.text[:300]
        except Exception:
            detail = resp.text[:300]
        return None, f"Schwab returned {resp.status_code}: {detail}"
    try:
        return resp.json(), ""
    except Exception:
        return None, f"Could not parse Schwab response: {resp.text[:300]}"


def get_account_hashes(app_key: str, secret: str) -> tuple[list[dict], str]:
    """Return ([{accountNumber, hashValue}], error)."""
    data, err = _api_get("/trader/v1/accounts/accountNumbers", app_key, secret)
    if err:
        return [], err
    if not isinstance(data, list):
        return [], "Unexpected account list response."
    return data, ""


def resolve_account_hash(app_key: str, secret: str,
                         preferred_number: str = "") -> tuple[str, str, str]:
    """Pick an account hash.

    Returns (hash, account_number, error). Uses preferred_number if it matches
    one of the user's accounts, otherwise the first account.
    """
    hashes, err = get_account_hashes(app_key, secret)
    if err:
        return "", "", err
    if not hashes:
        return "", "", "No accounts returned for this Schwab login."
    if preferred_number:
        for h in hashes:
            if h.get("accountNumber") == preferred_number:
                return h.get("hashValue", ""), preferred_number, ""
    first = hashes[0]
    return first.get("hashValue", ""), first.get("accountNumber", ""), ""


def get_account_summary(app_key: str, secret: str,
                        account_hash: str) -> tuple[dict, str]:
    """Return ({net_liquidation, cash}, error) for one account."""
    data, err = _api_get(f"/trader/v1/accounts/{account_hash}", app_key, secret)
    if err:
        return {}, err
    try:
        sa = data.get("securitiesAccount", {}) if isinstance(data, dict) else {}
        cb = sa.get("currentBalances", {}) or {}
        net_liq = cb.get("liquidationValue")
        cash = cb.get("cashBalance")
        if cash is None:
            cash = cb.get("totalCash")
        return {
            "net_liquidation": float(net_liq) if net_liq is not None else 0.0,
            "cash":            float(cash) if cash is not None else 0.0,
        }, ""
    except Exception as e:
        return {}, f"Could not read account balances: {e}"


def _iso_z(d, end_of_day: bool = False) -> str:
    """Format a date/ISO string as Schwab's required yyyy-MM-dd'T'HH:mm:ss.SSSZ."""
    s = str(d)[:10]
    suffix = "T23:59:59.000Z" if end_of_day else "T00:00:00.000Z"
    return f"{s}{suffix}"


def get_transactions(app_key: str, secret: str, account_hash: str,
                     start_date, end_date) -> tuple[list, str]:
    """Return (raw_transactions, error) for an account over a date range.

    Schwab caps the range at one year and returns up to ~3000 transactions.
    """
    params = {
        "startDate": _iso_z(start_date),
        "endDate":   _iso_z(end_date, end_of_day=True),
        "types":     "TRADE",
    }
    data, err = _api_get(
        f"/trader/v1/accounts/{account_hash}/transactions", app_key, secret, params
    )
    if err:
        return [], err
    if not isinstance(data, list):
        return [], "Unexpected transactions response."
    return data, ""


# ── Quotes (requires the Market Data API product) ──────────────────────────────

def get_quotes(app_key: str, secret: str, symbols: list[str]) -> dict[str, dict]:
    """Return {symbol: {"price": float, "prev_close": float}} for equities.

    Options are skipped (Schwab's option symbol format differs from the OCC
    compact symbols the log stores). Errors fall back to an empty dict.
    """
    result: dict[str, dict] = {}
    eq_syms = [s for s in symbols if s and "_" not in s and len(s) <= 6 and s.isalpha()]
    if not eq_syms:
        return result
    data, err = _api_get(
        "/marketdata/v1/quotes", app_key, secret,
        {"symbols": ",".join(eq_syms), "indicative": "false"},
    )
    if err or not isinstance(data, dict):
        return result
    for sym, payload in data.items():
        try:
            q = payload.get("quote", {}) if isinstance(payload, dict) else {}
            last = q.get("lastPrice")
            close = q.get("closePrice")
            if last is None and q.get("bidPrice") and q.get("askPrice"):
                last = (float(q["bidPrice"]) + float(q["askPrice"])) / 2
            result[sym] = {
                "price":      float(last) if last is not None else None,
                "prev_close": float(close) if close is not None else None,
            }
        except Exception:
            pass
    return result


# ── Transaction → trade parsing ─────────────────────────────────────────────--

_SECURITY_ASSET_TYPES = {
    "EQUITY":                "stock",
    "COLLECTIVE_INVESTMENT": "stock",
    "ETF":                   "stock",
    "MUTUAL_FUND":           "stock",
    "INDEX":                 "stock",
    "OPTION":                "option",
    "FUTURE":                "future",
}


def _txn_to_fills(txn: dict) -> list[dict]:
    """Turn one Schwab TRADE transaction into normalised fill dicts.

    A single transaction can carry several security legs (a spread filled as one
    order) plus fee legs. Fee legs are summed and attached to the first security
    leg so totals aren't double-counted across buckets.
    """
    items = txn.get("transferItems", []) or []
    when  = txn.get("tradeDate") or txn.get("time") or ""
    date  = str(when)[:10]
    txn_id = str(txn.get("activityId") or txn.get("orderId") or "")

    fees = 0.0
    sec_items: list[dict] = []
    for it in items:
        if it.get("feeType"):
            try:
                fees += abs(float(it.get("cost", 0) or 0))
            except (TypeError, ValueError):
                pass
            continue
        inst = it.get("instrument", {}) or {}
        itype = _SECURITY_ASSET_TYPES.get((inst.get("assetType") or "").upper())
        if not itype:
            continue
        if it.get("price") is None:
            continue
        sec_items.append((it, inst, itype))

    fills: list[dict] = []
    for idx, (it, inst, itype) in enumerate(sec_items):
        try:
            amount = float(it.get("amount", 0) or 0)
            if amount == 0:
                continue
            price  = float(it.get("price", 0) or 0)
            side   = "long" if amount > 0 else "short"   # bought vs sold
            pos    = (it.get("positionEffect") or "").upper()
            if pos == "OPENING":
                open_close = "O"
            elif pos == "CLOSING":
                open_close = "C"
            else:
                # AUTOMATIC / unknown: a buy adds (open long / close short), a sell
                # removes. Default a buy to open and a sell to close — fills_to_trades
                # will still pair them within a bucket cycle.
                open_close = "O" if amount > 0 else "C"

            is_opt = itype == "option"
            exp = inst.get("expirationDate") or inst.get("maturityDate") or None
            pc  = (inst.get("putCall") or "").upper()
            ticker = (inst.get("underlyingSymbol")
                      or inst.get("symbol") or "").strip().upper()
            try:
                mult = float(inst.get("multiplier")) if inst.get("multiplier") else (100.0 if is_opt else 1.0)
            except (TypeError, ValueError):
                mult = 100.0 if is_opt else 1.0

            fills.append({
                "date":            date,
                "datetime":        str(when),
                "ticker":          ticker,
                "exchange":        "",
                "instrument_type": itype,
                "side":            side,
                "quantity":        abs(amount),
                "price":           price,
                "expiration":      str(exp)[:10] if exp else None,
                "strike":          float(inst.get("strikePrice")) if inst.get("strikePrice") else None,
                "option_type":     "call" if pc == "CALL" else "put" if pc == "PUT" else None,
                "multiplier":      mult,
                "open_close":      open_close,
                "commission":      fees if idx == 0 else 0.0,
                "fifo_pnl":        0.0,
                "trade_id":        txn_id,
                "txn_type":        txn.get("type", "TRADE"),
            })
        except Exception:
            pass
    return fills


def parse_schwab_transactions_to_trades(transactions: list[dict]) -> list[dict]:
    """Aggregate Schwab TRADE transactions into add_trade()-compatible dicts."""
    fills: list[dict] = []
    for txn in transactions:
        if (txn.get("type") or "").upper() != "TRADE":
            continue
        fills.extend(_txn_to_fills(txn))
    return _ib.fills_to_trades(fills, "Schwab API")


# ── Orchestrator (mirrors ib_client.fetch_flex_report's return shape) ──────────

_EMPTY = lambda err=None: {
    "account_summary": {"net_liquidation": 0.0, "cash": 0.0,
                        "total_deposits": 0.0, "total_withdrawals": 0.0},
    "cash_transactions": [], "trades": [], "daily_nav": [], "error": err,
}


def fetch_schwab_report(app_key: str, secret: str, account_hash: str,
                        start_date, end_date) -> dict:
    """Fetch balances + trades for an account and return the unified report dict.

    Same shape as ``ib_client.fetch_flex_report`` so the Broker Sync UI can render
    Schwab and IB results through the same code paths.
    """
    if not app_key or not secret:
        return _EMPTY("Enter your Schwab App Key and Secret first.")
    if not account_hash:
        return _EMPTY("No Schwab account selected.")

    summary, err = get_account_summary(app_key, secret, account_hash)
    if err:
        return _EMPTY(err)

    txns, err = get_transactions(app_key, secret, account_hash, start_date, end_date)
    if err:
        return _EMPTY(err)

    # Persist the raw pull for troubleshooting (best effort).
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        (_IMPORTS_DIR / f"schwab_{ts}.json").write_text(
            json.dumps(txns, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    trades = parse_schwab_transactions_to_trades(txns)

    account_summary = {
        "net_liquidation":   summary.get("net_liquidation", 0.0),
        "cash":              summary.get("cash", 0.0),
        "total_deposits":    0.0,
        "total_withdrawals": 0.0,
    }
    return {
        "account_summary":   account_summary,
        "cash_transactions": [],
        "trades":            trades,
        "daily_nav":         [],
        "error":             None,
    }


def test_connection(app_key: str, secret: str) -> tuple[bool, str]:
    """Verify the stored token works by listing accounts. Safe for Streamlit."""
    if not _REQUESTS_AVAILABLE:
        return False, "The 'requests' library is not installed."
    if not app_key or not secret:
        return False, "Enter your App Key and Secret first."
    if not has_token():
        return False, "Not authorised yet — complete the Authorize step below."
    hashes, err = get_account_hashes(app_key, secret)
    if err:
        return False, err
    n = len(hashes)
    return True, f"Connected to Schwab — {n} account{'s' if n != 1 else ''} accessible."
