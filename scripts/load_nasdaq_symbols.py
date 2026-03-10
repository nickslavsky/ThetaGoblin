"""
Throwaway script: load symbols from Nasdaq screener API.
Run via: docker compose exec web python scripts/load_nasdaq_symbols.py
"""

import json
import logging
import os
import sys
import time
from urllib.request import Request, urlopen

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "thetagoblin.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from screener.models import Symbol  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXCHANGES = {
    "nyse": "XNYS",
    "nasdaq": "XNAS",
}
MIN_MARKET_CAP = 1_000_000_000
URL_TEMPLATE = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&exchange={exchange}&limit=5000"
)
# Nasdaq API blocks default urllib User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def parse_market_cap(raw: str) -> int | None:
    """Parse market cap string like '1,798,875,906,659' to int."""
    if not raw or raw.strip() == "":
        return None
    try:
        return int(raw.replace(",", ""))
    except (ValueError, TypeError):
        return None


def fetch_symbols(exchange: str) -> list[dict]:
    """Fetch symbol rows from Nasdaq API for one exchange."""
    url = URL_TEMPLATE.format(exchange=exchange)
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    rows = data["data"]["table"]["rows"]
    total = data["data"]["totalrecords"]
    logger.info("Fetched %d rows (totalrecords=%d) from %s", len(rows), total, exchange)
    return rows


def main():
    existing_tickers = set(Symbol.objects.values_list("ticker", flat=True))
    logger.info("Existing symbols in DB: %d", len(existing_tickers))

    stats = {
        "fetched": 0,
        "skipped_low_cap": 0,
        "skipped_exists": 0,
        "skipped_slash": 0,
        "created": 0,
        "errors": 0,
    }

    for exchange_key, mic in EXCHANGES.items():
        try:
            rows = fetch_symbols(exchange_key)
        except Exception:
            logger.exception("Failed to fetch %s", exchange_key)
            continue

        for row in rows:
            stats["fetched"] += 1
            ticker = row["symbol"].strip()

            # Skip class shares with slash (BRK/B, BF/B etc.)
            if "/" in ticker:
                stats["skipped_slash"] += 1
                continue

            mcap = parse_market_cap(row.get("marketCap", ""))
            if mcap is None or mcap < MIN_MARKET_CAP:
                stats["skipped_low_cap"] += 1
                continue

            if ticker in existing_tickers:
                stats["skipped_exists"] += 1
                continue

            try:
                Symbol.objects.create(
                    ticker=ticker,
                    exchange_mic=mic,
                    name=row.get("name", "")[:255],
                    market_cap=mcap,
                )
                existing_tickers.add(ticker)
                stats["created"] += 1
            except Exception:
                logger.exception("Failed to create %s", ticker)
                stats["errors"] += 1

        # Be polite between exchange requests
        time.sleep(1)

    logger.info("=== Results ===")
    for key, val in stats.items():
        logger.info("  %-20s %d", key, val)


if __name__ == "__main__":
    main()
