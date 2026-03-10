import logging
import time
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from screener.models import IV30Snapshot, Symbol
from screener.services import yfinance_svc
from screener.services.yfinance_svc import NoOptionsError, YFinanceError
from screener.services.rate_limit import call_with_backoff

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Pull IV30 from yfinance options chains for all symbols"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max symbols to process — 0 means all (default: 0)",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = settings.YFINANCE_REQUEST_DELAY
        today = date.today()

        # Skip symbols already computed today
        already_done = set(
            IV30Snapshot.objects.filter(
                date=today, iv30_yfinance__isnull=False,
            ).values_list("symbol_id", flat=True)
        )

        qs = Symbol.objects.exclude(id__in=already_done).order_by("ticker")
        if limit:
            qs = qs[:limit]

        symbols = list(qs)
        total = len(symbols)
        skipped = len(already_done)
        if skipped:
            self.stdout.write(f"Skipping {skipped} symbols already computed today")
        self.stdout.write(f"Processing {total} symbols for yfinance IV30 (delay={delay}s)")

        upserted = 0
        failed = 0
        no_options = 0

        for i, sym in enumerate(symbols, 1):
            try:
                iv30 = call_with_backoff(
                    yfinance_svc.fetch_iv30,
                    sym.ticker,
                    retryable_exc=YFinanceError,
                    label=sym.ticker,
                )
            except NoOptionsError:
                no_options += 1
                logger.debug("No options data for %s, skipping", sym.ticker)
                continue

            if iv30 is None:
                failed += 1
                if delay > 0:
                    time.sleep(delay)
                continue

            IV30Snapshot.objects.update_or_create(
                symbol=sym, date=today,
                defaults={"iv30_yfinance": iv30},
            )
            upserted += 1

            if i % 100 == 0:
                self.stdout.write(f"  Progress: {i}/{total} (upserted={upserted}, failed={failed})")

            if delay > 0:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Upserted: {upserted}, No options: {no_options}, "
                f"Failed: {failed}, Total: {total}"
            )
        )
