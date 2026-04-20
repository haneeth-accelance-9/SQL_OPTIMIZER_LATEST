"""
Management command: rollup_grafana_metrics
===========================================
Aggregates raw GrafanaMetricSnapshot rows into monthly summaries
(GrafanaMetricMonthlyRollup) and then purges snapshots older than 90 days.

Why this exists:
  GrafanaMetricSnapshot is a high-volume table — daily fetches produce
  24 rows × 8 metrics × N servers.  Keeping 90 days of raw data is enough
  for trend analysis.  Older data is summarised per-month (avg / max / min /
  count) into GrafanaMetricMonthlyRollup and then deleted to keep the DB lean.

How it works (step-by-step):
  1. Find every (server, metric_name, period_month) group in the snapshot table
     where the period_month is BEFORE the current calendar month
     (completed months only — never roll up the in-progress current month).
  2. For each group, compute avg / max / min / sample_count using Django ORM
     aggregation (no raw SQL required).
  3. Upsert into GrafanaMetricMonthlyRollup with update_or_create — safe to
     re-run; already-rolled-up months just get their numbers refreshed.
  4. Delete all GrafanaMetricSnapshot rows whose metric_ts is older than
     GRAFANA_SNAPSHOT_RETENTION_DAYS (default 90) from today.

Cron schedule (set in settings.py CRONJOBS):
  1st of every month at 03:00 — rolls up the previous month, then purges.
  Register: python manage.py crontab add

Usage:
  python manage.py rollup_grafana_metrics
  python manage.py rollup_grafana_metrics --dry-run          # no DB writes
  python manage.py rollup_grafana_metrics --retention-days 60 # custom retention
"""

import logging
from datetime import date, timedelta

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncMonth
from django.utils import timezone

from optimizer.models import GrafanaMetricMonthlyRollup, GrafanaMetricSnapshot

logger = logging.getLogger(__name__)

# Default retention window for raw snapshot rows
DEFAULT_RETENTION_DAYS = 90


class Command(BaseCommand):
    help = (
        "Aggregate GrafanaMetricSnapshot rows into monthly rollups and purge "
        "raw snapshots older than GRAFANA_SNAPSHOT_RETENTION_DAYS (default 90)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Compute rollups but do not write or delete anything.",
        )
        parser.add_argument(
            "--retention-days", type=int, default=None,
            help="Days to keep raw snapshots. Default: GRAFANA_SNAPSHOT_RETENTION_DAYS setting or 90.",
        )

    def handle(self, *_args, **options):
        import time

        dry_run       = options["dry_run"]
        retention     = (
            options["retention_days"]
            or getattr(django_settings, "GRAFANA_SNAPSHOT_RETENTION_DAYS", DEFAULT_RETENTION_DAYS)
        )
        run_start     = time.time()

        # The cutoff is the first day of the current month.
        # We only roll up months that are fully completed (before this month).
        today              = date.today()
        current_month_start = today.replace(day=1)

        # Anything older than this date will be purged after rollup
        purge_before       = today - timedelta(days=retention)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n══════════════════════════════════════════════\n"
            "  Grafana Metrics Rollup + Purge\n"
            "══════════════════════════════════════════════"
        ))
        self.stdout.write(f"  Roll up months before : {current_month_start}")
        self.stdout.write(f"  Purge snapshots before: {purge_before} ({retention} days)")
        if dry_run:
            self.stdout.write(self.style.WARNING("  ⚠ DRY RUN — no DB writes or deletes"))

        # ── Step 1: Aggregate completed months from snapshot table ────────────
        # Use Django ORM's TruncMonth to group metric_ts by calendar month.
        # Filter to only include rows whose month is before the current month
        # so we never partially roll up the still-in-progress current month.
        self.stdout.write("\n  ── Step 1: Computing monthly aggregates …")

        rollup_qs = (
            GrafanaMetricSnapshot.objects
            .filter(metric_ts__lt=timezone.make_aware(
                timezone.datetime(current_month_start.year, current_month_start.month, 1)
            ))
            .annotate(period_month=TruncMonth("metric_ts"))
            .values(
                "tenant_id",    # carry tenant FK through for upsert
                "server_id",    # carry server FK through for upsert
                "metric_name",
                "metric_unit",
                "period_month",
            )
            .annotate(
                avg_value    = Avg("metric_value"),
                max_value    = Max("metric_value"),
                min_value    = Min("metric_value"),
                sample_count = Count("id"),
            )
            .order_by("period_month", "server_id", "metric_name")
        )

        total_rollups   = 0
        total_created   = 0
        total_updated   = 0

        # ── Step 2: Upsert each aggregate into GrafanaMetricMonthlyRollup ─────
        # update_or_create uses unique_together (server, metric_name, period_month)
        # so re-running this command refreshes numbers without creating duplicates.
        self.stdout.write("  ── Step 2: Upserting rollup rows …")

        for row in rollup_qs:
            total_rollups += 1

            # period_month from TruncMonth is a datetime — convert to date
            # so it matches the DateField on GrafanaMetricMonthlyRollup
            period_date = (
                row["period_month"].date()
                if hasattr(row["period_month"], "date")
                else row["period_month"]
            )

            if dry_run:
                logger.debug(
                    "[dry-run] Would upsert rollup: server=%s metric=%s month=%s "
                    "avg=%.4f max=%.4f min=%.4f count=%d",
                    row["server_id"], row["metric_name"], period_date,
                    row["avg_value"] or 0, row["max_value"] or 0,
                    row["min_value"] or 0, row["sample_count"],
                )
                continue

            with transaction.atomic():
                _, created = GrafanaMetricMonthlyRollup.objects.update_or_create(
                    # Lookup key — matches unique_together constraint
                    tenant_id    = row["tenant_id"],
                    server_id    = row["server_id"],
                    metric_name  = row["metric_name"],
                    period_month = period_date,
                    # Fields to write / overwrite
                    defaults={
                        "metric_unit":  row["metric_unit"] or "",
                        "avg_value":    row["avg_value"],
                        "max_value":    row["max_value"],
                        "min_value":    row["min_value"],
                        "sample_count": row["sample_count"],
                    },
                )

            if created:
                total_created += 1
            else:
                total_updated += 1

            # Log progress every 500 rows for long runs
            if total_rollups % 500 == 0:
                self.stdout.write(f"  Processed {total_rollups:,} rollup groups …")

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ Rollup complete: {total_created:,} created, "
            f"{total_updated:,} updated, {total_rollups:,} total groups"
        ))

        # ── Step 3: Purge raw snapshots older than retention window ───────────
        # Only delete rows whose metric_ts is before the purge cutoff date.
        # Rows within the retention window are untouched.
        self.stdout.write(f"\n  ── Step 3: Purging snapshots older than {purge_before} …")

        purge_qs = GrafanaMetricSnapshot.objects.filter(
            metric_ts__date__lt=purge_before
        )

        # Count before deleting so we can report accurately
        purge_count = purge_qs.count()
        self.stdout.write(f"  Rows to purge: {purge_count:,}")

        if purge_count > 0 and not dry_run:
            # Delete in chunks to avoid a single massive transaction locking the table
            chunk_size = 10_000
            deleted_total = 0

            while True:
                # Get a batch of IDs to delete — avoids loading all rows into memory
                ids = list(
                    GrafanaMetricSnapshot.objects
                    .filter(metric_ts__date__lt=purge_before)
                    .values_list("id", flat=True)[:chunk_size]
                )
                if not ids:
                    break

                with transaction.atomic():
                    deleted, _ = GrafanaMetricSnapshot.objects.filter(id__in=ids).delete()
                deleted_total += deleted
                self.stdout.write(f"  Purged {deleted_total:,}/{purge_count:,} rows …")

            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Purge complete: {deleted_total:,} rows deleted"
            ))
        elif dry_run:
            self.stdout.write(f"  [dry-run] Would delete {purge_count:,} rows")
        else:
            self.stdout.write("  Nothing to purge.")

        # ── Step 4: Summary ───────────────────────────────────────────────────
        elapsed = time.time() - run_start
        self.stdout.write(self.style.SUCCESS(
            f"\n══ Rollup + purge complete in {int(elapsed // 60)}m "
            f"{int(elapsed % 60)}s ══\n"
        ))
        logger.info(
            "rollup_grafana_metrics: %d rollup groups, purge_before=%s, "
            "dry_run=%s, elapsed=%.1fs",
            total_rollups, purge_before, dry_run, elapsed,
        )
