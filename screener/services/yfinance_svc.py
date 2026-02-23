import logging
import yfinance as yf

logger = logging.getLogger(__name__)


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
                "strike": float(row["strike"]),
                "bid": float(row.get("bid") or 0),
                "ask": float(row.get("ask") or 0),
                "implied_volatility": float(row.get("impliedVolatility") or 0),
                "open_interest": int(row.get("openInterest") or 0),
                "volume": int(row.get("volume") or 0),
                "spot_price": spot,
            })
        return rows
    except Exception:
        logger.exception("Failed to get puts chain for %s exp %s", ticker, expiry)
        return None
