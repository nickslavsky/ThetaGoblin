import logging
import os

import requests

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


class RateLimitError(Exception):
    """Raised when Finnhub returns 429 Too Many Requests."""
    pass


def _get_token() -> str:
    token = os.environ.get("FINNHUB_TOKEN", "")
    if not token:
        raise ValueError("FINNHUB_TOKEN not set in environment")
    return token


def fetch_fundamentals(ticker: str) -> dict | None:
    """Fetch fundamental metrics for a single ticker from Finnhub.

    Returns a dict with keys matching Symbol model fields, or None on any error.
    Raises RateLimitError on 429 so callers can back off appropriately.
    Finnhub returns marketCapitalization in millions — we convert to USD.
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": _get_token()},
            timeout=15,
        )
        if resp.status_code == 429:
            raise RateLimitError(f"Rate limited fetching fundamentals for {ticker}")
        resp.raise_for_status()
        metrics = resp.json().get("metric", {})
        raw_cap = metrics.get("marketCapitalization")
        return {
            "market_cap": int(raw_cap * 1_000_000) if raw_cap is not None else None,
            "operating_margin": metrics.get("operatingMarginAnnual"),
            "cash_flow_per_share_annual": metrics.get("cashFlowPerShareAnnual"),
            "long_term_debt_to_equity_annual": metrics.get("longTermDebt/equityAnnual"),
            "ten_day_avg_trading_volume": metrics.get("10DayAverageTradingVolume"),
        }
    except RateLimitError:
        raise
    except Exception:
        logger.exception("Failed to fetch fundamentals for %s", ticker)
        return None


def fetch_symbols(exchange_mic: str) -> list[dict]:
    """Fetch list of symbols for a given exchange MIC.

    Returns list of raw Finnhub symbol dicts, or [] on error.
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/stock/symbol",
            params={"exchange": "US", "mic": exchange_mic, "token": _get_token()},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("Failed to fetch symbols for %s", exchange_mic)
        return []


def fetch_earnings(from_date: str, to_date: str) -> list[dict]:
    """Fetch earnings calendar for a date range.

    Args:
        from_date: YYYY-MM-DD start date
        to_date: YYYY-MM-DD end date
    Returns list of earnings calendar entries, or [] on error.
    Raises RateLimitError on 429 so callers can back off appropriately.
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/calendar/earnings",
            params={"from": from_date, "to": to_date, "token": _get_token()},
            timeout=15,
        )
        if resp.status_code == 429:
            raise RateLimitError(f"Rate limited fetching earnings {from_date} to {to_date}")
        resp.raise_for_status()
        return resp.json().get("earningsCalendar", [])
    except RateLimitError:
        raise
    except Exception:
        logger.exception("Failed to fetch earnings calendar %s to %s", from_date, to_date)
        return []
