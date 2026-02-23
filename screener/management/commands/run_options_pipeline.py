from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the options analysis pipeline: pull_options for all qualifying symbols"

    def handle(self, *args, **options):
        self.stdout.write("=== Starting options pipeline ===")
        call_command("pull_options", stdout=self.stdout, stderr=self.stderr)
        self.stdout.write("=== Options pipeline complete ===")
