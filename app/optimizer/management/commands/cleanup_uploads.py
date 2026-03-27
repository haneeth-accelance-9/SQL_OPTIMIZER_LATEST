"""
Management command: delete uploaded files older than OPTIMIZER_UPLOAD_RETENTION_DAYS.
Run via cron or scheduler. See docs/runbooks.md.
"""
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete uploaded Excel files older than retention days (OPTIMIZER_UPLOAD_RETENTION_DAYS)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files that would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        retention_days = getattr(settings, "OPTIMIZER_UPLOAD_RETENTION_DAYS", 7)
        if retention_days <= 0:
            self.stdout.write("Upload retention is disabled (OPTIMIZER_UPLOAD_RETENTION_DAYS <= 0).")
            return
        media_root = getattr(settings, "MEDIA_ROOT", None)
        if not media_root or not os.path.isdir(media_root):
            self.stdout.write("MEDIA_ROOT not set or not a directory.")
            return
        cutoff = timezone.now() - timedelta(days=retention_days)
        cutoff_ts = cutoff.timestamp()
        deleted = 0
        for name in os.listdir(media_root):
            path = os.path.join(media_root, name)
            if not os.path.isfile(path):
                continue
            try:
                if os.path.getmtime(path) < cutoff_ts:
                    if options.get("dry_run"):
                        self.stdout.write(f"Would delete: {path}")
                    else:
                        os.remove(path)
                        deleted += 1
                        logger.info("Deleted old upload: %s", path)
            except Exception as e:
                logger.warning("Failed to delete %s: %s", path, e)
        if options.get("dry_run"):
            self.stdout.write("Dry run complete.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} file(s)."))