import logging
import time
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from screener.models import EarningsDate, Symbol
from screener.services import finnhub_client
from screener.services.finnhub_client import RateLimitError
from screener.services.rate_limit import call_with_backoff

logger = logging.getLogger(__name__)

# Finnhub returns at most ~1500 records per request descending from the `to` date.
# One week of earnings stays well under that limit. Chunk all range requests by week
# to avoid silent truncation of earlier dates.
CHUNK_DAYS = 3
TRUNCATION_WARN_THRESHOLD = 1400


class Command(BaseCommand):
    help = "Pull upcoming earnings dates from Finnhub earnings calendar"

    def add_arguments(self, parser):
        parser.add_argument(
            "--weeks-ahead",
            type=int,
            default=8,
            help="How many weeks ahead to pull earnings (default: 8)",
        )

    def handle(self, *args, **options):
        weeks_ahead = options["weeks_ahead"]
        today = date.today()
        end_date = today + timedelta(weeks=weeks_ahead)

        self.stdout.write(
            f"Pulling earnings from {today.isoformat()} to {end_date.isoformat()} "
            f"in {CHUNK_DAYS}-day chunks..."
        )

        known_tickers = set(Symbol.objects.values_list("ticker", flat=True))
        created = 0
        skipped = 0

        chunk_start = today
        while chunk_start <= end_date:
            chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS - 1), end_date)

            chunk_label = f"earnings {chunk_start.isoformat()}–{chunk_end.isoformat()}"
            entries = call_with_backoff(
                finnhub_client.fetch_earnings,
                chunk_start.isoformat(),
                chunk_end.isoformat(),
                retryable_exc=RateLimitError,
                label=chunk_label,
            )

            if entries is None:
                logger.error("Failed to fetch %s after retries, skipping chunk", chunk_label)
                chunk_start = chunk_end + timedelta(days=1)
                continue

            if len(entries) >= TRUNCATION_WARN_THRESHOLD:
                logger.warning(
                    "Earnings chunk %s to %s returned %d entries — approaching API limit, "
                    "consider reducing chunk size.",
                    chunk_start.isoformat(),
                    chunk_end.isoformat(),
                    len(entries),
                )

            self.stdout.write(
                f"  {chunk_start.isoformat()} → {chunk_end.isoformat()}: {len(entries)} entries"
            )

            for entry in entries:
                ticker = entry.get("symbol")
                report_date_str = entry.get("date")

                if not ticker or not report_date_str:
                    skipped += 1
                    continue

                if ticker not in known_tickers:
                    skipped += 1
                    continue

                try:
                    symbol = Symbol.objects.get(ticker=ticker)
                    _, was_created = EarningsDate.objects.update_or_create(
                        symbol=symbol,
                        report_date=report_date_str,
                        defaults={"source": "finnhub"},
                    )
                    if was_created:
                        created += 1
                except Exception:
                    logger.exception(
                        "Failed to store earnings for %s on %s", ticker, report_date_str
                    )
                    skipped += 1

            chunk_start = chunk_end + timedelta(days=1)
            if chunk_start <= end_date:
                time.sleep(settings.FINNHUB_REQUEST_DELAY)

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created: {created}, Skipped: {skipped}")
        )
