import logging
import math
import warnings
from datetime import date

import yfinance as yf

# yfinance uses Timestamp.utcnow() internally, which is deprecated in pandas 2.x.
# This is a third-party issue we cannot fix — suppress to avoid log flooding.
warnings.filterwarnings(
    "ignore",
    message="Timestamp.utcnow is deprecated",
    module="yfinance",
)

logger = logging.getLogger(__name__)


class YFinanceError(Exception):
    """Raised on yfinance errors that should trigger backoff retry."""
    pass


class NoOptionsError(Exception):
    """Raised when a symbol has no suitable options data. Not retryable."""
    pass


def _safe_float(val, default: float = 0.0) -> float:
    """Cast to float, treating None and NaN as default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int | None = 0) -> int | None:
    """Cast to int, treating None and NaN as default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return default


def get_expiry_dates(ticker: str) -> list[str]:
    """Return available options expiry date strings (YYYY-MM-DD). Returns [] on error."""
    try:
        t = yf.Ticker(ticker)
        return list(t.options)
    except Exception:
        logger.exception("Failed to get expiry dates for %s", ticker)
        return []


def get_puts_chain(ticker: str, expiry: str) -> list[dict] | None:
    """Fetch puts chain for a ticker+expiry. Returns list of dicts or None on error.
    Dict keys: strike, bid, ask, implied_volatility, open_interest, volume, spot_price
    """
    try:
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry)
        spot = t.info.get("currentPrice") or t.info.get("regularMarketPrice")
        rows = []
        for _, row in chain.puts.iterrows():
            rows.append({
                "strike": _safe_float(row.get("strike")),
                "bid": _safe_float(row.get("bid")),
                "ask": _safe_float(row.get("ask")),
                "implied_volatility": _safe_float(row.get("impliedVolatility")),
                "open_interest": _safe_int(row.get("openInterest")),
                "volume": _safe_int(row.get("volume")),
                "spot_price": spot,
            })
        return rows
    except Exception:
        logger.exception("Failed to get puts chain for %s exp %s", ticker, expiry)
        return None


def _safe_optional(val):
    """Return val as-is if it's a real number, else None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else val
    except (TypeError, ValueError):
        return None


def _is_monthly_expiry(expiry_date: date) -> bool:
    """Check if a date is the 3rd Friday of its month (standard monthly options)."""
    if expiry_date.weekday() != 4:  # Friday
        return False
    # 3rd Friday falls on days 15-21
    return 15 <= expiry_date.day <= 21


def _find_atm_iv(df, spot: float) -> float | None:
    """Find the implied volatility of the strike closest to spot price.

    Returns None if dataframe is empty or has no valid IV.
    """
    if df.empty:
        return None
    strikes = df["strike"].values
    idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    iv = df.iloc[idx]["impliedVolatility"]
    return _safe_float(iv, default=None)


def fetch_iv30(ticker: str) -> float:
    """Compute 30-day implied volatility from yfinance options chain.

    Picks the nearest monthly expiry with >= 20 DTE, finds ATM strike,
    averages put and call IV at that strike.

    Returns IV as a decimal (e.g. 0.28).
    Raises YFinanceError if no suitable expiry or on network failure.
    """
    try:
        t = yf.Ticker(ticker)
        expiries = t.options
    except Exception as exc:
        raise YFinanceError(f"Failed to fetch options for {ticker}: {exc}") from exc

    if not expiries:
        raise NoOptionsError(f"No options expiries for {ticker}")

    today = date.today()
    min_dte = 20

    # Filter to monthly expiries with sufficient DTE
    candidates = []
    for exp_str in expiries:
        exp_date = date.fromisoformat(exp_str)
        dte = (exp_date - today).days
        if dte >= min_dte and _is_monthly_expiry(exp_date):
            candidates.append((dte, exp_str))

    if not candidates:
        raise NoOptionsError(f"No monthly expiry with >= {min_dte} DTE for {ticker}")

    # Pick nearest
    candidates.sort()
    target_expiry = candidates[0][1]

    try:
        chain = t.option_chain(target_expiry)
    except Exception as exc:
        raise YFinanceError(f"Failed to fetch chain for {ticker} exp {target_expiry}: {exc}") from exc

    # Spot price comes free from the option_chain response — no extra HTTP call
    underlying = chain.underlying or {}
    spot = underlying.get("regularMarketPrice")
    if not spot:
        raise NoOptionsError(f"No spot price for {ticker}")

    put_iv = _find_atm_iv(chain.puts, spot)
    call_iv = _find_atm_iv(chain.calls, spot)

    if put_iv is not None and call_iv is not None:
        return (put_iv + call_iv) / 2
    elif put_iv is not None:
        return put_iv
    elif call_iv is not None:
        return call_iv
    else:
        raise NoOptionsError(f"No valid ATM IV found for {ticker} exp {target_expiry}")


def fetch_fundamentals(ticker: str) -> dict:
    """Fetch fundamental metrics for a single ticker from yfinance.

    Returns a dict with keys matching Symbol model fields.
    Raises YFinanceError on any failure (for backoff compatibility).
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
    except Exception as exc:
        raise YFinanceError(f"Failed to fetch info for {ticker}: {exc}") from exc

    if not info:
        raise YFinanceError(f"Empty info response for {ticker}")

    return {
        "market_cap": _safe_int(info.get("marketCap"), default=None),
        "operating_margin": _safe_optional(info.get("operatingMargins")),
        "free_cash_flow": _safe_int(info.get("freeCashflow"), default=None),
        "debt_to_equity": _safe_optional(info.get("debtToEquity")),
        "avg_volume_10d": _safe_int(info.get("averageVolume10days"), default=None),
    }
