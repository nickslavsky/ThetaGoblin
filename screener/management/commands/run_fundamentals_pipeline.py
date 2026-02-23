from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the full fundamentals refresh pipeline: pull_fundamentals then pull_earnings"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting fundamentals pipeline ===")
        call_command("pull_fundamentals", stdout=self.stdout, stderr=self.stderr)
        call_command("pull_earnings", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== Fundamentals pipeline complete ===")
