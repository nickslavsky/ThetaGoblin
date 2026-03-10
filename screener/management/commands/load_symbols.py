import csv
import logging

from django.core.management.base import BaseCommand

from screener.models import Symbol

logger = logging.getLogger(__name__)


def _parse_float(value):
    """Return float from string or None if empty/invalid."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(value):
    """Return int from string or None if empty/invalid."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


class Command(BaseCommand):
    help = "Load symbols from a CSV file into the Symbol table"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to the CSV file")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        created_count = 0
        updated_count = 0
        error_count = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    _, created = Symbol.objects.update_or_create(
                        ticker=row["ticker"].strip(),
                        defaults={
                            "exchange_mic": row.get("exchange_mic", "").strip(),
                            "name": row.get("name", "").strip(),
                            "market_cap": _parse_int(row.get("market_cap")),
                            "operating_margin": _parse_float(row.get("operating_margin")),
                            "free_cash_flow": _parse_float(row.get("free_cash_flow")),
                            "debt_to_equity": _parse_float(row.get("debt_to_equity")),
                            "avg_volume_10d": _parse_float(row.get("avg_volume_10d")),
                        },
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
                except Exception as e:
                    logger.error("Failed to load ticker %s: %s", row.get("ticker"), e)
                    error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count}, Updated: {updated_count}, Errors: {error_count}"
            )
        )
