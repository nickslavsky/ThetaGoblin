import logging
import time
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from screener.models import IV30Snapshot, Symbol
from screener.services import yfinance_svc
from screener.services.yfinance_svc import YFinanceError
from screener.services.rate_limit import call_with_backoff

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


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

        qs = Symbol.objects.order_by("ticker")
        if limit:
            qs = qs[:limit]

        symbols = list(qs)
        total = len(symbols)
        self.stdout.write(f"Processing {total} symbols for yfinance IV30 (delay={delay}s)")

        rows = []
        failed = 0

        for i, sym in enumerate(symbols, 1):
            iv30 = call_with_backoff(
                yfinance_svc.fetch_iv30,
                sym.ticker,
                retryable_exc=YFinanceError,
                label=sym.ticker,
            )

            if iv30 is None:
                failed += 1
                if delay > 0:
                    time.sleep(delay)
                continue

            rows.append(IV30Snapshot(
                symbol=sym,
                date=today,
                iv30_yfinance=iv30,
            ))

            if i % 100 == 0:
                self.stdout.write(f"  Progress: {i}/{total} (collected={len(rows)}, failed={failed})")

            if delay > 0:
                time.sleep(delay)

        # Bulk upsert — only update iv30_yfinance, leave iv30 alone
        upserted = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            IV30Snapshot.objects.bulk_create(
                batch,
                update_conflicts=True,
                unique_fields=["symbol", "date"],
                update_fields=["iv30_yfinance"],
            )
            upserted += len(batch)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Upserted: {upserted}, Failed: {failed}, Total: {total}"
            )
        )
