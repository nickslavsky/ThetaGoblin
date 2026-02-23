import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from screener.models import EarningsDate, Symbol
from screener.services import finnhub_client

logger = logging.getLogger(__name__)


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
            f"Pulling earnings from {today.isoformat()} to {end_date.isoformat()}..."
        )

        entries = finnhub_client.fetch_earnings(today.isoformat(), end_date.isoformat())
        if not entries:
            self.stdout.write("No earnings returned from Finnhub.")
            return

        known_tickers = set(Symbol.objects.values_list("ticker", flat=True))
        created = 0
        skipped = 0

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
                logger.exception("Failed to store earnings for %s on %s", ticker, report_date_str)
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created: {created}, Skipped: {skipped}")
        )
