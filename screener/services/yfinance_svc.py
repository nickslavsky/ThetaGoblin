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


def _safe_float(val, default: float = 0.0) -> float:
    """Cast to float, treating None and NaN as default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int = 0) -> int:
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
