#!/usr/bin/env python3
"""
Build universe CSV from Finnhub.

Pulls symbols from XNAS and XNYS, fetches fundamentals for the
first 100 per exchange, filters market_cap > 1B, writes CSV.

Usage:
    python scripts/build_universe.py
    python scripts/build_universe.py --output data/my_universe.csv
    python scripts/build_universe.py --limit 50
"""
import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from project root (parent of scripts/)
load_dotenv(Path(__file__).parent.parent / ".env")

FINNHUB_TOKEN = os.environ.get("FINNHUB_TOKEN")
BASE_URL = "https://finnhub.io/api/v1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

EXCHANGES = ["XNAS", "XNYS"]
SYMBOLS_PER_EXCHANGE = 100
DELAY_SECONDS = 1.2
MARKET_CAP_MIN_USD = 1_000_000_000

FIELDNAMES = [
    "ticker",
    "exchange_mic",
    "name",
    "market_cap",
    "operating_margin",
    "cash_flow_per_share_annual",
    "long_term_debt_to_equity_annual",
    "ten_day_avg_trading_volume",
]


def fetch_symbols(mic: str) -> list[dict]:
    """Fetch list of equity symbols for a given MIC exchange."""
    try:
        resp = requests.get(
            f"{BASE_URL}/stock/symbol",
            params={"exchange": "US", "mic": mic, "token": FINNHUB_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        symbols = resp.json()
        # Filter to common stocks only
        return [s for s in symbols if s.get("type") in ("Common Stock", "EQS")]
    except Exception:
        logger.exception("Failed to fetch symbols for %s", mic)
        return []


def fetch_fundamentals(ticker: str) -> dict | None:
    """Fetch fundamental metrics for a single ticker. Returns None on error."""
    try:
        resp = requests.get(
            f"{BASE_URL}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": FINNHUB_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        metrics = resp.json().get("metric", {})
        raw_cap = metrics.get("marketCapitalization")
        if raw_cap is None:
            return None
        return {
            "market_cap": int(raw_cap * 1_000_000),
            "operating_margin": metrics.get("operatingMarginAnnual"),
            "cash_flow_per_share_annual": metrics.get("cashFlowPerShareAnnual"),
            "long_term_debt_to_equity_annual": metrics.get("longTermDebt/equityAnnual"),
            "ten_day_avg_trading_volume": metrics.get("10DayAverageTradingVolume"),
        }
    except Exception:
        logger.exception("Failed to fetch fundamentals for %s", ticker)
        return None


def main():
    if not FINNHUB_TOKEN:
        logger.error("FINNHUB_TOKEN not set. Add it to .env in the project root.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Build universe CSV from Finnhub")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent.parent / "data" / "universe.csv"),
        help="Output CSV path (default: data/universe.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=SYMBOLS_PER_EXCHANGE,
        help=f"Symbols per exchange (default: {SYMBOLS_PER_EXCHANGE})",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for mic in EXCHANGES:
        logger.info("Fetching symbols for %s...", mic)
        symbols = fetch_symbols(mic)
        logger.info("Got %d symbols from %s, taking first %d", len(symbols), mic, args.limit)
        symbols = symbols[: args.limit]

        for i, sym in enumerate(symbols, start=1):
            ticker = sym.get("symbol", "")
            name = sym.get("description", "")  # Finnhub uses 'description' not 'name'

            if not ticker:
                continue

            if i % 10 == 0:
                logger.info("[%s] Processed %d/%d symbols", mic, i, len(symbols))

            fundamentals = fetch_fundamentals(ticker)
            time.sleep(DELAY_SECONDS)

            if fundamentals is None:
                logger.warning("Skipping %s — no fundamentals returned", ticker)
                continue

            market_cap = fundamentals.get("market_cap", 0) or 0
            if market_cap < MARKET_CAP_MIN_USD:
                continue

            rows.append({
                "ticker": ticker,
                "exchange_mic": mic,
                "name": name,
                "market_cap": market_cap,
                "operating_margin": fundamentals.get("operating_margin", ""),
                "cash_flow_per_share_annual": fundamentals.get("cash_flow_per_share_annual", ""),
                "long_term_debt_to_equity_annual": fundamentals.get("long_term_debt_to_equity_annual", ""),
                "ten_day_avg_trading_volume": fundamentals.get("ten_day_avg_trading_volume", ""),
            })

    logger.info("Writing %d symbols to %s", len(rows), output_path)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Done! %d symbols written.", len(rows))


if __name__ == "__main__":
    main()
