import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from screener.models import Symbol
from screener.services.yfinance_svc import NoOptionsError, YFinanceError, fetch_iv30
from screener.services.rate_limit import call_with_backoff

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-check symbols flagged has_options=False to see if options are now available"

    def handle(self, *args, **options):
        delay = settings.YFINANCE_REQUEST_DELAY
        symbols = list(Symbol.objects.filter(has_options=False).order_by("ticker"))
        total = len(symbols)

        if total == 0:
            self.stdout.write("No symbols flagged has_options=False, nothing to do")
            return

        self.stdout.write(f"Re-checking {total} symbols for options availability")

        restored = 0
        still_no = 0

        for i, sym in enumerate(symbols, 1):
            try:
                call_with_backoff(
                    fetch_iv30,
                    sym.ticker,
                    retryable_exc=YFinanceError,
                    label=sym.ticker,
                )
            except NoOptionsError:
                still_no += 1
                if delay > 0:
                    time.sleep(delay)
                continue
            except Exception:
                logger.debug("Error re-checking %s, leaving flagged", sym.ticker)
                if delay > 0:
                    time.sleep(delay)
                continue

            # If we got here, options exist now
            sym.has_options = True
            sym.save(update_fields=["has_options"])
            restored += 1
            logger.info("Restored has_options=True for %s", sym.ticker)

            if delay > 0:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Restored: {restored}, Still no options: {still_no}, "
                f"Total checked: {total}"
            )
        )
