import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Min, Max, OuterRef, Q, Subquery

from screener.models import IV30Snapshot, IVRank, Symbol
from screener.services.iv_rank_svc import compute_iv_rank

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute IV rank from IV30 history for all symbols with IV30 data"

    def handle(self, *args, **options):
        today = date.today()
        cutoff = today - timedelta(days=365)

        latest_snap = (
            IV30Snapshot.objects
            .filter(symbol=OuterRef('pk'), date__gte=cutoff, iv30__isnull=False)
            .order_by('-date')
        )

        window = Q(iv30_snapshots__date__gte=cutoff, iv30_snapshots__iv30__isnull=False)

        symbols = (
            Symbol.objects
            .filter(iv30_snapshots__date__gte=cutoff, iv30_snapshots__iv30__isnull=False)
            .annotate(
                current_iv30=Subquery(latest_snap.values('iv30')[:1]),
                latest_date=Subquery(latest_snap.values('date')[:1]),
                iv_low=Min('iv30_snapshots__iv30', filter=window),
                iv_high=Max('iv30_snapshots__iv30', filter=window),
                earliest_date=Min('iv30_snapshots__date', filter=window),
                total_count=Count('iv30_snapshots', filter=window),
            )
            .annotate(
                count_lte=Count(
                    'iv30_snapshots',
                    filter=window & Q(iv30_snapshots__iv30__lte=F('current_iv30')),
                ),
            )
        )

        rows = []
        skipped = 0

        for sym in symbols:
            result = compute_iv_rank(
                current_iv30=sym.current_iv30,
                min_iv30=sym.iv_low,
                max_iv30=sym.iv_high,
                count_lte=sym.count_lte,
                total_count=sym.total_count,
                earliest_date=sym.earliest_date,
                latest_date=sym.latest_date,
            )
            if result is None:
                skipped += 1
                continue
            rows.append(IVRank(
                symbol=sym,
                computed_date=today,
                iv_rank=result["iv_rank"],
                iv_percentile=result["iv_percentile"],
                weeks_of_history=result["weeks_of_history"],
                is_reliable=result["is_reliable"],
            ))

        IVRank.objects.bulk_create(
            rows,
            update_conflicts=True,
            unique_fields=["symbol"],
            update_fields=["computed_date", "iv_rank", "iv_percentile", "weeks_of_history", "is_reliable"],
        )

        stale_count, _ = IVRank.objects.filter(computed_date__lt=today).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Updated {len(rows)} IV ranks. "
                f"Skipped {skipped} symbols. "
                f"Cleaned {stale_count} stale rows."
            )
        )
