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
