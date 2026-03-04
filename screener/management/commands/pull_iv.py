import logging
import time
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from screener.models import IV30Snapshot, Symbol
from screener.services import dolthub_client
from screener.services.dolthub_client import DoltHubError

logger = logging.getLogger(__name__)

BATCH_SIZE = 2000

# Alphabet splits to stay under DoltHub's 1000-row limit per query
ALPHABET_SPLITS = [
    {"sym_min": "A", "sym_max": "G"},
    {"sym_min": "G", "sym_max": "O"},
    {"sym_min": "O", "sym_max": None},
]

# Retry settings for DoltHubError
MAX_RETRIES = 3
BACKOFF_INTERVALS = [5, 15, 45]  # seconds


def _fetch_with_retry(date_from, date_to, sym_min, sym_max):
    """Fetch IV rows with retry logic for DoltHubError.

    Returns list of row dicts, or [] if all retries exhausted or on unexpected errors.
    """
    for attempt in range(MAX_RETRIES):
        try:
            return dolthub_client.fetch_iv_rows(
                date_from=date_from,
                date_to=date_to,
                sym_min=sym_min,
                sym_max=sym_max,
            )
        except DoltHubError as exc:
            backoff = BACKOFF_INTERVALS[min(attempt, len(BACKOFF_INTERVALS) - 1)]
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    "DoltHub error (attempt %d/%d) for %s [%s-%s]: %s. "
                    "Retrying in %ds...",
                    attempt + 1, MAX_RETRIES, date_from,
                    sym_min or "*", sym_max or "*", exc, backoff,
                )
                time.sleep(backoff)
            else:
                logger.error(
                    "DoltHub error (attempt %d/%d) for %s [%s-%s]: %s. "
                    "Skipping batch.",
                    attempt + 1, MAX_RETRIES, date_from,
                    sym_min or "*", sym_max or "*", exc,
                )
                return []
        except Exception:
            logger.exception(
                "Unexpected error fetching %s [%s-%s]. Skipping batch.",
                date_from, sym_min or "*", sym_max or "*",
            )
            return []
    return []


class Command(BaseCommand):
    help = "Incrementally fetch IV30 data from DoltHub and upsert into IV30Snapshot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-back",
            type=int,
            default=7,
            help="Fallback lookback days if no existing IV30 data (default: 7)",
        )

    def handle(self, *args, **options):
        days_back = options["days_back"]
        delay = getattr(settings, "DOLTHUB_REQUEST_DELAY", 2.0)

        # Step 1: Determine date range
        dolthub_latest_str = dolthub_client.fetch_latest_date()
        if dolthub_latest_str is None:
            self.stdout.write(
                self.style.WARNING("Could not reach DoltHub. Exiting.")
            )
            return

        dolthub_latest = date.fromisoformat(dolthub_latest_str)

        local_latest = (
            IV30Snapshot.objects.order_by("-date")
            .values_list("date", flat=True)
            .first()
        )

        if local_latest is None:
            start_date = date.today() - timedelta(days=days_back)
            logger.warning(
                "No local IV30 data found. Using --days-back=%d (start=%s). "
                "Consider running import_iv for historical backfill.",
                days_back, start_date,
            )
        elif local_latest >= dolthub_latest:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Already up to date (local={local_latest}, "
                    f"dolthub={dolthub_latest})."
                )
            )
            return
        else:
            start_date = local_latest + timedelta(days=1)

        logger.info(
            "Fetching IV30 from %s through %s (inclusive)",
            start_date, dolthub_latest,
        )

        # Step 2: Pre-load symbol lookup
        symbol_map = dict(Symbol.objects.values_list("ticker", "id"))
        self.stdout.write(f"Loaded {len(symbol_map)} symbols from DB")

        # Step 3: Fetch day-by-day with alphabet splits
        # Use dict keyed by (symbol_id, date) to deduplicate across splits
        snapshot_map = {}
        skipped_unknown = 0
        skipped_bad = 0

        current_date = start_date
        while current_date <= dolthub_latest:
            date_str = current_date.isoformat()
            next_date_str = (current_date + timedelta(days=1)).isoformat()
            logger.debug("Fetching IV data for %s", date_str)

            day_count = 0
            for split in ALPHABET_SPLITS:
                logger.debug(
                    "  Split %s-%s for %s",
                    split["sym_min"] or "*",
                    split["sym_max"] or "*",
                    date_str,
                )
                rows = _fetch_with_retry(
                    date_from=date_str,
                    date_to=next_date_str,
                    sym_min=split["sym_min"],
                    sym_max=split["sym_max"],
                )

                for row in rows:
                    ticker = row.get("act_symbol", "").strip()
                    iv_raw = row.get("iv_current", "").strip()

                    if not iv_raw:
                        skipped_bad += 1
                        continue

                    symbol_id = symbol_map.get(ticker)
                    if symbol_id is None:
                        skipped_unknown += 1
                        logger.debug("Skipped unknown symbol: %s", ticker)
                        continue

                    try:
                        iv_val = float(iv_raw)
                    except (ValueError, TypeError):
                        skipped_bad += 1
                        logger.debug("Skipped bad IV value: %s for %s", iv_raw, ticker)
                        continue

                    key = (symbol_id, current_date)
                    snapshot_map[key] = IV30Snapshot(
                        symbol_id=symbol_id,
                        date=current_date,
                        iv30=iv_val,
                    )
                    day_count += 1

                if delay > 0:
                    time.sleep(delay)

            logger.debug("  %s: %d rows collected", date_str, day_count)
            current_date += timedelta(days=1)

        # Step 4: Bulk upsert (deduplicated)
        rows_to_upsert = list(snapshot_map.values())
        total_fetched = len(rows_to_upsert)
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
                f"Done. Fetched: {total_fetched}, Upserted: {upserted}, "
                f"Skipped unknown: {skipped_unknown}, "
                f"Skipped bad IV: {skipped_bad}"
            )
        )
