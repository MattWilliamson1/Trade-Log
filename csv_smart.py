"""Smart CSV import (BETA) — read a trade export the app has never seen before.

`import_trades_from_csv` in app.py matches headers against a fixed table, so a
file saying "Trade Date" and "Shares" instead of "Entry Date" and "Q" imports
nothing at all. This module makes a best effort on an arbitrary export:

    read_table()        decode, sniff the delimiter, find the real header row
    propose_mapping()   score every (column, field) pair, assign greedily
    detect_shape()      one row per trade, or one row per fill?
    build_trades()      trade dicts ready for app.import_parsed_trades()

Two ideas do most of the work. Headers are matched *fuzzily* against an alias
table, and — the part that rescues a header nobody has ever seen — every column
is also profiled by its **values**: a column that is 95% parseable dates is a
date column whatever it calls itself, and a column of BUY/SELL is a side column
even when its header says "Type".

Everything here returns a *proposal*. Nothing is certain enough to import on
silently, so the caller is expected to show the mapping and let the user correct
it first. Deliberately free of Streamlit and database imports: the mapping can
be exercised straight against sample files.
"""

import io
import re
import csv
import hashlib
from dataclasses import dataclass, field as _dc_field
from difflib import SequenceMatcher

import pandas as pd


# ── Text helpers ─────────────────────────────────────────────────────────────

def normalize_header(h) -> str:
    """Header text → comparable form: lowercase, no units, no punctuation.

    "Entry Price (USD)" and "entry_price" both land on "entry price", which is
    what the alias table is written in.
    """
    s = str(h or "").strip().lower()
    s = re.sub(r"\([^)]*\)", " ", s)          # trailing units: "(USD)", "(local)"
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_CURRENCY_JUNK = "$€£¥₹₽  '"


def _normalize_decimal(s: str) -> str:
    """Resolve which of "." and "," is the decimal point, and drop the other.

    "1.234,50" and "1,234.50" are the same number written by different halves of
    the world, and a Dutch or German export full of "7500,00" would otherwise
    import as 750000. The last separator in the string is the decimal one; a lone
    comma trailed by one or two digits is decimal, because no thousands group is
    shorter than three.
    """
    last_c, last_d = s.rfind(","), s.rfind(".")
    if last_c >= 0 and last_d >= 0:
        if last_c > last_d:
            return s.replace(".", "").replace(",", ".")
        return s.replace(",", "")
    if last_c >= 0:
        tail = len(s) - last_c - 1
        if s.count(",") == 1 and 1 <= tail <= 2:
            return s.replace(",", ".")
        return s.replace(",", "")
    return s



def clean_number(v):
    """Parse a spreadsheet money/quantity cell, or None.

    Handles thousands separators, currency prefixes, trailing %, and accounting
    negatives — "(1,234.50)" is -1234.50. Deliberately strict about what it will
    *not* take: "12/31/2024" and "2024-01-05" must fail here, or every date
    column in the file profiles as a number and outscores the real price column.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "-", "--", "n/a", "na"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    s = s.replace("−", "-").rstrip("%").strip()
    for ch in _CURRENCY_JUNK:
        s = s.replace(ch, "")
    # Currency code either side: "USD1234.50", "1234.50USD"
    s = re.sub(r"(?i)^[a-z]{3}(?=[-+.,\d])", "", s)
    s = re.sub(r"(?i)[a-z]{3}$", "", s).strip()
    s = _normalize_decimal(s)
    if not re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s):
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


_DATEISH = re.compile(r"""
    ^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}          # 2024-01-05
  | ^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}        # 05/01/2024
  | ^\d{8}$                                 # 20240105
""", re.VERBOSE)

# Spelled-out dates ("5 Jan 2024"). A month name only counts alongside a digit, or
# every ticker from MAR to DEC would read as a date.
_MONTH_RE = re.compile(r"(?i)(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*")


def _looks_dateish(s: str) -> bool:
    """Cheap gate before handing a value to pandas.

    `pd.to_datetime` is happy to read a bare "150" as a date, which would let a
    price column profile as dates. Require something date-shaped first.
    """
    s = str(s).strip()
    if not s:
        return False
    if s.isdigit():
        return len(s) == 8 and s[:2] in ("19", "20")
    if _DATEISH.search(s):
        return True
    return bool(_MONTH_RE.search(s)) and bool(re.search(r"\d", s))


def parse_date(v, dayfirst: bool = False):
    """One cell → `datetime.date`, or None.

    `dayfirst` comes from the app's euro-dates setting: 03/04/2025 is genuinely
    ambiguous and the user's own preference is the best evidence available.
    Unambiguous formats (ISO, or a day above 12) parse the same either way.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s or not _looks_dateish(s):
        return None
    # Trim a time component so "2024-01-05 09:30:00" and "01/05/2024 9:30" both work
    s = re.split(r"[T ]", s, maxsplit=1)[0] if len(s) > 10 else s
    try:
        ts = pd.to_datetime(s, dayfirst=dayfirst, errors="coerce")
    except Exception:
        return None
    if ts is None or pd.isna(ts):
        return None
    d = ts.date()
    # IB writes 0 for an absent date, which lands on 1970-01-01
    return d if 1980 <= d.year <= 2100 else None


# ── Value profilers ──────────────────────────────────────────────────────────
# Each takes a sample of non-empty cell values and returns the fraction that fit.

def _frac(values, pred) -> float:
    vals = [v for v in values if str(v).strip() not in ("", "nan", "None")]
    if not vals:
        return 0.0
    return sum(1 for v in vals if pred(v)) / len(vals)


def _p_date(values) -> float:
    return _frac(values, lambda v: parse_date(v) is not None)


def _p_number(values) -> float:
    return _frac(values, lambda v: clean_number(v) is not None)


def _p_positive(values) -> float:
    """Numeric and non-negative — prices and quantities, not P&L columns."""
    def ok(v):
        n = clean_number(v)
        return n is not None and n >= 0
    return _frac(values, ok)


_TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-/ ]{0,24}$")


def _p_ticker(values) -> float:
    def ok(v):
        s = str(v).strip()
        if len(s) > 15 or s.count(" ") > 1:      # a sentence is not a symbol
            return False
        return bool(_TICKER_RE.fullmatch(s)) and clean_number(s) is None and not _looks_dateish(s)
    return _frac(values, ok)


_SIDE_WORDS = {
    "buy", "sell", "b", "s", "bot", "sld", "bought", "sold", "long", "short",
    "buy to open", "buy to close", "sell to open", "sell to close",
    "bto", "btc", "sto", "stc", "purchase", "sale", "sell short", "buy cover",
}


def _p_side(values) -> float:
    return _frac(values, lambda v: normalize_header(v) in _SIDE_WORDS)


_OPTION_TYPE_WORDS = {"c", "p", "call", "put", "calls", "puts"}


def _p_option_type(values) -> float:
    return _frac(values, lambda v: normalize_header(v) in _OPTION_TYPE_WORDS)


_INSTRUMENT_WORDS = (
    "stock", "stk", "equity", "eq", "option", "opt", "future", "fut", "cash",
    "forex", "fx", "bond", "etf", "fund", "crypto", "index", "ind", "bag", "combo",
)


def _p_instrument(values) -> float:
    def ok(v):
        n = normalize_header(v)
        return bool(n) and any(w in n.split() or w == n for w in _INSTRUMENT_WORDS)
    return _frac(values, ok)


_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "AUD", "CAD", "NZD", "JPY", "CHF", "HKD", "SGD", "SEK",
    "NOK", "DKK", "ZAR", "INR", "CNY", "KRW", "MXN", "BRL", "PLN", "CZK", "HUF",
    "ILS", "TRY", "TWD", "THB",
}


def _p_currency(values) -> float:
    """ISO currency codes. Membership, not shape: IBM, AMD and GE are also
    three capital letters, and a ticker column must not read as currency."""
    return _frac(values, lambda v: str(v).strip().upper() in _CURRENCY_CODES)


def _p_any(values) -> float:
    """No usable value signature — the header has to carry the mapping alone."""
    return 0.0


# ── Field catalogue ──────────────────────────────────────────────────────────

@dataclass
class FieldSpec:
    key: str
    label: str
    aliases: tuple
    profile: callable = _p_any
    strict: bool = False        # values must back the header up, or the match is a false friend
    distinct: bool = False      # content alone identifies it (BUY/SELL can only be a side)
    required: bool = False
    help: str = ""


FIELDS: list[FieldSpec] = [
    FieldSpec(
        "ticker", "Ticker", (
            "ticker", "symbol", "sym", "ticker symbol", "security", "security symbol",
            "stock", "stock symbol", "instrument", "contract", "local symbol",
            "asset", "market", "product",
        ),
        _p_ticker, strict=True, distinct=True, required=True,
    ),
    FieldSpec(
        "entry_date", "Entry date", (
            "entry date", "trade date", "date", "open date", "opened", "date opened",
            "purchase date", "buy date", "transaction date", "run date", "activity date",
            "date acquired", "opening date", "executed", "execution date", "filled date",
            "settlement date", "as of date",
        ),
        _p_date, strict=True, required=True,
    ),
    FieldSpec(
        "quantity", "Quantity", (
            "quantity", "qty", "q", "shares", "share qty", "size", "units",
            "no of shares", "number of shares", "contracts", "filled qty",
            "quantity filled", "amount of shares", "position", "volume",
        ),
        _p_number, strict=True, required=True,
    ),
    FieldSpec(
        "entry_price", "Entry price", (
            "entry price", "buy price", "open price", "price", "avg price",
            "average price", "cost", "cost per share", "purchase price", "fill price",
            "price per share", "opening price", "avg entry", "entry", "unit price",
            "trade price", "execution price", "price usd", "avg cost", "average cost",
        ),
        _p_positive, strict=True, required=True,
    ),
    FieldSpec(
        "exit_date", "Exit date", (
            "exit date", "close date", "closed", "date closed", "sell date",
            "date sold", "closing date", "sale date", "date of sale", "closed date",
        ),
        _p_date, strict=True,
    ),
    FieldSpec(
        "exit_price", "Exit price", (
            "exit price", "sell price", "close price", "closing price", "sale price",
            "avg exit", "exit", "proceeds per share", "sold price",
        ),
        _p_positive, strict=True,
    ),
    FieldSpec(
        "side", "Side / action", (
            "side", "buy sell", "action", "direction", "transaction type", "activity",
            "trade type", "b s", "buy or sell", "order action",
        ),
        _p_side, strict=True, distinct=True,
        help="BUY/SELL rows are paired into round trips; LONG/SHORT just labels the trade.",
    ),
    FieldSpec(
        "gross_amount", "Total amount", (
            "amount", "net amount", "gross amount", "proceeds", "total", "value",
            "net cash", "cost basis", "total cost", "consideration", "notional",
            "trade value", "principal",
        ),
        _p_number, strict=True,
        help="Only used when there is no price column — price is derived as amount ÷ quantity.",
    ),
    FieldSpec(
        "opening_stop", "Initial stop", (
            "initial stop loss", "initial stop", "opening stop", "stop loss", "stop",
            "original stop", "stop price", "sl",
        ),
        _p_positive, strict=True,
    ),
    FieldSpec(
        "current_stop", "Current stop", (
            "current stop", "stop now", "trailing stop", "updated stop", "new stop",
        ),
        _p_positive, strict=True,
    ),
    FieldSpec(
        "tags", "Tags", (
            "tags", "tag", "labels", "label", "strategy", "setup", "category", "system",
        ),
    ),
    FieldSpec(
        "notes", "Notes", (
            "notes", "note", "comment", "comments", "memo", "remarks", "description",
            "journal", "reason",
        ),
    ),
    FieldSpec(
        "instrument_type", "Instrument type", (
            "instrument type", "asset type", "asset class", "sectype", "security type",
            "product type", "asset category", "class", "type",
        ),
        _p_instrument, strict=True, distinct=True,
    ),
    FieldSpec(
        "expiration", "Expiration", (
            "expiration", "expiry", "exp date", "expiration date", "exp", "maturity",
        ),
        _p_date, strict=True,
    ),
    FieldSpec("strike", "Strike", ("strike", "strike price"), _p_positive, strict=True),
    FieldSpec(
        "option_type", "Put / call", (
            "option type", "put call", "p c", "call put", "right", "put or call",
        ),
        _p_option_type, strict=True, distinct=True,
    ),
    FieldSpec("multiplier", "Multiplier", ("multiplier", "contract multiplier", "mult"),
              _p_positive, strict=True),
    FieldSpec("underlying_ticker", "Underlying", ("underlying", "underlying ticker",
                                                  "underlying symbol", "root"), _p_ticker),
    FieldSpec("exchange", "Exchange", ("exchange", "listing exchange", "venue",
                                       "primary exchange", "mic", "market centre",
                                       "market center")),
    FieldSpec(
        "currency", "Currency", (
            "currency", "ccy", "curr", "cur", "native currency", "price currency",
            "trade currency", "currency code", "denomination", "fx currency",
        ),
        _p_currency, strict=True, distinct=True,
        help="The currency the prices in this file are in. Trades are converted "
             "to USD at each trade's own entry and exit dates on import.",
    ),
    FieldSpec(
        "transaction_id", "Transaction #", (
            "transaction id", "transaction number", "transaction no", "trans id",
            "txn id", "txn", "trade id", "trade number", "trade no", "order id",
            "order number", "execution id", "exec id", "reference", "ref", "ref no",
            "confirmation number", "confirm no", "id",
        ),
        help="The broker's reference for the fill. Kept in the trade's Notes as "
             "\"Ref: …\" — both sides when a buy and sell are paired.",
    ),
]

FIELDS_BY_KEY = {f.key: f for f in FIELDS}
REQUIRED_FIELDS = [f.key for f in FIELDS if f.required]


# ── Header + value scoring ───────────────────────────────────────────────────

_SAMPLE_ROWS = 200          # profiling more than this buys nothing and costs time
_ASSIGN_FLOOR = 0.35        # below this a column is left unmapped rather than guessed
_FUZZY_FLOOR = 0.82


def _header_score(norm: str, spec: FieldSpec) -> float:
    """0..1 on the header text alone."""
    if not norm:
        return 0.0
    if norm in spec.aliases:
        return 1.0
    for alias in spec.aliases:
        # "entry price usd" contains "entry price"; "qty" is contained by "qty filled"
        if norm == alias or f" {alias} " in f" {norm} ":
            return 0.90
    best = max((SequenceMatcher(None, norm, a).ratio() for a in spec.aliases), default=0.0)
    return best * 0.85 if best >= _FUZZY_FLOOR else 0.0


def score_column(header, values, spec: FieldSpec) -> float:
    """Confidence that `header`/`values` is `spec`, 0..1.

    Name and content are both evidence and neither is sufficient. A strong name
    with contradicting content is downweighted hard (that is the "Trade Date"
    column that actually holds settlement text). Content alone can carry a
    mapping, but only when it is overwhelming, and it never scores high enough
    to look confirmed — the user is meant to eyeball those.
    """
    hs = _header_score(normalize_header(header), spec)
    ps = spec.profile(values)
    if hs > 0:
        if spec.profile is _p_any:
            return hs                       # nothing to corroborate with; the name is all there is
        score = 0.60 * hs + 0.40 * ps
        if spec.strict and ps < 0.40:
            score *= 0.40
        return score
    if spec.distinct and ps >= 0.85:
        return 0.45 * ps
    return 0.0


def confidence_label(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


@dataclass
class Mapping:
    """field key → source column name, plus the score behind each choice."""
    columns: dict = _dc_field(default_factory=dict)
    scores: dict = _dc_field(default_factory=dict)

    def get(self, key):
        return self.columns.get(key)

    def missing_required(self) -> list:
        """Required fields with nothing behind them.

        `entry_price` is satisfied by a total-amount column too — `build_trades`
        derives the per-unit price as amount / quantity.
        """
        missing = [k for k in REQUIRED_FIELDS if not self.columns.get(k)]
        if ("entry_price" in missing and self.columns.get("gross_amount")
                and self.columns.get("quantity")):
            missing.remove("entry_price")
        return missing


def propose_mapping(df: pd.DataFrame) -> Mapping:
    """Best-guess field → column assignment for `df`.

    Greedy over every (field, column) score: the single most confident pair is
    taken first, and both sides are then spent. That keeps an unambiguous match
    ("Entry Price" → entry_price at 1.0) from being stolen by a weaker field
    that also likes the column, which is the failure mode of assigning
    field-by-field in declaration order.
    """
    samples = {c: df[c].dropna().astype(str).head(_SAMPLE_ROWS).tolist() for c in df.columns}

    candidates = []
    for spec in FIELDS:
        for col in df.columns:
            s = score_column(col, samples[col], spec)
            if s >= _ASSIGN_FLOOR:
                candidates.append((s, spec.key, col))
    candidates.sort(key=lambda t: (-t[0], t[1], str(t[2])))

    mapping, used_cols = Mapping(), set()
    for s, key, col in candidates:
        if key in mapping.columns or col in used_cols:
            continue
        mapping.columns[key] = col
        mapping.scores[key] = s
        used_cols.add(col)

    # Required fields get a second chance on content alone. A file whose price
    # column is headed "Px" leaves entry_price unmapped above; if exactly one
    # unclaimed column looks the part, taking it beats importing nothing.
    for key in REQUIRED_FIELDS:
        if mapping.columns.get(key):
            continue
        spec = FIELDS_BY_KEY[key]
        free = [(spec.profile(samples[c]), c) for c in df.columns if c not in used_cols]
        free = [(p, c) for p, c in free if p >= 0.70]
        if len(free) == 1 or (free and sorted(free, reverse=True)[0][0] >= 0.95):
            p, col = sorted(free, key=lambda t: (-t[0], str(t[1])))[0]
            mapping.columns[key] = col
            mapping.scores[key] = 0.40 * p
            used_cols.add(col)

    return mapping


# ── Reading the file ─────────────────────────────────────────────────────────

@dataclass
class ReadReport:
    encoding: str = ""
    delimiter: str = ","
    header_row: int = 0
    skipped_preamble: int = 0
    dropped_rows: int = 0
    messages: list = _dc_field(default_factory=list)


def _decode(raw: bytes) -> tuple:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (with replacements)"


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:
        # Sniffer gives up on ragged broker exports; fall back to whichever
        # candidate divides the sample lines most consistently.
        lines = [ln for ln in sample.splitlines()[:20] if ln.strip()]
        best, best_score = ",", -1.0
        for d in (",", ";", "\t", "|"):
            counts = [ln.count(d) for ln in lines]
            if not counts or max(counts) == 0:
                continue
            # reward many fields, punish rows disagreeing about how many
            spread = max(counts) - min(counts)
            score = max(counts) - spread
            if score > best_score:
                best, best_score = d, score
        return best


def _header_row_index(text: str, delim: str, limit: int = 30) -> int:
    """Index of the line that reads most like a header row.

    Broker exports routinely open with a title, an account number and a blank
    line, so row 0 is often junk. Score each early line by how many of its cells
    match a known field alias; the real header wins by a mile.
    """
    lines = text.splitlines()[:limit]
    best_idx, best_hits = 0, -1
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        cells = next(csv.reader([line], delimiter=delim), [])
        if len(cells) < 2:
            continue
        hits = 0
        for cell in cells:
            norm = normalize_header(cell)
            if not norm:
                continue
            if any(_header_score(norm, spec) >= 0.85 for spec in FIELDS):
                hits += 1
        filled = sum(1 for c in cells if str(c).strip())
        score = hits * 2 + (filled / max(len(cells), 1))
        if hits >= 2 and score > best_hits:
            best_idx, best_hits = i, score
    return best_idx


def read_table(raw: bytes) -> tuple:
    """Bytes of an uploaded CSV → (DataFrame, ReadReport).

    Tolerant on purpose: unknown encoding, unknown delimiter, a preamble above
    the header, ragged rows, and repeated header blocks in a multi-section
    export are all handled rather than raised.
    """
    rep = ReadReport()
    text, rep.encoding = _decode(raw)
    if not text.strip():
        raise ValueError("The file is empty.")

    sample = "\n".join(text.splitlines()[:50])
    rep.delimiter = _sniff_delimiter(sample)
    rep.header_row = _header_row_index(text, rep.delimiter)
    rep.skipped_preamble = rep.header_row

    df = pd.read_csv(
        io.StringIO(text),
        delimiter=rep.delimiter,
        skiprows=rep.header_row,
        engine="python",
        on_bad_lines="skip",         # ragged multi-section exports
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    df.columns = [str(c).strip() for c in df.columns]

    before = len(df)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    # A repeated header block inside the file re-states the column names as data
    norm_cols = {normalize_header(c) for c in df.columns}
    if len(df.columns):
        first = df.columns[0]
        df = df[~df[first].astype(str).map(lambda v: normalize_header(v) in norm_cols and bool(str(v).strip()))]
    df = df.reset_index(drop=True)
    rep.dropped_rows = before - len(df)

    if df.empty:
        raise ValueError("No data rows found under the header.")
    if rep.skipped_preamble:
        rep.messages.append(
            f"Skipped {rep.skipped_preamble} line(s) above the header row.")
    if rep.dropped_rows:
        rep.messages.append(
            f"Dropped {rep.dropped_rows} blank or repeated-header row(s).")
    return df, rep


def header_fingerprint(columns) -> str:
    """Stable id for a file *layout*, so a remembered mapping can be re-offered.

    Order-insensitive: the same export with columns rearranged is the same
    layout, and re-confirming it would be busywork.
    """
    norm = sorted({normalize_header(c) for c in columns if normalize_header(c)})
    return hashlib.sha1("|".join(norm).encode("utf-8")).hexdigest()[:16]


# ── Row shape ────────────────────────────────────────────────────────────────

_SELL_WORDS = {"sell", "s", "sld", "sold", "sale", "short", "sell short",
               "sell to open", "sell to close", "sto", "stc"}
_OPEN_WORDS = {"buy to open", "sell to open", "bto", "sto", "open"}
_CLOSE_WORDS = {"buy to close", "sell to close", "btc", "stc", "close", "cover",
                "buy cover"}


def _is_sell(v) -> bool:
    return normalize_header(v) in _SELL_WORDS


def detect_shape(df: pd.DataFrame, mapping: Mapping) -> str:
    """"trades" (one row per round trip) or "fills" (one row per execution).

    Getting this wrong is the expensive error: reading fills as trades turns a
    single round trip into two bogus open positions. An exit column is decisive
    evidence of the trade shape; failing that, a side column — or signed
    quantities against repeated tickers — means fills.
    """
    if mapping.get("exit_price") or mapping.get("exit_date"):
        return "trades"
    side_col = mapping.get("side")
    if side_col:
        vals = df[side_col].dropna().astype(str)
        # LONG/SHORT labels a trade; BUY/SELL is an execution
        if vals.map(lambda v: normalize_header(v) in ("buy", "sell", "b", "s", "bot",
                                                      "sld", "bought", "sold")).any():
            return "fills"
        if vals.map(lambda v: normalize_header(v) in _OPEN_WORDS | _CLOSE_WORDS).any():
            return "fills"
    qty_col, tkr_col = mapping.get("quantity"), mapping.get("ticker")
    amt_col = mapping.get("gross_amount")
    if qty_col and tkr_col:
        qtys = df[qty_col].map(clean_number).dropna()
        if (qtys < 0).any() and df[tkr_col].duplicated().any():
            return "fills"
    if amt_col and tkr_col and df[tkr_col].duplicated().any():
        # Direction carried only by the sign of the cash column
        amts = df[amt_col].map(clean_number).dropna()
        if (amts < 0).any() and (amts > 0).any():
            return "fills"
    return "trades"


# ── Building trades ──────────────────────────────────────────────────────────

def _cell(row, mapping: Mapping, key):
    col = mapping.get(key)
    if not col:
        return None
    v = row.get(col)
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    return v


def _instrument_of(itype_raw, expiration, strike) -> str:
    """Option/future/stock. Option-only fields outrank whatever the label says."""
    if expiration or strike is not None:
        return "option"
    s = str(itype_raw or "").lower()
    if any(k in s for k in ("opt", "call", "put", "bag", "combo")):
        return "option"
    if any(k in s for k in ("fut", "future")):
        return "future"
    return "stock"


def _common_fields(row, mapping: Mapping, dayfirst: bool) -> dict:
    """Instrument identity and stops — the parts shared by both row shapes."""
    expiration = _cell(row, mapping, "expiration")
    if expiration:
        d = parse_date(expiration, dayfirst)
        expiration = d.isoformat() if d else None
    strike = clean_number(_cell(row, mapping, "strike"))
    opening_stop = clean_number(_cell(row, mapping, "opening_stop"))
    current_stop = clean_number(_cell(row, mapping, "current_stop"))
    pc = _cell(row, mapping, "option_type")
    tags_raw = _cell(row, mapping, "tags")

    ccy = _cell(row, mapping, "currency")
    ref = _cell(row, mapping, "transaction_id")

    return {
        "native_currency": str(ccy).strip().upper() if ccy else None,
        "transaction_id": str(ref).strip() if ref else None,
        "instrument_type": _instrument_of(_cell(row, mapping, "instrument_type"),
                                          expiration, strike),
        "expiration":   expiration,
        "strike":       strike,
        "option_type":  ("call" if str(pc).strip().lower().startswith("c") else "put") if pc else None,
        "multiplier":   clean_number(_cell(row, mapping, "multiplier")) or 1.0,
        "exchange":     str(_cell(row, mapping, "exchange") or "").strip(),
        "notes":        (str(_cell(row, mapping, "notes")).strip()
                         if _cell(row, mapping, "notes") else None),
        "opening_stop": opening_stop,
        "current_stop": current_stop,
        "stop_enabled": opening_stop is not None or current_stop is not None,
        "tags":         [t.strip() for t in str(tags_raw).split(",") if t.strip()] if tags_raw else [],
    }


def _price_from(row, mapping: Mapping, key, qty, messages, derived_flag) -> float | None:
    """Per-unit price, falling back to total ÷ quantity.

    Cash-activity exports often carry only "Amount" — a total, signed by
    direction. Dividing it back out beats dropping the row, but it is worth
    saying out loud, because commission bundled into the total quietly shifts
    the price.
    """
    px = clean_number(_cell(row, mapping, key))
    if px is not None:
        return abs(px)
    amount = clean_number(_cell(row, mapping, "gross_amount"))
    if amount is not None and qty:
        derived_flag[0] = True
        return abs(amount) / abs(qty)
    return None


def build_trades(df: pd.DataFrame, mapping: Mapping, shape: str,
                 dayfirst: bool = False) -> tuple:
    """(trade dicts, messages). Dicts are shaped for app.import_parsed_trades().

    Rows that cannot yield a ticker, date, quantity and price are reported by
    row number rather than silently dropped — a student needs to know which
    three of their eighty trades did not make it.
    """
    if shape == "fills":
        return _build_from_fills(df, mapping, dayfirst)
    return _build_from_trades(df, mapping, dayfirst)


def _build_from_trades(df: pd.DataFrame, mapping: Mapping, dayfirst: bool) -> tuple:
    trades, messages = [], []
    derived = [False]
    skipped = 0

    for i, row in df.iterrows():
        ticker = _cell(row, mapping, "ticker")
        if not ticker:
            skipped += 1
            continue
        qty = clean_number(_cell(row, mapping, "quantity"))
        entry_date = parse_date(_cell(row, mapping, "entry_date"), dayfirst)
        entry_price = _price_from(row, mapping, "entry_price", qty, messages, derived)
        if qty is None or entry_price is None or entry_date is None:
            missing = ", ".join(n for n, v in (("date", entry_date), ("quantity", qty),
                                               ("price", entry_price)) if v is None)
            messages.append(f"Row {i + 2} ({ticker}): no {missing} — skipped.")
            continue

        raw_side = _cell(row, mapping, "side")
        td = {
            "ticker":      str(ticker).upper().strip(),
            "entry_date":  entry_date,
            "quantity":    abs(qty),
            "entry_price": entry_price,
            "exit_date":   parse_date(_cell(row, mapping, "exit_date"), dayfirst),
            "exit_price":  clean_number(_cell(row, mapping, "exit_price")),
            "side":        "short" if (raw_side and _is_sell(raw_side)) or (qty < 0) else "long",
        }
        td.update(_common_fields(row, mapping, dayfirst))
        trades.append(td)

    if skipped:
        messages.append(f"{skipped} row(s) had no ticker and were skipped.")
    if derived[0]:
        messages.append("Some prices were derived as amount ÷ quantity — check them; "
                        "any commission folded into the total shifts the price slightly.")
    return trades, messages


def _build_from_fills(df: pd.DataFrame, mapping: Mapping, dayfirst: bool) -> tuple:
    """FIFO-pair buy and sell executions into round trips.

    Leftover buys become open positions. A leftover *sell* is marked
    `close_only`, on the reading that its opening fill predates the export —
    far more common in a student's partial statement than an unflagged short.
    `import_parsed_trades` then matches it against an existing open trade and
    reports it plainly if there is nothing to match.
    """
    messages, derived = [], [False]
    fills, skipped = [], 0

    for i, row in df.iterrows():
        ticker = _cell(row, mapping, "ticker")
        if not ticker:
            skipped += 1
            continue
        qty = clean_number(_cell(row, mapping, "quantity"))
        date = parse_date(_cell(row, mapping, "entry_date"), dayfirst)
        price = _price_from(row, mapping, "entry_price", qty, messages, derived)
        if qty is None or price is None or date is None:
            missing = ", ".join(n for n, v in (("date", date), ("quantity", qty),
                                               ("price", price)) if v is None)
            messages.append(f"Row {i + 2} ({ticker}): no {missing} — skipped.")
            continue

        raw_side = _cell(row, mapping, "side")
        amount = clean_number(_cell(row, mapping, "gross_amount"))
        if raw_side:
            is_sell = _is_sell(raw_side)
        elif qty < 0:
            is_sell = True
        else:
            # Nothing else says which way this fill went, so read the cash: money
            # leaving the account bought, money arriving sold. Common in bank-style
            # statements where quantity is always positive.
            is_sell = amount is not None and amount > 0
        common = _common_fields(row, mapping, dayfirst)
        fills.append({
            "row": i + 2, "ticker": str(ticker).upper().strip(), "date": date,
            "qty": abs(qty), "price": price, "sell": is_sell, "common": common,
        })

    # Identity has to include the option leg: two strikes on one underlying are
    # different instruments and must not be paired against each other.
    def ident(f):
        c = f["common"]
        return (f["ticker"], c["instrument_type"], c["expiration"],
                c["strike"], c["option_type"])

    fills.sort(key=lambda f: (f["date"], f["row"]))

    trades, open_lots, closed_only = [], {}, 0
    for f in fills:
        key = ident(f)
        lots = open_lots.setdefault(key, [])
        if not f["sell"]:
            lots.append(dict(f))
            continue

        remaining = f["qty"]
        while remaining > 1e-9 and lots:
            lot = lots[0]
            take = min(lot["qty"], remaining)
            td = {
                "ticker": f["ticker"], "entry_date": lot["date"],
                "quantity": take, "entry_price": lot["price"],
                "exit_date": f["date"], "exit_price": f["price"], "side": "long",
            }
            td.update(lot["common"])
            td["exit_transaction_id"] = f["common"].get("transaction_id")
            trades.append(td)
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] <= 1e-9:
                lots.pop(0)

        if remaining > 1e-9:
            td = {
                "ticker": f["ticker"], "entry_date": None, "quantity": remaining,
                "entry_price": None, "exit_date": f["date"], "exit_price": f["price"],
                "side": "long", "close_only": True,
            }
            td.update(f["common"])
            # The only reference we hold is the sell's; it is the exit side.
            td["exit_transaction_id"] = td.pop("transaction_id", None)
            trades.append(td)
            closed_only += 1

    for key, lots in open_lots.items():
        for lot in lots:
            if lot["qty"] <= 1e-9:
                continue
            td = {
                "ticker": lot["ticker"], "entry_date": lot["date"],
                "quantity": lot["qty"], "entry_price": lot["price"],
                "exit_date": None, "exit_price": None, "side": "long",
            }
            td.update(lot["common"])
            trades.append(td)

    trades.sort(key=lambda t: (t.get("entry_date") or t.get("exit_date"), t["ticker"]))

    if skipped:
        messages.append(f"{skipped} row(s) had no ticker and were skipped.")
    if closed_only:
        messages.append(
            f"{closed_only} sell fill(s) had no matching buy in this file — treated as "
            "closes of positions already in your log. If they were short entries, "
            "add them by hand instead.")
    if derived[0]:
        messages.append("Some prices were derived as amount ÷ quantity — check them; "
                        "any commission folded into the total shifts the price slightly.")
    return trades, messages
