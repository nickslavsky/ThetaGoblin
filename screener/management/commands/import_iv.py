import csv
import logging
from datetime import datetime

from django.core.management.base import BaseCommand

from screener.models import IV30Snapshot, Symbol

logger = logging.getLogger(__name__)

BATCH_SIZE = 2000


class Command(BaseCommand):
    help = "Import IV30 history from a CSV exported from Dolt"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            help="Path to the IV CSV file",
        )

    def handle(self, *args, **options):
        csv_path = options["file"]

        # Pre-load symbol lookup: ticker -> id
        symbol_map = dict(Symbol.objects.values_list("ticker", "id"))
        self.stdout.write(f"Loaded {len(symbol_map)} symbols from DB")

        rows_to_upsert = []
        skipped_unknown = 0
        skipped_null = 0
        total_read = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_read += 1
                ticker = row.get("act_symbol", "").strip()
                iv_raw = row.get("iv_current", "").strip()
                date_str = row.get("date", "").strip()

                if not iv_raw:
                    skipped_null += 1
                    logger.debug("Skipped null IV: %s on %s", ticker, date_str)
                    continue

                symbol_id = symbol_map.get(ticker)
                if symbol_id is None:
                    skipped_unknown += 1
                    logger.debug("Skipped unknown symbol: %s", ticker)
                    continue

                try:
                    iv_val = float(iv_raw)
                    date_val = datetime.strptime(date_str, "%Y-%m-%d").date()
                except (ValueError, TypeError) as e:
                    skipped_null += 1
                    logger.warning("Skipped bad row ticker=%s date=%s iv=%s: %s", ticker, date_str, iv_raw, e)
                    continue

                rows_to_upsert.append(
                    IV30Snapshot(symbol_id=symbol_id, date=date_val, iv30=iv_val)
                )

        upserted = 0
        for i in range(0, len(rows_to_upsert), BATCH_SIZE):
            batch = rows_to_upsert[i : i + BATCH_SIZE]
            IV30Snapshot.objects.bulk_create(
                batch,
                update_conflicts=True,
                unique_fields=["symbol", "date"],
                update_fields=["iv30"],
            )
            upserted += len(batch)
            logger.info("Upserted batch %d-%d", i, i + len(batch))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Read: {total_read}, Upserted: {upserted}, "
                f"Skipped unknown symbol: {skipped_unknown}, "
                f"Skipped null/bad IV: {skipped_null}"
            )
        )
