from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the IV pipeline: pull IV30 from yfinance, then compute IV rank"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting IV pipeline ===")

        try:
            call_command("pull_iv_yfinance", stdout=self.stdout, stderr=self.stderr)
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f"pull_iv_yfinance failed: {exc}. Skipping compute_iv_rank.")
            )
            return

        call_command("compute_iv_rank", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write("=== IV pipeline complete ===")
