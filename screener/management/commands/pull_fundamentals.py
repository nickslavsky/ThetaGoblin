import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.timezone import now

from screener.models import Symbol
from screener.services import finnhub_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull/refresh fundamentals from Finnhub for stale symbols"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-days",
            type=int,
            default=7,
            help="Only refresh symbols not updated in N days (default: 7)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max symbols to process — 0 means all (default: 0)",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Seconds between API calls to avoid rate limiting (default: 1.0)",
        )

    def handle(self, *args, **options):
        stale_days = options["stale_days"]
        limit = options["limit"]
        delay = options["delay"]

        cutoff = now() - timedelta(days=stale_days)
        qs = Symbol.objects.filter(
            Q(fundamentals_updated_at__isnull=True) | Q(fundamentals_updated_at__lt=cutoff)
        ).order_by("ticker")

        if limit:
            qs = qs[:limit]

        symbols = list(qs)
        total = len(symbols)
        self.stdout.write(f"Processing {total} symbols (stale_days={stale_days}, limit={limit})")

        updated = 0
        failed = 0

        for sym in symbols:
            data = finnhub_client.fetch_fundamentals(sym.ticker)

            if data is None:
                failed += 1
                logger.warning("Failed to fetch fundamentals for %s, skipping", sym.ticker)
                if delay > 0:
                    time.sleep(delay)
                continue

            for field, value in data.items():
                if value is not None:
                    setattr(sym, field, value)
            sym.fundamentals_updated_at = now()
            sym.save()
            updated += 1

            if delay > 0:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated: {updated}, Failed: {failed}"
            )
        )
