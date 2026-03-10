from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the IV pipeline: pull_iv (DoltHub), pull_iv_yfinance, then compute_iv_rank"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting IV pipeline ===")

        # Step 1: DoltHub IV pull
        try:
            call_command("pull_iv", stdout=self.stdout, stderr=self.stderr)
        except SystemExit as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"pull_iv failed (exit {exc.code}). Continuing with yfinance."
                )
            )

        # Step 2: yfinance IV pull
        try:
            call_command("pull_iv_yfinance", stdout=self.stdout, stderr=self.stderr)
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f"pull_iv_yfinance failed: {exc}. Continuing.")
            )

        # Step 3: Compute IV rank (uses iv30 column from DoltHub)
        call_command("compute_iv_rank", stdout=self.stdout, stderr=self.stderr)

        self.stdout.write("=== IV pipeline complete ===")
