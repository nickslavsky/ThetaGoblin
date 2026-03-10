import logging
import math
import warnings

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
