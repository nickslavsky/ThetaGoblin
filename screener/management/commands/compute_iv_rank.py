import logging
from datetime import date

from django.core.management.base import BaseCommand

from screener.models import IV30Snapshot, IVRank, Symbol
from screener.services.iv_rank_svc import compute_iv_rank

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute IV rank from IV30 history for all symbols with IV30 data"

    def handle(self, *args, **options):
        today = date.today()
        symbols_with_iv30 = Symbol.objects.filter(
            iv30_snapshots__isnull=False
        ).distinct()

        updated = 0
        skipped = 0

        for sym in symbols_with_iv30:
            history = list(
                IV30Snapshot.objects.filter(symbol=sym)
                .order_by("date")
                .values_list("iv30", flat=True)
            )
            current = history[-1]
            result = compute_iv_rank(current_iv30=current, historical_iv30s=history)

            if result is None:
                skipped += 1
                continue

            IVRank.objects.update_or_create(
                symbol=sym,
                defaults={
                    "computed_date": today,
                    "iv_rank": result["iv_rank"],
                    "iv_percentile": result["iv_percentile"],
                    "weeks_of_history": result["weeks_of_history"],
                    "is_reliable": result["is_reliable"],
                },
            )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated {updated} IV ranks. Skipped {skipped} symbols."
            )
        )
