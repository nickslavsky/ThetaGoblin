from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the IV pipeline: pull_iv from DoltHub then compute_iv_rank"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting IV pipeline ===")
        try:
            call_command("pull_iv", stdout=self.stdout, stderr=self.stderr)
        except SystemExit as exc:
            self.stderr.write(
                self.style.ERROR(
                    f"pull_iv failed (exit {exc.code}). Skipping compute_iv_rank."
                )
            )
            return
        call_command("compute_iv_rank", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== IV pipeline complete ===")
