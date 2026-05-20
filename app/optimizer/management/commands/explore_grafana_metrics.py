"""
Management command: explore_grafana_metrics
============================================
Helper utility to discover what Prometheus metrics are actually available
in the Mimir cluster — run this ONCE to find the correct metric names, then
update GRAFANA_METRICS in fetch_grafana_metrics.py with real PromQL expressions.

Usage:
  # List ALL metric names (can be thousands)
  python manage.py explore_grafana_metrics

  # Filter by keyword (recommended — narrow it down)
  python manage.py explore_grafana_metrics --filter mysql
  python manage.py explore_grafana_metrics --filter memory
  python manage.py explore_grafana_metrics --filter connection
  python manage.py explore_grafana_metrics --filter node

  # Test a specific PromQL expression to see if it returns data
  python manage.py explore_grafana_metrics --test "mysql_global_status_threads_connected"
  python manage.py explore_grafana_metrics --test "up{job=~'.*mysql.*'}"
"""

import logging

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand

from optimizer.clients import get_client

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Discover available Prometheus metric names in the Mimir cluster."

    def add_arguments(self, parser):
        parser.add_argument(
            "--filter", default=None, dest="keyword",
            help="Case-insensitive keyword to filter metric names (e.g. 'mysql', 'memory').",
        )
        parser.add_argument(
            "--test", default=None, dest="promql",
            help="Test a specific PromQL expression — shows labels of matching series.",
        )
        parser.add_argument(
            "--jobs", action="store_true",
            help="List all distinct job label values (shows what exporters are active).",
        )

    def handle(self, *_args, **options):
        gf_token = getattr(django_settings, "GRAFANA_TOKEN", "")
        if not gf_token:
            self.stderr.write(self.style.ERROR("GRAFANA_TOKEN not set in .env"))
            return

        grafana = get_client("grafana")

        # ── Option A: list all job label values (what exporters are running) ──
        if options["jobs"]:
            self.stdout.write(self.style.MIGRATE_HEADING("\n── Active Prometheus jobs (exporters) ──"))
            jobs = grafana.list_job_values()
            for job in jobs:
                self.stdout.write(f"  {job}")
            self.stdout.write(f"\nTotal: {len(jobs)} jobs\n")
            return

        # ── Option B: test a specific PromQL expression ───────────────────
        if options["promql"]:
            promql = options["promql"]
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n── Testing PromQL: {promql} ──"))
            results = grafana.test_promql(promql)
            self.stdout.write(f"  Matches : {len(results)} series")
            for r in results[:10]:
                self.stdout.write(f"  Labels  : {r.get('metric', {})}")
                val = r.get("value", [None, None])
                self.stdout.write(f"  Value   : {val[1]}")
                self.stdout.write("")
            if len(results) > 10:
                self.stdout.write(f"  … and {len(results) - 10} more series")
            return

        # ── Option C: list all metric names (with optional keyword filter) ─
        keyword = options["keyword"] or None
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n── Metric names"
            + (f" matching '{keyword}'" if keyword else " (ALL)")
            + " ──"
        ))

        all_names = grafana.list_metric_names()
        filtered = grafana.list_metric_names(keyword) if keyword else all_names

        for name in filtered:
            self.stdout.write(f"  {name}")

        self.stdout.write(
            f"\nShowing {len(filtered)} of {len(all_names)} total metrics.\n"
        )
        if not keyword:
            self.stdout.write(
                "Tip: use --filter <keyword> to narrow results, e.g.:\n"
                "  python manage.py explore_grafana_metrics --filter mysql\n"
                "  python manage.py explore_grafana_metrics --filter memory\n"
                "  python manage.py explore_grafana_metrics --jobs\n"
            )
