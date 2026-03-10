import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.timezone import now

from screener.models import Symbol
from screener.services import yfinance_svc
from screener.services.yfinance_svc import YFinanceError
from screener.services.rate_limit import call_with_backoff

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Pull/refresh fundamentals from Yahoo Finance for stale symbols"

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

    def handle(self, *args, **options):
        stale_days = options["stale_days"]
        limit = options["limit"]
        delay = settings.YFINANCE_REQUEST_DELAY

        cutoff = now() - timedelta(days=stale_days)
        qs = Symbol.objects.filter(
            Q(fundamentals_updated_at__isnull=True) | Q(fundamentals_updated_at__lt=cutoff)
        ).order_by("ticker")

        if limit:
            qs = qs[:limit]

        symbols = list(qs)
        total = len(symbols)
        self.stdout.write(f"Processing {total} symbols (stale_days={stale_days}, delay={delay}s)")

        updated = 0
        failed = 0

        for i, sym in enumerate(symbols, 1):
            data = call_with_backoff(
                yfinance_svc.fetch_fundamentals,
                sym.ticker,
                retryable_exc=YFinanceError,
                label=sym.ticker,
            )

            if data is None:
                failed += 1
                if delay > 0:
                    time.sleep(delay)
                continue

            for field, value in data.items():
                if value is not None:
                    setattr(sym, field, value)
            sym.fundamentals_updated_at = now()
            sym.save()
            updated += 1

            if i % 50 == 0:
                self.stdout.write(f"  Progress: {i}/{total} (updated={updated}, failed={failed})")

            if delay > 0:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated: {updated}, Failed: {failed}, Total: {total}"
            )
        )
