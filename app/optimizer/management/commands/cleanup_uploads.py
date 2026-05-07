"""
No-op stub: Excel file upload was removed. This command is retained so
existing cron/scheduler entries do not error; it exits immediately.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "No-op: Excel upload has been removed. This command does nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write("Excel upload has been removed; no files to clean up.")
